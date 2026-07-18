"""
LARA MAS v2.2 — Orchestrator
Builds the LangGraph StateGraph and runs the multi-agent flow.

Agent logic is split across:
  explorer.py        — Explorer node  (GPT-4.1-nano, OpenAI native function calling)
  executor.py        — Executor node  (Qwen via Ollama)
  supervisor.py      — Supervisor node (routing decisions)
  reviewer.py        — Code Reviewer node (GPT-4.1-nano, triggers on wrong answer)
  executor_helpers.py — Bootstrap helpers prepended to every Executor code block
  prompts.py         — All system prompts
  llms.py            — LLM wrappers + .env loading
  config.py          — Runtime constants (limits, model names, URLs)
  state.py           — AgentState TypedDict
"""

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

import logger
from config import MAX_EXECUTOR_RUNS, MAX_ITERATIONS
from explorer import explorer_node
from executor import executor_node
from reviewer import reviewer_node
from state import AgentState
from supervisor import supervisor_node


def _after_executor(state: AgentState) -> str:
    """
    Routing function called after every Executor run.

    Normal path → Supervisor. Exception: if complete_task() was called but the answer
    was WRONG (a wrong value, not a crash), the Reviewer hasn't run yet for this task,
    there is still an Executor attempt left, AND iteration budget remains for the retry
    to actually finish → route to the Reviewer for a structured diagnosis the Executor
    consumes on its next attempt.

    Bounded re-enable (was disabled after the 19/05 benchmark showed 0 improvement). That
    result is explained by MAX_ITERATIONS=3 leaving no room for the corrected attempt and
    gpt-4.1-nano being too weak to act on the diagnosis — both now fixed (limits ↑, model
    → gpt-4.1-mini). The guards below cap the blast radius: Reviewer fires at most once,
    only on a wrong (not crashed) answer, and only when a retry can complete.

    The Reviewer→Executor edge BYPASSES the Supervisor, so the MAX_EXECUTOR_RUNS /
    MAX_ITERATIONS guards MUST live here — otherwise the limits never fire on this path.
    """
    eval_failure   = state.get("last_eval_failure", "")
    had_code_error = bool(state.get("last_error", ""))
    reviewer_ran   = state.get("reviewer_ran", False)
    executor_runs  = state.get("executor_runs", 0)
    iterations     = state.get("iterations", 0)

    wrong_answer = bool(eval_failure) and not had_code_error
    if (wrong_answer and not reviewer_ran
            and executor_runs < MAX_EXECUTOR_RUNS
            and iterations < MAX_ITERATIONS - 1):
        return "Reviewer"
    return "Supervisor"


def process_goal(goal: str, task_id: str = "") -> bool:
    """
    Run the full MAS flow for a single task.
    Returns True if world.evaluate() confirms the task was solved correctly.
    """
    logger.phase("🚀 LARA MAS v2.2 — Starting multi-agent flow")

    workflow = StateGraph(AgentState)
    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("Explorer",   explorer_node)
    workflow.add_node("Executor",   executor_node)
    workflow.add_node("Reviewer",   reviewer_node)

    workflow.add_edge("Explorer",  "Supervisor")
    workflow.add_edge("Reviewer",  "Executor")    # Reviewer → Executor (retry with diagnosis)

    workflow.add_conditional_edges(
        "Executor",
        _after_executor,
        {"Supervisor": "Supervisor", "Reviewer": "Reviewer"},
    )
    workflow.add_conditional_edges(
        "Supervisor",
        lambda s: s["next_agent"],
        {"Explorer": "Explorer", "Executor": "Executor", "FINISH": END},
    )

    workflow.set_entry_point("Supervisor")
    app = workflow.compile()

    initial_state: AgentState = {
        "messages":             [HumanMessage(content=goal)],
        "plan":                 "",
        "findings":             {},
        "iterations":           0,
        "explorer_runs":        0,
        "executor_runs":        0,
        "last_error":           "",
        "reviewer_diagnosis":   "",
        "task_signal_complete": False,
        "final_answer":         "",
        "next_agent":           "",
        "last_code":            "",
        "last_eval_failure":    "",
        "reviewer_ran":         False,
        "active_app":           "",
    }

    try:
        # recursion_limit must be > MAX_ITERATIONS to avoid LangGraph cutting us off
        # before our own limits fire. Raised from ×2 to ×4 on 2026-05-24: with the
        # Reviewer disabled, each wrong-answer attempt costs 2 graph iterations
        # (Executor → Supervisor → Executor), so ×2 was tight and recursion_limit
        # was firing before our MAX_EXECUTOR_RUNS check.
        final_state = app.invoke(initial_state,
                                 config={"recursion_limit": MAX_ITERATIONS * 4, "executor": "synchronous"})
        answer  = final_state.get("final_answer", "")
        success = bool(final_state.get("task_signal_complete"))

        summary = (
            f"final_answer={answer!r}  |  "
            f"task_signal_complete={final_state.get('task_signal_complete')}  |  "
            f"executor_runs={final_state.get('executor_runs')}"
        )
        if success:
            logger.success(f"Flow finished — task complete. {summary}")
        else:
            logger.warning(f"Flow finished — task NOT signalled complete. {summary}")

        return success
    except Exception as e:
        logger.error(f"Flow crashed: {e}")
        return False
