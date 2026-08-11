"""
Compare two traced runs of the SAME task IDs
============================================
The quality gate for the hardcode removal. Two runs, same slice, same task ids —
this reports the score delta, every task that flipped in either direction, and how
the hardcode surface usage changed underneath.

Why per-task and not just the score: CLAUDE.md records run-to-run variance large
enough that a 10/20 -> 8/20 can be noise. A flip list plus a surface diff lets you
ask the only question that settles it — was the code path we changed even exercised
on the tasks that moved?

    python analysis/compare_traces.py <baseline.jsonl> <candidate.jsonl>
"""

from __future__ import annotations

import json
import sys
from collections import Counter


def load(path: str) -> dict[str, dict]:
    rows = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("task_id"):
                rows[r["task_id"]] = r
    return rows


def surfaces(rows: dict[str, dict]) -> tuple[Counter, Counter]:
    """(tasks touching each surface, total hits per surface)."""
    tasks, hits = Counter(), Counter()
    for r in rows.values():
        for s, n in (r.get("surfaces") or {}).items():
            tasks[s] += 1
            hits[s] += n
    return tasks, hits


def main(base_path: str, cand_path: str) -> str:
    base, cand = load(base_path), load(cand_path)
    shared = sorted(set(base) & set(cand))
    only_base = sorted(set(base) - set(cand))
    only_cand = sorted(set(cand) - set(base))

    out: list[str] = []
    add = out.append

    b_ok = sum(1 for t in shared if base[t].get("correct"))
    c_ok = sum(1 for t in shared if cand[t].get("correct"))
    n = len(shared)

    add("SCORE")
    add(f"  baseline   {b_ok}/{n}")
    add(f"  candidate  {c_ok}/{n}")
    delta = c_ok - b_ok
    add(f"  delta      {delta:+d}" + ("  (no change)" if delta == 0 else ""))
    if only_base or only_cand:
        add(f"  NOTE: task sets differ — only-baseline={only_base} only-candidate={only_cand}")

    gained = [t for t in shared if cand[t].get("correct") and not base[t].get("correct")]
    lost = [t for t in shared if base[t].get("correct") and not cand[t].get("correct")]

    add("")
    add(f"FLIPS  (+{len(gained)} / -{len(lost)})")
    for t in lost:
        add(f"  LOST     {t}  {str(base[t].get('instruction',''))[:76]}")
    for t in gained:
        add(f"  GAINED   {t}  {str(cand[t].get('instruction',''))[:76]}")
    if not gained and not lost:
        add("  none — every task landed the same way")

    # Effort: a fix can hold the score while costing far more steps, which shows up
    # on harder slices later rather than here.
    b_steps = sum(base[t].get("react_steps", 0) for t in shared)
    c_steps = sum(cand[t].get("react_steps", 0) for t in shared)
    b_blocks = sum(base[t].get("code_blocks", 0) for t in shared)
    c_blocks = sum(cand[t].get("code_blocks", 0) for t in shared)
    add("")
    add("EFFORT")
    add(f"  ReAct steps   {b_steps} -> {c_steps} ({c_steps - b_steps:+d})")
    add(f"  code blocks   {b_blocks} -> {c_blocks} ({c_blocks - b_blocks:+d})")

    bt, bh = surfaces({t: base[t] for t in shared})
    ct, ch = surfaces({t: cand[t] for t in shared})
    all_s = sorted(set(bt) | set(ct), key=lambda s: -(ct[s] + bt[s]))

    add("")
    add("HARDCODE SURFACES   (tasks touching / total hits)")
    add(f"  {'surface':<42} {'baseline':>14} {'candidate':>14}")
    add("  " + "-" * 72)
    for s in all_s:
        mark = ""
        if bt[s] and not ct[s]:
            mark = "  ← GONE"
        elif ct[s] and not bt[s]:
            mark = "  ← NEW"
        add(f"  {s:<42} {f'{bt[s]}t/{bh[s]}h':>14} {f'{ct[s]}t/{ch[s]}h':>14}{mark}")

    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    print(main(sys.argv[1], sys.argv[2]))
