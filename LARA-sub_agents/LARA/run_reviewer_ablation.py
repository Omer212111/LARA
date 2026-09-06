"""Run the Reviewer-contribution ablation on the fixed 45-task slice.

    python run_reviewer_ablation.py noreviewer   # arm A — reference (no retry)
    python run_reviewer_ablation.py reviewer     # arm B — Reviewer diagnosis + retry
    python run_reviewer_ablation.py blindretry   # arm C — retry, Reviewer bypassed

Three arms on the SHIPPED LARA pipeline (dispatch Executor, full Explorer plan,
ledger). The ONLY thing that varies is the retry configuration:

    arm          ENABLE_RETRY  MAX_EXECUTOR_RUNS  REVIEWER_BYPASS   isolates
    noreviewer   False         1                  -                 reference floor
    reviewer     True          2                  False             diagnosis + retry
    blindretry   True          2                  True              a bare re-roll

    B - C  ==>  what the Reviewer's diagnosis (+ its retry context) buys over
                simply re-running the Executor a second time.

Per-arm outputs never collide: experiment name, token log and reviewer-event log
are all suffixed with the arm.

    experiment : rev_<arm>_ext          (AppWorld experiments/outputs/<experiment>)
    tokens     : token_usage_<arm>.jsonl
    events     : reviewer_events_<arm>.jsonl

SMOKE-FIRST BY DESIGN. Default runs only the first 3 slice tasks so a full 45-task
arm can never launch by accident. Pass --full for all 45, --smoke N for the first
N, or --tasks id1,id2,... for an explicit set.

NOT to be run on test_normal / test_challenge: AppWorld forbids using the held-out
splits for analysis or tuning. Dataset is train.
"""
import json
import os
import shutil
import sys
import time

# ── Arm selection ─────────────────────────────────────────────────────────────
# arm -> (LARA_ENABLE_RETRY, LARA_MAX_EXECUTOR_RUNS, LARA_REVIEWER_BYPASS)
ARMS = {
    "noreviewer": ("0", "1", "0"),
    "reviewer":   ("1", "2", "0"),
    "blindretry": ("1", "2", "1"),
}
MODE = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
if MODE not in ARMS:
    print(__doc__)
    print(f"arms: {', '.join(ARMS)}")
    sys.exit(1)

# Repeat suffix (_r1, _r2, ...) so two runs of the same arm never overwrite each
# other's experiment dir or logs. Hosted-model drift across days exceeds the effect
# under test, so repeats are meant to run same-session and be compared as a spread.
_rep = ""
for i, a in enumerate(sys.argv):
    if a == "--rep" and i + 1 < len(sys.argv):
        _rep = f"_r{sys.argv[i + 1]}"

EXPERIMENT = f"rev_{MODE}_ext{_rep}"

# CRITICAL: set the arm's env BEFORE importing config/benchmark. config.py reads
# these at import time to build MAX_EXECUTOR_RUNS / ENABLE_REVIEWER_RETRY /
# REVIEWER_BYPASS, and planning_loop/supervisor bind those constants at their own
# import. Setting them here, first, is what makes the arm take effect.
_enable, _maxruns, _bypass = ARMS[MODE]
os.environ["LARA_ENABLE_RETRY"]       = _enable
os.environ["LARA_MAX_EXECUTOR_RUNS"]  = _maxruns
os.environ["LARA_REVIEWER_BYPASS"]    = _bypass
os.environ["LARA_ARM"]                = EXPERIMENT
os.environ["LARA_TOKEN_LOG"]          = f"token_usage_{MODE}{_rep}.jsonl"
os.environ["LARA_REVIEWER_LOG"]       = f"reviewer_events_{MODE}{_rep}.jsonl"

# ── Task selection ────────────────────────────────────────────────────────────
FULL     = "--full" in sys.argv
_smoke_n = 3
_tasks_arg = None
for i, a in enumerate(sys.argv):
    if a == "--smoke" and i + 1 < len(sys.argv):
        _smoke_n = int(sys.argv[i + 1])
    if a == "--tasks" and i + 1 < len(sys.argv):
        _tasks_arg = sys.argv[i + 1]

import benchmark  # noqa: E402  (must come AFTER the env is set)
from config import ENABLE_REVIEWER_RETRY, MAX_EXECUTOR_RUNS, REVIEWER_BYPASS  # noqa: E402


if __name__ == "__main__":
    slice_ids = json.load(open("extended_slice.json"))
    if _tasks_arg:
        ids = [t.strip() for t in _tasks_arg.split(",") if t.strip()]
    elif FULL:
        ids = slice_ids
    else:
        ids = slice_ids[:_smoke_n]

    # Confirm the arm actually took effect (config reads env at import) before we
    # spend any API budget — a silent mis-set env would invalidate the whole arm.
    print(f"[rev-ablation] arm={MODE} experiment={EXPERIMENT} tasks={len(ids)}"
          f"{' (FULL)' if FULL else ' (smoke)'}")
    print(f"[rev-ablation] config: ENABLE_REVIEWER_RETRY={ENABLE_REVIEWER_RETRY} "
          f"MAX_EXECUTOR_RUNS={MAX_EXECUTOR_RUNS} REVIEWER_BYPASS={REVIEWER_BYPASS}")
    print(f"[rev-ablation] logs: token={os.environ['LARA_TOKEN_LOG']} "
          f"events={os.environ['LARA_REVIEWER_LOG']}", flush=True)

    # Guard against the two ways an arm can be silently wrong.
    _exp = ARMS[MODE]
    assert (str(int(ENABLE_REVIEWER_RETRY)), str(MAX_EXECUTOR_RUNS),
            str(int(REVIEWER_BYPASS))) == _exp, \
        f"arm {MODE} config mismatch: got {(ENABLE_REVIEWER_RETRY, MAX_EXECUTOR_RUNS, REVIEWER_BYPASS)}"

    import appworld as _aw
    _orig = _aw.AppWorld

    class _P(_orig):
        def __init__(self, *a, **kw):
            kw["experiment_name"] = EXPERIMENT
            kw.setdefault("timeout_seconds", None)
            super().__init__(*a, **kw)

    _aw.AppWorld = _P
    benchmark.AppWorld = _P
    t0 = time.monotonic()
    try:
        benchmark.run_official_benchmark(num_tasks=len(ids),
                                         dataset="train", task_ids=ids)
    finally:
        _aw.AppWorld = _orig
        benchmark.AppWorld = _orig
    print(f"\n[rev-ablation] {MODE} DONE in {(time.monotonic()-t0)/60:.1f} min",
          flush=True)

    if os.path.exists("run_log.html"):
        dest = f"run_log_rev_{MODE}{_rep}.html"
        shutil.copy("run_log.html", dest)
        print(f"[rev-ablation] saved {dest}", flush=True)
