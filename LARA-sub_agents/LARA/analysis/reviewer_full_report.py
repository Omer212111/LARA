"""Full numbers for the Reviewer-contribution ablation (3 arms x 2 repeats).

    python analysis/reviewer_full_report.py

Reads, for each arm/repeat:
  experiments/outputs/rev_<arm>_ext_r<N>/tasks/<tid>/evaluation/report.md   (outcomes)
  token_usage_<arm>_r<N>.jsonl                                             (tokens)
  reviewer_events_<arm>_r<N>.jsonl                                         (retries)

Outcome per task is one of:
  correct    — every test passed
  wrong      — complete_task() called, some test failed
  no_submit  — no report.md, i.e. complete_task() never called

Conversions/regressions are reported as fractions (k/n), never bare percentages.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from math import comb

ROOT = "experiments/outputs"
ARMS = ["noreviewer", "reviewer", "blindretry"]
LABEL = {"noreviewer": "A no-reviewer", "reviewer": "B reviewer",
         "blindretry": "C blind-retry"}
REPS = [1, 2]


# ── loaders ──────────────────────────────────────────────────────────────────

def load_outcomes(arm: str, rep: int) -> dict[str, str]:
    base = os.path.join(ROOT, f"rev_{arm}_ext_r{rep}", "tasks")
    if not os.path.isdir(base):
        return {}
    out: dict[str, str] = {}
    for tid in os.listdir(base):
        rp = os.path.join(base, tid, "evaluation", "report.md")
        if not os.path.exists(rp):
            out[tid] = "no_submit"
            continue
        text = open(rp).read()
        p = re.search(r"Num Passed Tests\s*:\s*(\d+)", text)
        t = re.search(r"Num Total\s+Tests\s*:\s*(\d+)", text)
        ok = bool(p and t and int(t.group(1)) > 0 and int(p.group(1)) == int(t.group(1)))
        out[tid] = "correct" if ok else "wrong"
    return out


def load_jsonl(path: str) -> list[dict]:
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


def solved(o: dict[str, str]) -> dict[str, bool]:
    return {k: (v == "correct") for k, v in o.items()}


# ── stats ────────────────────────────────────────────────────────────────────

def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / (2 ** n))


def tgc_sgc(o: dict[str, str]) -> tuple[float, float, int, int]:
    n = len(o)
    ok = sum(1 for v in o.values() if v == "correct")
    scen = defaultdict(list)
    for t, v in o.items():
        scen[t.rsplit("_", 1)[0]].append(v == "correct")
    sgc_n = sum(1 for v in scen.values() if all(v))
    return (100 * ok / n if n else 0.0,
            100 * sgc_n / len(scen) if scen else 0.0, ok, len(scen))


def compare(na: str, a: dict[str, bool], nb: str, b: dict[str, bool]) -> None:
    shared = sorted(set(a) & set(b))
    only_a = sum(1 for t in shared if a[t] and not b[t])
    only_b = sum(1 for t in shared if b[t] and not a[t])
    both = sum(1 for t in shared if a[t] and b[t])
    neither = sum(1 for t in shared if not a[t] and not b[t])
    p = mcnemar_exact(only_a, only_b)
    disc = only_a + only_b
    print(f"  {na} vs {nb}  (paired n={len(shared)})")
    print(f"    both {both}  neither {neither}  only-{na} {only_a}  only-{nb} {only_b}")
    print(f"    discordant {disc}   McNemar exact p = {p:.4f}"
          + ("  *sig" if p < 0.05 else ""))
    if disc < 10:
        print(f"    !! {disc} discordant pairs (<10) — DIRECTIONAL ONLY, underpowered")


# ── main ─────────────────────────────────────────────────────────────────────

O, T, E = {}, {}, {}
for arm in ARMS:
    for rep in REPS:
        O[(arm, rep)] = load_outcomes(arm, rep)
        T[(arm, rep)] = load_jsonl(f"token_usage_{arm}_r{rep}.jsonl")
        E[(arm, rep)] = load_jsonl(f"reviewer_events_{arm}_r{rep}.jsonl")

print("=" * 78)
print("1. PER-ARM TGC / SGC BY REPEAT, AND WITHIN-ARM SPREAD")
print("=" * 78)
print(f"{'arm':<16}{'rep':<5}{'TGC':>8}{'solved':>9}{'SGC':>8}{'no_submit':>11}{'wrong':>7}")
for arm in ARMS:
    tgcs = []
    for rep in REPS:
        o = O[(arm, rep)]
        if not o:
            print(f"{LABEL[arm]:<16}r{rep:<4}  (missing)")
            continue
        tgc, sgc, ok, nsc = tgc_sgc(o)
        c = Counter(o.values())
        tgcs.append(tgc)
        print(f"{LABEL[arm]:<16}r{rep:<5}{tgc:>7.1f}{ok:>6}/{len(o):<3}{sgc:>7.1f}"
              f"{c['no_submit']:>11}{c['wrong']:>7}")
    if len(tgcs) == 2:
        print(f"{'':<16}{'spread':<5}{abs(tgcs[0]-tgcs[1]):>7.1f} TGC points "
              f"({abs(round(tgcs[0]*45/100)-round(tgcs[1]*45/100)):.0f} tasks)")

print()
print("=" * 78)
print("2. WITHIN-ARM 2x2  (attempt-1 x final)  — B and C, fractions")
print("=" * 78)
for arm in ("reviewer", "blindretry"):
    for rep in REPS:
        ev = E[(arm, rep)]
        if not ev:
            print(f"\n{LABEL[arm]} r{rep}: no retry events")
            continue
        n = len(ev)
        cells = Counter()
        for r in ev:
            cells[(bool(r.get("attempt1_correct")), bool(r.get("final_correct")))] += 1
        conv = cells[(False, True)]
        stay = cells[(False, False)]
        reg = cells[(True, False)]
        held = cells[(True, True)]
        wrong_at1 = conv + stay
        print(f"\n{LABEL[arm]} r{rep}   retries fired: {n}/45  (trigger rate {n}/45)")
        print(f"  attempt1 wrong -> final correct  CONVERSION  {conv}/{n} retries"
              + (f"  ({conv}/{wrong_at1} of wrong-at-1)" if wrong_at1 else ""))
        print(f"  attempt1 wrong -> final wrong                {stay}/{n}")
        print(f"  attempt1 correct -> final correct            {held}/{n}")
        print(f"  attempt1 correct -> final wrong  REGRESSION  {reg}/{n}")

print()
print("=" * 78)
print("3. submission_differed  (did the retry actually change the answer?)")
print("=" * 78)
for arm in ("reviewer", "blindretry"):
    for rep in REPS:
        ev = E[(arm, rep)]
        if not ev:
            continue
        n = len(ev)
        diff = [r for r in ev if r.get("submission_differed")]
        same = [r for r in ev if not r.get("submission_differed")]
        dc = sum(1 for r in diff if not r.get("attempt1_correct") and r.get("final_correct"))
        sc = sum(1 for r in same if not r.get("attempt1_correct") and r.get("final_correct"))
        print(f"\n{LABEL[arm]} r{rep}:  differed {len(diff)}/{n}   identical {len(same)}/{n}")
        print(f"    of those that DIFFERED : converted {dc}/{len(diff) if diff else 0}")
        print(f"    of those IDENTICAL     : converted {sc}/{len(same) if same else 0}")

print()
print("=" * 78)
print("4. TOKEN COST")
print("=" * 78)
tot = {}
for arm in ARMS:
    for rep in REPS:
        rows = T[(arm, rep)]
        if not rows:
            continue
        total = sum(r.get("total_tokens") or 0 for r in rows)
        rev = sum(r.get("total_tokens") or 0 for r in rows if r["role"] == "reviewer")
        ex2 = sum(r.get("total_tokens") or 0 for r in rows
                  if r["role"] == "executor" and r.get("attempt") == 2)
        ok = sum(1 for v in O[(arm, rep)].values() if v == "correct")
        tot[(arm, rep)] = (total, rev, ex2, ok)
        retry_path = rev + ex2
        print(f"\n{LABEL[arm]} r{rep}")
        print(f"  total tokens        {total:>12,}   ({total/45:,.0f}/task)")
        print(f"  reviewer calls      {rev:>12,}")
        print(f"  executor attempt-2  {ex2:>12,}")
        print(f"  RETRY PATH total    {retry_path:>12,}   "
              f"({100*retry_path/total if total else 0:.1f}% of arm)")
        print(f"  solved / 1M tokens  {1e6*ok/total if total else 0:>12.2f}")

print("\n  --- marginal cost vs arm A (same repeat) ---")
for rep in REPS:
    if (("noreviewer", rep) not in tot):
        continue
    at, _, _, ao = tot[("noreviewer", rep)]
    for arm in ("reviewer", "blindretry"):
        if (arm, rep) not in tot:
            continue
        bt, _, _, bo = tot[(arm, rep)]
        d_tok, d_ok = bt - at, bo - ao
        if d_ok > 0:
            per = f"{d_tok/d_ok:,.0f} tokens per additional task solved"
        elif d_ok == 0:
            per = "no additional tasks solved — cost buys nothing (undefined)"
        else:
            per = f"solved {abs(d_ok)} FEWER while spending {d_tok:+,} tokens"
        print(f"  r{rep}  {LABEL[arm]} vs A: Dtokens {d_tok:+,}  Dsolved {d_ok:+}  -> {per}")

print()
print("=" * 78)
print("5. PAIRED McNEMAR")
print("=" * 78)
for rep in REPS:
    print(f"\n-- repeat {rep} --")
    if O[("noreviewer", rep)] and O[("reviewer", rep)]:
        compare("A", solved(O[("noreviewer", rep)]), "B", solved(O[("reviewer", rep)]))
    if O[("reviewer", rep)] and O[("blindretry", rep)]:
        compare("B", solved(O[("reviewer", rep)]), "C", solved(O[("blindretry", rep)]))
    if O[("noreviewer", rep)] and O[("blindretry", rep)]:
        compare("A", solved(O[("noreviewer", rep)]), "C", solved(O[("blindretry", rep)]))

print()
print("=" * 78)
print("6. FAILURE-TYPE SHIFT — did retries trade wrong_answer for no_submit?")
print("=" * 78)
print("\n  arm-level failure mix:")
for arm in ARMS:
    for rep in REPS:
        o = O[(arm, rep)]
        if not o:
            continue
        c = Counter(o.values())
        print(f"    {LABEL[arm]:<16}r{rep}  correct {c['correct']:>2}  "
              f"wrong {c['wrong']:>2}  no_submit {c['no_submit']:>2}")

print("\n  within-arm, per retry (attempt-1 submitted -> final submitted?):")
for arm in ("reviewer", "blindretry"):
    for rep in REPS:
        ev = E[(arm, rep)]
        if not ev:
            continue
        lost = [r for r in ev if r.get("attempt1_completed") and not r.get("final_completed")]
        gained = [r for r in ev if not r.get("attempt1_completed") and r.get("final_completed")]
        print(f"    {LABEL[arm]:<16}r{rep}  submitted->no_submit {len(lost)}/{len(ev)}"
              f"   no_submit->submitted {len(gained)}/{len(ev)}")
        for r in lost:
            print(f"        lost: {r['task_id']}")

print()
print("=" * 78)
print("7. REPRESENTATIVE REVIEWER DIAGNOSES (arm B, verbatim)")
print("=" * 78)
picked = {}
for rep in REPS:
    for r in E[("reviewer", rep)]:
        if not r.get("reviewer_fired"):
            continue
        a1, fin = bool(r.get("attempt1_correct")), bool(r.get("final_correct"))
        kind = ("CONVERTED" if (not a1 and fin) else
                "REGRESSED" if (a1 and not fin) else
                "DID NOT CONVERT")
        picked.setdefault(kind, (r, rep))
for kind in ("CONVERTED", "DID NOT CONVERT", "REGRESSED"):
    if kind not in picked:
        print(f"\n### {kind}: none occurred in either repeat")
        continue
    r, rep = picked[kind]
    print(f"\n### {kind} — task {r['task_id']} (arm B r{rep})")
    print(f"    attempt1_correct={r.get('attempt1_correct')} "
          f"final_correct={r.get('final_correct')} "
          f"submission_differed={r.get('submission_differed')}")
    print(f"    reviewer_tokens={r.get('reviewer_tokens')} "
          f"executor_run2_tokens={r.get('executor_run2_tokens')}")
    print("    --- diagnosis verbatim ---")
    for line in (r.get("diagnosis") or "(empty)").splitlines():
        print(f"    {line}")
