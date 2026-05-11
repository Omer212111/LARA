# LARA Project — Session Context for New Chat

## What is this project?

**LARA** is an AI agent system that solves tasks on the **AppWorld benchmark** — a simulated environment of 11 apps (Spotify, Gmail, Amazon, Venmo, Splitwise, Todoist, simple_note, Phone, file_system, Supervisor, API Docs). The agent interacts with these apps by writing Python code that calls their REST-style APIs through a Python REPL.

**Active codebase:** `/home/omer2/LARA_project/LARA-MAS/LARA/` (MAS v2.3)
**Virtual environment:** `/home/omer2/LARA_project/.venv/`
**Platform:** WSL (Ubuntu on Windows)
**Last updated:** 2026-05-11

---

## LLM Backends

| Agent | Model | Endpoint |
|-------|-------|----------|
| Explorer | **GPT-4.1-nano** (OpenAI) | `api.openai.com` |
| Executor | **GPT-4.1-nano** (OpenAI) — switchable to Qwen | `api.openai.com` or `https://192.116.98.6/api/chat` |
| Supervisor | **qwen2.5-coder:latest** (Ollama) | `https://192.116.98.6/api/generate` |
| Reviewer | **qwen2.5-coder:latest** (Ollama) | `https://192.116.98.6/api/generate` |

**Backend abstraction:** `EXECUTOR_BACKEND` in `config.py` toggles the Executor between OpenAI (`"openai"`) and Ollama (`"ollama"`) with a single line. Currently set to `"openai"`.

OpenAI API key is stored in `LARA-MAS/LARA/.env` (gitignored).

---

## File Structure

| File | Role |
|------|------|
| `main.py` | Entry point: loads one task, runs `process_goal()`, calls `world.evaluate()` for real correctness |
| `benchmark.py` | Batch runner. Usage: `python benchmark.py [num_tasks] [start]` (e.g. `python benchmark.py 2 18` runs tasks 19-20) |
| `planning_loop.py` | LangGraph orchestrator: builds StateGraph with 4 nodes (Supervisor → Explorer → Executor → Reviewer) |
| `config.py` | Constants: `MAX_ITERATIONS=12`, `MAX_EXECUTOR_RUNS=2`, `MAX_REACT_STEPS=10`, `EXECUTOR_BACKEND`, model names, Ollama URLs/auth |
| `state.py` | `AgentState` TypedDict — all shared state fields |
| `llms.py` | LLM wrappers: `CustomOllamaLLM` (with retry), `OpenAILLM`, factory functions |
| `prompts.py` | All prompt strings: `build_explorer_system()`, `EXPLORER_TOOLS_OPENAI`, `REACT_EXECUTOR_SYSTEM`, `build_react_initial_message()` |
| `explorer.py` | Explorer agent (OpenAI native function calling), `_detect_apps()`, `_call_gpt_explorer()` |
| `executor.py` | **ReAct Executor agent**: `_llm_call()` dispatcher (openai/ollama), `executor_node()` runs ReAct loop |
| `executor_helpers.py` | `BOOTSTRAP_CODE` injected into every Executor code block: `login_to_app`, `call_api`, `fetch_all`, `filter_results`, `get_field`, `sort_by`, `find_contact` |
| `reviewer.py` | Reviewer agent: diagnoses wrong-answer attempts; produces ROOT_CAUSE / EVIDENCE / FIX_INSTRUCTION |
| `supervisor.py` | Supervisor agent: routing decisions between Explorer / Executor / Reviewer / FINISH |
| `tools.py` | LangChain `@tool` definitions + `evaluate_task()` helper that calls `world.evaluate()` |
| `logger.py` | Writes `run_log.html` (auto-refreshes every 5s) — open with `explorer.exe run_log.html` |
| `.env` | `OPENAI_API_KEY=...` (never commit) |

---

## Architecture: MAS v2.3 (Supervisor → Explorer → ReAct Executor → Reviewer)

```
process_goal(task)
  │
  ├─ StateGraph (LangGraph) with 4 nodes:
  │
  │   SUPERVISOR (Qwen) — routing decisions
  │     • Checks state: has_plan? task_done? last_error? executor_runs?
  │     • Routes to: Explorer | Executor | Reviewer | FINISH
  │     • Hard limits: MAX_ITERATIONS=12, MAX_EXECUTOR_RUNS=2
  │     • If Ollama returns "Error:..." → defaults to Executor (skips wasted Explorer run)
  │
  │   EXPLORER (GPT-4.1-nano) — discovery only, NO code execution
  │     • Uses OpenAI native function calling (NOT LangChain ReAct)
  │     • tool_choice="required" on round 0 → model MUST call at least one tool
  │     • Pre-injects explore_app_apis results for detected apps into system prompt
  │     • Tools: explore_app_apis, get_api_details
  │     • Hard cap of 9 total tool calls — after that, forced plan generation
  │     • Force-plan injects OUTPUT FORMAT reminder so the plan is always structured
  │     • Writes a plan with APP / REASONING (Scope, Metric, Ambiguities) / PLAN sections
  │     • On re-run: receives last_error / reviewer_diagnosis, refines the plan
  │
  │   EXECUTOR (GPT-4.1-nano via ReAct loop) — writes and runs Python code STEP BY STEP
  │     • System prompt: REACT_EXECUTOR_SYSTEM with helper functions, IMPORTANT FACTS, format rules
  │     • Loop up to MAX_REACT_STEPS=10 iterations:
  │         1. LLM writes Thought + small ```python``` code block
  │         2. Code runs in AppWorld REPL with BOOTSTRAP_CODE prepended
  │         3. Output fed back as Observation in next user message
  │         4. evaluate_task() checked after each step
  │     • Each code block is SELF-CONTAINED (re-login, re-fetch each step)
  │     • Calls apis.supervisor.complete_task(answer=...) when done
  │
  │   REVIEWER (Qwen) — diagnoses wrong answers
  │     • Triggered when complete_task() called but world.evaluate() failed
  │     • Outputs structured diagnosis: ROOT_CAUSE / EVIDENCE / EXPLANATION / FIX_INSTRUCTION
  │     • Diagnosis fed to Executor's next attempt via reviewer_diagnosis state field
  │
  └─ After each Executor run: evaluate_task() calls world.evaluate()
       task_signal_complete = True only if world.evaluate().success == True
```

### Key state fields (AgentState TypedDict)
- `messages` — conversation history
- `plan` — Explorer's latest plan text
- `findings` — dict `{attempt_N: result}` across Executor runs
- `last_error` — last Executor crash text (fed back to Explorer/Executor)
- `reviewer_diagnosis` — structured wrong-answer diagnosis from Reviewer
- `task_signal_complete` — True only if world.evaluate() passes
- `executor_runs` / `explorer_runs` / `iterations` — counters
- `last_code` / `last_eval_failure` — fed to Reviewer for diagnosis

---

## Critical correctness fix

**`world.task_completed()` ≠ correct answer.**
`task_completed()` only checks that `complete_task()` was called. `world.evaluate()` runs the actual AppWorld test suite.

All evaluation goes through `evaluate_task()` in `tools.py`:
```python
result = env.evaluate()
return {"correct": result.success, "pass_count": ..., "failures": ...}
```

`task_signal_complete` is set to `True` only when `evaluate_task()["correct"] == True`.

---

## Major fixes in current codebase

| Fix | File | Description |
|-----|------|-------------|
| **ReAct Executor** | `executor.py` | Replaced single-shot code generation with step-by-step Thought→Action→Observation loop |
| **Backend abstraction** | `config.py`, `executor.py` | `EXECUTOR_BACKEND="openai"` or `"ollama"` — single toggle |
| **Phone login fix** | `executor_helpers.py` | Phone app uses `phone_number` (not `email`) as username |
| **simple_note app name** | `prompts.py` | App directory is `simple_note` (with underscore), NOT `simplenote` |
| **file_system create_file** | `prompts.py` | Correct API name is `create_file(file_path=..., content=...)` |
| **like_count semantics** | `prompts.py` | `like_count` = global popularity; `show_liked_songs`/`liked=True` = user personally liked |
| **fetch_all helper** | `executor_helpers.py` | `fetch_all(app, api, token)` — fetches all pages automatically. Fixes silent truncation where `call_api` returned only first 5 items (e.g. 5/8 playlists) |
| **Explorer prompt reduction** | `prompts.py` | Reduced from 169 → 86 lines (49%). Preserved all load-bearing rules. Added CONTAINER vs ITEM APIs rule and two-level AGGREGATION SCOPE reasoning |
| **Explorer tool-call cap** | `explorer.py` | Hard cap of 9 total tool calls + forced-plan reminder injected on cap/repeat. Prevents infinite loops where model calls A→B→A→B without writing a plan |
| **KEYWORD DISCOVERY rule** | `prompts.py` | Explorer must search API names for unknown metric words instead of guessing field names from general knowledge |
| **show_recommendations pattern** | `prompts.py` | "most/least recommended artist" = count artist appearances across all pages of show_recommendations (no score field exists) |
| **AGGREGATION SCOPE two-level** | `prompts.py` | Explorer identifies WHAT noun the metric modifies: metric on item → iterate all containers; metric on container → filter container first, then items within |
| **CONTAINER vs ITEM APIs** | `prompts.py` | Item-level fields (play_count, rating) live on show_song/show_product, NOT on show_album/show_playlist. Explorer must call get_api_details on the item API |
| **BOOTSTRAP_CODE helpers** | `executor_helpers.py` | Auto-injected: `login_to_app`, `call_api`, `fetch_all`, `filter_results`, `get_field`, `sort_by`, `find_contact` |
| `exit()` forbidden | `prompts.py` | AppWorld blocks `exit()`/`sys.exit()` — must use `failed = True` flag pattern |
| Ollama retry | `llms.py` | 1 retry + 10s sleep on connection failure |

---

## Design principle (IMPORTANT — apply in every future fix)

**Every prompt or code fix should solve a general problem, not just patch the specific failing task.**

Before implementing a fix, ask: *"What is the general failure class this represents? Could it occur in other tasks too?"*

Examples from this session:
- Task 1 failed due to pagination → fixed with `fetch_all` helper that benefits ALL list API calls across ALL tasks
- Task 20 failed because Explorer guessed a field → fixed with KEYWORD DISCOVERY rule that applies to ANY unknown metric word
- Task 2 failed because Explorer looked at container API for item fields → fixed with CONTAINER vs ITEM APIs rule that applies to any nested data structure
- Explorer looped on tool calls → fixed with a hard cap + structured reminder that prevents loops on ANY task

A fix that only adds a task-specific example is a plaster. A fix that adds a general rule is a real improvement.

---

## Dependency notes (important)

These packages must stay in sync:

| Package | Required version | Why |
|---------|-----------------|-----|
| pydantic | `<2.0.0` (1.10.x) | appworld + sqlmodel require pydantic v1 |
| langchain | `0.1.20` | compatible with langchain-core 0.2.x |
| langchain-core | `0.2.43` | required by langgraph 0.2.76 |
| langgraph | `0.2.76` | 0.0.69 has `__start__` KeyError; 1.x requires langchain-core 1.x |
| openai | latest | for GPT-4.1-nano Explorer/Executor |

**Never run `pip install langgraph --upgrade`** — it pulls langchain-core 1.x which breaks everything.

---

## Benchmark results — 20-task train split

| Run | Setup | Score |
|-----|-------|-------|
| Run 1 | Qwen Explorer (baseline) | 2/20 (10%) |
| Run 2 | GPT Explorer + 1 task tested | — |
| Run 3 | GPT Explorer + updated prompt | 2/20 (10%) |
| Run 4 | OpenAI native function calling + pre-injection (single-shot Executor) | 1/20 (5%) |
| Run 5 | First ReAct Executor (no targeted fixes) | 3/20 (15%) |
| Run 6 | Aggressive "ALWAYS code block" prompt | **0/20 (0%)** ← regression |
| Run 7 | Careful prompts + phone login fix + backend abstraction | 3/20 (15%) |
| Run 8 | Explorer prompt optimization + fetch_all + general rules (pending) | TBD |

### Run 7 — failure classes (still open before Run 8)
1. **Spotify rating tasks (4, 5, 6)** — wrong song_ids for review update vs add
2. **"complete_task() never called" (7, 10, 13)** — model writes answer in prose, no code block
3. **Phone SMS (14, 15)** — login works but `send_text_message` not invoked correctly
4. **Venmo cross-app filter (16, 17, 18)** — "after_threshold" filter wrong
5. **file_system content shape (11, 12)** — CSV writes succeed but song-title-to-artist mapping wrong
6. **Task 1 scope** — fixed in this session (pagination + AGGREGATION SCOPE)
7. **Task 20 metric** — fixed in this session (KEYWORD DISCOVERY + show_recommendations pattern)

### Changes made in this session (post Run 7, pre Run 8)
- Explorer prompt: 169 → 86 lines, all critical logic preserved
- Added `fetch_all()` helper to BOOTSTRAP_CODE (fixes all pagination-related failures)
- Added KEYWORD DISCOVERY rule (fixes unknown metric words across all tasks)
- Added `show_recommendations` pattern (fixes task 20 and similar)
- Added CONTAINER vs ITEM APIs rule (fixes field lookup on wrong API level)
- Added two-level AGGREGATION SCOPE reasoning (fixes metric-on-container vs metric-on-item ambiguity)
- Explorer tool-call hard cap (9) + forced-plan reminder (fixes infinite tool-call loops)
- Validated tasks 1, 2, 3, 19, 20 all correct after fixes

---

## How to run

```bash
cd /home/omer2/LARA_project/LARA-MAS/LARA
source ../../.venv/bin/activate

# Single task (debugging):
python main.py

# Full benchmark (20 tasks):
python benchmark.py

# Subset — e.g. only tasks 19-20:
python benchmark.py 2 18

# Single task by index (0-based):
python benchmark.py 1 0   # task 1
python benchmark.py 1 19  # task 20

# Switch executor model:
# edit config.py:  EXECUTOR_BACKEND = "openai"  ↔  "ollama"

# View live log (Windows):
explorer.exe run_log.html

# Official AppWorld evaluation (after benchmark):
appworld evaluate lara_langchain_agent train
```

---

## Documentation

`/home/omer2/LARA_project/LARA - Documentation.docx` — full per-run experiment log with per-task tables and root-cause analysis. Updated after every run.
