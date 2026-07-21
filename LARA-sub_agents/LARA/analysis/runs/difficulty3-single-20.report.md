# Run report — `difficulty3-single-20`

- **Date:** 2026-07-20 20:08
- **Log:** `analysis/runs/difficulty3-single-20.log`
- **Tasks:** 20
- **Correct:** 10 / 20 (**50%**)
- **Mean time/task:** 58.9s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 3 | 20 | 10 | 50% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 10 | 4 | 40% |
| 2-app | 3 | 2 | 67% |
| 3-app | 7 | 4 | 57% |

## Failure categories

| category | count |
|---|---|
| retry_killed_stale_eval | 7 |
| code_error | 2 |
| wrong_answer | 1 |

## Reviewer effectiveness

- Fired on **9** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **9**.
- Diagnosed root causes: `WRONG FORMAT` ×3, `WRONG FILTER` ×2, `WRONG FIELD` ×2, `WRONG DATA SOURCE` ×1, `ENVIRONMENT_ERROR` ×1
- Premature `complete_task` strips across the slice: **9**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `0a9d82a_1` | ❌ | 3 | simple_note | 1/2 | 41s | code_error | What is my longest practiced-good-posture habit streak, in n |
| `0a9d82a_2` | ❌ | 3 | simple_note | 1/2 | 35s | retry_killed_stale_eval | What is my longest limited-screen-time-to-1-hr habit streak, |
| `0a9d82a_3` | ❌ | 3 | simple_note | 1/2 | 34s | retry_killed_stale_eval | What is my longest ate-homemade-meals habit streak, in numbe |
| `0de03ea_1` | ✅ | 3 | file_system,spotify | 5/5 | 19s |  | I am going for a 15-minute drive without internet. Play an a |
| `0de03ea_2` | ✅ | 3 | file_system,spotify | 5/5 | 25s |  | I am going for a half-hour walk without internet. Play a pla |
| `0de03ea_3` | ❌ | 3 | file_system,spotify | 3/5 | 29s | retry_killed_stale_eval | I am going for a 20-minute drive without internet. Play an a |
| `23d431c_3` | ✅ | 3 | amazon,file_system,gmail | 8/8 | 66s |  | Buy me a watch from amazon within $110 (excluding tax). Only |
| `34d9492_1` | ❌ | 3 | file_system | 4/5 | 45s | retry_killed_stale_eval | Arrange my "~/photographs/vacations/" directory by organizin |
| `34d9492_2` | ✅ | 3 | file_system | 5/5 | 49s |  | Arrange my "~/photographs/vacations/" directory by organizin |
| `34d9492_3` | ✅ | 3 | file_system | 5/5 | 34s |  | Arrange my "~/photographs/vacations/" directory by organizin |
| `69ba40f_1` | ❌ | 3 | gmail | 2/12 | 36s | retry_killed_stale_eval | I just finished sending out my job applications to many pote |
| `69ba40f_3` | ❌ | 3 | gmail | 5/12 | 68s | retry_killed_stale_eval | I just finished sending out my job applications to many pote |
| `7264edc_1` | ✅ | 3 | gmail | 4/4 | 20s |  | I sent out many job application emails this week. I had sche |
| `7264edc_2` | ✅ | 3 | gmail | 4/4 | 27s |  | I sent out many job application emails this week. I had sche |
| `ec437da_1` | ✅ | 3 | amazon,file_system,gmail | 9/9 | 48s |  | Buy one Apple Watch Series 7 on Amazon. I need to get it gif |
| `ec437da_2` | ✅ | 3 | amazon,file_system,gmail | 9/9 | 41s |  | Buy one Samsung Galaxy Buds Pro on Amazon. I need to get it  |
| `ec437da_3` | ✅ | 3 | amazon,file_system,gmail | 9/9 | 55s |  | Buy one Philips Norelco OneBlade Pro on Amazon. I need to ge |
| `f99d726_1` | ❌ | 3 | amazon,file_system,gmail | 11/12 | 63s | retry_killed_stale_eval | The last t-shirt I bought on Amazon is a bit too small for m |
| `f99d726_2` | ❌ | 3 | amazon,file_system,gmail | 8/12 | 375s | wrong_answer | The last sweater I bought on Amazon is a bit too large for m |
| `f99d726_3` | ❌ | 3 | amazon,file_system,gmail | 11/12 | 68s | code_error | The last flip-flops I bought on Amazon is a bit too small fo |
