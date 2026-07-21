# Run report — `splitwise-random15`

- **Date:** 2026-07-20 17:56
- **Log:** `analysis/runs/splitwise-random15.log`
- **Tasks:** 15
- **Correct:** 1 / 15 (**7%**)
- **Mean time/task:** 71.8s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 2 | 3 | 1 | 33% |
| 3 | 12 | 0 | 0% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 2-app | 5 | 1 | 20% |
| 3-app | 1 | 0 | 0% |
| 4-app | 3 | 0 | 0% |
| 5-app | 3 | 0 | 0% |
| 6-app | 3 | 0 | 0% |

## Failure categories

| category | count |
|---|---|
| code_error | 7 |
| retry_killed_stale_eval | 6 |
| sandbox_timeout | 1 |

## Reviewer effectiveness

- Fired on **14** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **14**.
- Diagnosed root causes: `WRONG FILTER` ×5, `ENVIRONMENT_ERROR` ×4, `WRONG FORMAT` ×2, `WRONG SCOPE` ×2, `WRONG ENTITY` ×1
- Premature `complete_task` strips across the slice: **1**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `32616b5_2` | ❌ | 3 | simple_note,splitwise | 5/10 | 85s | code_error | I went on a few trips each with some of my coworkers. My Sim |
| `32616b5_3` | ❌ | 3 | simple_note,splitwise | 3/10 | 44s | code_error | I went on a few trips each with some of my friends. My Simpl |
| `3aa1a22_1` | ✅ | 2 | phone,splitwise | 7/7 | 46s |  | I got some Splitwise group invitations over phone text messa |
| `3aa1a22_2` | ❌ | 2 | phone,splitwise | 6/7 | 55s | code_error | I got some Splitwise group invitations over phone voice mess |
| `3aa1a22_3` | ❌ | 2 | phone,splitwise | 5/7 | 59s | code_error | I got some Splitwise group invitations over phone text messa |
| `6b6ca61_2` | ❌ | 3 | file_system,gmail,splitwise,venmo | 9/19 | 118s | sandbox_timeout | I have a list of people I owe money to, including amounts an |
| `6b6ca61_3` | ❌ | 3 | file_system,gmail,simple_note,splitwise,venmo | 9/19 | 146s | code_error | I have a list of people I owe money to, including amounts an |
| `83a7951_1` | ❌ | 3 | file_system,gmail,simple_note,splitwise,venmo | 7/10 | 91s | retry_killed_stale_eval | I owed people some money. They put the associated expenses o |
| `83a7951_3` | ❌ | 3 | file_system,gmail,simple_note,splitwise,venmo | 9/10 | 86s | code_error | I owed people some money. They put the associated expenses o |
| `8d42650_1` | ❌ | 3 | file_system,gmail,simple_note,splitwise | 4/10 | 95s | retry_killed_stale_eval | I get monthly electricity bill via email on the 1st of every |
| `8d42650_3` | ❌ | 3 | file_system,gmail,simple_note,splitwise | 4/10 | 76s | retry_killed_stale_eval | I get monthly cable bill via email on the 1st of every month |
| `988af8e_1` | ❌ | 3 | amazon,file_system,gmail,splitwise,todoist,venmo | 9/24 | 37s | retry_killed_stale_eval | I am going on a camping trip with some of my friends. I have |
| `988af8e_2` | ❌ | 3 | amazon,file_system,gmail,splitwise,todoist,venmo | 9/24 | 37s | retry_killed_stale_eval | I am going on a camping trip with some of my friends. I have |
| `988af8e_3` | ❌ | 3 | amazon,file_system,gmail,splitwise,todoist,venmo | 9/24 | 37s | retry_killed_stale_eval | I am going on a camping trip with some of my friends. I have |
| `fb05fed_2` | ❌ | 3 | amazon,gmail,splitwise | 7/11 | 66s | code_error | I ordered a few sweaters on amazon today. Ones in burgundy a |
