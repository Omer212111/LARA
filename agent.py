import re

from jinja2 import Template

from config import MAX_HISTORY_MESSAGES, MAX_REPEATED_CODE
from llm_client import call_llm
from prompts import PLANNER_PROMPT_TEMPLATE, PROMPT_TEMPLATE


class BaseAgent:
    """Shared history management and LLM interaction logic."""

    def __init__(self, task, prompt_template: str, extra_vars: dict = None):
        self.task = task
        self._prompt_template = prompt_template
        self._extra_vars = extra_vars or {}
        self.history: list[dict] = self._build_initial_messages()
        self._initial_len = len(self.history)
        self._recent_codes: list[str] = []

    def _build_initial_messages(self) -> list[dict]:
        dictionary = {
            "supervisor": self.task.supervisor,
            "instruction": self.task.instruction,
            **self._extra_vars,
        }
        prompt = Template(self._prompt_template.lstrip()).render(dictionary)

        messages: list[dict] = []
        last_start = 0
        for match in re.finditer(r"(USER|ASSISTANT|SYSTEM):\n", prompt):
            last_end = match.span()[0]
            if not messages and last_end != 0:
                raise ValueError(f"Prompt starts with no role: {prompt[:last_end]}")
            if messages:
                messages[-1]["content"] = prompt[last_start:last_end].strip()
            role = match.group(1).lower()
            if role not in ("user", "assistant", "system"):
                role = "user"
            messages.append({"role": role, "content": None})
            last_start = match.span()[1]

        messages[-1]["content"] = prompt[last_start:].strip()
        return messages

    def _trim_history(self) -> list[dict]:
        if len(self.history) <= MAX_HISTORY_MESSAGES:
            return self.history
        head = self.history[:self._initial_len]
        tail = self.history[-(MAX_HISTORY_MESSAGES - self._initial_len):]
        return head + tail

    @staticmethod
    def _normalize_code(code: str) -> str:
        """Strip comment-only lines so stuck detection compares logic, not comments."""
        lines = [l for l in code.strip().splitlines() if not l.strip().startswith("#")]
        return "\n".join(lines).strip()

    def _record_code(self, code: str) -> None:
        self._recent_codes.append(self._normalize_code(code))
        if len(self._recent_codes) > MAX_REPEATED_CODE * 2:
            self._recent_codes.pop(0)

    def is_stuck(self) -> bool:
        n = len(self._recent_codes)
        # Period-1: [A, A, A]
        if n >= MAX_REPEATED_CODE and len(set(self._recent_codes[-MAX_REPEATED_CODE:])) == 1:
            return True
        # Period-2: [A, B, A, B]
        if n >= 4:
            if (self._recent_codes[-1] == self._recent_codes[-3] and
                    self._recent_codes[-2] == self._recent_codes[-4]):
                return True
        return False

    def next_code_block(self, last_output: str | None = None) -> str:
        if last_output is not None:
            self.history.append({"role": "user", "content": last_output})
        code = call_llm(self._trim_history())
        self.history.append({"role": "assistant", "content": code})
        self._record_code(code)
        return code


class PlannerAgent(BaseAgent):
    """Phase-1 agent: writes a high-level execution strategy. Accepts optional error feedback for revision rounds."""

    def __init__(self, task, feedback: str = ""):
        super().__init__(task, PLANNER_PROMPT_TEMPLATE, extra_vars={"feedback": feedback})


class ExecutorAgent(BaseAgent):
    """Phase-2 agent: follows a plan to complete the task via the AppWorld REPL."""

    def __init__(self, task, plan: str = ""):
        super().__init__(task, PROMPT_TEMPLATE, extra_vars={"plan": plan})


# Backward-compatible alias — unchanged behaviour when plan is not provided
class MinimalReactAgent(ExecutorAgent):
    def __init__(self, task):
        super().__init__(task, plan="")
