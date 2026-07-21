# Run report — `spotify-random15`

- **Date:** 2026-07-20 14:20
- **Log:** `analysis/runs/spotify-random15.log`
- **Tasks:** 15
- **Correct:** 10 / 15 (**67%**)
- **Mean time/task:** 26.3s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 1 | 10 | 5 | 50% |
| 2 | 4 | 4 | 100% |
| 3 | 1 | 1 | 100% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 14 | 9 | 64% |
| 2-app | 1 | 1 | 100% |

## Failure categories

| category | count |
|---|---|
| retry_killed_stale_eval | 4 |
| code_error | 1 |

## Reviewer effectiveness

- Fired on **6** task(s); rescued **1**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **6**.
- Diagnosed root causes: `WRONG FILTER` ×2, `WRONG FORMAT` ×2, `WRONG SCOPE` ×1, `WRONG ENTITY` ×1
- Premature `complete_task` strips across the slice: **13**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `287e338_1` | ✅ | 1 | spotify | 2/2 | 23s |  | Name the artist most recommended to me on Spotify. |
| `287e338_2` | ✅ | 1 | spotify | 2/2 | 14s |  | Name the artist least recommended to me on Spotify. |
| `396c5a2_1` | ❌ | 1 | spotify | 1/6 | 38s | retry_killed_stale_eval | Add all the songs from Lily Moon that have been played over  |
| `4ec8de5_1` | ❌ | 1 | spotify | 1/2 | 64s | retry_killed_stale_eval | How many songs from across my spotify song and album librari |
| `4ec8de5_2` | ❌ | 1 | spotify | 1/2 | 33s | retry_killed_stale_eval | How many songs from across my spotify song and album librari |
| `57c3486_3` | ❌ | 1 | spotify | 4/5 | 28s | code_error | Like all the songs from the artists I follow on Spotify. |
| `6bdbc26_2` | ✅ | 1 | spotify | 2/2 | 13s |  | How many people follow the artist of the currently playing s |
| `82e2fac_1` | ✅ | 1 | spotify | 2/2 | 22s |  | What is the title of the most-liked song in my Spotify playl |
| `82e2fac_2` | ✅ | 1 | spotify | 2/2 | 15s |  | What is the title of the least-played song in my Spotify son |
| `aa8502b_1` | ✅ | 2 | spotify | 4/4 | 20s |  | Follow all the artists who have sung at least one song I hav |
| `aa8502b_3` | ✅ | 2 | spotify | 4/4 | 28s |  | Follow all the artists who have sung at least one song I hav |
| `b0a8eae_1` | ✅ | 3 | simple_note,spotify | 5/5 | 25s |  | Start playing a playlist on Spotify that has enough songs fo |
| `b119b1f_3` | ✅ | 2 | spotify | 6/6 | 18s |  | Keep going to the previous song on Spotify until you reach a |
| `ce359b5_1` | ✅ | 2 | spotify | 8/8 | 25s |  | Remove all songs from my Spotify song library and playlists  |
| `e85d92a_2` | ❌ | 1 | spotify | 1/2 | 30s | retry_killed_stale_eval | What is the title of the least played song by Zoey James on  |
