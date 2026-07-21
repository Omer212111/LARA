# Run report — `amazon-random15`

- **Date:** 2026-07-20 16:07
- **Log:** `analysis/runs/amazon-random15.log`
- **Tasks:** 15
- **Correct:** 7 / 15 (**47%**)
- **Mean time/task:** 125.2s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 | 2 | 2 | 100% |
| 2 | 7 | 2 | 29% |
| 3 | 6 | 3 | 50% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 1 | 1 | 100% |
| 2-app | 2 | 1 | 50% |
| 3-app | 11 | 4 | 36% |
| 4-app | 1 | 1 | 100% |

## Failure categories

| category | count |
|---|---|
| code_error | 3 |
| retry_killed_stale_eval | 3 |
| no_submit | 2 |

## Reviewer effectiveness

- Fired on **5** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **5**.
- Diagnosed root causes: `WRONG FORMAT` ×1, `WRONG FIELD` ×1, `ENVIRONMENT_ERROR` ×1, `WRONG FILTER` ×1, `WRONG SCOPE` ×1
- Premature `complete_task` strips across the slice: **4**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `1c4bd27_1` | ✅ | 2 | amazon,file_system,gmail | 4/4 | 33s |  | Initiate returns via FedEx for everything in my last 2 amazo |
| `2e9b91e_1` | ✅ | 1 | amazon,venmo | 5/5 | 25s |  | Everything in my amazon cart is for my friend, Denise. Reque |
| `4242c97_1` | ❌ | 2 | amazon,file_system,gmail | 6/8 | 65s | code_error | Make an order for two same-colored Hanes Men's ComfortSoft S |
| `6474048_3` | ✅ | 2 | amazon,file_system,gmail | 8/8 | 70s |  | Buy me a cutting board on amazon with at least 4.1 seller ra |
| `6588a51_3` | ✅ | 1 | amazon | 6/6 | 31s |  | Post a question about the last t-shirt I ordered on amazon,  |
| `66b7899_3` | ❌ | 2 | amazon,venmo | 1/5 | 39s | retry_killed_stale_eval | My amazon package that is to be delivered today was an order |
| `7434096_1` | ❌ | 2 | amazon,file_system,gmail | 4/6 | 66s | code_error | I bought a few Hanes Men's Tagless Crewneck Undershirts on a |
| `7434096_3` | ❌ | 2 | amazon,file_system,gmail | 5/6 | 60s | retry_killed_stale_eval | I bought a few Gildan Women's Softstyle Cotton T-Shirts on a |
| `7e1be84_2` | ✅ | 3 | amazon,file_system,gmail,phone | 8/8 | 45s |  | Buy me a stand mixer as Connor recommended in their phone me |
| `9b2dc64_2` | ❌ | 2 | amazon,file_system,gmail | 9/10 | 77s | retry_killed_stale_eval | I liked that last sweater I bought on amazon. Place a new or |
| `e201314_3` | ✅ | 3 | amazon,file_system,gmail | 11/11 | 59s |  | I am throwing a party for all of my coworkers and roommates  |
| `efc3cea_1` | ❌ | 3 | amazon,file_system,gmail | 3/9 | 374s | code_error | I am going to Japan this weekend, and my check-in bag sums t |
| `fdc4b74_2` | ✅ | 3 | amazon,gmail,todoist | 8/8 | 49s |  | I am planning to buy a few things on amazon for my company's |
| `b6d1f70_3` | ❌ | 3 | amazon,file_system,gmail | — | 378s | no_submit | Buy 2 identical headphones from amazon with at least 5 revie |
| `dc5c5c6_2` | ❌ | 3 | amazon,file_system,gmail | — | 505s | no_submit | Buy me the top-rated watch that's available now on amazon fo |
