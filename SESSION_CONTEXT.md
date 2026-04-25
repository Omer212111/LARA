# LARA Project — Session Context for New Chat

## What is this project?

**LARA** is an AI agent system that solves tasks on the **AppWorld benchmark** — a simulated environment of 11 apps (Spotify, Gmail, Amazon, Venmo, Splitwise, Todoist, SimpleNote, Phone, FileSystem, Supervisor, API Docs). The agent interacts with these apps by writing Python code that calls their REST-style APIs through a Python REPL. AppWorld executes each code snippet and returns the output.

The LLM backend is **GPT-4.1-nano** (OpenAI), called via the OpenAI Python SDK. The project is in `/home/omer2/LARA_project` on WSL (Ubuntu on Windows).

> **Note:** There is a second (older) implementation at `/home/omer2/LARA_project/LARA-MAS/LARA/` — a LangGraph multi-agent system with Explorer → Executor → Supervisor nodes. The root project (`/home/omer2/LARA_project/`) uses the simpler Planner → Executor pipeline and is the one actively being benchmarked.

---

## File structure

| File | Role |
|------|------|
| `main.py` | Outer loop: loads tasks, runs planner → executor pipeline, retries |
| `agent.py` | `BaseAgent`, `PlannerAgent`, `ExecutorAgent` |
| `llm_client.py` | OpenAI API calls with retries + prose detection (`_looks_like_python`) |
| `prompts.py` | `PLANNER_PROMPT_TEMPLATE` + `PROMPT_TEMPLATE` (executor) |
| `tools.py` | Python helpers injected into the AppWorld REPL (see Tools section below) |
| `config.py` | All constants: model, `MAX_PLAN_STEPS=7`, `MAX_PLANNING_ROUNDS=3`, etc. |
| `logger.py` | Writes `run_log.html` — open in browser, auto-refreshes every 2s |
| `.env` | `OPENAI_API_KEY=...` |

---

## Architecture: Planner → Executor pipeline

```
main.py
  ├─ For each cycle (up to MAX_PLANNING_ROUNDS=3):
  │
  │   PHASE 1: PlannerAgent (up to MAX_PLAN_STEPS=7 steps)
  │     • Writes a HIGH-LEVEL plain-English strategy — no API calls, no code
  │     • On cycle > 0: receives executor failure feedback (error + completed steps)
  │       and writes a REVISED plan that continues from where execution stopped
  │     • Final step: blackboard.set_plan([...], status="complete") + print(blackboard)
  │     • Blackboard is reset at the start of each planning cycle
  │
  │   PHASE 2: ExecutorAgent (up to max_interactions=25 steps)
  │     • Receives the plan from blackboard.plan_text()
  │     • Discovers APIs using list_app_apis() + get_api_doc() before every new call
  │     • Marks steps done: blackboard.mark_done(N)
  │     • main.py auto-injects real API list when "No API named X" error appears
  │     • Has consecutive_errors guard (aborts after 3 straight failures)
  │     • Has is_stuck() detection (breaks on 3× same normalized code)
  │
  │   If execution fails → collect (completed_steps, last_error)
  │     → build planner_feedback string → start next cycle
  │
  └─ Retry: up to max_mission_retries=2 full attempts per task
```

### Agent class hierarchy

```
BaseAgent
  ├─ PlannerAgent   — uses PLANNER_PROMPT_TEMPLATE
  └─ ExecutorAgent  — uses PROMPT_TEMPLATE with plan= injected
```

`BaseAgent._normalize_code()` strips comment-only lines before stuck detection.

---

## Tools injected into the AppWorld REPL (`tools.py`)

All of the following are available as globals in every executor code block:

### API Discovery (MANDATORY — use before every new API call)

```python
list_app_apis(app_name)          # → list of {name, description}
                                  #   Use when unsure which API to call
get_api_doc(app_name, api_name)  # → full spec: params + response field names
                                  #   Use BEFORE calling any API to know exact names
                                  #   If api_name is wrong, auto-falls back to list_app_apis()
```

### Searching & Filtering

```python
filter_results(data, key, value)    # all items where key contains value (case-insensitive)
find_one(data, key, value)          # first matching item, or None
get_by_id(data, id_key, id_value)   # exact ID match
```

### Sorting

```python
sort_results(data, key, reverse=False)
# key = string field name OR a lambda
# Example (string):   sort_results(emails, 'date', reverse=True)[0]
# Example (lambda):   sort_results(songs, lambda x: x.get('like_count', 0), reverse=True)[0]
```

### Pagination

```python
paginate_all(api_fn, page_size=20, **kwargs)
# Use instead of manual page loops for any paginated API
```

### Blackboard

```python
blackboard.plan_text()   # read the full execution plan
blackboard.mark_done(N)  # mark step N complete
```

---

## Key prompt rules

### Executor prompt (`PROMPT_TEMPLATE`)

1. **ONE-STEP RULE**: Write exactly ONE small action per response. Wait for output. Never combine multiple API calls.
2. **API DISCOVERY RULE**: Call `get_api_doc(app, api_name)` BEFORE calling any API for the first time. If unsure which API, call `list_app_apis(app)` first. If you get "No API named X": STOP, call `list_app_apis`.
3. **FIELD NAME RULE**: AppWorld response fields are NEVER generic `id`. They use type-prefixed names: `playlist_id`, `song_id`, `album_id`, `transaction_id`, etc. Always confirm via `get_api_doc()` before accessing.
4. **CREDENTIALS RULE**:
   ```python
   passwords = apis.supervisor.show_account_passwords()
   creds = find_one(passwords, 'account_name', 'spotify')
   result = apis.spotify.login(username="{{ supervisor.email }}", password=creds['password'])
   access_token = result['access_token']
   ```
5. **MANDATORY TOOL RULES**: Use `sort_results` (not `max()`), `filter_results` (not list comprehensions), `find_one` (not `next()`), `paginate_all` (not manual loops).
6. **Relationships** (roommates, coworkers, friends, siblings): look them up from phone app contacts, never hardcode names.

### Planner prompt (`PLANNER_PROMPT_TEMPLATE`)

- Output ONLY valid Python (the `blackboard.set_plan([...])` call + `print(blackboard)`)
- Reason through 6 questions in `#` comments before writing the plan
- Always include "Get credentials and log in" step for every app needing auth
- Common errors section covers: wrong API name, 401 Unauthorized, NameError, missing task requirements

---

## The Blackboard

```python
# Planner writes:
blackboard.set_plan(["Step 1: ...", "Step 2: ..."], status="complete")
print(blackboard)

# Executor reads/updates:
print(blackboard.plan_text())
blackboard.mark_done(1)

# main.py polls:
world.execute("print(blackboard.plan_status)")  # "complete" | ""
world.execute("print(blackboard.plan_text())")  # numbered plan string
world.execute("print(blackboard.completed_steps)")  # for feedback
```

---

## Current config values (`config.py`)

```python
MODEL_NAME           = "gpt-4.1-nano"
LLM_MAX_TOKENS       = 2000
MAX_PLAN_STEPS       = 7
MAX_PLANNING_ROUNDS  = 3
# main.py run config:
max_interactions     = 25
max_mission_retries  = 2
max_consecutive_errors = 3
experiment_name      = "lara_gpt_nano_run"
dataset              = "train"
task_ids[:20]        # runs first 20 tasks
```

---

## Benchmark history

| Run | Model | Tasks | Notes |
|-----|-------|-------|-------|
| Before session | Qwen2.5-coder (Ollama) | 5 | Old config |
| Run 4 | GPT-4.1-nano | 20 | First GPT run — `item['id']` KeyError, wrong API names, `sort_results` lambda crash |
| Run 5 | GPT-4.1-nano | 20 | With `list_app_apis` + `get_api_doc` + lambda fix. Deep analysis done (see below) |

---

## Deep failure analysis — Run 5 (first 5 tasks, 2026-04-25)

### Bug A — REPL state persists between replan cycles (CRITICAL, not yet fixed)

When a replan happens, a new `ExecutorAgent` is created with empty history, but the AppWorld REPL is NOT reset. Old variables (`access_token`, `albums`, `playlists`, etc.) from the failed cycle are still in scope. The new executor:
- Accidentally uses stale variables as if they belong to the new plan
- Gets confused about which user is logged in (log shows 3 different emails in one task)
- Sometimes gets `NameError` when it expects a variable that the OLD cycle defined but the new cycle didn't

**Fix:** Before each new executor cycle in `main.py`, reset REPL variables:
```python
TOOLS_NAMES = ['blackboard','filter_results','find_one','get_by_id','sort_results',
               'paginate_all','list_app_apis','get_api_doc','filter_apis','Blackboard']
world.execute(f"""
import builtins
keep = set(dir(builtins)) | set({TOOLS_NAMES!r}) | {{'apis'}}
for k in list(globals().keys()):
    if k not in keep:
        del globals()[k]
""")
```

### Bug B — `blackboard.mark_done(N)` never called (HIGH, not yet fixed)

Every replan feedback shows:
```
Steps completed before failure: []
```
The planner always gets told "nothing was completed" and writes a plan from Step 1, even when login and data-fetching succeeded. Wasted 3–5 steps per cycle.

**Fix:** Add to executor prompt — call `blackboard.mark_done(N)` in the SAME code block as the step, not as a separate step:
```python
result = apis.spotify.login(...)
access_token = result['access_token']
blackboard.mark_done(1)   ← same block, not a separate step
```

### Bug C — `show_playlist` returns songs with `id` not `song_id` (HIGH, partially fixed)

The FIELD NAME RULE in the prompt says "AppWorld always uses type-prefixed IDs like `song_id`". But `show_playlist` response has:
```json
"songs": [{"id": 1, "title": "string", "artist_ids": [...]}]
```
The executor calls `get_api_doc`, sees `"id": 1` in the schema, but follows the prompt rule instead → `KeyError: 'song_id'` every time.

**Fix:** Remove the blanket FIELD NAME RULE. Replace with: "Response field names vary by API — ALWAYS use exactly the names shown in `get_api_doc` response_schemas. Never assume `song_id` without checking."

### Bug D — Agent guesses non-existent APIs even after `inject_real_apis` (HIGH)

Seen 5+ times in one task run:
```
Exception: No API named 'show_playlist_tracks' found in the spotify app.
Exception: No API named 'show_user_albums' found in the spotify app.
Exception: No API named 'get_liked_songs' found in the spotify app.
```
After `inject_real_apis` injects the real list, the executor reads the list but on the NEXT step guesses a different wrong name. It doesn't actually pick from the list.

**Key insight:** Spotify songs within a playlist are accessed via `show_playlist(playlist_id=X)` → response field `songs`. There is NO separate `show_playlist_tracks`. This pattern must be in the prompt or plan.

**Fix:** Add to the PLANNER's COMMON ERRORS section:
> "Spotify songs within a playlist: use `show_playlist(playlist_id=X)` → `.songs` field (songs have `id`, NOT `song_id`). There is no `show_playlist_tracks`."

### Bug E — Executor drifts off plan after errors (HIGH)

After getting an API error and receiving the inject, the executor stops following the plan and generates code based on its own reasoning. Example: plan says "get albums", executor switches to "show_song_library" after an API error. The plan becomes irrelevant by step 5–6.

**Root cause:** The prompt shows the plan once at the start, but after 5+ error/recovery messages, the plan text is far up in the conversation history and the model forgets it.

**Fix options:**
1. Re-inject `blackboard.plan_text()` as a user message every time an error occurs
2. Add to prompt: "After ANY error — re-read the plan with `print(blackboard.plan_text())` before writing the next step"

### Bug F — create vs update review — logic gap (MEDIUM)

Task 692c77d: "Give 5-star rating to liked songs. If already rated lower, increase to 5."

The executor only called `update_song_review`, missing songs that had NO review yet (needed `create_review`). Failed:
```
assert song_ids of the ADDED song reviews match private_data.to_add_review_song_ids
```

**Fix:** Add to COMMON ERRORS in planner prompt:
> "When setting/updating a rating: first check if a review exists. If not, CREATE it. If it exists and the rating is lower, UPDATE it. Two different APIs."

---

## Known AppWorld API quirks (discovered empirically)

| App | API | Quirk |
|-----|-----|-------|
| spotify | `show_playlist(playlist_id)` | Returns `songs[].id` (NOT `song_id`) |
| spotify | Playlist tracks | No `show_playlist_tracks` — use `show_playlist()['songs']` |
| spotify | Liked songs | `show_liked_songs` (not `get_liked_songs`) |
| spotify | Song reviews | May need `create_review` OR `update_review` depending on existence |

---

## How to run

```bash
cd /home/omer2/LARA_project
source .venv/bin/activate
python main.py

# Watch live:
explorer.exe run_log.html

# Official score after run:
appworld evaluate lara_gpt_nano_run train
```

---

## History of major changes (this project)

1. Planner + Executor split (replaced single ReAct agent with two-phase pipeline)
2. Blackboard shared memory (structured communication between planner/executor/main.py)
3. Planner reasoning process (6-step comment reasoning before set_plan)
4. Auto-inject real API list on "No API named X" errors (`inject_real_apis` in main.py)
5. Smarter planner feedback on API errors (names the wrong API, instructs lookup)
6. Mandatory tool usage rules in executor prompt
7. **Switched LLM from Qwen/Ollama → GPT-4.1-nano/OpenAI** (`llm_client.py` rewritten)
8. **Added `list_app_apis` + `get_api_doc` tools** (force real API discovery before every call)
9. **Fixed `sort_results` to accept callable (lambda) key**
10. **Added FIELD NAME RULE to executor prompt** (AppWorld uses type-prefixed IDs)
11. **Added roommates → phone contacts rule to executor prompt**

---

## Pending fixes (priority order)

1. **[CRITICAL] Reset REPL between replan cycles** — `main.py` Bug A above
2. **[HIGH] Re-inject plan after each error** — executor loses plan context after 5+ messages
3. **[HIGH] Fix FIELD NAME RULE** — remove blanket rule, trust `get_api_doc` schema only
4. **[HIGH] Add `blackboard.mark_done(N)` in same code block** — prompt change
5. **[MEDIUM] Add Spotify API quirks to planner COMMON ERRORS** — `show_playlist` → songs.id, no `show_playlist_tracks`, create vs update review
