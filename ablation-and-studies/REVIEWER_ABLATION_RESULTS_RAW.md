# Reviewer-contribution ablation — raw results

Run date 2026-09-06/07, all six runs same session. Model `gpt-4.1-mini`,
OpenAI direct (`OPENAI_BASE_URL` unset). Dataset `train`, fixed 45-task
`extended_slice.json`, original slice order, no task selection.

Arms (only the retry configuration varies; attempt 1 is identical code in all three):

| arm | ENABLE_REVIEWER_RETRY | MAX_EXECUTOR_RUNS | REVIEWER_BYPASS |
|---|---|---|---|
| A no-reviewer | False | 1 | — |
| B reviewer    | True  | 2 | False |
| C blind-retry | True  | 2 | True  |

Arm C = "bare re-roll": attempt 2 gets no diagnosis, no failed-assert
passthrough, no previous-answer anti-repeat, per-step routing on, premature
`complete_task` guard on. Identical to a fresh attempt 1.

## Scoring basis

Primary = AppWorld `report.md` per task (all tests passed), the same basis as
`appworld evaluate` and the prior specialist-dispatch study.

Known constant offset: `c901732_1` is an ACTION task ("Play the least listened
to song on Spotify from the Echo Chamber Chronicles album") that the agent
completes correctly — 6/6 assertions pass — but WITHOUT calling
`complete_task()`. It scores solved in `report.md` and unsolved in the
benchmark's own stdout counter (which gates on `task_completed()`). It behaves
identically in all six runs, so every stdout figure is exactly 1 lower than the
`report.md` figure, and no paired comparison is affected.

---

## 1. Run inventory

| # | arm | rep | TGC | solved | SGC | wall clock | output dir |
|---|---|---|---|---|---|---|---|
| 1 | A no-reviewer | r1 | 66.7 | 30/45 | 56.0 | 16.9 min | `experiments/outputs/rev_noreviewer_ext_r1` |
| 2 | B reviewer    | r1 | 68.9 | 31/45 | 64.0 | 27.0 min | `experiments/outputs/rev_reviewer_ext_r1` |
| 3 | C blind-retry | r1 | 80.0 | 36/45 | 76.0 | 19.1 min | `experiments/outputs/rev_blindretry_ext_r1` |
| 4 | A no-reviewer | r2 | 75.6 | 34/45 | 64.0 | 17.4 min | `experiments/outputs/rev_noreviewer_ext_r2` |
| 5 | B reviewer    | r2 | 73.3 | 33/45 | 64.0 | 24.6 min | `experiments/outputs/rev_reviewer_ext_r2` |
| 6 | C blind-retry | r2 | 75.6 | 34/45 | 68.0 | 18.8 min | `experiments/outputs/rev_blindretry_ext_r2` |

Total wall clock 123.8 min. 25 scenarios per run (SGC denominator).

Benchmark-stdout counts (the -1 variant, for cross-reference):
A r1 29, B r1 30, C r1 35, A r2 33, B r2 32, C r2 33.

## 2. Per-arm TGC / SGC by repeat, and spread

| arm | rep | TGC | solved | SGC | wrong | no_submit |
|---|---|---|---|---|---|---|
| A no-reviewer | r1 | 66.7 | 30/45 | 56.0 | 15 | 0 |
| A no-reviewer | r2 | 75.6 | 34/45 | 64.0 |  9 | 2 |
| **A spread**  |    | **8.9 pts** | **4 tasks** | 8.0 | | |
| B reviewer    | r1 | 68.9 | 31/45 | 64.0 | 14 | 0 |
| B reviewer    | r2 | 73.3 | 33/45 | 64.0 | 11 | 1 |
| **B spread**  |    | **4.4 pts** | **2 tasks** | 0.0 | | |
| C blind-retry | r1 | 80.0 | 36/45 | 76.0 |  9 | 0 |
| C blind-retry | r2 | 75.6 | 34/45 | 68.0 | 11 | 0 |
| **C spread**  |    | **4.4 pts** | **2 tasks** | 8.0 | | |

Pooled over both repeats (out of 90 task-runs):
A 64/90, B 64/90, C 70/90.

## 3. Attempt-1 noise floor

Attempt 1 is the same code path in all three arms; the arms differ only in what
happens AFTER a wrong attempt 1. Attempt-1 solved count is therefore an estimate
of the same quantity six times over.

Measured as: `attempt-1 correct = final correct - conversions`.
Valid because retries fired only on non-correct attempt-1s (the
attempt1-correct row of every 2x2 below is 0) and there were 0 regressions, so
no correct attempt-1 was ever lost.

| arm | rep | final solved | conversions | attempt-1 solved |
|---|---|---|---|---|
| A | r1 | 30 | 0 | 30 |
| A | r2 | 34 | 0 | 34 |
| B | r1 | 31 | 3 | 28 |
| B | r2 | 33 | 2 | 31 |
| C | r1 | 36 | 0 | 36 |
| C | r2 | 34 | 1 | 33 |

**Range 28-36 solved (62.2-80.0 TGC), a spread of 8 tasks / 17.8 TGC points on
identical code.** Mean 32.0.

## 4. Within-arm 2x2 (attempt-1 x final)

| arm | rep | retries | wrong->correct | wrong->wrong | correct->correct | correct->wrong |
|---|---|---|---|---|---|---|
| B reviewer    | r1 | 17 | 3/17 | 14/17 | 0/17 | 0/17 |
| B reviewer    | r2 | 14 | 2/14 | 12/14 | 0/14 | 0/14 |
| C blind-retry | r1 |  9 | 0/9  | 9/9   | 0/9  | 0/9  |
| C blind-retry | r2 | 12 | 1/12 | 11/12 | 0/12 | 0/12 |

Pooled: **B conversions 5/31, C conversions 1/21. B regressions 0/31,
C regressions 0/21.**

## 5. Trigger rate (fractions of 45)

| arm | rep | triggered |
|---|---|---|
| B reviewer    | r1 | 17/45 |
| B reviewer    | r2 | 14/45 |
| C blind-retry | r1 |  9/45 |
| C blind-retry | r2 | 12/45 |

Pooled B 31/90, C 21/90. Arm A 0/90 by construction (MAX_EXECUTOR_RUNS=1);
arm A produced no reviewer-event rows and zero `reviewer`-role token rows.

## 6. Conversions and regressions (fractions)

| arm | rep | conversions | regressions | of wrong-at-attempt-1 |
|---|---|---|---|---|
| B | r1 | 3/17 | 0/17 | 3/17 |
| B | r2 | 2/14 | 0/14 | 2/14 |
| C | r1 | 0/9  | 0/9  | 0/9  |
| C | r2 | 1/12 | 0/12 | 1/12 |
| **B pooled** | | **5/31** | **0/31** | |
| **C pooled** | | **1/21** | **0/21** | |

## 7. submission_differed — CORRECTED

### 7a. Why the originally reported figure is void

The shipped extractor regex-parsed the model's own code. It fails two ways:
* ACTION tasks submit `answer=None` -> extractor yields `""` for BOTH attempts
* computed answers render as the same expression text for both attempts even
  when the value changed (e.g. `<computed: str(total_cost)>` on both sides of
  `0.0 -> correct`)

Originally reported (DO NOT USE): B differed 3/31, C differed 2/21, with 46/52
retries having an empty extracted answer on both sides.

Recomputed from AppWorld's own per-task transcript
(`logs/environment_io.md`), which records every executed code block and its
output for both attempts. Script: `analysis/recompute_submission_differed.py`.
Forward fix in `app_agents/base.py`: `_read_submitted_answer()` reads the value
back from `apis.supervisor.show_active_task()` (ground truth — `complete_task`
stores `json.dumps(answer)` on the Task model), logged as
`submission_differed_v2` / `submission_resolved`.

### 7b. Corrected classification, pooled (52 retries)

| category | count |
|---|---|
| ACTION — no answer submitted, metric not applicable | 44/52 |
| VALUE/differed (both literals, exact) | 2/52 |
| VALUE/inferred-differed (computed; submitting-block output differs) | 2/52 |
| VALUE/inferred-same (computed; submitting-block output identical) | 2/52 |
| unresolvable (<2 executed complete_task calls found) | 2/52 |

Of the 6 resolvable VALUE retries: **4 differed, 2 same.**

For the 44 ACTION retries the answer cannot differ (None both times); the
analogous question is whether the executed code differed:
**23/44 code differed, 21/44 code identical.**

### 7c. Per run

| arm | rep | n | OLD said differed | ACTION | VALUE/differed | VALUE/inferred-differed | VALUE/inferred-same | unresolvable |
|---|---|---|---|---|---|---|---|---|
| B | r1 | 17 | 1/17 | 14/17 | 0 | 2/17 | 0 | 1/17 |
| B | r2 | 14 | 2/14 | 11/14 | 1/14 | 0 | 1/14 | 1/14 |
| C | r1 |  9 | 1/9  | 8/9  | 1/9  | 0 | 0 | 0 |
| C | r2 | 12 | 1/12 | 11/12 | 0 | 0 | 1/12 | 0 |

### 7d. Split by converted vs not

| arm | rep | outcome | breakdown |
|---|---|---|---|
| B | r1 | converted (3)     | ACTION 2/3, VALUE/inferred-differed 1/3 |
| B | r1 | not converted (14)| ACTION 12/14, VALUE/inferred-differed 1/14, unresolvable 1/14 |
| B | r2 | converted (2)     | ACTION 1/2, VALUE/differed 1/2 |
| B | r2 | not converted (12)| ACTION 10/12, VALUE/inferred-same 1/12, unresolvable 1/12 |
| C | r1 | converted (0)     | — |
| C | r1 | not converted (9) | ACTION 8/9, VALUE/differed 1/9 |
| C | r2 | converted (1)     | ACTION 1/1 |
| C | r2 | not converted (11)| ACTION 10/11, VALUE/inferred-same 1/11 |

ACTION-task code change, split by outcome (pooled):
converted 3 code-differed / 1 code-identical; not converted 20 code-differed /
20 code-identical.

### 7e. Cases where the OLD metric was wrong, both directions

False negatives (old said identical, actually differed):
* `76f2c72_3` B r1 — computed, output differs, CONVERTED (`0.0` -> correct)
* `22cc237_2` B r1 — ACTION, code differed, CONVERTED

False positives (old said differed, actually same):
* `e7a10f8_2` B r2 — computed, submitting-block output identical
* `6104387_2` C r2 — computed, submitting-block output identical

Exact literal changes observed:
* `287e338_2` B r2 — `'Apollo Serenade'` -> `'Evelyn Rose'`, CONVERTED
* `76f2c72_3` C r1 — `'8092'` -> `'262.90'`, did NOT convert

## 8. Token cost

| arm | rep | total | per task | reviewer calls | executor run-2 | retry path | retry path % | solved/1M |
|---|---|---|---|---|---|---|---|---|
| A | r1 | 2,139,773 | 47,551 | 0 | 0 | 0 | 0.0% | 14.02 |
| A | r2 | 2,092,378 | 46,497 | 0 | 0 | 0 | 0.0% | 16.25 |
| B | r1 | 2,852,023 | 63,378 | 45,286 | 652,466 | 697,752 | 24.5% | 10.87 |
| B | r2 | 2,836,579 | 63,035 | 35,626 | 686,845 | 722,471 | 25.5% | 11.63 |
| C | r1 | 2,670,282 | 59,340 | 0 | 547,094 | 547,094 | 20.5% | 13.48 |
| C | r2 | 2,744,155 | 60,981 | 0 | 661,165 | 661,165 | 24.1% | 12.39 |

Arm totals over both repeats: A 4,232,151 · B 5,688,602 · C 5,414,437.
Reviewer-call share of arm B: 80,912 / 5,688,602 = 1.4%.

Tokens per additional task solved, vs arm A:

| comparison | delta tokens | delta solved | tokens per additional task |
|---|---|---|---|
| B vs A, r1 | +712,250 | +1 | 712,250 |
| C vs A, r1 | +530,509 | +6 | 88,418 |
| B vs A, r2 | +744,201 | −1 | negative — solved 1 fewer while spending more |
| C vs A, r2 | +651,777 | 0 | undefined — no additional tasks solved |
| **B vs A, pooled** | **+1,456,451** | **0** | **undefined — no additional tasks solved** |
| **C vs A, pooled** | **+1,182,286** | **+6** | **197,048** |

## 9. McNemar (paired, exact, two-sided)

```
-- repeat 1 --
  A vs B  (paired n=45)
    both 26  neither 10  only-A 4  only-B 5
    discordant 9   McNemar exact p = 1.0000
    !! 9 discordant pairs (<10) — DIRECTIONAL ONLY, underpowered
  B vs C  (paired n=45)
    both 29  neither 7  only-B 2  only-C 7
    discordant 9   McNemar exact p = 0.1797
    !! 9 discordant pairs (<10) — DIRECTIONAL ONLY, underpowered
  A vs C  (paired n=45)
    both 29  neither 8  only-A 1  only-C 7
    discordant 8   McNemar exact p = 0.0703
    !! 8 discordant pairs (<10) — DIRECTIONAL ONLY, underpowered

-- repeat 2 --
  A vs B  (paired n=45)
    both 29  neither 7  only-A 5  only-B 4
    discordant 9   McNemar exact p = 1.0000
    !! 9 discordant pairs (<10) — DIRECTIONAL ONLY, underpowered
  B vs C  (paired n=45)
    both 31  neither 9  only-B 2  only-C 3
    discordant 5   McNemar exact p = 1.0000
    !! 5 discordant pairs (<10) — DIRECTIONAL ONLY, underpowered
  A vs C  (paired n=45)
    both 31  neither 8  only-A 3  only-C 3
    discordant 6   McNemar exact p = 1.0000
    !! 6 discordant pairs (<10) — DIRECTIONAL ONLY, underpowered
```

All six comparisons have fewer than 10 discordant pairs. None reaches
significance at .05. Every comparison is directional only.

## 10. Failure-type shift

Question: did retries convert wrong_answer into no_submit by consuming
iteration budget?

Per-retry, attempt-1 submitted -> final not submitted:

| arm | rep | submitted -> no_submit | no_submit -> submitted |
|---|---|---|---|
| B | r1 | 0/17 | 1/17 |
| B | r2 | 0/14 | 0/14 |
| C | r1 | 0/9  | 0/9  |
| C | r2 | 0/12 | 0/12 |

Zero occurrences across all 52 retries. One retry moved the other way
(no_submit -> submitted, arm B r1).

Arm-level failure mix:

| arm | rep | correct | wrong | no_submit |
|---|---|---|---|---|
| A | r1 | 30 | 15 | 0 |
| A | r2 | 34 |  9 | 2 |
| B | r1 | 31 | 14 | 0 |
| B | r2 | 33 | 11 | 1 |
| C | r1 | 36 |  9 | 0 |
| C | r2 | 34 | 11 | 0 |

The two no_submit tasks in A r2 and one in B r2 are attempt-1 variance, not
retry-induced (no retry lost a submission).

## 11. Anomalies, caveats, limitations, and disconfirming evidence

### Disconfirming / does not fit a "Reviewer doesn't help" reading

1. **B converts 5/31, C converts 1/21.** Directionally the diagnosis converts
   ~3.4x more often than a bare re-roll. Not significant at these counts, and
   the B-vs-C McNemar on final outcomes is p=0.1797 (r1) / p=1.0000 (r2), but
   the within-arm conversion counts point the same way in both repeats
   (3/17 and 2/14 vs 0/9 and 1/12).
2. **Zero regressions in both arms (0/31, 0/21).** The retry never broke a
   correct answer and never consumed budget into a no_submit (0/52). The retry
   path is downside-free in this data.
3. **Two exact literal answer changes tied to a diagnosis.** `287e338_2` B r2
   went `'Apollo Serenade'` -> `'Evelyn Rose'` and converted. `76f2c72_3` B r1
   went from a `0.0` submission to correct after a WRONG FILTER diagnosis
   naming the hardcoded file list.
4. **Arm B's SGC is stable at 64.0 in both repeats** while A moved 56.0 -> 64.0
   and C moved 76.0 -> 68.0.

### Confounds and limitations

5. **The attempt-1 noise floor (28-36, 17.8 TGC points) exceeds every effect
   measured.** All between-arm TGC differences sit inside it.
6. **Arms are not paired on attempt-1 quality.** Trigger rates differ sharply
   (B 17 and 14 vs C 9 and 12), i.e. C simply had fewer wrong attempt-1s. Most
   of C's TGC lead is attempt-1 luck, not its retry — C's retry converted 1/21.
   A B-vs-C comparison on FINAL outcomes is therefore confounded; the within-arm
   2x2 is the only unconfounded comparison here.
7. **`b0a8eae_1` (B r1) converted with byte-identical ACTION code.** Same code,
   different outcome across attempts — attributable to residual world state from
   attempt 1 or to nondeterminism, not to the diagnosis. At least 1 of the 6
   pooled conversions is not attributable to a changed submission.
8. **44/52 retries are ACTION tasks**, where no answer is submitted at all. The
   study's central "did the answer change" question is inapplicable to 85% of
   the retry population on this slice.
9. **`submission_differed` for computed answers is INFERRED**, from whether the
   submitting block's printed output differed — not an exact value comparison.
   4 of the 8 VALUE retries rest on that inference.
10. **2/52 retries are unresolvable**: `3c13f5a_1` (B r1) shows 1 executed
    complete_task call and `22cc237_1` (B r2) shows 0, despite a retry event
    being logged. Cause not established.
11. **`c901732_1` scoring ambiguity** (section "Scoring basis") — solved under
    `report.md`, unsolved under `task_completed()`. Constant across all arms.
12. **Two repeats only.** Within-arm spreads (4-8 TGC points) are estimated from
    n=2 per arm.
13. **Single model tier** (`gpt-4.1-mini`), train split only, 45-task slice
    that is spotify-heavy and ACTION-heavy.
14. **The retry-path token figures for arm B include the Reviewer call
    (1.4% of arm) and the second Executor attempt (~24%)**; the two are not
    separable in the per-task TGC effect.
15. **Reviewer/Executor endpoint parity holds only while `OPENAI_BASE_URL` is
    unset.** The Reviewer client hardcodes api.openai.com; the Executor honours
    the env var. Unset for all six runs (verified); a warning now fires if set.

### Instrumentation notes

16. The originally reported `submission_differed` numbers (B 3/31, C 2/21) are
    void — see 7a. Every other metric in this file is unaffected by that bug.
17. Arm A emitted zero reviewer-event rows and zero `reviewer`-role token rows
    across both repeats, confirming the Reviewer never fired.
18. Arm C emitted zero `reviewer`-role token rows across both repeats,
    confirming the bypass.
