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


# Reading the ledger back out of the sandbox.  This is a SEPARATE execute rather
# than a print appended to the model's own block, because the block we most want
# a ledger view after is the one that RAISED — an appended print would never run.
_LEDGER_PROBE = "print(ledger_summary())"


def _read_ledger(max_chars: int = 900) -> str:
    """Current ledger contents, or "" when empty/unavailable.

    Surfaced in every observation on multi-app tasks so the model sees the table
    it is building instead of having to remember that the accessors exist.  The
    first ledger run measured 3/130 code blocks (2.3%) using them and ZERO uses of
    remember_entity/all_entities: availability alone did not change behaviour,
    because the surrounding loop still fed printed stdout back as the observation
    and re-reading that print stayed the cheapest path.
    """
    try:
        out = execute_python_code.invoke({"code": BOOTSTRAP_CODE + "\n" + _LEDGER_PROBE})
    except Exception:
        return ""
    if not out or "Traceback" in out or out.startswith(("Execution failed", "Execution Failed")):
        return ""
    out = out.strip()
    # "LEDGER: 0 entities, 0 artifacts, tokens for none" — nothing worth showing yet.
    if not out.startswith("LEDGER:") or "0 entities, 0 artifacts" in out:
        return ""
    return out[:max_chars]


_LEDGER_WRITE_RE = re.compile(r"\b(remember_entity|remember)\s*\(")
# Reads that CONSUME stored facts — the half that decides whether the ledger is
# actually load-bearing.  ledger_summary() is deliberately excluded: it only
# prints a view, so counting it would let "print the ledger" masquerade as use.
_LEDGER_READ_RE = re.compile(r"\b(recall_entity|recall|all_entities)\s*\(")


_OUT_RE = re.compile(r"^\s*OUT:\s*(.+)$", re.MULTILINE)
_IN_RE  = re.compile(r"^\s*IN:\s*(.+)$",  re.MULTILINE)


def _parse_declared_schema(plan: str) -> tuple[list[str], list[str]]:
    """(record_sets, fields) the plan's OUT: lines declare.

    Two OUT forms, per prompts_explorer.py:
        OUT: debts[] {name, email, amount}   → record set + its initial fields
        OUT: debts[].venmo_id                → one field added to each record

    Returned as display strings, not a structure: this is fed back to the model
    as the schema it said it would build, so it stays close to what it wrote.
    Parsing is best-effort — a plan with no OUT: lines yields ([], []), which
    keeps single-app and legacy plans on exactly the old code path.
    """
    sets: list[str] = []
    fields: list[str] = []
    for raw in _OUT_RE.findall(plan or ""):
        raw = raw.strip()
        # Pull out the brace form FIRST — "debts[] {name, email}" contains commas
        # that must not be treated as separators between OUT entries.
        def _take_set(m: "re.Match") -> str:
            cols = [c.strip() for c in m.group(2).split(",") if c.strip()]
            sets.append(f"{m.group(1)}[] {{{', '.join(cols)}}}")
            fields.extend(cols)
            return ""                                # consume it
        rest = re.sub(r"(\w+)\[\]\s*\{([^}]*)\}", _take_set, raw)
        for part in rest.split(","):
            part = part.strip().rstrip(".")
            if not part:
                continue
            m = re.match(r"^(\w+)\[\]\.(\w+)$", part)
            if m:                                    # debts[].venmo_id
                fields.append(m.group(2))
                continue
            m = re.match(r"^(\w+)\[\]$", part)       # debts[]
            if m:
                sets.append(f"{m.group(1)}[]")
                continue
            if re.match(r"^\w+$", part):             # receipt_path — a scalar
                fields.append(part)
    # de-duplicate, preserve order
    return list(dict.fromkeys(sets)), list(dict.fromkeys(fields))


def _count_ledger_use(code: str) -> tuple[int, int]:
    """(writes, reads) the model's own code performs against the ledger.

    Counts calls only in the model's block, never in BOOTSTRAP_CODE (which
    *defines* these names, and whose docstrings contain worked examples like
    `remember_entity('Andrew', amount=42.50)` — 5 of them).  Bootstrap is
    prepended to `full_code`, not to `code`, so the call site already passes the
    model's block alone; stripping it here as well keeps the metric honest if
    that ever changes, since a silent +5 per step would manufacture adoption.

    Writes and reads are counted separately because they answer different
    questions: writes say the model records facts, reads say it actually acts on
    them.  A task with writes but no reads is hoarding — the ledger is costing
    prompt space without being load-bearing.
    """
    if BOOTSTRAP_CODE and BOOTSTRAP_CODE in code:
        code = code.replace(BOOTSTRAP_CODE, "")
    writes = reads = 0
    in_docstring = False
    for line in code.splitlines():
        stripped = line.strip()
        # Toggle on lines that open/close a docstring (odd number of triple quotes).
        if (stripped.count('"""') + stripped.count("'''")) % 2 == 1:
            in_docstring = not in_docstring
            continue
        if in_docstring or stripped.startswith("#") or stripped.startswith("def "):
            continue
        writes += len(_LEDGER_WRITE_RE.findall(line))
        reads  += len(_LEDGER_READ_RE.findall(line))
    return writes, reads


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
        # Grader ground truth + what we actually submitted last time.  Both are
        # already in state (set below on a wrong answer) but until now only the
        # Reviewer read them; the Executor saw only the Reviewer's paraphrase.
        prev_eval_failure  = state.get("last_eval_failure", "")
        prev_answer        = state.get("final_answer", "")

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
        app_labels: set[str] = set()
        if step_specialist_map:
            app_labels = {s.app_name for s in step_specialist_map.values() if s.app_name}
            logger.info(f"Per-step dispatch map: {dict((k, v.app_name or 'generic') for k, v in step_specialist_map.items())}")
            logger.info(f"Specialist(s) active: {app_labels or {'generic'}}")

        # A task is a cross-app JOIN when the PLAN touches more than one app — that
        # is exactly when the ledger earns its prompt cost, so gate visibility on it.
        #
        # Counted from the plan's [app] tags directly, NOT from step_specialist_map:
        # that map drops any step whose app has no registered specialist, so a
        # simple_note→splitwise task (a real join, and simple_note has no specialist)
        # would collapse to one label and read as single-app.  Measured on the first
        # probe run: plan tagged [simple_note] ×3 + [splitwise] ×3, map showed only
        # {'splitwise'}, and ledger visibility never fired.
        plan_apps = set(re.findall(r"^\s*\d+[.)]\s*\[([a-z_]+)\]", plan or "", re.MULTILINE))
        is_multi_app_plan = len(plan_apps) > 1

        # The plan's own OUT: declarations, parsed once. These name the ledger
        # schema the Explorer committed to, so the model is told what to record
        # rather than left to invent keys. Measured motivation: on a 6-app task
        # with 12 ledger writes the model stored only raw lists via remember()
        # and never once used remember_entity — it kept its INPUTS and dropped
        # the record of what it had already DONE, which is what the grader checks.
        declared_sets, declared_fields = _parse_declared_schema(plan)
        if declared_sets or declared_fields:
            logger.info(
                f"Plan declares schema: sets={declared_sets or '—'} "
                f"fields={declared_fields or '—'}"
            )
        if is_multi_app_plan:
            logger.info(f"Multi-app plan ({sorted(plan_apps)}) — ledger visibility ON")

        # Premature-complete_task guard: count numbered plan steps. If the model
        # calls complete_task while more than 3 plan steps remain (i.e. we are at
        # ReAct step r and total_plan_steps - r > 3), the orchestrator strips the
        # call before execution and tells the model to continue.  0 = guard off.
        total_plan_steps = _count_plan_steps(plan)
        _PREMATURE_TOLERANCE = 3

        # Base conversation — system message is replaced per-step
        # Grader assertions and the prior answer are retry-only context: on
        # attempt 1 there is nothing graded yet, and a value left over in state
        # would read as "you already tried this" when we have not.
        _is_retry = bool(reviewer_diagnosis)
        base_user_msg = build_react_initial_message(
            task, plan,
            _summarize_findings(findings),
            last_error         if last_error         else "None",
            reviewer_diagnosis if reviewer_diagnosis else "None",
            eval_failure    = prev_eval_failure if _is_retry else "",
            previous_answer = prev_answer       if _is_retry else "",
        )
        if _is_retry:
            logger.info(
                f"Retry context: failed_asserts={len(prev_eval_failure.splitlines())} line(s), "
                f"previous_answer={prev_answer[:60]!r}"
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
        # Ledger adoption counters (multi-app steps only — the ledger is silent
        # elsewhere, so single-app steps would dilute the rate toward zero).
        ledger_writes_total      = 0
        ledger_reads_total       = 0
        ledger_steps_total       = 0
        ledger_steps_with_writes = 0
        ledger_steps_with_reads  = 0
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

            # ── Ledger visibility (multi-app tasks only) ──────────────────────
            # Show the model the cross-app table it is building, every step.  The
            # ledger is only worth its prompt cost when a task actually spans apps;
            # on single-app plans it stays silent.
            # Adoption instrumentation.  The ledger's whole open question is whether
            # the model writes to it; nothing in the log answered that, because the
            # logger records CODE and OUTPUT but never the user turn we build here.
            # So count writes in the code the model just wrote, and record which
            # ledger prompt it was shown when it did (or did not) write.
            _writes, _reads = _count_ledger_use(code)
            if is_multi_app_plan:
                ledger_writes_total += _writes
                ledger_reads_total  += _reads
                ledger_steps_total  += 1
                if _writes:
                    ledger_steps_with_writes += 1
                if _reads:
                    ledger_steps_with_reads += 1
                logger.info(
                    f"Ledger adoption: step {step} wrote {_writes} / read {_reads} "
                    f"[w:{ledger_steps_with_writes} r:{ledger_steps_with_reads} "
                    f"of {ledger_steps_total} steps]"
                )

            # The schema the plan committed to, restated every step. Without this
            # the model picks its own keys — measured: all writes went to
            # remember() as raw lists, none to remember_entity, so nothing
            # recorded which items had already been acted on.
            schema_block = ""
            if is_multi_app_plan and (declared_sets or declared_fields):
                schema_block = "\nSCHEMA YOUR PLAN DECLARED (record these as you go):\n"
                if declared_sets:
                    schema_block += "".join(f"  {s}\n" for s in declared_sets)
                if declared_fields:
                    schema_block += f"  fields: {', '.join(declared_fields)}\n"
                schema_block += (
                    "  Use remember_entity('<name>', <field>=<value>) — one row per person/thing —\n"
                    "  NOT remember() with a whole list. After an action succeeds, record it on the\n"
                    "  SAME row (e.g. paid=True, txn_id=...) so a later step can skip what is done.\n"
                )

            ledger_block = ""
            if is_multi_app_plan:
                ledger_view = _read_ledger()
                if ledger_view:
                    ledger_block = (
                        f"\nYOUR LEDGER (persists across steps and attempts):\n{ledger_view}\n"
                        "Read from it with recall_entity(name) / all_entities() instead of "
                        "re-deriving facts from earlier output.\n"
                    )
                else:
                    ledger_block = (
                        "\nYOUR LEDGER IS EMPTY. This task spans several apps, so you are "
                        "building a join: the same people/things appear in more than one app. "
                        "Record each fact as you learn it —\n"
                        "  remember_entity('<name>', <field>=<value>)   e.g. amount=, venmo_id=, email=\n"
                        "then iterate all_entities() when you act, instead of re-reading earlier output.\n"
                    )
                # Which prompt the model actually got. The user turn is never
                # logged, so without this the two branches are indistinguishable
                # after the fact — and that ambiguity already produced one wrong
                # diagnosis ("the teaching branch never runs").
                logger.info(
                    f"Ledger prompt shown: {'TABLE' if ledger_view else 'EMPTY/teaching'}"
                )

            conversation.append({
                "role": "user",
                "content": (
                    f"Observation:\n{output}\n\n"
                    f"{progress_line}"
                    f"{guard_message}"
                    f"{schema_block}"
                    f"{ledger_block}"
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

        # Prefer a quoted literal (the answer verbatim).  Fall back to the raw
        # argument expression so computed submissions — complete_task(answer=total),
        # the common VALUE-task shape — still yield something the retry can be told
        # not to repeat, instead of an empty string.
        answer = ""
        for code_step in all_code_steps:
            m = re.search(r"complete_task\(\s*answer\s*=\s*['\"](.+?)['\"]", code_step)
            if m:
                answer = m.group(1).strip()
                break
        if not answer:
            for code_step in all_code_steps:
                m = re.search(r"complete_task\(\s*answer\s*=\s*", code_step)
                if not m:
                    continue
                # Scan to the matching close-paren so nested calls survive intact
                # (round(x, 2) must not truncate to "round(x, 2").
                depth, start = 1, m.end()
                for i in range(start, len(code_step)):
                    ch = code_step[i]
                    depth += (ch == "(") - (ch == ")")
                    if depth == 0:
                        expr = code_step[start:i].strip()
                        if expr and expr != "None":
                            answer = f"<computed: {expr}>"
                        break
                if answer:
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

        # One grep-able adoption line per multi-app task. This is the number the
        # whole passive-vs-voluntary decision rests on, so it is emitted even when
        # it is zero — a silent absence is what made the last read ambiguous.
        if ledger_steps_total:
            _wrate = ledger_steps_with_writes / ledger_steps_total
            _rrate = ledger_steps_with_reads / ledger_steps_total
            # The verdict this metric exists to produce:
            #   HOARDING  — records facts, never acts on them (ledger not load-bearing)
            #   READ_ONLY — reads without writing (stale/empty reads; likely a no-op)
            #   JOINING   — both, i.e. the ledger is doing the job it was built for
            #   UNUSED    — neither
            if ledger_writes_total and ledger_reads_total:
                _verdict = "JOINING"
            elif ledger_writes_total:
                _verdict = "HOARDING"
            elif ledger_reads_total:
                _verdict = "READ_ONLY"
            else:
                _verdict = "UNUSED"
            logger.info(
                f"LEDGER_ADOPTION apps={len(plan_apps)}({'+'.join(sorted(plan_apps))}) "
                f"attempt={attempt_num} steps={ledger_steps_total} "
                f"writes={ledger_writes_total} reads={ledger_reads_total} "
                f"w_steps={ledger_steps_with_writes} r_steps={ledger_steps_with_reads} "
                f"w_rate={_wrate:.2f} r_rate={_rrate:.2f} verdict={_verdict}"
            )

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
