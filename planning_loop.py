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
    Normal path: go to Supervisor.
    Exception: if complete_task() was called but the answer was WRONG,
               the Reviewer hasn't run yet this attempt,
               AND there is still an executor run left for the retry → send to Reviewer.

    The MAX_EXECUTOR_RUNS check here is critical: the Reviewer→Executor edge bypasses
    the Supervisor, so without this check the limit would never fire on wrong-answer paths.
    """
    eval_failure  = state.get("last_eval_failure", "")
    reviewer_ran  = state.get("reviewer_ran", False)
    had_code_error = bool(state.get("last_error", ""))
    executor_runs = state.get("executor_runs", 0)

    wrong_answer = bool(eval_failure) and not had_code_error
    if wrong_answer and not reviewer_ran and executor_runs < MAX_EXECUTOR_RUNS:
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
    }

    try:
        # recursion_limit must be > MAX_ITERATIONS to avoid LangGraph cutting us off
        # before our own limits fire. Set to 2× MAX_ITERATIONS as a safe ceiling.
        final_state = app.invoke(initial_state, config={"recursion_limit": MAX_ITERATIONS * 2})
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
