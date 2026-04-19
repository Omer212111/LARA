# LARA Project — Session Context for New Chat

## What is this project?

**LARA** is an AI agent system that solves tasks on the **AppWorld benchmark** — a simulated environment of 11 apps (Spotify, Gmail, Amazon, Venmo, Splitwise, Todoist, SimpleNote, Phone, FileSystem, Supervisor, API Docs). The agent interacts with these apps by writing Python code that calls their REST-style APIs through a Python REPL. AppWorld executes each code snippet and returns the output.

The LLM backend is **qwen2.5-coder:latest** running on a remote Ollama server (`https://192.116.98.6`), called via `/api/chat`. The project is in `/home/omer2/LARA_project` on WSL (Ubuntu on Windows).

---

## File structure

| File | Role |
|------|------|
| `main.py` | Outer loop: loads tasks, runs planner → executor pipeline, retries |
| `agent.py` | `BaseAgent`, `PlannerAgent`, `ExecutorAgent`, `MinimalReactAgent` |
| `llm_client.py` | Ollama API calls with retries + prose detection (`_looks_like_python`) |
| `prompts.py` | `PLANNER_PROMPT_TEMPLATE` + `PROMPT_TEMPLATE` (executor) |
| `tools.py` | Python helpers injected into the AppWorld REPL: `filter_results`, `find_one`, `get_by_id`, `sort_results`, `paginate_all`, `filter_apis`, `Blackboard` class + `blackboard` instance |
| `config.py` | All constants: model, URLs, `MAX_PLAN_STEPS=5`, `MAX_PLANNING_ROUNDS=2`, `MAX_FEEDBACK_STEPS=5` |
| `logger.py` | Writes `run_log.html` — open in browser, auto-refreshes every 2s to watch runs live |
| `planning_loop.py` | Old LangChain ReAct implementation — not used by `main.py`, kept for reference |

---

## Architecture: Planner → Executor pipeline

### How a task runs

```
main.py
  ├─ For each cycle (up to MAX_PLANNING_ROUNDS):
  │
  │   PHASE 1: PlannerAgent (up to MAX_PLAN_STEPS=7 steps)
  │     • Writes a HIGH-LEVEL plain-English strategy — no API calls, no code
  │     • On cycle > 0: receives executor failure feedback (error + completed steps)
  │       and writes a REVISED plan that fixes the identified problem
  │     • Final step: blackboard.set_plan([...], status="complete")
  │     • Blackboard is reset at the start of each planning cycle
  │
  │   PHASE 2: ExecutorAgent (up to max_interactions=15 steps)
  │     • Receives the plan from blackboard.plan_text()
  │     • Discovers APIs on its own using show_api_descriptions
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
  ├─ PlannerAgent        — uses PLANNER_PROMPT_TEMPLATE
  ├─ ExecutorAgent       — uses PROMPT_TEMPLATE with plan= injected
  └─ MinimalReactAgent   — alias for ExecutorAgent(plan="")
```

`BaseAgent._normalize_code()` strips comment-only lines before stuck detection, so `is_stuck()` compares logic not comments.

---

## The Blackboard (shared communication)

`Blackboard` is defined in `tools.py` and injected into the AppWorld REPL as `blackboard = Blackboard()`.

**Planner writes:**
```python
blackboard.add_apis('spotify', relevant_spotify)      # store filtered APIs
blackboard.set_plan(["Step 1: ...", "Step 2: ..."], status="complete")
print(blackboard)
```

**Executor reads and updates:**
```python
print(blackboard.plan_text())    # read full plan
blackboard.mark_done(1)          # mark step complete
blackboard.discovered_apis       # see what planner already found
```

**main.py reads:**
```python
world.execute("print(blackboard.plan_status)")   # "complete" | "incomplete" | ""
world.execute("print(blackboard.plan_text())")   # numbered plan string
```

---

## Key prompt rules (both templates enforce these)

1. **ONE-STEP RULE**: One code snippet per response. Wait for output before the next.
2. **API DISCOVERY RULE**: Never guess an API name. If "No API named X found" — STOP and call `show_api_descriptions` to get the real list.
3. **CREDENTIALS RULE**: Never hardcode passwords. Always:
   ```python
   passwords = apis.supervisor.show_account_passwords()
   creds = find_one(passwords, 'account_name', 'spotify')
   result = apis.spotify.login(username="<supervisor_email>", password=creds['password'])
   access_token = result['access_token']
   ```
4. **filter_apis rule** (planner only): After `show_api_descriptions`, always filter before printing. Never print a raw list over ~10 entries.
5. **Blackboard rule** (planner): After filtering, call `blackboard.add_apis()`. Final step must call `blackboard.set_plan()`.

---

## Known issues / things to watch

- **Planner may run business logic code** in round 2 if fed poor context. The blackboard mitigates this since the planner writes structured data, not prose.
- **`world.task_completed()` ≠ correct answer** — it only checks that `complete_task()` was called. Always use `world.evaluate()` for real correctness. Now done after every `task_completed()` check.
- **`LLM_MAX_TOKENS = 800`** — raised from 400 to prevent truncation mid-`set_plan()`.
- **System time warning** (`SSL verification`) appears every call — harmless, the Ollama server has a self-signed cert and `verify=False` is set.
- **`run_log.html`** is overwritten on each run. Open with `explorer.exe run_log.html` from WSL.
- `main.py` currently runs `task_ids[0:1]` (one task at a time) for debugging — change to `[0:5]` or larger for batch runs.

---

## What we built this session (in order)

1. **Planner + Executor split** — replaced single `MinimalReactAgent` with two-phase pipeline
2. **PLAN_COMPLETE / PLAN_INCOMPLETE signals** — planner signals readiness; feedback loop feeds executor output back to planner if incomplete
3. **Fixed planner prose output** — rewrote planner prompt framing to match executor's Python-REPL style
4. **`filter_apis` tool** — prevents API list flooding; planner must filter before printing
5. **Comment-normalized stuck detection** — `_normalize_code()` strips comments so `is_stuck()` catches repeated logic even when comments differ
6. **Consecutive errors guard in feedback loop** — same 3-error abort as Phase 2
7. **Explicit credentials pattern** — both prompts show exact `show_account_passwords` → `find_one` → `login` pattern
8. **plan_context sanitization** — discard plan if it contains error tracebacks
9. **Strengthened API DISCOVERY RULE** — added explicit recovery instruction for "No API named X"
10. **Blackboard shared memory** — replaced string-based `# PLAN_COMPLETE` markers with a structured Python object; planner writes, executor reads, main.py polls
11. **Planner keyword derivation rule** (`prompts.py`) — added strict rule + example comment forcing the planner to derive `filter_apis` keywords from the task description rather than copying the example. *Root cause:* planner used `['playlist', 'login']` for a "find most-liked song" task, missing all song-level APIs. *Result: superseded by item 14.*
12. **`LLM_MAX_TOKENS` raised 400 → 800** (`config.py`) — 400 tokens truncated `set_plan([...])` mid-list, causing `SyntaxError: '[' was never closed` in both planning attempts. *Result: pending re-run.*
13. **Auto-inject real API list on "No API named X" errors** (`main.py`) — when the executor hits `No API named 'X' found in the Y app`, `main.py` immediately calls `show_api_descriptions(app_name=Y)` and injects the real list as the next input, resetting `consecutive_errors`. Prevents the model from guessing the same wrong name 15 times. *Result: pending re-run.*
14. **Planner→Executor redesign** (`prompts.py`, `agent.py`, `main.py`, `config.py`) — Planner now writes a plain-English high-level strategy only (no API discovery, no code). Executor does all API discovery on its own. When execution fails, `main.py` collects the last error + completed steps and feeds them back to the planner as structured feedback; the planner writes a corrected plan. Planner prompt includes 4 common-error recovery patterns. Removed the "feedback executor" phase entirely. `MAX_PLAN_STEPS` raised to 7. *Result: pending re-run.*
15. **Planner reasoning process** (`prompts.py`) — Example rewritten to show 6-step reasoning in comments (apps involved → final answer → data needed → auth requirements → data shape concerns → step order) before calling `set_plan()`. Strict rules now require the planner to answer all 6 questions in comments before submitting. *Result: pending re-run.*
16. **Auto-inject moved to output check** (`main.py`) — `world.execute()` returns errors as strings, not exceptions. Moved "No API named X" detection from the `except` block to the `output` string check so it actually fires. *Root cause:* auto-inject never ran in practice. *Result: pending re-run.*
17. **`blackboard.done_steps` → `completed_steps`** (`main.py`) — AttributeError was masking all planner feedback (planner got a traceback instead of completed steps). Fixed to use the real attribute name. *Result: pending re-run.*
18. **Smarter planner feedback on API errors** (`main.py`) — When `last_error` contains "No API named X found in Y app", planner feedback now names the specific wrong API and instructs the planner to add a `show_api_descriptions('Y')` step at the point of failure. Previously the planner got "executor got stuck" and just rewrote the same plan. *Result: pending re-run.*
19. **Mandatory tool usage rules** (`prompts.py`) — Executor prompt now has explicit MANDATORY TOOL RULES: `sort_results` for extremes, `filter_results` for filtering, `find_one` for lookups, `paginate_all` for paginated APIs. *Result: pending re-run.*

---

## How to run

```bash
cd /home/omer2/LARA_project
source .venv/bin/activate
python main.py
# View live log:
explorer.exe run_log.html
```
