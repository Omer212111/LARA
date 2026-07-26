"""
LARA MAS — App-Agent base classes

BaseAppExecutor
    Abstract base that holds an app_name and app_system_prompt.
    Subclasses (SpotifyExecutor, GmailExecutor, etc.) only override those two attributes.

AppOrchestrator(BaseAppExecutor)
    The actual LangGraph node.  Runs the full ReAct loop but swaps in the right
    specialist's system prompt at each step based on which app the plan step involves.
    Falls back to the generic REACT_EXECUTOR_SYSTEM when no specialist matches.
"""

import os
import re
import time

import requests
from langchain_core.messages import AIMessage

import logger
from config import (
    EXECUTOR_BACKEND,
    EXECUTOR_MODEL_OLLAMA,
    EXECUTOR_MODEL_OPENAI,
    MAX_REACT_STEPS,
    OLLAMA_AUTH_PASS,
    OLLAMA_AUTH_USER,
    OLLAMA_CHAT_URL,
    OLLAMA_TIMEOUT,
)
from executor_helpers import BOOTSTRAP_CODE
from prompts_executor import REACT_EXECUTOR_SYSTEM, build_react_initial_message
from state import AgentState
from tools import evaluate_task, execute_python_code


# ── Shared helpers ────────────────────────────────────────────────────────────

def _extract_code_block(text: str) -> str:
    m = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


# Premature complete_task guard — counts numbered top-level plan steps using the
# same regex as _build_step_specialist_map.  Returns 0 if no steps could be parsed,
# which disables the guard.
_PLAN_STEP_RE = re.compile(r"^\s*(\d+)[.)]\s+", re.MULTILINE)
_COMPLETE_TASK_LINE_RE = re.compile(
    r"^[^\n]*\bcomplete_task\s*\([^\n]*\)[^\n]*\n?", re.MULTILINE
)


def _count_plan_steps(plan: str) -> int:
    """Count numbered top-level steps in the Explorer plan."""
    return len(_PLAN_STEP_RE.findall(plan or ""))


def _strip_complete_task(code: str) -> tuple[str, bool]:
    """Remove any `complete_task(...)` call lines from code.
    Returns (cleaned_code, was_stripped)."""
    cleaned, n = _COMPLETE_TASK_LINE_RE.subn("", code)
    return cleaned, n > 0


def _summarize_findings(findings: dict, max_chars: int = 1500) -> str:
    if not findings:
        return "None yet."
    parts = [f"[{key}]: {str(value)[:400]}" for key, value in findings.items()]
    return "\n".join(parts)[:max_chars]


def _llm_call(messages: list[dict]) -> str:
    """Call the configured LLM backend. Returns assistant text."""
    if EXECUTOR_BACKEND == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        response = client.chat.completions.create(
            model=EXECUTOR_MODEL_OPENAI,
            messages=messages,
            temperature=0.1,
            max_tokens=1500,
        )
        return response.choices[0].message.content or ""

    elif EXECUTOR_BACKEND == "ollama":
        payload = {
            "model": EXECUTOR_MODEL_OLLAMA,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1500},
        }
        last_err = None
        for attempt in range(2):
            try:
                resp = requests.post(
                    OLLAMA_CHAT_URL,
                    json=payload,
                    auth=(OLLAMA_AUTH_USER, OLLAMA_AUTH_PASS),
                    verify=False,
                    timeout=OLLAMA_TIMEOUT,
                )
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "")
            except Exception as e:
                last_err = e
                if attempt == 0:
                    logger.warning(f"Ollama chat failed (attempt 1), retrying in 10s... ({e})")
                    time.sleep(10)
        raise RuntimeError(f"Ollama chat error after 2 attempts: {last_err}")

    else:
        raise ValueError(f"Unknown EXECUTOR_BACKEND: {EXECUTOR_BACKEND!r}")


# ── Base specialist ───────────────────────────────────────────────────────────

class BaseAppExecutor:
    """
    Lightweight base for app specialists.  Subclasses set:
      app_name          — lowercase app key, e.g. "spotify"
      app_system_prompt — extra prompt block appended after REACT_EXECUTOR_SYSTEM
    """
    app_name: str = ""
    app_system_prompt: str = ""

    def build_system_prompt(self) -> str:
        """Combine the shared ReAct base with this specialist's extra knowledge."""
        if self.app_system_prompt:
            return (
                REACT_EXECUTOR_SYSTEM
                + f"\n\n=== {self.app_name.upper()} SPECIALIST ==="
                + f"\n{self.app_system_prompt}"
            )
        return REACT_EXECUTOR_SYSTEM


# ── Orchestrator ──────────────────────────────────────────────────────────────

class AppOrchestrator(BaseAppExecutor):
    """
    The single LangGraph node that replaces executor_node.

    Per-step dispatch
    -----------------
    At each ReAct step the orchestrator:
      1. Looks up which plan step is running.
      2. Finds the app name mentioned in that step's text.
      3. Swaps the system message to the matching specialist's prompt.
      4. Falls back to the generic REACT_EXECUTOR_SYSTEM when no specialist matches.

    This gives every code step the tightest possible specialist context without
    splitting the conversation across multiple LangGraph nodes.
    """

    def __init__(self, specialists: dict["str", BaseAppExecutor] | None = None):
        self.specialists: dict[str, BaseAppExecutor] = specialists or {}

    # ── Plan parsing ──────────────────────────────────────────────────────────

    def _build_step_specialist_map(self, plan: str) -> dict[int, BaseAppExecutor]:
        """
        Parse numbered plan steps and map each to a specialist.

        Primary signal: the Explorer's ``[app]`` tag that every plan line now
        starts with (see prompts_explorer.py) — e.g.

          "2. [gmail] fetch the thread ..."  →  GmailExecutor

        This tag is ground truth: it is what the planner *declared* the step's app
        to be, not a guess from scanning free text.  For any line missing a tag (or
        tagged with an unknown app) we fall back to the legacy text scan so behaviour
        never regresses on an untagged plan.
        """
        step_map: dict[int, BaseAppExecutor] = {}
        for line in plan.splitlines():
            m = re.match(r"^\s*(\d+)[.)]\s+(.+)", line)
            if not m:
                continue
            step_num = int(m.group(1))
            step_text = m.group(2)

            # Primary: leading [app] tag.
            tag = re.match(r"\s*\[([a-z_]+)\]", step_text)
            if tag and tag.group(1) in self.specialists:
                step_map[step_num] = self.specialists[tag.group(1)]
                continue

            # Fallback: legacy free-text scan.
            lowered = step_text.lower()
            for app_name, specialist in self.specialists.items():
                if app_name in lowered or app_name.replace("_", " ") in lowered:
                    step_map[step_num] = specialist
                    break
        return step_map

    def _specialist_for_step(
        self,
        declared_step: int | None,
        step_map: dict[int, BaseAppExecutor],
        last_specialist: BaseAppExecutor | None,
    ) -> BaseAppExecutor:
        """
        Choose the specialist for the code block about to run.

        Routing is driven by the step the model *declares* it is working on
        (``STEP: K`` — see prompts_executor.py), NOT by the ReAct iteration
        counter.  Those two quantities diverge the moment a plan step needs more
        than one ReAct iteration, which is exactly the multi-app misrouting bug this
        replaces.  Precedence:

          1. declared_step is in the plan map  → that step's specialist (authoritative)
          2. declared_step absent/unmapped     → reuse last_specialist (sticky, safe:
             consecutive blocks of one app keep its specialist until the model says
             otherwise)
          3. nothing declared yet (first block) → single-app fallback, else generic
        """
        if declared_step is not None and declared_step in step_map:
            return step_map[declared_step]

        # Sticky: no fresh declaration → stay on the app we were last routed to.
        if last_specialist is not None:
            return last_specialist

        # First block, no declaration yet: if the whole plan is one app, use it.
        unique_specialists = list({id(s): s for s in step_map.values()}.values())
        if len(unique_specialists) == 1:
            return unique_specialists[0]

        return self  # multi-app or no-map → generic

    @staticmethod
    def _parse_declared_step(text: str) -> int | None:
        """Extract the plan step the model declared it is working on.

        Recognises a ``STEP: <n>`` line (case-insensitive, tolerant of markdown
        bold/space) anywhere in the assistant message.  Returns None when absent so
        the caller falls back to sticky routing.
        """
        m = re.search(r"(?im)^\s*\**\s*STEP\s*:?\s*(\d+)", text)
        return int(m.group(1)) if m else None

    # ── LangGraph node ────────────────────────────────────────────────────────

    def node(self, state: AgentState) -> dict:
        attempt_num = state.get("executor_runs", 0) + 1
        backend_label = (
            f"{EXECUTOR_BACKEND}:"
            f"{EXECUTOR_MODEL_OLLAMA if EXECUTOR_BACKEND == 'ollama' else EXECUTOR_MODEL_OPENAI}"
        )
        logger.phase(f"⚙️  Executor/Orchestrator (attempt {attempt_num}, {backend_label})")

        task               = state["messages"][0].content
        plan               = state.get("plan", "[no plan available]")
        findings           = state.get("findings", {})
        last_error         = state.get("last_error", "")
        reviewer_diagnosis = state.get("reviewer_diagnosis", "")

        # Action tasks (place order, buy, rate, send...) must submit answer=None.
        _task_body = task.split("Task:", 1)[-1].strip().lower()
        is_action_task = (
            "action task" in plan.lower()
            or bool(re.match(r"(place an order|buy me|order all|order the)", _task_body))
        )
        if is_action_task:
            final_answer_hint = (
                "• Done? This is an ACTION task → `apis.supervisor.complete_task(answer=None)` "
                "and STOP. NEVER pass an order id, count, or message string."
            )
        else:
            final_answer_hint = (
                "• Have the final answer? → `apis.supervisor.complete_task(answer='<value>')` and STOP."
            )

        # Build step→specialist map from the Explorer's plan
        step_specialist_map = self._build_step_specialist_map(plan)
        if step_specialist_map:
            app_labels = {s.app_name for s in step_specialist_map.values() if s.app_name}
            logger.info(f"Per-step dispatch map: {dict((k, v.app_name or 'generic') for k, v in step_specialist_map.items())}")
            logger.info(f"Specialist(s) active: {app_labels or {'generic'}}")

        # Premature-complete_task guard: count numbered plan steps. If the model
        # calls complete_task while more than 3 plan steps remain (i.e. we are at
        # ReAct step r and total_plan_steps - r > 3), the orchestrator strips the
        # call before execution and tells the model to continue.  0 = guard off.
        total_plan_steps = _count_plan_steps(plan)
        _PREMATURE_TOLERANCE = 3

        # Base conversation — system message is replaced per-step
        base_user_msg = build_react_initial_message(
            task, plan,
            _summarize_findings(findings),
            last_error         if last_error         else "None",
            reviewer_diagnosis if reviewer_diagnosis else "None",
        )
        # We store conversation WITHOUT a system message; it's injected fresh each step.
        conversation: list[dict] = [{"role": "user", "content": base_user_msg}]

        if reviewer_diagnosis:
            is_env_error = "ENVIRONMENT_ERROR" in reviewer_diagnosis or "SIGALRM" in reviewer_diagnosis
            if is_env_error:
                injection = (
                    f"⚠️  CRITICAL: Your previous attempt was KILLED by a sandbox timeout (SIGALRM).\n"
                    f"Reviewer diagnosis:\n{reviewer_diagnosis}\n\n"
                    "YOU MUST FOLLOW THESE RULES FOR THIS ATTEMPT:\n"
                    "1. Do NOT put all logic in one code block — use one ReAct step per operation.\n"
                    "2. Step 1: login + fetch the top-level list + print its length. Nothing else.\n"
                    "3. Step 2: print ONE item from the list to see its fields/keys.\n"
                    "4. Step 3+: if the items already have the field you need, iterate in memory.\n"
                    "5. If you MUST fetch per-item, process at most 15 items per step.\n"
                    "6. Keep each code block under 10 lines.\n"
                    "7. The FIX_INSTRUCTION below tells you exactly what to change — follow it.\n"
                )
            else:
                injection = (
                    f"Your previous attempt was WRONG (submitted an incorrect answer).\n"
                    f"Reviewer diagnosis:\n{reviewer_diagnosis}\n\n"
                    "Read the ROOT_CAUSE and FIX_INSTRUCTION carefully.\n"
                    "The FIX_INSTRUCTION OVERRIDES any conflicting step in the Explorer plan.\n"
                    "Do NOT repeat the same algorithmic approach — implement the fix exactly as described."
                )
            conversation.append({"role": "user", "content": injection})
            print(
                f"\n[Self-Correction] Injecting reviewer diagnosis "
                f"(attempt {attempt_num}, env_error={is_env_error})",
                flush=True,
            )
            print(f"[Self-Correction] Diagnosis preview: {reviewer_diagnosis[:300]}", flush=True)

        all_code_steps: list[str] = []
        all_outputs:    list[str] = []
        eval_info = {
            "correct": False, "completed": False,
            "pass_count": 0, "total_count": 0,
            "pass_percentage": 0.0, "failures": [],
        }
        last_output_had_error = False
        active_app = ""
        # Attempt-scoped submission tracking.  AppWorld's task status is STICKY:
        # once any attempt calls complete_task(), env.task_completed() stays True
        # for the rest of the task.  Evaluating on that flag judges a retry on the
        # PREVIOUS attempt's answer.  complete_task() is a plain overwrite
        # (supervisor/apis.py), so a retry may legitimately re-submit — we just
        # have to wait until it actually does.
        submitted_this_attempt = False
        # On a reviewer-driven retry the model deliberately reproduces the whole
        # corrected solution in one block, so "ReAct step 1 of ~10 plan steps"
        # measures the wrong quantity and the premature-submit guard misfires.
        is_reviewer_retry = bool(reviewer_diagnosis)
        _SIGALRM_TOKENS = ("SIGALRM", "Alarm clock", "signal.alarm", "timed out", "Killed", "TimeoutExpired")

        # ── Per-step dispatch cursor (Option D + C) ───────────────────────────
        # We route on the plan step the model DECLARES (STEP: K), not the ReAct
        # iteration counter.  `last_specialist` makes routing sticky: until the
        # model declares a new step, code blocks stay on the current app's
        # specialist.  Seed it from the plan so block 1 is correct before any
        # declaration exists.  On a reviewer retry the model collapses the whole
        # plan into one block, so per-step routing does not apply — we fall back to
        # the single-app / generic dispatch (last_specialist stays None).
        last_specialist: BaseAppExecutor | None = None
        if not is_reviewer_retry:
            last_specialist = self._specialist_for_step(None, step_specialist_map, None)

        for step in range(1, MAX_REACT_STEPS + 1):
            # ── Select specialist for this ReAct block ────────────────────────
            # Route on the sticky cursor (updated from the previous block's
            # declaration).  On retries, last_specialist is None → single-app/generic.
            if is_reviewer_retry:
                specialist = self._specialist_for_step(None, step_specialist_map, None)
            else:
                specialist = last_specialist
            system_prompt = specialist.build_system_prompt()
            if specialist.app_name:
                active_app = specialist.app_name
                print(f"[Orchestrator] Step {step}: dispatching to {specialist.__class__.__name__}", flush=True)
            else:
                print(f"[Orchestrator] Step {step}: generic executor", flush=True)

            # Inject system message fresh each step (specialist may change)
            messages = [{"role": "system", "content": system_prompt}, *conversation]

            try:
                assistant_text = _llm_call(messages)
            except Exception as e:
                logger.error(f"LLM call failed on step {step}: {e}")
                print(f"[Orchestrator] LLM call FAILED step {step}: {e}", flush=True)
                break

            conversation.append({"role": "assistant", "content": assistant_text})

            # Update the dispatch cursor from the step the model just declared, so
            # the NEXT block routes to the app it announced.  Absent declaration →
            # cursor unchanged (sticky).  Skipped on retries (single-block path).
            if not is_reviewer_retry:
                declared = self._parse_declared_step(assistant_text)
                if declared is not None:
                    routed = self._specialist_for_step(
                        declared, step_specialist_map, last_specialist
                    )
                    if routed is not last_specialist:
                        print(
                            f"[Orchestrator] Cursor → declared STEP {declared} "
                            f"({routed.app_name or 'generic'})",
                            flush=True,
                        )
                    last_specialist = routed

            code = _extract_code_block(assistant_text)
            if not code:
                logger.info(f"[ReAct step {step}] No code block — attempting recovery")
                print(f"[Orchestrator] No code block at step {step} — attempting recovery", flush=True)
                recovery_prompt = (
                    "⚠️ You responded without a Python code block. You MUST write one.\n"
                    f"If you have the final answer: {final_answer_hint}\n"
                    "If you need more information, write the next step as a code block.\n"
                    "Respond with a code block and nothing else."
                )
                messages_recovery = [{"role": "system", "content": system_prompt}, *conversation,
                                     {"role": "user", "content": recovery_prompt}]
                try:
                    recovery_text = _llm_call(messages_recovery)
                    code = _extract_code_block(recovery_text)
                    if code:
                        conversation.append({"role": "user", "content": recovery_prompt})
                        conversation.append({"role": "assistant", "content": recovery_text})
                        logger.info(f"[ReAct step {step}] Recovery succeeded — executing recovered code block")
                        print(f"[Orchestrator] Recovery succeeded at step {step}", flush=True)
                    else:
                        logger.info(f"[ReAct step {step}] Recovery failed — stopping")
                        print(f"[Orchestrator] Recovery failed at step {step} — stopping", flush=True)
                        break
                except Exception as e:
                    logger.error(f"Recovery LLM call failed: {e}")
                    break

            # ── Premature complete_task guard ─────────────────────────────────
            # If the plan is parseable and many steps remain, strip any complete_task
            # call before execution so the answer isn't locked at the sandbox.
            # Disabled on reviewer-driven retries (see is_reviewer_retry above).
            stripped_complete_task = False
            if (not is_reviewer_retry
                    and total_plan_steps > 0
                    and (total_plan_steps - step) > _PREMATURE_TOLERANCE):
                if "complete_task(" in code:
                    code, stripped_complete_task = _strip_complete_task(code)
                    if stripped_complete_task:
                        steps_remaining = total_plan_steps - step
                        print(
                            f"[Orchestrator] ⚠️  Stripped premature complete_task at step "
                            f"{step} (≈{steps_remaining} plan steps remain)",
                            flush=True,
                        )

            # Checked AFTER stripping: a stripped call never reaches the sandbox,
            # so it must not count as this attempt's submission.  Confirmed below
            # only if the block actually ran (a SIGALRM kill submits nothing).
            code_had_complete_task = "complete_task(" in code

            logger.code_block(code, label=f"ReAct step {step} / attempt {attempt_num}")
            all_code_steps.append(code)

            full_code = BOOTSTRAP_CODE + "\n" + code
            output = execute_python_code.invoke({"code": full_code})
            logger.output_block(output, label=f"ReAct step {step} / attempt {attempt_num}")
            all_outputs.append(output)

            last_output_had_error = (
                output.startswith("Execution failed")
                or output.startswith("Execution Failed")
                or "Traceback" in output
            )

            # ── Mid-loop SIGALRM detection ─────────────────────────────────────
            hit_sigalrm = any(tok in output for tok in _SIGALRM_TOKENS)
            if hit_sigalrm:
                print(f"[Orchestrator] ⚠️  SIGALRM at step {step} — injecting recovery hint", flush=True)
                conversation.append({
                    "role": "user",
                    "content": (
                        f"Observation:\n{output}\n\n"
                        "⚠️  YOUR CODE WAS KILLED BY SANDBOX TIMEOUT (SIGALRM).\n"
                        "The code block was too heavy. You MUST simplify:\n"
                        "- If you were looping over items and calling an API per item, STOP.\n"
                        "- Check if the list items already contain the field you need.\n"
                        "- If you must fetch details, do at most 10-15 items per step.\n"
                        "- Write a SMALLER code block (under 8 lines) for the next step.\n"
                        "Continue with a simpler approach."
                    ),
                })
                continue

            # The block ran to completion (no SIGALRM) and raised nothing, so any
            # complete_task() in it reached the sandbox — this attempt now owns the
            # submitted answer.  The error check matters: the model sometimes writes
            # a bare `complete_task(...)` instead of `apis.supervisor.complete_task(...)`,
            # which raises NameError and submits nothing.  Trusting the substring
            # alone would mark the attempt submitted and let evaluate_task() read a
            # PREVIOUS attempt's sticky verdict — the very bug this tracking fixes.
            if code_had_complete_task and not last_output_had_error:
                submitted_this_attempt = True

            # Plan-progress line (only when we can count steps).
            if total_plan_steps > 0:
                steps_remaining = max(total_plan_steps - step, 0)
                progress_line = (
                    f"Plan progress: ReAct step {step} of ~{total_plan_steps} plan steps "
                    f"(≈{steps_remaining} remaining).\n"
                )
            else:
                progress_line = ""

            # Strong follow-up if we just stripped a premature complete_task.
            if stripped_complete_task:
                steps_remaining = max(total_plan_steps - step, 0)
                guard_message = (
                    "\n⚠️  You called complete_task too early. The plan has ~"
                    f"{total_plan_steps} steps and you are on step {step} — about "
                    f"{steps_remaining} remain. The call was STRIPPED (not executed).\n"
                    "Continue executing the remaining plan steps before calling "
                    "complete_task. Do NOT submit intermediate setup outputs as the "
                    "final answer.\n"
                )
            else:
                guard_message = ""

            conversation.append({
                "role": "user",
                "content": (
                    f"Observation:\n{output}\n\n"
                    f"{progress_line}"
                    f"{guard_message}"
                    "Respond with a Python ```python ... ``` code block:\n"
                    f"{final_answer_hint}\n"
                    "• Need more data? → write the next step.\n"
                    "You MUST write a code block — do not write prose only."
                ),
            })

            # Attempt-scoped: only evaluate once THIS attempt has submitted.
            # Otherwise env.task_completed() reports a previous attempt's verdict
            # and we would break the loop before this attempt can submit at all.
            if not submitted_this_attempt:
                continue

            eval_info = evaluate_task()
            if eval_info["completed"]:
                if eval_info["correct"]:
                    logger.success(
                        f"Task CORRECT at step {step} — "
                        f"{eval_info['pass_count']}/{eval_info['total_count']} tests passed "
                        f"({eval_info['pass_percentage']:.0f}%)"
                    )
                    print(f"[Orchestrator] ✅ CORRECT at step {step}", flush=True)
                else:
                    logger.error(
                        f"complete_task() called but WRONG — "
                        f"{eval_info['pass_count']}/{eval_info['total_count']} tests passed "
                        f"({eval_info['pass_percentage']:.0f}%). Failed: {eval_info['failures']}"
                    )
                    print(f"[Orchestrator] ❌ WRONG at step {step}: {eval_info['failures'][:2]}", flush=True)
                break

        # This attempt submitted but the loop ended before any evaluation ran
        # (e.g. step budget exhausted, or the submit block hit SIGALRM handling).
        # Score it now rather than reporting a submitted answer as never-completed.
        if submitted_this_attempt and not eval_info["completed"]:
            eval_info = evaluate_task()
            logger.info(
                f"Post-loop evaluation (attempt {attempt_num}): "
                f"completed={eval_info['completed']}, correct={eval_info['correct']}"
            )

        # ── Build return state ─────────────────────────────────────────────────
        combined_output = "\n".join(all_outputs)
        last_code       = "\n---\n".join(all_code_steps)

        eval_failure_str = ""
        if eval_info["completed"] and not eval_info["correct"]:
            eval_failure_str = "\n".join(eval_info.get("failures", []))

        answer = ""
        for code_step in all_code_steps:
            m = re.search(r"complete_task\(\s*answer\s*=\s*['\"](.+?)['\"]", code_step)
            if m:
                answer = m.group(1).strip()
                break

        new_findings = dict(findings)
        new_findings[f"attempt_{attempt_num}"] = combined_output[:1500]

        report = (
            f"EXECUTOR_REPORT (attempt {attempt_num}, {len(all_code_steps)} ReAct steps):\n"
            f"--- Last step code ---\n"
            f"{all_code_steps[-1][:600] if all_code_steps else 'none'}\n"
            f"--- Combined output ---\n{combined_output[:1200]}"
        )

        had_error = last_output_had_error and not eval_info["completed"]

        print(
            f"[Orchestrator] Done — attempt {attempt_num}, {len(all_code_steps)} steps, "
            f"completed={eval_info['completed']}, correct={eval_info['correct']}, "
            f"had_error={had_error}",
            flush=True,
        )

        return {
            "messages":             [AIMessage(content=report)],
            "findings":             new_findings,
            "last_error":           combined_output if had_error else "",
            "reviewer_diagnosis":   "",
            "task_signal_complete": eval_info["correct"],
            "final_answer":         answer,
            "executor_runs":        attempt_num,
            "iterations":           state.get("iterations", 0) + 1,
            "last_code":            last_code,
            "last_eval_failure":    eval_failure_str,
            "reviewer_ran":         False,
            "active_app":           active_app,
        }
