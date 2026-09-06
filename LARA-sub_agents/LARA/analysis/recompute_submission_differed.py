"""Recompute submission_differed for the six completed reviewer-ablation runs.

The shipped metric compared a regex pull from the model's own code, which is
wrong two ways:
  * ACTION tasks submit answer=None -> extractor yields "" for BOTH attempts
  * computed answers render as the same expression text (`str(total_cost)`)
    for both attempts even when the VALUE changed

Neither case can be fixed from the event log alone (it stored only the broken
value), so this reads AppWorld's own per-task transcript instead:
    experiments/outputs/<exp>/tasks/<tid>/logs/environment_io.md
which records every code block actually executed and its output, for BOTH
attempts, in order.

Each retry is classified into one of:
    VALUE/differed     - both answers are literals and they differ
    VALUE/same         - both answers are literals and they match
    VALUE/inferred-*   - answer is a computed expression; compared via the
                         submitting block's printed output (INFERRED, not exact)
    ACTION             - answer is None/absent both times: no answer exists to
                         differ. Reported separately, never as "same".
    unresolvable       - fewer than 2 executed complete_task calls found
"""
import json
import os
import re
import sys
from collections import Counter

ARMS = ["reviewer", "blindretry"]
REPS = [1, 2]
LABEL = {"reviewer": "B reviewer", "blindretry": "C blind-retry"}

INTERACTION_RE = re.compile(r"### Environment Interaction \d+")
BLOCK_RE = re.compile(r"```python\n(.*?)\n```\s*\n```\n(.*?)\n```", re.S)
CT_RE = re.compile(r"complete_task\s*\(([^)]*)\)", re.S)


def parse_interactions(path: str) -> list[tuple[str, str]]:
    """[(code, output)] for every executed environment interaction."""
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        return []
    out = []
    for chunk in INTERACTION_RE.split(text):
        m = BLOCK_RE.search(chunk)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def answer_arg(code: str) -> str | None:
    """The text of the answer= argument of the executed complete_task call."""
    m = CT_RE.search(code)
    if not m:
        return None
    args = m.group(1).strip()
    if not args:
        return "None"
    a = re.search(r"answer\s*=\s*(.+)", args, re.S)
    return (a.group(1) if a else args).strip()


def classify(arg: str | None) -> tuple[str, str | None]:
    """(kind, literal_value) — kind in {action, literal, computed}."""
    if arg is None or arg in ("None", "answer=None"):
        return "action", None
    m = re.fullmatch(r"""['"](.*)['"]""", arg, re.S)
    if m:
        return "literal", m.group(1)
    return "computed", None


def main() -> None:
    grand = Counter()
    per_run = {}
    for arm in ARMS:
        for rep in REPS:
            ev_path = f"reviewer_events_{arm}_r{rep}.jsonl"
            if not os.path.exists(ev_path):
                continue
            events = [json.loads(l) for l in open(ev_path) if l.strip()]
            base = f"experiments/outputs/rev_{arm}_ext_r{rep}/tasks"
            rows = []
            for e in events:
                tid = e["task_id"]
                inter = parse_interactions(os.path.join(base, tid, "logs", "environment_io.md"))
                subs = [(c, o) for (c, o) in inter if "complete_task(" in c]
                converted = (not e.get("attempt1_correct")) and e.get("final_correct")
                if len(subs) < 2:
                    cat = "unresolvable"
                    detail = f"{len(subs)} executed complete_task call(s)"
                else:
                    c1, o1 = subs[0]
                    c2, o2 = subs[-1]
                    k1, v1 = classify(answer_arg(c1))
                    k2, v2 = classify(answer_arg(c2))
                    if k1 == "action" and k2 == "action":
                        cat = "ACTION (no answer submitted)"
                        detail = "code differed" if c1.strip() != c2.strip() else "code identical"
                    elif k1 == "literal" and k2 == "literal":
                        cat = "VALUE/differed" if v1 != v2 else "VALUE/same"
                        detail = f"{v1!r} -> {v2!r}"
                    else:
                        same_out = o1.strip() == o2.strip()
                        cat = ("VALUE/inferred-same" if same_out
                               else "VALUE/inferred-differed")
                        detail = f"computed; submitting-block output "\
                                 f"{'identical' if same_out else 'differs'}"
                rows.append((tid, cat, detail, converted, e.get("submission_differed")))
                grand[cat] += 1
            per_run[(arm, rep)] = rows

    print("=" * 78)
    print("CORRECTED submission_differed — per run")
    print("=" * 78)
    for (arm, rep), rows in per_run.items():
        c = Counter(r[1] for r in rows)
        old_diff = sum(1 for r in rows if r[4])
        print(f"\n{LABEL[arm]} r{rep}  (n={len(rows)} retries)")
        print(f"  OLD metric said differed: {old_diff}/{len(rows)}")
        for k in sorted(c):
            print(f"    {k:<32} {c[k]}/{len(rows)}")
        conv = [r for r in rows if r[3]]
        nonconv = [r for r in rows if not r[3]]
        print(f"  split by outcome — converted {len(conv)}, not converted {len(nonconv)}")
        for label, grp in (("converted", conv), ("not converted", nonconv)):
            if not grp:
                continue
            cc = Counter(r[1] for r in grp)
            print(f"    {label}: " + ", ".join(f"{k} {v}/{len(grp)}" for k, v in sorted(cc.items())))

    print("\n" + "=" * 78)
    print("POOLED across all four retry runs (52 retries)")
    print("=" * 78)
    tot = sum(grand.values())
    for k in sorted(grand):
        print(f"  {k:<34} {grand[k]}/{tot}")

    print("\n" + "=" * 78)
    print("PER-TASK DETAIL")
    print("=" * 78)
    for (arm, rep), rows in per_run.items():
        print(f"\n-- {LABEL[arm]} r{rep} --")
        for tid, cat, detail, conv, old in rows:
            print(f"  {tid:<12} {cat:<30} conv={str(conv):<5} old_differed={str(old):<5} {detail}")


if __name__ == "__main__":
    main()
