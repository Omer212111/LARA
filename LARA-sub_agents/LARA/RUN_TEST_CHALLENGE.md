# Running `test_challenge` — instructions for whoever runs it

**What this is:** the second half of the AppWorld leaderboard submission.
`test_normal` has already been run (TGC 61.9 / SGC 50.0). A submission needs two
bundles, and there is no requirement that they be produced on the same machine —
run it, send back the bundle file, and both go into one PR.

**Scope:** 416 tasks, ~7-9 hours, real OpenAI cost (`gpt-4.1-mini`, your own key).

---

## ⚠️ The rule that governs everything: do not touch the code

The run must be on **exactly `3eb7770`** — the same commit `test_normal` ran on.

Before merging, the AppWorld maintainer verifies that **no changes were made between
the two evaluations**. Any change — a "small fix", a debug line — voids **both** runs
and forces a full re-run (~10 hours).

If you spot something worth fixing, write it down and send it. Do not fix it.

---

## 1. Setup

```bash
cd <project dir>/LARA-sub_agents/LARA

git fetch origin
git checkout 3eb7770

# Three checks — all must pass:
git rev-parse HEAD        # 3eb77700856b62d0876b7f17bfc0dc59c2539b1b
git status --short        # empty (except "?? data" if the symlink is there)
appworld --version        # 0.1.3.post1
```

Confirm the configuration:

```bash
python -c "
import config
print(config.MAX_EXECUTOR_RUNS, config.ENABLE_REVIEWER_RETRY, config.MAX_REACT_STEPS)
print(config.EXECUTOR_MODEL_OPENAI, config.EXPLORER_MODEL)"
```

Must print exactly:
```
1 False 16
gpt-4.1-mini gpt-4.1-mini
```

`OPENAI_API_KEY` must be in `.env`.

---

## 2. Run script

Save as `run_test_challenge.py` in the `LARA/` root:

```python
"""OFFICIAL leaderboard run — test_challenge, 416 tasks, ONE TIME ONLY.

Per the AppWorld README, test_challenge may be used only to obtain an aggregate
score: no per-task report inspection, no error analysis, no tuning on anything it
produces. Code must be commit 3eb7770, unchanged.
"""
import sys, time
sys.path.insert(0, ".")
import benchmark

EXPERIMENT = "lara_test_challenge"   # prefix "lara" must match lara_test_normal

if __name__ == "__main__":
    ids = benchmark.load_task_ids("test_challenge")
    print(f"[official] experiment={EXPERIMENT} tasks={len(ids)}", flush=True)
    import appworld as _aw
    _orig = _aw.AppWorld
    class _P(_orig):
        def __init__(self, *a, **kw):
            kw["experiment_name"] = EXPERIMENT
            super().__init__(*a, **kw)
    _aw.AppWorld = _P; benchmark.AppWorld = _P
    t0 = time.monotonic()
    try:
        benchmark.run_official_benchmark(num_tasks=len(ids),
                                         dataset="test_challenge", task_ids=ids)
    finally:
        _aw.AppWorld = _orig; benchmark.AppWorld = _orig
    print(f"\n[official] DONE in {(time.monotonic()-t0)/60:.1f} min", flush=True)
```

`benchmark.py` hardcodes `experiment_name`, so the script overrides it by subclassing
`AppWorld` rather than editing the file — editing it would change the commit and
invalidate the run.

---

## 3. Run

```bash
python -u run_test_challenge.py 2>&1 | tee test_challenge.log
```

**Before starting, make sure the machine will not sleep.** An interrupted run starts
over from zero.
- Windows: `Settings → System → Power & battery → Sleep = Never` (while plugged in)
- Laptop: don't close the lid, or set `Lid close action = Do nothing`
- WSL: the screen may switch off, but if Windows sleeps the VM stops with it

Quick progress check while it runs:
```bash
grep -cE "^(✅|❌) Task [0-9a-f]{7}_[0-9]" test_challenge.log   # tasks completed
```

---

## 4. Evaluate and pack

```bash
appworld evaluate lara_test_challenge test_challenge
```

**Read the aggregate score only.** Do not open `tasks/<task_id>/evaluation/report.md`,
do not analyse failures, and do not change anything based on what you see. This is an
explicit restriction in the AppWorld README for the test splits.

```bash
appworld pack lara_test_challenge test_challenge \
  "LARA MAS" \
  "Explorer writes an app-tagged plan; per-app specialist executors run a ReAct loop; single attempt per task" \
  "gpt-4.1-mini" \
  "gpt-4.1-mini for all agents (explorer, executor, supervisor)" \
  "https://github.com/Omer212111/LARA"
```

**The metadata must match `test_normal` word for word** — it appears as a single
leaderboard entry.

---

## 5. What to send back

1. `experiments/outputs/lara_test_challenge/leaderboard.bundle` ← the submission file
2. The aggregate score (the table `evaluate` prints)
3. Wall-clock duration

⚠️ The bundle is encrypted by design. **Do not post the experiment outputs anywhere
public in unencrypted form** — that is an AppWorld licence requirement, intended to
keep the tasks out of LLM training corpora.

---

## Background: what is already done

| split | status |
|---|---|
| `test_normal` | ✅ TGC **61.9** / SGC **50.0** (104/168, 136 min) |
| `test_challenge` | ⬜ this run |

The code at `3eb7770` is hardcode-free: `amazon_template_plan`, the ACTION regex over
the task text, `login_to_app` and `find_contact` were all removed. Verified by AST
analysis — zero `apis.*` calls in live code; every remaining mention sits inside a
prompt string, which the rules explicitly permit.

Removing the hardcode actually **improved** the score (54.8 → 61.9), most likely
because the model now writes its own login function instead of calling our helper.
