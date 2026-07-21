# Run report — `todoist-random15`

- **Date:** 2026-07-20 18:54
- **Log:** `analysis/runs/todoist-random15.log`
- **Tasks:** 15
- **Correct:** 3 / 15 (**20%**)
- **Mean time/task:** 66.1s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 3 | 15 | 3 | 20% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 3 | 1 | 33% |
| 2-app | 5 | 0 | 0% |
| 3-app | 5 | 2 | 40% |
| 6-app | 2 | 0 | 0% |

## Failure categories

| category | count |
|---|---|
| retry_killed_stale_eval | 9 |
| code_error | 3 |

## Reviewer effectiveness

- Fired on **12** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **12**.
- Diagnosed root causes: `WRONG ENTITY` ×3, `ENVIRONMENT_ERROR` ×2, `WRONG FILTER` ×2, `WRONG SCOPE` ×2, `WRONG FORMAT` ×1, `WRONG DATA SOURCE` ×1, `WRONG FIELD` ×1
- Premature `complete_task` strips across the slice: **5**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `4441ee9_1` | ❌ | 3 | gmail,todoist | 8/11 | 74s | retry_killed_stale_eval | My manager assigns me tasks at the beginning of every week w |
| `4441ee9_2` | ❌ | 3 | gmail,todoist | 8/11 | 56s | retry_killed_stale_eval | My manager assigns me tasks at the beginning of every week w |
| `8ce6779_1` | ❌ | 3 | todoist | 5/9 | 61s | code_error | At my job, we manage the tasks on todoist. But I am changing |
| `8ce6779_2` | ❌ | 3 | todoist | 5/9 | 57s | code_error | At my job, we manage the tasks on todoist. But I am changing |
| `8ce6779_3` | ✅ | 3 | todoist | 9/9 | 47s |  | At my job, we manage the tasks on todoist. But I am changing |
| `986aa4e_1` | ❌ | 3 | spotify,todoist | 6/10 | 105s | retry_killed_stale_eval | I am going on a trip to Beijing with some of my roommates. W |
| `986aa4e_2` | ❌ | 3 | spotify,todoist | 5/10 | 57s | code_error | I am going on a trip to Edinburgh with some of my siblings.  |
| `986aa4e_3` | ❌ | 3 | spotify,todoist | 5/10 | 88s | retry_killed_stale_eval | I am going on a trip to Bangkok with some of my friends. We  |
| `988af8e_1` | ❌ | 3 | amazon,file_system,gmail,splitwise,todoist,venmo | 9/24 | 56s | retry_killed_stale_eval | I am going on a camping trip with some of my friends. I have |
| `988af8e_3` | ❌ | 3 | amazon,file_system,gmail,splitwise,todoist,venmo | 9/24 | 35s | retry_killed_stale_eval | I am going on a camping trip with some of my friends. I have |
| `bde252e_1` | ❌ | 3 | gmail,simple_note,todoist | 4/9 | 73s | retry_killed_stale_eval | I maintain my work schedule in SimpleNote and track my tasks |
| `bde252e_3` | ❌ | 3 | gmail,simple_note,todoist | 5/9 | 104s | retry_killed_stale_eval | I maintain my work schedule in SimpleNote and track my tasks |
| `fdc4b74_1` | ✅ | 3 | amazon,gmail,todoist | 8/8 | 64s |  | I am planning to buy a few things on amazon for my company's |
| `fdc4b74_2` | ✅ | 3 | amazon,gmail,todoist | 8/8 | 67s |  | I am planning to buy a few things on amazon for my company's |
| `fdc4b74_3` | ❌ | 3 | amazon,gmail,todoist | 0/8 | 46s | retry_killed_stale_eval | I am planning to buy a few things on amazon for my company's |
