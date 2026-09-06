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

_LOCK = threading.Lock()
_PATH = os.environ.get("LARA_TOKEN_LOG", "token_usage.jsonl")

# Set by the benchmark loop so each row can be attributed to a task.
current_task_id: str | None = None


def set_task(task_id: str | None) -> None:
    global current_task_id
    current_task_id = task_id


def record(role: str, response, **extra) -> None:
    """Append one usage row. Never raises."""
    try:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        row = {
            "role": role,
            "model": getattr(response, "model", None),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "task_id": current_task_id,
            "t": round(time.time(), 3),
        }
        row.update(extra)
        with _LOCK, open(_PATH, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:
        pass


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
