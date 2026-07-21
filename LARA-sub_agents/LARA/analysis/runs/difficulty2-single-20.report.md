# Run report — `difficulty2-single-20`

- **Date:** 2026-07-20 19:47
- **Log:** `analysis/runs/difficulty2-single-20.log`
- **Tasks:** 20
- **Correct:** 14 / 20 (**70%**)
- **Mean time/task:** 43.2s

## Success rate by difficulty

| difficulty | n | correct | rate |
|---|---|---|---|
| 2 | 20 | 14 | 70% |

## Success rate by task breadth (number of apps involved)

| apps required | n | correct | rate |
|---|---|---|---|
| 1-app | 8 | 7 | 88% |
| 2-app | 1 | 0 | 0% |
| 3-app | 11 | 7 | 64% |

## Failure categories

| category | count |
|---|---|
| retry_killed_stale_eval | 5 |
| code_error | 1 |

## Reviewer effectiveness

- Fired on **6** task(s); rescued **0**.
- Retries killed at step 1 by the stale-completion race (corrected answer computed but never submitted): **6**.
- Diagnosed root causes: `WRONG FILTER` ×3, `WRONG ENTITY` ×2, `WRONG FORMAT` ×1
- Premature `complete_task` strips across the slice: **1**.

## Per-task results

| task | ✓ | d | apps | tests | time | failure | instruction |
|---|---|---|---|---|---|---|---|
| `09ac073_2` | ✅ | 2 | gmail | 6/6 | 54s |  | Delete all my read Gmail threads from inbox/outbox, except t |
| `4242c97_1` | ✅ | 2 | amazon,file_system,gmail | 8/8 | 44s |  | Make an order for two same-colored Hanes Men's ComfortSoft S |
| `476b213_1` | ✅ | 2 | amazon | 2/2 | 25s |  | Tell me the card name I used for my last amazon prime member |
| `4815c06_1` | ✅ | 2 | amazon,file_system,gmail | 9/9 | 62s |  | Place an amazon order for 1 quantity of 'Sony PlayStation 5' |
| `6171bbc_2` | ✅ | 2 | spotify | 7/7 | 34s |  | Make me a Spotify playlist called "My Highest Rated Playlist |
| `6474048_1` | ✅ | 2 | amazon,file_system,gmail | 8/8 | 42s |  | Buy me a microwave on amazon with at least 4.2 seller rating |
| `6474048_3` | ✅ | 2 | amazon,file_system,gmail | 8/8 | 33s |  | Buy me a cutting board on amazon with at least 4.1 seller ra |
| `77bcb81_3` | ❌ | 2 | amazon,file_system,gmail | 2/7 | 59s | retry_killed_stale_eval | Place an order for everything in my amazon cart and wishlist |
| `953b296_3` | ✅ | 2 | amazon,file_system,gmail | 9/9 | 50s |  | Buy me any t-shirt in my size on amazon. Assure from QAs/rev |
| `9b2dc64_1` | ✅ | 2 | amazon,file_system,gmail | 10/10 | 46s |  | I liked that last t-shirt I bought on amazon. Place a new or |
| `a8f302f_1` | ✅ | 2 | amazon,file_system,gmail | 9/9 | 36s |  | I have a few things in my amazon cart. For each product type |
| `aa8502b_1` | ✅ | 2 | spotify | 4/4 | 21s |  | Follow all the artists who have sung at least one song I hav |
| `af84964_1` | ❌ | 2 | gmail,simple_note | 9/11 | 93s | retry_killed_stale_eval | Respond to all the emails I have received within the last 5  |
| `b0934aa_2` | ❌ | 2 | amazon,file_system,gmail | 3/11 | 42s | retry_killed_stale_eval | Buy me a external hard drive on amazon under $50 (excluding  |
| `b119b1f_2` | ✅ | 2 | spotify | 6/6 | 12s |  | Keep going to the next song on Spotify until you reach a son |
| `b3bdcc1_1` | ❌ | 2 | amazon,file_system,gmail | 8/9 | 45s | code_error | Buy me a air purifier on amazon from its highest-rated selle |
| `b7a9ee9_3` | ✅ | 2 | spotify | 4/4 | 30s |  | Follow all artists of all indie-genre songs in any of my pla |
| `c77c005_3` | ✅ | 2 | venmo | 5/5 | 65s |  | Befriend on Venmo anyone I have received money from this mon |
| `ccb4494_3` | ❌ | 2 | spotify | 4/5 | 22s | retry_killed_stale_eval | Like all the songs played so far in my spotify music player  |
| `d9987f6_2` | ❌ | 2 | amazon,file_system,gmail | 3/9 | 53s | retry_killed_stale_eval | Buy me a gaming console controller on amazon with a rating o |
