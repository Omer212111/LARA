# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**LARA** is a multi-agent system (MAS v2.2) that solves tasks on the **AppWorld benchmark** — a simulated environment of ~11 apps (Spotify, Gmail, Amazon, Venmo, Splitwise, Todoist, SimpleNote, Phone, FileSystem, Supervisor, API Docs). The agent solves tasks by writing Python that calls AppWorld's app APIs through a sandboxed REPL (`env.execute(code)`).

## Commands

```bash
# Single task (debugging) — runs train task index 0
python main.py

# Benchmark — N tasks from a dataset
python benchmark.py --n 20 --dataset train

# Benchmark only tasks that touch one app (filters by evaluation.py marker, instant)
python benchmark.py --app file_system --n 10

# Official AppWorld scoring after a benchmark run
appworld evaluate lara_langchain_agent train
```

`load_dotenv()` runs at startup; `OPENAI_API_KEY` must be in `.env`. There is no test suite, lint config, or build step — correctness is measured only by `world.evaluate()`.

## Architecture

A LangGraph `StateGraph` (built in [planning_loop.py](planning_loop.py)) routes a single `AgentState` ([state.py](state.py)) between four nodes:

```
Supervisor ──> Explorer ──> Supervisor ──> Executor ──> Reviewer ──> Executor
   (routing)   (plan)                      (run code)   (diagnose)   (retry)
```

- **Supervisor** ([supervisor.py](supervisor.py)) — routing only; picks Explorer / Executor / FINISH. Enforces hard limits.
- **Explorer** ([explorer.py](explorer.py)) — GPT-4.1-nano using OpenAI **native function calling**. Discovers real API names/schemas and writes a numbered plain-English plan. No code execution.
- **Executor** — `executor_node` is `AppOrchestrator.node`, see below.
- **Reviewer** ([reviewer.py](reviewer.py)) — GPT-4.1-nano. Runs only when `complete_task()` was called but the answer was **wrong**; produces a structured diagnosis the Executor consumes on retry. The `Reviewer → Executor` edge bypasses the Supervisor, so `_after_executor` in [planning_loop.py](planning_loop.py) must itself check `MAX_EXECUTOR_RUNS` or the limit never fires on wrong-answer paths.

### Executor = AppOrchestrator + per-app specialists

This is the key abstraction. [app_agents/base.py](app_agents/base.py) defines `AppOrchestrator`, the single LangGraph node that runs a ReAct loop. **Per ReAct step** it:
1. Parses the Explorer's numbered plan, mapping each step to a specialist whose `app_name` appears in that step's text.
2. Swaps in that specialist's system prompt for the LLM call (falls back to generic `REACT_EXECUTOR_SYSTEM` for multi-app glue steps).

Specialists ([app_agents/](app_agents/)) are thin `BaseAppExecutor` subclasses that only set `app_name` + `app_system_prompt` — a large, hand-tuned block of exact API names, field names, calling conventions, and task patterns. They are registered in the `_orchestrator` dict in [executor.py](executor.py). Currently: spotify, gmail, amazon, file_system.

**When editing a specialist prompt, verify every API/field name against `data/api_docs/standard/<app>.json`** — these JSON files are the ground truth. Wrong names crash the sandbox.

### Bootstrap helpers

[executor_helpers.py](executor_helpers.py) defines `BOOTSTRAP_CODE`, prepended to **every** code block the Executor runs. It provides in-scope helpers — `login_to_app`, `call_api`, `fetch_all_pages`, `filter_results`, `find_contact`, etc. Specialist prompts should instruct the model to use these (e.g. `call_api('gmail', 'show_thread', token, ...)`).

## Critical correctness rules

- **`world.task_completed()` ≠ correct.** `task_completed()` only checks that `complete_task()` was called; `world.evaluate()` runs the real test suite. `task_signal_complete` in state is `True` only when `evaluate_task()` (in [tools.py](tools.py)) reports `correct == True`.
- **ACTION tasks** (place order, send, create, delete, move…) must call `apis.supervisor.complete_task(answer=None)` — never an id, count, or `'done'`. VALUE tasks pass the computed value.
- The sandbox **blocks `exit()` / `sys.exit()`** (use a `failed = True` flag) and **forbids `open()` / `os` / `shutil`** — all I/O goes through app APIs.
- The sandbox clock is **not today's date** — never filter by `datetime.now()` (e.g. payment-card expiry).

## Configuration & dependencies

All runtime constants live in [config.py](config.py): `MAX_ITERATIONS`, `MAX_EXECUTOR_RUNS`, `MAX_REACT_STEPS`, model names, Ollama URL/auth. Switch the Executor LLM with the single line `EXECUTOR_BACKEND` (`"openai"` or `"ollama"`).

Dependency versions are pinned and fragile — appworld/sqlmodel need **pydantic <2**, and langgraph/langchain-core must stay in sync. **Never `pip install langgraph --upgrade`** (pulls langchain-core 1.x and breaks everything).

[logger.py](logger.py) writes `run_log.html` (auto-refreshes every 2s) — open it to watch a live run.

## Prompt surfaces — two files, two owners

The former single `prompts.py` was split so the Explorer and Executor prompt
surfaces stop colliding in merges. Nothing is shared between them:

| file | surfaces | consumed by |
|---|---|---|
| [prompts_explorer.py](prompts_explorer.py) | `build_explorer_system`, `EXPLORER_TOOLS_OPENAI` | [explorer.py](explorer.py) |
| [prompts_executor.py](prompts_executor.py) | `REACT_EXECUTOR_SYSTEM`, `build_react_initial_message` | [app_agents/base.py](app_agents/base.py) |

Each file has exactly one importer. Edit the one belonging to the agent you are
changing; never reintroduce a shared `prompts.py`.

(The legacy `EXECUTOR_SYSTEM_TEMPLATE` — a pre-ReAct single-shot prompt with no
remaining importers — was dropped in the split.)

## Working in parallel: file ownership

Two tracks divide the codebase along its natural seam. They are nearly disjoint;
the rules below keep them that way.

**Track A — pipeline & orchestration**
`app_agents/base.py` (orchestrator, dispatch loop, guards) · `tools.py` ·
`planning_loop.py` · `reviewer.py` · `state.py` · `config.py` ·
`prompts_executor.py`

**Track B — knowledge, specialists & measurement**
`app_agents/<app>.py` (one file per specialist, no coupling between them) ·
`explorer.py` · `prompts_explorer.py` · `analysis/*`

### The frozen contract

`BaseAppExecutor` in [app_agents/base.py](app_agents/base.py) is the interface
every specialist inherits:

```python
class BaseAppExecutor:
    app_name: str = ""            # lowercase app key, e.g. "spotify"
    app_system_prompt: str = ""   # appended after REACT_EXECUTOR_SYSTEM
    def build_system_prompt(self) -> str: ...
```

**Do not change this class without agreeing with the other track first.** While it
holds, Track B never needs to open `base.py` — specialists are pure subclass
files, and Track A can rewrite the orchestrator freely.

### Sequencing constraint

The Reviewer retry path currently discards most of its own work (see
[analysis/CAPABILITY_STUDY_2026-07-20.md](analysis/CAPABILITY_STUDY_2026-07-20.md)):
58 fires, 1 rescue over 105 tasks, and 12 of 16 failures above difficulty 1.
Until that is fixed, **benchmark numbers understate real capability and cannot
distinguish an improvement from noise**. Fix it and re-baseline before either
track measures anything.
