# Per-App Capability Study — 2026-07-20

**Branch under test:** `feat/specialists-and-success-rate` (commit `dfb58c7`, Gilad)
**Conducted by:** Omer
**Goal:** Identify which *task types* the current agents are weakest on, per app.

## Method

Tasks are sampled from **ground-truth metadata**, not instruction keyword matching:

| source | field | use |
|---|---|---|
| `data/tasks/<id>/ground_truth/required_apps.json` | exact app labels | per-app sampling |
| `data/tasks/<id>/ground_truth/metadata.json` | `difficulty` (1/2/3) | per-difficulty sampling |

This matters: `benchmark.find_tasks_by_app()` greps the *instruction text*, so it
mislabels tasks that merely mention an app. The sampler
(`analysis/sample_tasks.py`) uses the ground truth instead.

15 tasks per app, sampled with **seed 20260720** from `train`+`dev` (147 tasks) —
the only splits shipping `required_apps.json`. Slices are pinned in `slices.json`
as `<app>-random15`, so every run is reproducible.

Multi-app tasks are **included** (the realistic setting). Consequence: `phone` and
`venmo` samples overlap, because those apps are almost never used alone.

### Environment

- Executor / Explorer / Reviewer: `gpt-4.1-mini`, temperature 0.1
- `MAX_ITERATIONS=6`, `MAX_EXECUTOR_RUNS=2`, `MAX_REACT_STEPS=16`
- Scoring: `world.evaluate()` — the official AppWorld scorer

### Coverage — initial reading, and its correction

**Experiments 1–3 were run against train+dev only** (147 tasks), where
`required_apps.json` is shipped. That pool contains tasks for just five apps:
spotify (78), phone (48), venmo (42), file_system (21), simple_note (15) — and
none for splitwise, todoist, amazon, gmail or api_docs.

I initially concluded from this that the branch's new specialists could not be
evaluated at all, on the reasoning that the test splits "withhold ground truth."
**That conclusion was wrong.** The test splits withhold only `required_apps.json`
and `solution.py`. They *do* ship `evaluation.py`, `test_data.json` and
`private_data.json` — everything `world.evaluate()` needs. Test tasks score
normally; they merely carry no app label.

Verified directly: splitwise task `3aa1a22_1` (test split) ran end-to-end and
scored **7/7 tests, CORRECT, 62s**.

To recover the missing labels, `sample_tasks.infer_apps()` reads the models
`evaluation.py` asserts on (e.g. `venmo.Friendship`, `splitwise.Expense`) plus
the instruction text and the other shipped ground-truth files. Validated against
the 147 tasks where the true label is known: **84% of tasks get a label set
covering the truth, with occasional over-prediction and never a wrong app** —
acceptable for sampling, because actually running the task verifies it. Inferred
labels are marked `~` in the sampler output and recorded in each slice's
`sampling.method`.

Full availability across all 732 tasks:

| app | tasks | d1 | d2 | d3 | ≤2 apps |
|---|---|---|---|---|---|
| gmail | 369 | 33 | 138 | 198 | 138 |
| file_system | 289 | 24 | 106 | 159 | 85 |
| amazon | 235 | 45 | 96 | 94 | 59 |
| venmo | 167 | 30 | 54 | 83 | — |
| spotify | 161 | 66 | 53 | 42 | — |
| simple_note | 130 | 15 | 39 | 76 | — |
| phone | 122 | 25 | 46 | 51 | — |
| **splitwise** | **21** | 0 | 3 | 18 | 6 |
| **todoist** | **18** | 0 | 0 | 18 | 9 |
| **api_docs** | **0** | — | — | — | — |

Two consequences for Experiments 4–7 below:

- **Splitwise and Todoist tasks are overwhelmingly difficulty-3 and multi-app.**
  All 18 todoist tasks are d3; splitwise is 18/21. Several span *six* apps
  (`988af8e_*`: amazon+file_system+gmail+splitwise+todoist+venmo). Given Finding 1
  (3-app tasks score 11%), these slices are expected to score near zero, and a low
  score will **not** by itself indict the specialist — the log evidence of which
  APIs the specialist chose matters more than the pass rate.
- **`api_docs` has zero tasks in any split** and remains untestable.

---

## Experiment 1 — Spotify (15 tasks)

**Result: 10/15 correct (67%)**, mean 26.3s/task.
Full report: `analysis/runs/spotify-random15.report.md`
Run log (HTML): `analysis/runs/spotify-random15.run_log.html`

### By difficulty — inverted

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 (easy) | 10 | 5 | **50%** |
| 2 (medium) | 4 | 4 | **100%** |
| 3 (hard) | 1 | 1 | **100%** |

**Every failure was a difficulty-1 task.** All 4 medium and the 1 hard task passed.
This inverts the expected curve and is the single most important finding so far.

### Failure categories

| category | count |
|---|---|
| `retry_noop` | 4 |
| `code_error` | 1 |

### The dominant failure mode: the retry path is structurally dead

Four of five failures share one signature. The Reviewer fires, diagnoses the
problem **correctly**, and attempt 2 then dies at **step 1**:

```
[Orchestrator] Done — attempt 1, 9 steps, completed=True, correct=False
🔎 Code Reviewer — diagnosing wrong answer
ROOT_CAUSE: WRONG FILTER
[Orchestrator] ⚠️  Stripped premature complete_task at step 1 (≈9 plan steps remain)
[Orchestrator] ❌ WRONG at step 1: ['assert answers match.']
[Orchestrator] Done — attempt 2, 1 steps, completed=True, correct=False
→ FINISH (hit MAX_EXECUTOR_RUNS)
```

This is **not** the retry being lazy. Reading the attempt-2 code in the log shows
it writes a *complete, corrected* solution that implements the Reviewer's fix and
computes a fresh answer. The bug is a **stale-state race** between two guards:

1. The **premature-submit guard** (`base.py:366`) sees a long plan and only step 1,
   so it **strips** the `complete_task()` call. The answer is never submitted.
2. Immediately after, `evaluate_task()` (`base.py:447`) is called. It reads
   `env.task_completed()` (`tools.py:45`) — which is **sticky**: attempt 1 already
   called `complete_task`, so AppWorld still reports `completed=True` with
   attempt 1's stale, wrong verdict.
3. The orchestrator sees `completed=True, correct=False` and **`break`s** out of the
   ReAct loop at step 1.

So attempt 2 is judged on attempt 1's answer, and is killed before it can submit
its own. The two guards are individually reasonable and jointly fatal: the strip
guarantees the new answer is absent, and the sticky flag guarantees the old one is
what gets scored.

Reviewer effectiveness across the slice:

- Fired on **6** tasks, rescued **1**.
- **6/6** retries died this way at step 1.
- Root causes diagnosed: `WRONG FILTER` ×2, `WRONG FORMAT` ×2, `WRONG SCOPE` ×1,
  `WRONG ENTITY` ×1 — the diagnoses are *accurate* and the corrected code is
  *written*; it is simply never allowed to count.

**Diagnosis quality is not the bottleneck. The retry plumbing is.**

Fix directions (any one breaks the deadlock):
- Reset / snapshot AppWorld completion state between attempts, so `evaluate_task()`
  reflects only the current attempt; **or**
- Skip the `evaluate_task()` break when this attempt has not itself submitted
  (track a per-attempt `submitted` flag); **or**
- Disable the premature-strip guard on retry attempts — on a retry the model is
  deliberately reproducing the whole solution in one block, so "step 1 of ~10" is
  a miscount of its actual progress.

### Secondary signal: premature-submit pressure

**13** `Stripped premature complete_task` events across 15 tasks. The guard is
firing constantly — the Executor persistently tries to submit before finishing the
plan. This is the same underlying impulse that makes `retry_noop` possible.

### Why easy tasks fail

The d1 failures are counting/lookup questions (`4ec8de5_1/2` "how many songs…",
`e85d92a_2` "least played song by…") where the answer is a single value and
`assert answers match` fails. These have short plans, so the Executor reaches a
plausible-looking answer in few steps and submits early — with a wrong
filter or scope. Medium/hard tasks have longer plans that force more
discovery before submission, which appears to *protect* them.

### Conclusions — Spotify

1. **`retry_noop` is the highest-value fix.** The Reviewer works; the retry
   wastes it. 6 fires → 1 rescue. Fixing the retry could recover up to 4 tasks
   (67% → ~93% on this slice).
2. **Difficulty inversion is real** and should be checked against the other apps
   before drawing a general conclusion.
3. Not a specialist problem — Spotify's specialist handles the complex tasks fine.

---

## Experiment 2 — Phone (15 tasks)

**Result: 8/15 correct (53%)**, mean 43.0s/task.
Full report: `analysis/runs/phone-random15.report.md`
Run log (HTML): `analysis/runs/phone-random15.run_log.html`

### By difficulty — hard tasks collapse

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 (easy) | 7 | 4 | 57% |
| 2 (medium) | 4 | 3 | **75%** |
| 3 (hard) | 4 | 1 | **25%** |

Medium again beats easy (75% vs 57%), reproducing the Spotify inversion. But
difficulty 3 collapses to 25% — which Spotify's single d3 task could not show.

### By task breadth — the real driver

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 2 | 1 | 50% |
| 2-app | 9 | 6 | **67%** |
| 3-app | 4 | 1 | **25%** |

**3-app tasks are where the agent breaks.** All four d3 tasks are also the four
3-app tasks, so on this slice "hard" and "spans 3 apps" are the same population.
Task breadth is the more mechanistic explanation: more apps means more logins,
more cross-app entity matching, and longer plans.

### Failure categories

| category | count |
|---|---|
| `retry_killed_stale_eval` | 5 |
| `code_error` | 2 |

### Reviewer: 7 fires, 0 rescues

The retry bug found on Spotify is **systemic, not app-specific**:

- Fired on **7** tasks, rescued **0**.
- **7/7** retries killed at step 1 by the stale-completion race.
- Root causes: `WRONG FORMAT` ×4, `ENVIRONMENT_ERROR` ×2, `WRONG SCOPE` ×1.

Across Spotify + Phone the Reviewer has now fired **13 times and rescued 1**.

### New signal: sandbox timeouts on multi-app tasks

Two `ENVIRONMENT_ERROR` root causes (`22cc237_3`, `383cbac_2`) are SIGALRM
sandbox kills — the Executor wrote code heavy enough to be killed. Both are
phone+venmo or 3-app tasks. This does not appear in the Spotify slice at all,
and is a distinct failure class from wrong reasoning.

### Same-family split: `383cbac_1/2/3`

Three near-identical d1 tasks ("I went on dinner with my coworkers at X, my
manager paid, send them my share") — `_3` passed, `_1` and `_2` failed with
`assert answers match`. Identical task shape, opposite outcomes: evidence of
**run-to-run instability** rather than a missing capability. Worth a repeat run
to quantify variance before attributing any fix to a code change.

### Conclusions — Phone

1. **3-app tasks are the weakest shape (25%).** Cross-app coordination, not any
   single app's API, is the limiting factor.
2. The retry bug costs *more* here than on Spotify — 7 fires, 0 rescues.
3. Sandbox timeouts appear specifically on multi-app tasks; the heavier the task,
   the likelier the Executor writes code that gets killed.
4. Same-family tasks disagree, so single-run per-task results carry real noise.

## Experiment 3 — Venmo (15 tasks)

**Result: 7/15 correct (47%)**, mean 68.3s/task.
Full report: `analysis/runs/venmo-random15.report.md`
Run log (HTML): `analysis/runs/venmo-random15.run_log.html`

### By difficulty — a clean monotonic collapse

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 (easy) | 4 | 4 | **100%** |
| 2 (medium) | 5 | 3 | 60% |
| 3 (hard) | 6 | 0 | **0%** |

The cleanest gradient in the study: perfect on easy, zero on hard.

### By task breadth

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 1 | 1 | 100% |
| 2-app | 9 | 6 | 67% |
| 3-app | 5 | 0 | **0%** |

3-app tasks: **0/5**. Combined with Phone's 1/4, the agent solves
**1 of 9** three-app tasks across the whole study.

### Failure categories

| category | count |
|---|---|
| `retry_killed_stale_eval` | 5 |
| `code_error` | 2 |
| `sandbox_timeout` | 1 |

### Reviewer: 7 fires, 0 rescues (again)

Root causes: `WRONG SCOPE` ×2, `WRONG ENTITY` ×2, `WRONG FORMAT` ×2,
`ENVIRONMENT_ERROR` ×1. Zero premature strips on this slice, yet every retry
still died — confirming the stale `task_completed()` flag, not the strip guard,
is the necessary cause.

### Run-to-run instability is substantial

Three tasks appear in both the Phone and Venmo slices with **different outcomes**
from identical code:

| task | phone run | venmo run |
|---|---|---|
| `3c13f5a_1` | ✅ 6/6, 38s | ❌ 2/6, 35s |
| `3c13f5a_2` | ❌ 2/6 `code_error` | ❌ 2/6 `retry_killed` |
| `4fab96f_2` | ✅ 8/8, **38s** | ❌ 3/8, **390s** |

`4fab96f_2` ran **10× slower** and failed. At temperature 0.1 the Executor still
samples materially different programs. **Single-run per-task results are not
reliable evidence**; only aggregate rates over ≥15 tasks should be trusted, and
A/B comparisons of any future fix need repeat runs.

---

## Experiment 4 — Amazon (15 tasks)

**Result: 7/15 correct (47%)**, mean 125.2s/task.
Report: `analysis/runs/amazon-random15.report.md`

Two tasks (`b6d1f70_3`, `dc5c5c6_2`) burned 378s and 505s and never submitted.
Over the 13 that reached a verdict the rate is **7/13 (54%)**.

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 | 2 | 2 | 100% |
| 2 | 7 | 2 | 29% |
| 3 | 4 | 3 | 75% |

**Amazon breaks the breadth pattern — in a good way.** Its 3-app tasks scored
**4/11 (36%)**, against 1/9 (11%) for phone/venmo 3-app tasks, and it solved a
4-app d3 task (`7e1be84_2`, 8/8) and an 11-assertion d3 task (`e201314_3`, 11/11)
outright. Difficulty-3 *outperformed* difficulty-2 here.

This is the first evidence that **breadth alone does not determine failure** — it
interacts with *which* apps are combined. amazon+gmail+file_system coordinates
better than phone+venmo+simple_note. Failures split 3 `code_error` /
3 `retry_killed_stale_eval`; Reviewer fired 5, rescued 0.

## Experiment 5 — Gmail (15 tasks)

**Result: 6/15 correct (40%)**, mean 45.1s/task.
Report: `analysis/runs/gmail-random15.report.md`

Gmail tasks are heavy: one (`30e8586_1`) ran 434s. Breadth spread is wide —
1-app 1/3, 2-app 2/4, 3-app 2/5, 4-app 1/2, 6-app 0/1. Reviewer fired 7,
rescued 0.

## Experiment 6 — Splitwise (15 tasks) — new specialist

**Result: 1/15 correct (7%)**, mean 71.8s/task.
Report: `analysis/runs/splitwise-random15.report.md`

**The score does not indict the specialist.** Every Splitwise API the agent
called was checked against the 65-API surface in
`data/api_docs/standard/splitwise.json`:

```
show_groups ×20   record_expense ×20   search_users ×10   record_payment ×10
attach_expense_receipt_file ×10   accept_group_invitation ×6
post_payment_comment ×2   show_group_expenses ×1   show_activity ×7
```

**All real. Zero hallucinated names.** The specialist knows its surface.

What the score tracks instead is task breadth:

| apps in task | correct |
|---|---|
| 2-app | 1/5 |
| 3-app | 0/1 |
| 4-app | 0/3 |
| 5-app | 0/3 |
| 6-app | 0/3 |

Partial credit shows near-misses rather than collapse: `83a7951_3` scored 9/10,
`3aa1a22_2` 6/7, `3aa1a22_3` 5/7. The three 6-app `988af8e_*` tasks each scored
exactly 9/24 — the agent completes the Splitwise portion and fails the
amazon/todoist/venmo work around it. The most-failed assertions are about *other*
apps (`assert model changes match todoist.Task, amazon.Order, splitwise.Group…`
×3; `obtain added amazon.Order records… assert 1 is added` ×3).

Reviewer fired **14** times, rescued **0**.

## Experiment 7 — Todoist (15 tasks) — new specialist

**Result: 3/15 correct (20%)**, mean 66.1s/task.
Report: `analysis/runs/todoist-random15.report.md`

All 15 tasks are difficulty 3 — no easier todoist task exists in the dataset.
Same API check, same conclusion:

```
show_projects ×45   show_tasks ×43   show_task_comments ×18   update_task ×15
post_task_comment ×13   delete_task ×10   assign_or_unassign_task ×6
create_task ×5   search_users ×2   show_task ×1
```

All valid members of the 56-API Todoist surface. **Zero hallucinations.**

Breadth: 1-app 1/3, 2-app 0/5, 3-app 2/5, 6-app 0/2. Reviewer fired 12,
rescued 0.

---

## Cross-app summary — 105 tasks

| app | correct | rate | mean time | reviewer fired/rescued |
|---|---|---|---|---|
| Spotify | 10/15 | **67%** | 26.3s | 6 / 1 |
| Phone | 8/15 | **53%** | 43.0s | 7 / 0 |
| Venmo | 7/15 | **47%** | 68.3s | 7 / 0 |
| Amazon | 7/15 | **47%** | 125.2s | 5 / 0 |
| Gmail | 6/15 | **40%** | 45.1s | 7 / 0 |
| Todoist | 3/15 | **20%** | 66.1s | 12 / 0 |
| Splitwise | 1/15 | **7%** | 71.8s | 14 / 0 |
| **Total** | **42/105** | **40%** | | **58 / 1** |

### Finding 1 — Task breadth is the dominant predictor

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 24 | 14 | **58%** |
| 2-app | 35 | 17 | **49%** |
| 3-app | 31 | 9 | **29%** |
| 4-app | 6 | 2 | 33% |
| 5-app | 3 | 0 | **0%** |
| 6-app | 6 | 0 | **0%** |

Monotonic collapse past 2 apps. **Nine tasks span 5+ apps; zero were solved.**

The per-app rates in the table above are therefore **largely a proxy for the
breadth of that app's tasks**, not a measure of specialist quality. Splitwise
scores 7% because 10 of its 15 tasks span ≥3 apps; Spotify scores 67% because 14
of 15 are single-app.

Amazon is the informative exception: 36% on 3-app tasks vs 11% for phone/venmo.
Breadth interacts with *which* apps combine, so "3-app" is not one uniform class.

### Finding 2 — Both new specialists are sound; the pipeline is not

Splitwise and Todoist were audited API-call by API-call against their shipped
docs. **Every call was a real API. Zero hallucinations in either.** Partial-credit
patterns show them completing their own portion of a task and failing on
cross-app coordination. Their low scores measure Finding 1, not their own
correctness.

`api_docs` has zero tasks in any split and remains **untested**.

### Finding 3 — The Reviewer retry path is completely broken

**58 fires, 1 rescue** across 105 tasks. `retry_killed_stale_eval` is the largest
failure category in the study — **36 of 63 failures (57%)**.

| category | count |
|---|---|
| `retry_killed_stale_eval` | 36 |
| `code_error` | 21 |
| `sandbox_timeout` | 3 |
| `no_submit` | 3 |

Mechanism is unchanged from Experiment 1: the premature-submit guard strips the
retry's `complete_task()`, then `evaluate_task()` reads AppWorld's sticky
`task_completed()` flag — still `True` from attempt 1 — and breaks the ReAct loop
at step 1. The corrected answer is computed and discarded.

### Finding 4 — Difficulty collapses only at level 3

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 | 26 | 16 | 62% |
| 2 | 30 | 17 | 57% |
| 3 | 49 | 9 | **18%** |

d1 and d2 are indistinguishable (62% vs 57%); d3 collapses. Since d3 tasks are
also the multi-app ones, this largely restates Finding 1.

---

## Recommended next steps, in priority order

1. **Fix the retry path** — gates 36 of 63 failures. Make `evaluate_task()`
   attempt-scoped: track a per-attempt `submitted` flag and only break the ReAct
   loop when *this* attempt submitted. Cheapest, highest-yield fix in the study.
2. **Target multi-app coordination** (5+ apps: 0/9). The real capability ceiling.
   Amazon's relative success suggests this is tractable, not inherent.
3. **Do not judge the Splitwise/Todoist specialists on these scores.** They are
   sound. Re-measure them after fix 1, ideally on the ≤2-app subset.
4. **Require repeat runs before any A/B.** Demonstrated variance is large
   (`4fab96f_2`: 8/8 in 38s vs 3/8 in 390s across runs).
5. **Obtain or write `api_docs` tasks** — that specialist has never been executed.

---

# Part 3 — What makes a task difficult? (controlled, 60 tasks)

**Question:** the per-app study showed difficulty-3 tasks collapse, but difficulty
and app-count are confounded — AppWorld's own `difficulty` label rises with
`num_apps` (1.18 → 1.55 → 2.47 across levels). Does *complexity* hurt on its own,
independent of multi-app coordination?

**Design:** 20 tasks at each difficulty level, **restricted to ground-truth
`num_apps == 1`**. Holding app-count constant isolates task complexity. Pool:
168 / 138 / 24 single-app tasks at d1 / d2 / d3. Seed 20260720.

Slices: `difficulty1-single-20`, `difficulty2-single-20`, `difficulty3-single-20`.
Instrumentation: `analysis/difficulty_probe.py`.

## Results

| metric | d1 | d2 | d3 |
|---|---|---|---|
| **success rate** | **85%** (17/20) | **70%** (14/20) | **50%** (10/20) |
| GT solution lines | 25.7 | 44.7 | 48.5 |
| GT API calls needed | 47.6 | 35.0 | 74.0 |
| agent API calls made | 17.7 | 34.9 | 35.4 |
| plan steps written | 5.8 | 9.0 | 9.2 |
| ReAct steps used | 5.2 | 8.3 | 8.4 |
| step coverage | 0.90 | 0.89 | 0.92 |
| mean seconds | 31s | 43s | 59s |

### Failure modes

| mode | d1 | d2 | d3 |
|---|---|---|---|
| solved | 17 | 14 | 10 |
| `retry_killed` | 0 | 5 | 7 |
| `out_of_steps` | 0 | 0 | 1 |
| `near_miss` / `partial` | 3 | 1 | 2 |

## Findings

**[1] Complexity hurts on its own — but far less than multi-app breadth does.**

Holding app-count at 1, the curve is a gentle 85% → 70% → 50%. The unrestricted
difficulty curve from Parts 1–2 was 62% → 57% → **18%**. Single-app d3 scores
**50% versus 18% unrestricted** — so most of what the `difficulty` label captures
is *coordination*, not complexity. Complexity alone costs ~35 points across three
levels; adding apps costs far more.

Single-app d1 also scores 85% versus 62% unrestricted — a 23-point gap that is
purely the confound.

**[2] The agent does not give up. Step coverage is ~0.90 at every level.**

It consistently executes the plan it writes, and only **one task in 60** ran out
of ReAct steps. Neither planning discipline nor the step budget (`MAX_REACT_STEPS=16`)
is the binding constraint. The plans themselves scale correctly with difficulty
(5.8 → 9.0 → 9.2 steps).

**[3] Failing tasks work *harder*, not less — the agent thrashes rather than quits.**

| | solved | failed |
|---|---|---|
| d1 steps / call-ratio | 5.0 / 0.81 | 6.0 / 0.52 |
| d2 steps / call-ratio | 7.4 / 1.41 | 10.2 / **2.48** |
| d3 steps / call-ratio | 8.0 / 0.87 | 8.8 / 1.01 |

At every level, failed tasks consume more ReAct steps than solved ones. At d2 they
make nearly **2.5× the API calls of the reference solution**. This is not
under-exploration; it is unproductive searching — the agent keeps fetching without
converging. (The d1 exception, where failures under-call at 0.52, is a different
mode: three short lookup tasks answered too early on too little data.)

**[4] From d2 upward, the retry bug becomes the single dominant failure mode.**

`retry_killed` accounts for **0 of 3** failures at d1, but **5 of 6** at d2 and
**7 of 10** at d3 — 12 of the 16 failures above difficulty 1. The hardest tasks are
precisely where the Reviewer fires most, and precisely where its output is
discarded by the stale-completion race.

This means the measured d2/d3 rates **understate the pipeline's real capability**:
a substantial share of those failures are a plumbing defect, not a reasoning limit.

**[5] Aggregate API volume at d3 is the one genuine under-exploration signal.**

The reference solution needs 74 API calls; the agent averages 35. Across the whole
d3 slice it gathers roughly half the data the task requires. Combined with [3],
the picture is an agent that fetches the wrong things energetically rather than
the right things insufficiently.

## Conclusions — Part 3

**[1]** Fixing the retry path is worth even more than Parts 1–2 suggested — it is
concentrated exactly on the hard tasks (12 of 16 failures above d1).

**[2]** Multi-app coordination, not task complexity, is the dominant capability
gap. Single-app d3 at 50% versus unrestricted d3 at 18% quantifies the gap.

**[3]** Do not raise `MAX_REACT_STEPS`. Only 1 task in 60 exhausted it, and failing
tasks already use more steps than successful ones.

**[4]** The productive direction for hard single-app tasks is *convergence*, not
more searching: helping the Executor recognise when it has enough data, rather
than letting it keep querying.
