"""
LARA MAS — Supervisor agent

Makes routing decisions after each Explorer or Executor run.
Most decisions are deterministic (hard-coded rules).
The LLM is only consulted in ambiguous mid-run states.
"""

import logger
from config import MAX_EXECUTOR_RUNS, MAX_ITERATIONS
from llms import get_llm
from state import AgentState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decide_next_from_text(text: str) -> str:
    """Parse the Supervisor LLM's free-text reply into a node name."""
    text = text.strip().upper()
    last_idx = {
        "FINISH":   text.rfind("FINISH"),
        "EXECUTOR": text.rfind("EXECUTOR"),
        "EXPLORER": text.rfind("EXPLORER"),
    }
    found = {k: v for k, v in last_idx.items() if v != -1}
    if not found:
        return "Explorer"
    winner = max(found, key=lambda k: found[k])
    return {"FINISH": "FINISH", "EXECUTOR": "Executor", "EXPLORER": "Explorer"}[winner]


# ── LangGraph node ────────────────────────────────────────────────────────────

def supervisor_node(state: AgentState) -> dict:
    logger.phase("🧭 Supervisor — routing decision")

    iterations    = state.get("iterations", 0)
    executor_runs = state.get("executor_runs", 0)
    explorer_runs = state.get("explorer_runs", 0)
    plan_val      = state.get("plan", "")
    has_plan      = bool(plan_val) and "Explorer crashed" not in plan_val
    task_done     = state.get("task_signal_complete", False)
    last_error    = state.get("last_error", "")
    final_answer  = state.get("final_answer", "")

    logger.info(
        f"State: iter={iterations}  exec_runs={executor_runs}  "
        f"explore_runs={explorer_runs}  has_plan={has_plan}  "
        f"task_done={task_done}  answer={final_answer[:50]!r}"
    )

    def _route(decision: str, reason: str) -> dict:
        logger.info(f"→ {decision} ({reason})")
        return {"next_agent": decision}

    # ── Hard limits ───────────────────────────────────────────────────────────
    if iterations >= MAX_ITERATIONS:
        return _route("FINISH", "hit MAX_ITERATIONS")
    if executor_runs >= MAX_EXECUTOR_RUNS:
        return _route("FINISH", "hit MAX_EXECUTOR_RUNS")
    if task_done:
        return _route("FINISH", "task verified correct by world.evaluate()")

    # ── Deterministic rules ───────────────────────────────────────────────────
    if not has_plan:
        if explorer_runs >= 2:
            return _route("Executor", "no good plan after 2 explorer tries — trying executor directly")
        return _route("Explorer", "no plan yet")

    if has_plan and executor_runs == 0:
        return _route("Executor", "plan ready, first execution")

    if last_error and executor_runs >= 3 and explorer_runs < 2:
        return _route("Explorer", "executor keeps failing — re-planning")

    # ── LLM-based routing (ambiguous mid-run state) ───────────────────────────
    llm = get_llm()
    recent  = state["messages"][-2:]
    history = "\n".join([f"{m.type}: {m.content[:600]}" for m in recent])

    prompt = f"""You are LARA's Supervisor. Decide the next step.

RECENT HISTORY:
{history}

STATE:
  - iterations so far: {iterations}
  - executor runs: {executor_runs}
  - has plan: {has_plan}
  - last error: {last_error[:300] if last_error else "none"}

Reply with exactly ONE of these words as the final line: EXPLORER, EXECUTOR, or FINISH.
  EXPLORER  -> the plan is wrong or missing, discover again
  EXECUTOR  -> the plan looks right, try executing (or fix the last error)
  FINISH    -> we have the correct answer already
"""
    raw = llm.invoke(prompt)

    # Guard: if LLM returned an error string, default to Executor (don't waste an Explorer run)
    if raw.startswith("Error:"):
        logger.error(f"Supervisor LLM failed: {raw[:120]} — defaulting to Executor")
        return _route("Executor", "Supervisor LLM error — retrying executor")

    decision = _decide_next_from_text(raw)
    logger.info(f"→ {decision} (LLM decision, raw: {raw.strip()[:120]!r})")
    return {"next_agent": decision}
