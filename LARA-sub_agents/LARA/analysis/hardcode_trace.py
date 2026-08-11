"""
Hardcode-usage tracer
=====================
Records, per task, WHICH hardcoded surface actually fired at runtime — so the
AppWorld-compliance inventory can be ranked by measured load rather than by
guesswork about what the agent "probably" leans on.

Why runtime and not just grep: a static list says a surface EXISTS. It cannot say
whether the agent reached it, how often, or whether the tasks that used it are the
ones that passed. Those three are what decide how risky each removal is.

Design constraints
------------------
* **Zero behaviour change.** Every public function swallows its own exceptions and
  returns None. A tracer bug must never flip a task's result, or the run is void
  as a measurement.
* **Off by default.** Enabled only when the env var LARA_HARDCODE_TRACE names an
  output path. Unset → every hook is a no-op returning immediately, so the agent
  code carrying the hooks is still the code that ran the leaderboard.
* **Append-only JSONL,** one object per task, flushed at task end. A crashed run
  still leaves every completed task on disk.

Usage
-----
    LARA_HARDCODE_TRACE=hardcode_broad20.jsonl python analysis/run_slice.py broad-20
    python analysis/hardcode_trace.py hardcode_broad20.jsonl        # report
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter

# ── Enablement ────────────────────────────────────────────────────────────────

_PATH: str = os.environ.get("LARA_HARDCODE_TRACE", "").strip()
ENABLED: bool = bool(_PATH)

# Current task's record. None between tasks, so a stray hook outside a task
# window is dropped rather than mis-attributed to the previous task.
_cur: dict | None = None


# ── What counts as a traced surface ───────────────────────────────────────────
# Bootstrap helpers, split by WHY each is a compliance question.
#
#   api_call  — the helper body itself calls an AppWorld API. This is the category
#               the rule names explicitly ("hardcode any API calls into their
#               agent's logic"). login_to_app is the rule's literal example.
#   convention— no app-specific API call, but a hardcoded AppWorld protocol detail
#               discovered offline (pagination parameter names, page_limit cap).
#   generic   — pure data manipulation over lists/dicts. Nothing AppWorld-specific;
#               the same code would work against any JSON API.
#   ledger    — cross-step memory. Framework state, no API knowledge.
#   model_owned — the model defines this itself, in its own code, from a prompt
#               instruction. Not our hardcode at all; tracked because whether the
#               model actually writes it is the whole question behind removing the
#               helper it replaced.
_HELPER_KIND = {
    # Removed from BOOTSTRAP_CODE — kept here so a regression shows up as a hit
    # instead of vanishing silently.
    "login_to_app":    "api_call",     # apis.supervisor.show_account_passwords + <app>.login
    "find_contact":    "api_call",     # apis.phone.search_contacts / show_contacts
    # Its replacement: model-authored, defined in the model's own first code block.
    "login":           "model_owned",
    "call_api":        "convention",   # injects access_token= for you
    "fetch_all_pages": "convention",   # page_index/page_limit=20 pagination protocol
    "filter_results":  "generic",
    "get_field":       "generic",
    "sort_by":         "generic",
    "remember":        "ledger",
    "recall":          "ledger",
    "remember_entity": "ledger",
    "recall_entity":   "ledger",
    "all_entities":    "ledger",
    "ledger_summary":  "ledger",
}

# Did the model actually write the login helper the prompt asks it to define? If this
# never fires but `login(` calls do, every one of those calls is a NameError.
_LOGIN_DEF_RE = re.compile(r"^\s*def\s+login\s*\(", re.M)

# Call sites in the MODEL's code. Word-boundary + open paren so a mention inside a
# string or comment is far less likely to count. Longest names first is irrelevant
# here because each pattern is anchored on its own \b.
_HELPER_RE = {
    name: re.compile(r"\b" + name + r"\s*\(") for name in _HELPER_KIND
}

# Direct `apis.<app>.<api>(` calls the model writes itself, bypassing the helpers.
# This is the counterfactual: the share of API traffic the model already routes
# without help tells us how much the helpers are actually load-bearing.
_DIRECT_API_RE = re.compile(r"\bapis\.([a-z_]+)\.([a-z_]+)\s*\(")


def _blank(task_id: str, instruction: str) -> dict:
    return {
        "task_id": task_id,
        "instruction": instruction[:300],
        # surface -> hit count
        "surfaces": Counter(),
        # extra detail per surface (which regex matched, which apps detected, ...)
        "detail": {},
        "code_blocks": 0,
        "react_steps": 0,
        "helper_calls": Counter(),      # helper name -> call count in model code
        "helper_blocks": Counter(),     # helper name -> #blocks containing it
        "direct_api_calls": Counter(),  # "app.api" -> count (helper-free calls)
        "specialist_steps": Counter(),  # app name (or "generic") -> steps injected
        "signalled_success": None,
        "correct": None,
    }


# ── Task window ───────────────────────────────────────────────────────────────

def start_task(task_id: str, instruction: str = "") -> None:
    """Open a fresh record. Any un-ended previous record is written first so a
    crashed task is still measured rather than silently merged into the next."""
    global _cur
    if not ENABLED:
        return
    try:
        if _cur is not None:
            end_task()
        _cur = _blank(task_id, instruction or "")
    except Exception:
        _cur = None


def end_task(correct: bool | None = None, signalled: bool | None = None) -> None:
    """Write the current record as one JSONL line and close the window."""
    global _cur
    if not ENABLED or _cur is None:
        return
    try:
        rec = _cur
        _cur = None
        if correct is not None:
            rec["correct"] = bool(correct)
        if signalled is not None:
            rec["signalled_success"] = bool(signalled)
        # Counters are not JSON types — flatten to plain dicts.
        out = {
            k: (dict(v) if isinstance(v, Counter) else v)
            for k, v in rec.items()
        }
        with open(_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    except Exception:
        _cur = None


# ── Hooks ─────────────────────────────────────────────────────────────────────

def note(surface: str, detail=None, n: int = 1) -> None:
    """Record that `surface` fired. `detail` is kept for the first hit only —
    later hits would overwrite it with the same kind of value and the count
    already carries the frequency."""
    if not ENABLED or _cur is None:
        return
    try:
        _cur["surfaces"][surface] += n
        if detail is not None and surface not in _cur["detail"]:
            _cur["detail"][surface] = detail
    except Exception:
        pass


def note_specialist(app_name: str) -> None:
    """One ReAct step was handed a specialist prompt (or the generic fallback)."""
    if not ENABLED or _cur is None:
        return
    try:
        _cur["react_steps"] += 1
        key = app_name or "generic"
        _cur["specialist_steps"][key] += 1
        _cur["surfaces"][f"specialist_prompt:{key}"] += 1
    except Exception:
        pass


def note_code_block(code: str) -> None:
    """Scan one block of MODEL-written code for hardcoded-surface usage.

    Counts helper calls and direct apis.* calls separately: the first says the
    model used our injected scaffolding, the second says it went around it. Both
    numbers are needed — "helper X is called 40 times" only means X is
    load-bearing if the model is not also doing the same thing by hand.
    """
    if not ENABLED or _cur is None or not code:
        return
    try:
        _cur["code_blocks"] += 1
        if _LOGIN_DEF_RE.search(code):
            _cur["surfaces"]["model_defined_login"] += 1
        # Count CALLS, not definitions: the model's own `def login(app):` would
        # otherwise register as a use of login and overstate adoption by one per task.
        callable_code = "\n".join(
            ln for ln in code.splitlines() if not ln.lstrip().startswith("def ")
        )
        for name, rx in _HELPER_RE.items():
            hits = len(rx.findall(callable_code))
            if hits:
                _cur["helper_calls"][name] += hits
                _cur["helper_blocks"][name] += 1
                _cur["surfaces"][f"bootstrap_helper:{name}"] += hits
        for app, api in _DIRECT_API_RE.findall(code):
            _cur["direct_api_calls"][f"{app}.{api}"] += 1
    except Exception:
        pass


# ── Report ────────────────────────────────────────────────────────────────────

def _load(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def report(path: str) -> str:
    """Per-surface usage across a traced run, ranked by how many tasks touched it."""
    rows = _load(path)
    if not rows:
        return f"No trace records in {path}"

    n = len(rows)
    n_correct = sum(1 for r in rows if r.get("correct"))

    # surface -> (tasks touching it, tasks touching it that PASSED, total hits)
    tasks_with: Counter = Counter()
    passed_with: Counter = Counter()
    hits_total: Counter = Counter()
    for r in rows:
        passed = bool(r.get("correct"))
        for surface, hits in (r.get("surfaces") or {}).items():
            tasks_with[surface] += 1
            hits_total[surface] += hits
            if passed:
                passed_with[surface] += 1

    lines = [
        f"HARDCODE USAGE — {path}",
        f"{n} tasks traced, {n_correct} correct ({100.0 * n_correct / n:.0f}%)",
        "",
        f"{'surface':<44} {'tasks':>6} {'%':>5} {'hits':>6} {'passed':>7}",
        "-" * 72,
    ]
    for surface, t in tasks_with.most_common():
        kind = ""
        if surface.startswith("bootstrap_helper:"):
            kind = _HELPER_KIND.get(surface.split(":", 1)[1], "")
        label = f"{surface}" + (f" [{kind}]" if kind else "")
        lines.append(
            f"{label:<44} {t:>6} {100.0 * t / n:>4.0f}% {hits_total[surface]:>6} "
            f"{passed_with[surface]:>7}"
        )

    # Helper-free API traffic — the counterfactual for the helper layer.
    direct: Counter = Counter()
    tasks_direct = 0
    for r in rows:
        d = r.get("direct_api_calls") or {}
        if d:
            tasks_direct += 1
        for k, v in d.items():
            direct[k] += v
    lines += [
        "",
        f"DIRECT apis.* CALLS (model bypassing the helpers): "
        f"{sum(direct.values())} calls in {tasks_direct}/{n} tasks",
    ]
    for k, v in direct.most_common(20):
        lines.append(f"  {k:<50} {v:>4}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else _PATH
    if not target:
        print("usage: python analysis/hardcode_trace.py <trace.jsonl>")
        raise SystemExit(2)
    print(report(target))
