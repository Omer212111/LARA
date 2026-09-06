"""Run the specialist-dispatch ablation on a fixed, paired task slice.

    python run_specialist_ablation.py dispatch --extended
    python run_specialist_ablation.py monolith --extended
    python run_specialist_ablation.py generic  --extended

All arms run the SAME task ids (paired design) with the SAME Explorer plans, the
same step budget, the same ledger and the same helpers. The only thing that varies
is which system prompt each code step is given. See ablation_specialists.py for
why `monolith` — not `generic` — is the arm the claim rests on.

NOT to be run on test_normal / test_challenge: AppWorld forbids using the held-out
splits for analysis or tuning. Default dataset is train.
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, "/home/omer2/LARA_ablation")

ARMS = ("dispatch", "monolith", "generic")
MODE = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
if MODE not in ARMS:
    print(__doc__)
    print(f"arms: {', '.join(ARMS)}")
    sys.exit(1)

EXTENDED = "--extended" in sys.argv
DEMO = "--demo" in sys.argv

import benchmark
import executor as _executor
import ablation_specialists

# Same fixed slice as the planning ablation, so results are comparable across the
# two studies and the difficulty spread is already known (5/5/10 at levels 1/2/3).
TASK_IDS = [
    "82e2fac_1", "82e2fac_2", "82e2fac_3",
    "07b42fd_2", "166f4ff_1", "3aa1a22_1",
    "8d42650_1", "8d42650_2", "8d42650_3",
    "6b6ca61_2", "83a7951_1", "988af8e_1",
    "e0fe09c_1", "7e1be84_2", "50e1ac9_1",
    "fac291d_1", "32616b5_2", "3c13f5a_2",
    "8ce6779_1", "b119b1f_3",
]

_suffix = "_ext" if EXTENDED else ("_demo" if DEMO else "")
EXPERIMENT = f"spec_{MODE}{_suffix}"

if __name__ == "__main__":
    if EXTENDED:
        ids = json.load(open("extended_slice.json"))
    elif DEMO:
        ids = TASK_IDS[:3]
    else:
        ids = TASK_IDS

    stats = ablation_specialists.install(MODE, _executor._orchestrator)
    print(f"[spec-ablation] arm={MODE} experiment={EXPERIMENT} tasks={len(ids)}")
    print(f"[spec-ablation] prompt sizes: {stats}", flush=True)

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
    print(f"\n[spec-ablation] {MODE} DONE in {(time.monotonic()-t0)/60:.1f} min",
          flush=True)

    if os.path.exists("run_log.html"):
        dest = f"run_log_spec_{MODE}.html"
        shutil.copy("run_log.html", dest)
        print(f"[spec-ablation] saved {dest}", flush=True)
