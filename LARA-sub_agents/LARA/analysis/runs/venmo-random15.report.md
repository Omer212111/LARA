# Run report — `venmo-random15`

- **Date:** 2026-07-20 14:42
- **Log:** `analysis/runs/venmo-random15.log`
- **Tasks:** 15
- **Correct:** 7 / 15 (**47%**)
- **Mean time/task:** 68.3s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 | 4 | 4 | 100% |
| 2 | 5 | 3 | 60% |
| 3 | 6 | 0 | 0% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 1 | 1 | 100% |
| 2-app | 9 | 6 | 67% |
| 3-app | 5 | 0 | 0% |

## Failure categories

| category | count |
|---|---|
| retry_killed_stale_eval | 5 |
| code_error | 2 |
| sandbox_timeout | 1 |

## Reviewer effectiveness

- Fired on **7** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **7**.
- Diagnosed root causes: `WRONG SCOPE` ×2, `WRONG ENTITY` ×2, `WRONG FORMAT` ×2, `ENVIRONMENT_ERROR` ×1
- Premature `complete_task` strips across the slice: **0**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `0d8a4ee_3` | ✅ | 2 | phone,venmo | 5/5 | 38s |  | Send the following phone message to my roommates and friends |
| `22cc237_2` | ❌ | 3 | phone,simple_note,venmo | 3/4 | 70s | retry_killed_stale_eval | I went on a dinner with some of my friends yesterday. I paid |
| `22cc237_3` | ❌ | 3 | phone,simple_note,venmo | 3/4 | 51s | retry_killed_stale_eval | I went on a dinner with some of my coworkers yesterday. I pa |
| `23cf851_1` | ✅ | 1 | venmo | 2/2 | 23s |  | How many likes did all Venmo transactions, I sent this month |
| `2a163ab_1` | ✅ | 2 | phone,venmo | 6/6 | 59s |  | Like all the venmo transactions from today involving any of  |
| `2a163ab_2` | ✅ | 2 | phone,venmo | 6/6 | 76s |  | Like all the venmo transactions from yesterday involving any |
| `37a8675_2` | ❌ | 2 | phone,venmo | 0/6 | 28s | retry_killed_stale_eval | Send $100 publicly on Venmo to the person with this phone nu |
| `3c13f5a_1` | ❌ | 3 | file_system,phone,venmo | 2/6 | 35s | code_error | I paid for our last month's electricity bill. Its amount is  |
| `3c13f5a_2` | ❌ | 3 | file_system,phone,venmo | 2/6 | 41s | retry_killed_stale_eval | I paid for our last month's internet bill. Its amount is sup |
| `3c13f5a_3` | ❌ | 3 | file_system,phone,venmo | 2/6 | 39s | sandbox_timeout | I paid for our last month's cable bill. Its amount is suppos |
| `4fab96f_2` | ❌ | 2 | phone,venmo | 3/8 | 390s | code_error | Send a reminder on Venmo for all my payment requests to my c |
| `530b157_2` | ❌ | 3 | phone,venmo | 2/10 | 63s | retry_killed_stale_eval | Joseph paid for my grocery recently as my payment cards were |
| `6ea6792_1` | ✅ | 1 | phone,venmo | 6/6 | 36s |  | Accept all pending Venmo payment requests from my roommates  |
| `df61dc5_2` | ✅ | 1 | phone,venmo | 7/7 | 34s |  | Like all the venmo transactions of the ongoing month to and  |
| `df61dc5_3` | ✅ | 1 | phone,venmo | 7/7 | 42s |  | Like all the venmo transactions of the ongoing year to and f |
