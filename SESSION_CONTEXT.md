# LARA Project — Session Context for New Chat

## What is this project?

**LARA** is an AI agent system that solves tasks on the **AppWorld benchmark** — a simulated environment of 11 apps (Spotify, Gmail, Amazon, Venmo, Splitwise, Todoist, SimpleNote, Phone, FileSystem, Supervisor, API Docs). The agent interacts with these apps by writing Python code that calls their REST-style APIs through a Python REPL.

**Active codebase:** `/home/omer2/LARA_project/LARA-MAS/LARA/` (MAS v2.1)
**Virtual environment:** `/home/omer2/LARA_project/.venv/`
**Platform:** WSL (Ubuntu on Windows)

---

## LLM Backends

| Agent | Model | Endpoint |
|-------|-------|----------|
| Explorer | **GPT-4.1-nano** (OpenAI) | `api.openai.com` |
| Executor | **qwen2.5-coder:latest** (Ollama) | `https://192.116.98.6/api/generate` |
| Supervisor | **qwen2.5-coder:latest** (Ollama) | `https://192.116.98.6/api/generate` |

OpenAI API key is stored in `LARA-MAS/LARA/.env` (gitignored).

---

## File Structure (refactored into 7 modules — previous monolithic planning_loop.py split)

| File | Role |
|------|------|
| `main.py` | Entry point: loads one task, runs `process_goal()`, calls `world.evaluate()` for real correctness |
| `benchmark.py` | Batch runner: runs N tasks, uses `world.evaluate()` per task, prints summary table |
| `planning_loop.py` | Thin orchestrator: builds LangGraph StateGraph, imports nodes from other modules |
| `config.py` | Runtime constants: `MAX_ITERATIONS=12`, `MAX_EXECUTOR_RUNS=5`, model names, Ollama URL/auth |
| `state.py` | `AgentState` TypedDict — all shared state fields |
| `llms.py` | LLM wrappers: `CustomOllamaLLM` (with 1-retry on timeout), `OpenAILLM`, `get_llm()` factory |
| `prompts.py` | All prompt strings: `EXPLORER_TOOLS_OPENAI` (tool schemas), `EXECUTOR_SYSTEM_TEMPLATE` |
| `explorer.py` | Explorer agent: `_detect_apps()`, `_call_gpt_explorer()`, `explorer_node()` |
| `executor.py` | Executor agent: `_extract_code_block()`, `executor_node()` |
| `supervisor.py` | Supervisor agent: `_decide_next_from_text()`, `supervisor_node()` |
| `tools.py` | LangChain `@tool` definitions + `evaluate_task()` helper that calls `world.evaluate()` |
| `logger.py` | Writes `run_log.html` — auto-refreshes every 2s, open with `explorer.exe run_log.html` |
| `.env` | `OPENAI_API_KEY=...` (never commit) |

---

## Architecture: MAS v2.1 (Explorer → Supervisor → Executor)

```
process_goal(task)
  │
  ├─ StateGraph (LangGraph) with 3 nodes:
  │
  │   SUPERVISOR (Qwen) — routing decisions
  │     • Checks state: has_plan? task_done? last_error? iterations?
  │     • Routes to: Explorer | Executor | FINISH
  │     • Hard limits: MAX_ITERATIONS=12, MAX_EXECUTOR_RUNS=5
  │     • If executor fails 3+ times → sends back to Explorer
  │     • If Ollama returns "Error:..." → defaults to Executor (skips wasted Explorer run)
  │
  │   EXPLORER (GPT-4.1-nano) — discovery only, no code execution
  │     • Uses OpenAI native function calling (NOT LangChain ReAct)
  │     • tool_choice="required" on round 0 → model MUST call at least one tool
  │     • Pre-injects explore_app_apis results for detected apps into system prompt
  │     • Tools: explore_app_apis, get_api_details
  │     • Writes a numbered plain-English plan (no code, verified API names only)
  │     • On re-run: receives last_error from Executor, refines the plan
  │
  │   EXECUTOR (Qwen) — writes and runs Python code
  │     • Receives plan from Explorer
  │     • Calls execute_python_code tool which runs code in AppWorld REPL
  │     • Stores results in findings dict across attempts
  │     • Skips evaluate_task() when code has execution error (complete_task never called)
  │     • Calls apis.supervisor.complete_task(answer=...) when done
  │
  └─ After each successful Executor run: evaluate_task() calls world.evaluate()
       task_signal_complete = True only if world.evaluate().success == True
```

### Key state fields (AgentState TypedDict)
- `messages` — full conversation history
- `plan` — Explorer's latest plan text
- `findings` — dict of `{attempt_N: result}` across Executor runs
- `last_error` — last Executor error, fed back to Explorer on re-plan
- `task_signal_complete` — True only if world.evaluate() passes (NOT just complete_task() called)
- `executor_runs` / `explorer_runs` / `iterations` — counters for limits

---

## Critical correctness fix

**`world.task_completed()` ≠ correct answer.**
`task_completed()` only checks that `complete_task()` was called. `world.evaluate()` runs the actual AppWorld test suite.

All evaluation is now done via `evaluate_task()` in `tools.py`:
```python
result = env.evaluate()
return {"correct": result.success, "pass_count": result.pass_count, ...}
```

`task_signal_complete` in the state is only set to `True` when `evaluate_task()["correct"] == True`.

---

## Code fixes applied (all in current codebase)

| Fix | File | Description |
|-----|------|-------------|
| `top[1]` bug | `prompts.py` | Working example used `top[0]` for title but tuple is `(likes, title)` — `top[0]` is like_count |
| `exit()` forbidden | `prompts.py` | Added Rule 9: AppWorld blocks `exit()`, `sys.exit()`. Must use `failed = True` flag pattern |
| `_detect_apps` keywords | `explorer.py` | Removed generic keywords ("buy", "split", "message") that caused false positives; use specific phrases |
| Ollama retry | `llms.py` | 1 retry + 10s sleep on connection failure before returning `"Error: ..."` |
| Supervisor error guard | `supervisor.py` | If Ollama returns `"Error:..."` string, defaults to Executor instead of Explorer |
| Evaluate skip on error | `executor.py` | Skips `evaluate_task()` when code has Traceback (complete_task never ran) |

---

## Dependency notes (important)

These packages must stay in sync — any upgrade can break appworld or LangGraph:

| Package | Required version | Why |
|---------|-----------------|-----|
| pydantic | `<2.0.0` (1.10.x) | appworld + sqlmodel require pydantic v1 |
| langchain | `0.1.20` | compatible with langchain-core 0.2.x |
| langchain-core | `0.2.43` | required by langgraph 0.2.76 |
| langgraph | `0.2.76` | 0.0.69 has `__start__` KeyError bug; 1.x requires langchain-core 1.x |
| openai | latest | for GPT-4.1-nano Explorer |

**Never run `pip install langgraph --upgrade`** — it will pull langchain-core 1.x which breaks everything.

---

## Benchmark results

### Run 1 — Qwen Explorer (baseline, 20 tasks)
- **2/20 correct (10%)**
- Correct: 82e2fac_3, 287e338_2
- Top failure causes:
  1. Wrong/non-existent API names (8 tasks) — Explorer guessed APIs that don't exist
  2. Relationship lookup failures (5 tasks) — agent didn't know how to find roommates/coworkers from phone contacts
  3. Case-sensitive account name lookup (3 tasks) — `'Venmo'` instead of `'venmo'`
  4. File I/O forbidden in sandbox (3 tasks) — used `open()` instead of filesystem API
- ACTION tasks: 0/15 correct. VALUE tasks: 2/5 correct.
- 9/20 tasks never called `complete_task()` at all (stuck)

### Run 2 — GPT-4.1-nano Explorer (1 task tested: 82e2fac_1)
- API naming errors: **eliminated** — Explorer produced valid API names immediately
- Explorer still skipped tool calls entirely, went straight to Final Answer from memory
- Wrong data source: `show_liked_songs` instead of `show_playlist_library`

### Run 3 — GPT-4.1-nano Explorer + updated EXPLORER_SYSTEM prompt (20 tasks)
- Added MANDATORY DISCOVERY PROCESS rule and semantic warnings to prompt
- **2/20 correct (10%)** — same score, Explorer still skipped tool calls
- Confirmed: prompt rules insufficient; structural fix needed

### Run 4 — OpenAI native function calling + pre-injection (20 tasks) ← CURRENT
- **2/20 correct (10%)** — same score
- Explorer now calls tools reliably (structural fix worked)
- **Bottleneck confirmed: Qwen Executor**
  - Generates wrong parameter names despite correct Explorer plans
  - Uses `open()` instead of filesystem APIs
  - Uses `exit()` which is blocked in sandbox
  - Hallucinates API names for complex tasks (multi-app tasks like Venmo+Phone)
- Run time improved from ~1hr → ~14min (Ollama retry + evaluate skip on error)
- Regression: 287e338_2 was correct in Run 1, now failing (not yet investigated)

---

## Current bottleneck & next steps

**Root cause of 10% plateau:** Explorer plans are now correct. Qwen Executor fails to implement them correctly.

### Planned next work: Executor helper tools
Build specialized LangChain tools that the Executor can call to perform common operations reliably:
- Login helper (handles the credential pattern automatically)
- Common API call wrappers
- Data extraction helpers

### Other open items
- Investigate 287e338_2 regression (was correct in Run 1, now failing in Run 4)
- `last_eval` in AgentState — pass wrong-answer details (which tests failed) back to Explorer on re-plan
- Consider GPT-4.1-nano for Executor as well (if Ollama remains the bottleneck)

---

## How to run

```bash
cd /home/omer2/LARA_project/LARA-MAS/LARA
source ../../.venv/bin/activate

# Single task (for debugging):
python main.py

# Full benchmark (20 tasks):
python benchmark.py

# Official AppWorld evaluation (after benchmark):
appworld evaluate lara_langchain_agent lara_mas_run

# View live log:
explorer.exe run_log.html
```

### Custom dataset file for evaluate
`data/datasets/lara_mas_run.txt` — lists only the 20 tasks that were actually run.
Use this instead of `train` to avoid "from_db_home_path does not exist" errors on unrun tasks.
