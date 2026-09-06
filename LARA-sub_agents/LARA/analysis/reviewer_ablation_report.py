"""Summarise the Reviewer-ablation event logs.

    python analysis/reviewer_ablation_report.py reviewer_events_reviewer.jsonl \
                                                reviewer_events_blindretry.jsonl

Per log (one arm each) it reports:
  - retries fired, of which Reviewer-driven vs blind
  - executor_runs distribution (sanity: retries should show 2)
  - the within-arm 2x2  (attempt-1 correct/wrong  x  final correct/wrong)
  - RESCUES: attempt-1 wrong -> final correct  (the number the study is about)
  - REGRESSIONS: attempt-1 correct -> final wrong
  - how often the resubmitted answer actually DIFFERED from attempt 1
  - reviewer vs executor-run-2 token totals

This reads only the retry-event rows, so arm A (no retries, empty/absent log) is
correctly reported as zero fires. Final TGC across ALL tasks still comes from the
AppWorld report.md files, not from here.
"""
import json
import sys
from collections import Counter


def load(path: str) -> list[dict]:
    rows = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows


def summarise(path: str) -> None:
    rows = load(path)
    print(f"\n=== {path} ===")
    if not rows:
        print("  no retry events (arm A / no wrong-answer retries fired)")
        return

    fired = sum(1 for r in rows if r.get("reviewer_fired"))
    blind = len(rows) - fired
    runs = Counter(r.get("executor_runs") for r in rows)

    # 2x2 on the rows that actually completed attempt 1 (a no_submit attempt 1 has
    # no correctness cell). completed=None is treated as not-completed.
    cells = Counter()
    rescues = regressions = 0
    for r in rows:
        a1 = bool(r.get("attempt1_correct"))
        fin = bool(r.get("final_correct"))
        cells[(a1, fin)] += 1
        if not a1 and fin:
            rescues += 1
        if a1 and not fin:
            regressions += 1
    differed = sum(1 for r in rows if r.get("submission_differed"))

    rev_tok = sum(r.get("reviewer_tokens") or 0 for r in rows)
    ex2_tok = sum(r.get("executor_run2_tokens") or 0 for r in rows)

    print(f"  retries: {len(rows)}   reviewer-driven: {fired}   blind: {blind}")
    print(f"  executor_runs: {dict(runs)}")
    print(f"  2x2 (attempt1 -> final):")
    print(f"     wrong -> correct (RESCUE)     {cells[(False, True)]}")
    print(f"     wrong -> wrong                {cells[(False, False)]}")
    print(f"     correct -> correct            {cells[(True, True)]}")
    print(f"     correct -> wrong (REGRESSION) {cells[(True, False)]}")
    print(f"  net: rescues={rescues}  regressions={regressions}  "
          f"resubmission differed: {differed}/{len(rows)}")
    print(f"  tokens: reviewer={rev_tok:,}  executor_run2={ex2_tok:,}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for p in sys.argv[1:]:
        summarise(p)
