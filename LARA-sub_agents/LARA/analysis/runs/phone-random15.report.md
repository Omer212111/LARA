# Run report — `phone-random15`

- **Date:** 2026-07-20 14:22
- **Log:** `analysis/runs/phone-random15.log`
- **Tasks:** 15
- **Correct:** 8 / 15 (**53%**)
- **Mean time/task:** 43.0s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 | 7 | 4 | 57% |
| 2 | 4 | 3 | 75% |
| 3 | 4 | 1 | 25% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 2 | 1 | 50% |
| 2-app | 9 | 6 | 67% |
| 3-app | 4 | 1 | 25% |

## Failure categories

| category | count |
|---|---|
| retry_killed_stale_eval | 5 |
| code_error | 2 |

## Reviewer effectiveness

- Fired on **7** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **7**.
- Diagnosed root causes: `WRONG FORMAT` ×4, `ENVIRONMENT_ERROR` ×2, `WRONG SCOPE` ×1
- Premature `complete_task` strips across the slice: **4**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `22cc237_2` | ❌ | 3 | phone,simple_note,venmo | 3/4 | 78s | retry_killed_stale_eval | I went on a dinner with some of my friends yesterday. I paid |
| `22cc237_3` | ❌ | 3 | phone,simple_note,venmo | 3/4 | 46s | retry_killed_stale_eval | I went on a dinner with some of my coworkers yesterday. I pa |
| `29caf6f_1` | ❌ | 2 | phone,simple_note | 7/8 | 44s | retry_killed_stale_eval | Christopher has asked for my movie recommendations via phone |
| `2a163ab_1` | ✅ | 2 | phone,venmo | 6/6 | 37s |  | Like all the venmo transactions from today involving any of  |
| `302c169_2` | ✅ | 1 | phone | 8/8 | 25s |  | I am going on a vacation. Move my wake-up phone alarm to 40  |
| `383cbac_1` | ❌ | 1 | phone,venmo | 1/2 | 71s | retry_killed_stale_eval | I went on dinner with my coworkers yesterday at Azure Harbor |
| `383cbac_2` | ❌ | 1 | phone,venmo | 1/2 | 40s | retry_killed_stale_eval | I went on lunch with my coworkers yesterday at Enchanted Eat |
| `383cbac_3` | ✅ | 1 | phone,venmo | 2/2 | 45s |  | I went on dinner with my coworkers yesterday at Whimsical Bi |
| `3c13f5a_1` | ✅ | 3 | file_system,phone,venmo | 6/6 | 38s |  | I paid for our last month's electricity bill. Its amount is  |
| `3c13f5a_2` | ❌ | 3 | file_system,phone,venmo | 2/6 | 45s | code_error | I paid for our last month's internet bill. Its amount is sup |
| `4fab96f_2` | ✅ | 2 | phone,venmo | 8/8 | 38s |  | Send a reminder on Venmo for all my payment requests to my c |
| `60d0b5b_1` | ✅ | 2 | phone,venmo | 7/7 | 28s |  | The last Venmo payment request I sent to Robert was an accid |
| `771d8fc_2` | ❌ | 1 | phone | 4/6 | 43s | code_error | All phone text messages and voice messages from 9294880327 a |
| `df61dc5_2` | ✅ | 1 | phone,venmo | 7/7 | 31s |  | Like all the venmo transactions of the ongoing month to and  |
| `df61dc5_3` | ✅ | 1 | phone,venmo | 7/7 | 37s |  | Like all the venmo transactions of the ongoing year to and f |
