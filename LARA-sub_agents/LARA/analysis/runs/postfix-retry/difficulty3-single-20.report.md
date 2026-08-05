# Run report — `difficulty3-single-20`

- **Date:** 2026-08-05 20:45
- **Log:** `d3_retryfix.log`
- **Tasks:** 20
- **Correct:** 11 / 20 (**55%**)
- **Mean time/task:** 94.3s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 3 | 20 | 11 | 55% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 10 | 6 | 60% |
| 2-app | 3 | 3 | 100% |
| 3-app | 7 | 2 | 29% |

## Failure categories

| category | count |
|---|---|
| wrong_answer | 8 |
| no_submit | 1 |

## Reviewer effectiveness

- Fired on **7** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **0**.
- Diagnosed root causes: `WRONG FIELD` ×3, `WRONG FILTER` ×2, `WRONG FORMAT` ×1, `WRONG FORMAT and WRONG FILTER` ×1
- Premature `complete_task` strips across the slice: **12**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `0a9d82a_1` | ✅ | 3 | simple_note | 2/2 | 39s |  | What is my longest practiced-good-posture habit streak, in n |
| `0a9d82a_2` | ✅ | 3 | simple_note | 2/2 | 31s |  | What is my longest limited-screen-time-to-1-hr habit streak, |
| `0a9d82a_3` | ✅ | 3 | simple_note | 2/2 | 33s |  | What is my longest ate-homemade-meals habit streak, in numbe |
| `0de03ea_1` | ✅ | 3 | file_system,spotify | 5/5 | 38s |  | I am going for a 15-minute drive without internet. Play an a |
| `0de03ea_2` | ✅ | 3 | file_system,spotify | 5/5 | 31s |  | I am going for a half-hour walk without internet. Play a pla |
| `0de03ea_3` | ✅ | 3 | file_system,spotify | 5/5 | 49s |  | I am going for a 20-minute drive without internet. Play an a |
| `23d431c_3` | ❌ | 3 | amazon,file_system,gmail | 3/8 | 174s | wrong_answer | Buy me a watch from amazon within $110 (excluding tax). Only |
| `34d9492_1` | ✅ | 3 | file_system | 5/5 | 45s |  | Arrange my "~/photographs/vacations/" directory by organizin |
| `34d9492_3` | ✅ | 3 | file_system | 5/5 | 206s |  | Arrange my "~/photographs/vacations/" directory by organizin |
| `69ba40f_1` | ❌ | 3 | gmail | 5/12 | 89s | wrong_answer | I just finished sending out my job applications to many pote |
| `69ba40f_3` | ❌ | 3 | gmail | 2/12 | 101s | wrong_answer | I just finished sending out my job applications to many pote |
| `7264edc_1` | ✅ | 3 | gmail | 4/4 | 58s |  | I sent out many job application emails this week. I had sche |
| `7264edc_2` | ❌ | 3 | gmail | 2/4 | 138s | wrong_answer | I sent out many job application emails this week. I had sche |
| `ec437da_1` | ✅ | 3 | amazon,file_system,gmail | 9/9 | 58s |  | Buy one Apple Watch Series 7 on Amazon. I need to get it gif |
| `ec437da_2` | ❌ | 3 | amazon,file_system,gmail | 5/9 | 136s | wrong_answer | Buy one Samsung Galaxy Buds Pro on Amazon. I need to get it  |
| `ec437da_3` | ✅ | 3 | amazon,file_system,gmail | 9/9 | 62s |  | Buy one Philips Norelco OneBlade Pro on Amazon. I need to ge |
| `f99d726_1` | ❌ | 3 | amazon,file_system,gmail | 9/12 | 133s | wrong_answer | The last t-shirt I bought on Amazon is a bit too small for m |
| `f99d726_2` | ❌ | 3 | amazon,file_system,gmail | 6/12 | 120s | wrong_answer | The last sweater I bought on Amazon is a bit too large for m |
| `f99d726_3` | ❌ | 3 | amazon,file_system,gmail | 9/12 | 111s | wrong_answer | The last flip-flops I bought on Amazon is a bit too small fo |
| `34d9492_2` | ❌ | 3 | file_system | — | 234s | no_submit | Arrange my "~/photographs/vacations/" directory by organizin |
