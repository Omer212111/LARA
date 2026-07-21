# Run report — `difficulty1-single-20`

- **Date:** 2026-07-20 19:32
- **Log:** `analysis/runs/difficulty1-single-20.log`
- **Tasks:** 20
- **Correct:** 17 / 20 (**85%**)
- **Mean time/task:** 31.4s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 | 20 | 17 | 85% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 20 | 17 | 85% |

## Failure categories

| category | count |
|---|---|
| sandbox_timeout | 2 |
| no_submit | 1 |

## Reviewer effectiveness

- Fired on **2** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **2**.
- Diagnosed root causes: `ENVIRONMENT_ERROR` ×2
- Premature `complete_task` strips across the slice: **4**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `07b42fd_2` | ✅ | 1 | spotify | 5/5 | 25s |  | Follow all the edm artists on Spotify that have at least 23  |
| `166f4ff_1` | ✅ | 1 | venmo | 2/2 | 43s |  | How much money have I been requested on Venmo in the last 7  |
| `21abae1_1` | ✅ | 1 | venmo | 2/2 | 22s |  | How much money have I sent to others on venmo this month so  |
| `23cf851_1` | ✅ | 1 | venmo | 2/2 | 33s |  | How many likes did all Venmo transactions, I sent this month |
| `27e1026_2` | ✅ | 1 | spotify | 2/2 | 56s |  | What is the title of the newest released song in my Spotify  |
| `287e338_1` | ✅ | 1 | spotify | 2/2 | 17s |  | Name the artist most recommended to me on Spotify. |
| `287e338_3` | ✅ | 1 | spotify | 2/2 | 15s |  | Name the artist most recommended to me on Spotify. |
| `365e0a3_3` | ✅ | 1 | amazon | 2/2 | 24s |  | How much have I paid in prime membership since I made the am |
| `4d12842_3` | ✅ | 1 | gmail | 4/4 | 31s |  | Delete all my archived gmail threads that are from this or t |
| `57c3486_1` | ❌ | 1 | spotify | 4/5 | 42s | sandbox_timeout | Like all the songs from the artists I follow on Spotify. |
| `59fae45_1` | ✅ | 1 | spotify | 6/6 | 29s |  | Update all my Spotify playlist titles with the most common s |
| `5a83b05_1` | ✅ | 1 | file_system | 3/3 | 26s |  | Delete all .pdf files from my file system ~/downloads folder |
| `5e27cd7_2` | ✅ | 1 | gmail | 4/4 | 21s |  | Delete all my Gmail drafts that have empty subject or body. |
| `6588a51_2` | ✅ | 1 | amazon | 6/6 | 28s |  | Post a question about the last sweater I ordered on amazon,  |
| `68ee2c9_1` | ✅ | 1 | file_system | 5/5 | 41s |  | In my file system, add the prefix "YYYY-MM-DD_" to all file  |
| `771d8fc_3` | ❌ | 1 | phone | 4/6 | 63s | sandbox_timeout | All phone text messages and voice messages from 5708520672 a |
| `a30375d_2` | ✅ | 1 | simple_note | 3/3 | 22s |  | Give me a random inspirational quote from my SimpleNote note |
| `dac78d9_2` | ✅ | 1 | venmo | 2/2 | 34s |  | How many venmo friends have I made since the start of Octobe |
| `e7a10f8_2` | ✅ | 1 | spotify | 2/2 | 26s |  | How long is my shortest Spotify playlist, in minutes, rounde |
| `6a5e690_3` | ❌ | 1 | gmail | — | 29s | no_submit | Send all my future-scheduled emails on Gmail right away. |
