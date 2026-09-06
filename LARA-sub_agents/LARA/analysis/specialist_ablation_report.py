"""Paired analysis for the specialist-dispatch ablation.

    python analysis/specialist_ablation_report.py spec_dispatch_ext spec_monolith_ext [spec_generic_ext]

Reports, per arm: TGC, SGC, per-difficulty TGC, and mean API calls / ReAct steps.
Between arms: McNemar's exact test on the paired per-task outcomes.

Why McNemar and not a chi-square or a two-proportion z-test: the arms run the SAME
tasks, so the outcomes are paired, not independent. McNemar conditions on the
discordant pairs (tasks one arm solved and the other did not), which is the only
place the arms actually differ. Using an unpaired test here would throw away the
pairing and overstate the variance.

The exact binomial version is used because the discordant count is small at n=45;
the chi-square approximation is unreliable below ~25 discordant pairs.
"""
import json
import os
import re
import sys
from collections import defaultdict
from math import comb

ROOT = "/home/omer2/LARA_ablation/experiments/outputs"


def load_arm(experiment: str) -> dict[str, bool]:
    """task_id -> success.

    Reads the per-task evaluation/report.md files rather than an
    `appworld evaluate` summary: evaluate insists on scoring the whole `train`
    split and aborts on the first task outside the slice, so it cannot be used
    on a 45-task subset. report.md holds the same official pass/fail counts —
    a task counts as solved only when every one of its tests passed.
    """
    base = os.path.join(ROOT, experiment, "tasks")
    if not os.path.isdir(base):
        sys.exit(f"no run output for {experiment} at {base}")
    res: dict[str, bool] = {}
    for tid in os.listdir(base):
        rp = os.path.join(base, tid, "evaluation", "report.md")
        if not os.path.exists(rp):
            res[tid] = False          # never reached complete_task()
            continue
        text = open(rp).read()
        passed = re.search(r"Num Passed Tests\s*:\s*(\d+)", text)
        total = re.search(r"Num Total\s+Tests\s*:\s*(\d+)", text)
        res[tid] = bool(passed and total
                        and int(total.group(1)) > 0
                        and int(passed.group(1)) == int(total.group(1)))
    return res


def difficulty_of(task_id: str) -> str:
    return task_id.rsplit("_", 1)[-1]


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value. b, c are the discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def summarise(name: str, res: dict[str, bool]) -> None:
    n = len(res)
    tgc = 100 * sum(res.values()) / n if n else 0
    by_diff = defaultdict(list)
    for t, ok in res.items():
        by_diff[difficulty_of(t)].append(ok)
    # SGC: a scenario counts only if every one of its variants passed
    scen = defaultdict(list)
    for t, ok in res.items():
        scen[t.rsplit("_", 1)[0]].append(ok)
    sgc = 100 * sum(all(v) for v in scen.values()) / len(scen) if scen else 0
    print(f"\n{name}  (n={n})")
    print(f"  TGC {tgc:5.1f}   SGC {sgc:5.1f}  ({len(scen)} scenarios)")
    for d in sorted(by_diff):
        v = by_diff[d]
        print(f"  difficulty {d}: {100*sum(v)/len(v):5.1f}  (n={len(v)})")


def compare(name_a: str, a: dict[str, bool], name_b: str, b: dict[str, bool]) -> None:
    shared = sorted(set(a) & set(b))
    if not shared:
        print(f"\n!! {name_a} and {name_b} share no task ids — cannot pair")
        return
    only_a = sum(1 for t in shared if a[t] and not b[t])
    only_b = sum(1 for t in shared if b[t] and not a[t])
    both = sum(1 for t in shared if a[t] and b[t])
    neither = sum(1 for t in shared if not a[t] and not b[t])
    p = mcnemar_exact(only_a, only_b)
    print(f"\n{name_a}  vs  {name_b}   (paired on {len(shared)} tasks)")
    print(f"  both solved      {both}")
    print(f"  neither solved   {neither}")
    print(f"  only {name_a:<14} {only_a}")
    print(f"  only {name_b:<14} {only_b}")
    print(f"  McNemar exact p = {p:.4f}" + ("  *significant at .05" if p < 0.05 else ""))
    if only_a + only_b < 10:
        print("  NOTE: fewer than 10 discordant pairs — underpowered, treat as directional only.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    arms = sys.argv[1:]
    loaded = {a: load_arm(a) for a in arms}
    for name, res in loaded.items():
        summarise(name, res)
    names = list(loaded)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            compare(names[i], loaded[names[i]], names[j], loaded[names[j]])
