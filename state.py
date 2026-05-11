"""
LARA MAS — Shared agent state
AgentState is the single object passed between Explorer, Supervisor, and Executor.
"""

import operator
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict, total=False):
    """Shared memory for LARA's agents. `total=False` makes all keys optional."""
    messages:             Annotated[Sequence[BaseMessage], operator.add]
    plan:                 str    # Explorer's latest plan text
    findings:             dict   # {attempt_N: result_snippet} across Executor runs
    iterations:           int    # total state-graph steps taken
    explorer_runs:        int
    executor_runs:        int
    last_error:           str    # last Executor code crash output (empty when code ran cleanly)
    task_signal_complete: bool   # True only if world.evaluate() passes
    final_answer:         str    # extracted FINAL_ANSWER from Executor output
    next_agent:           str    # Supervisor's routing decision
    # Reviewer fields (populated by Executor/Reviewer, consumed by executor_node)
    last_code:            str    # last code block the Executor ran
    last_eval_failure:    str    # failed test requirements from evaluate_task()
    reviewer_ran:         bool   # True after Reviewer has processed this wrong attempt
    reviewer_diagnosis:   str    # structured diagnosis from Reviewer (separate from last_error)
