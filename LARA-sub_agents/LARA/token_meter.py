"""Token accounting for LARA runs.

The agent discarded `response.usage` at every call site, so no run before this
module has a measured token count — only reconstructions from prompt sizes and
step counts, which undercount badly (they miss conversation history, tool output
and completions).

This records the provider's own numbers instead. One JSONL line per LLM call:

    {"role": "executor", "model": "...", "prompt_tokens": 19144,
     "completion_tokens": 210, "total_tokens": 19354, "task_id": "...",
     "specialist": "venmo", "t": 1756...}

Usage — wrap the call site:

    from token_meter import record
    response = client.chat.completions.create(...)
    record("executor", response, specialist=spec.app_name)

Set LARA_TOKEN_LOG to choose the output file; defaults to token_usage.jsonl in
the CWD. Recording is best-effort: a provider that omits `usage` (or any error
in here) must never break a run, so every failure path is swallowed.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict

_LOCK = threading.Lock()
_PATH = os.environ.get("LARA_TOKEN_LOG", "token_usage.jsonl")

# Metering is OFF unless LARA_TOKEN_LOG is set. This keeps a normal LARA run
# byte-for-byte unchanged: record() early-returns, no file is written, and the
# in-memory accumulator stays empty. The reviewer/specialist ablations set the
# env var to switch it on. Read once at import — the runner sets it before this
# module loads.
_ENABLED = bool(os.environ.get("LARA_TOKEN_LOG"))

# Set by the benchmark loop / Executor node so each row can be attributed to a
# task and to the Executor attempt it belongs to. current_attempt lets the
# reviewer ablation separate "executor run 2" tokens from "executor run 1".
current_task_id: str | None = None
current_attempt: int | None = None

# In-memory running totals, keyed (task_id, attempt, role) -> summed total_tokens.
# tokens_for() reads this so a caller (base.py) can get "reviewer call tokens" and
# "executor run 2 tokens" for the current task without re-parsing the JSONL.
_totals: dict[tuple, int] = defaultdict(int)


def set_task(task_id: str | None) -> None:
    global current_task_id
    current_task_id = task_id


def set_attempt(attempt: int | None) -> None:
    global current_attempt
    current_attempt = attempt


def record(role: str, response, **extra) -> None:
    """Append one usage row and add it to the in-memory totals. Never raises.

    No-op unless metering is enabled (LARA_TOKEN_LOG set).
    """
    if not _ENABLED:
        return
    try:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        attempt = extra.get("attempt", current_attempt)
        total = getattr(usage, "total_tokens", None) or 0
        row = {
            "role": role,
            "model": getattr(response, "model", None),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "task_id": current_task_id,
            "attempt": attempt,
            "t": round(time.time(), 3),
        }
        row.update(extra)
        with _LOCK:
            _totals[(current_task_id, attempt, role)] += total
            with open(_PATH, "a") as fh:
                fh.write(json.dumps(row) + "\n")
    except Exception:
        pass


def tokens_for(task_id: str | None = None, attempt: int | None = None,
               role: str | None = None) -> int:
    """Sum total_tokens recorded for the current task, filtered by attempt/role.

    attempt/role left as None means "any". Used by base.py to report the reviewer
    call's tokens (role='reviewer') and the second Executor attempt's tokens
    (attempt=2, role='executor') into the reviewer event log.
    """
    task_id = task_id if task_id is not None else current_task_id
    with _LOCK:
        return sum(
            v for (t, a, r), v in _totals.items()
            if t == task_id
            and (attempt is None or a == attempt)
            and (role is None or r == role)
        )


def summarise(path: str | None = None) -> dict:
    """Aggregate a token log: totals, per-role, per-task mean."""
    path = path or _PATH
    rows = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        return {}
    if not rows:
        return {}
    by_role: dict[str, dict[str, int]] = {}
    tasks: set[str] = set()
    for r in rows:
        d = by_role.setdefault(r.get("role", "?"), {"calls": 0, "in": 0, "out": 0})
        d["calls"] += 1
        d["in"] += r.get("prompt_tokens") or 0
        d["out"] += r.get("completion_tokens") or 0
        if r.get("task_id"):
            tasks.add(r["task_id"])
    tot_in = sum(d["in"] for d in by_role.values())
    tot_out = sum(d["out"] for d in by_role.values())
    n = len(tasks) or 1
    return {
        "calls": len(rows),
        "tasks": len(tasks),
        "prompt_tokens": tot_in,
        "completion_tokens": tot_out,
        "total_tokens": tot_in + tot_out,
        "per_task_total": (tot_in + tot_out) / n,
        "by_role": by_role,
    }


if __name__ == "__main__":
    import sys
    s = summarise(sys.argv[1] if len(sys.argv) > 1 else None)
    if not s:
        print("no token log found — set LARA_TOKEN_LOG or pass a path")
        raise SystemExit(1)
    print(f"calls {s['calls']}  tasks {s['tasks']}")
    print(f"prompt     {s['prompt_tokens']:>12,}")
    print(f"completion {s['completion_tokens']:>12,}")
    print(f"TOTAL      {s['total_tokens']:>12,}   ({s['per_task_total']:,.0f}/task)")
    for role, d in sorted(s["by_role"].items()):
        print(f"  {role:10} calls {d['calls']:>4}  in {d['in']:>11,}  out {d['out']:>9,}")
