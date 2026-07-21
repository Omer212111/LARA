# Run report — `gmail-random15`

- **Date:** 2026-07-20 16:56
- **Log:** `analysis/runs/gmail-random15.log`
- **Tasks:** 15
- **Correct:** 6 / 15 (**40%**)
- **Mean time/task:** 45.1s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 | 3 | 1 | 33% |
| 2 | 7 | 4 | 57% |
| 3 | 5 | 1 | 20% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 3 | 1 | 33% |
| 2-app | 4 | 2 | 50% |
| 3-app | 5 | 2 | 40% |
| 4-app | 2 | 1 | 50% |
| 6-app | 1 | 0 | 0% |

## Failure categories

| category | count |
|---|---|
| retry_killed_stale_eval | 4 |
| code_error | 3 |
| sandbox_timeout | 1 |
| no_submit | 1 |

## Reviewer effectiveness

- Fired on **7** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **7**.
- Diagnosed root causes: `WRONG FILTER` ×3, `WRONG FORMAT` ×2, `ENVIRONMENT_ERROR` ×1, `WRONG ENTITY` ×1
- Premature `complete_task` strips across the slice: **1**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `245cb43_2` | ❌ | 1 | amazon,file_system,gmail | 7/8 | 91s | sandbox_timeout | Buy me a cutting board from my amazon wishlist that will fit |
| `277d81d_2` | ✅ | 1 | gmail | 6/6 | 85s |  | Mark everything in my Gmail inbox and outbox in the current  |
| `30e8586_1` | ❌ | 2 | amazon,file_system,gmail | 4/10 | — | code_error | Buy the highest rated popcorn maker available on Amazon now, |
| `4441ee9_2` | ❌ | 3 | gmail,todoist | 9/11 | 68s | retry_killed_stale_eval | My manager assigns me tasks at the beginning of every week w |
| `4815c06_3` | ✅ | 2 | amazon,file_system,gmail | 9/9 | 56s |  | Place an amazon order for 1 quantity of 'Ascend Ultralight H |
| `8d42650_2` | ❌ | 3 | file_system,gmail,simple_note,splitwise | 4/10 | 42s | retry_killed_stale_eval | I get monthly internet bill via email on the 1st of every mo |
| `9016950_1` | ✅ | 3 | gmail,phone,venmo | 7/7 | 54s |  | I need my parents to have a venmo account. Last time I check |
| `9126bf0_1` | ✅ | 2 | gmail,phone | 7/7 | 43s |  | Our weekly standup time has changed. Update my phone alarm a |
| `96bf160_3` | ❌ | 2 | gmail | 4/8 | 52s | retry_killed_stale_eval | My roommate sent me "cable_bill.pdf" on Gmail sometime ago.  |
| `988af8e_3` | ❌ | 3 | amazon,file_system,gmail,splitwise,todoist,venmo | 8/24 | 46s | code_error | I am going on a camping trip with some of my friends. I have |
| `998908e_1` | ❌ | 3 | file_system,gmail | 2/5 | — | retry_killed_stale_eval | I booked a few hotel rooms today for my upcoming trip. How m |
| `a3ba388_2` | ✅ | 2 | file_system,gmail | 9/9 | 34s |  | I have drafted my resignation email on Gmail. Attach "~/docu |
| `b3bdcc1_3` | ❌ | 2 | amazon,file_system,gmail | 2/9 | 47s | code_error | Buy me a portable air conditioner on amazon from its highest |
| `e0fe09c_1` | ✅ | 2 | amazon,gmail,spotify,venmo | 9/9 | 33s |  | Label all email threads in my Gmail inbox from notifications |
| `6a5e690_3` | ❌ | 1 | gmail | — | 25s | no_submit | Send all my future-scheduled emails on Gmail right away. |
