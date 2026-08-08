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

## Prompt surfaces — two files, two owners (Explorer = Track B, Executor = Track C)

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

Three tracks, one per open problem. Each owns a disjoint file set; the rules
below keep them that way.

### The measured problem statement

From the 10 saved slices in `analysis/runs/*.results.json` (n=165, 2026-07-20):

| apps in task | n | correct | rate |
|---|---|---|---|
| 1 | 62 | 42 | 0.677 |
| 2 | 39 | 19 | 0.487 |
| 3 | 49 | 20 | 0.408 |
| 4 | 6 | 2 | 0.333 |
| 5 | 3 | 0 | **0.000** |
| 6 | 6 | 0 | **0.000** |

Reviewer over the same 165 tasks: **fired 75, rescued 1 (1.3%)**.

The degradation starts at 2 apps and is total at 5+ (0/9). These are not three
independent problems: **memory is the mechanism of the multi-app cliff** (a
6-app task fails because entities gathered in app A are gone by app D), and the
reviewer cannot write an actionable diagnosis without a record of what the
previous attempt actually did. Track A is therefore upstream of B and C.

**Track A — memory & cross-app state (problem: agent memory)**
`executor_helpers.py` (the ledger) · `app_agents/base.py` · `tools.py` ·
`state.py` · `config.py`

**Track B — multi-app orchestration (problem: 3+ app collapse)**
`explorer.py` · `prompts_explorer.py` · `app_agents/<app>.py` · `analysis/*`

**Track C — reviewer & retry (problem: reviewer never rescues)**
`reviewer.py` · `planning_loop.py` · `prompts_executor.py`

### base.py is single-owner

`app_agents/base.py` is the one file all three tracks have reason to touch (it
holds both the ledger-visibility block and the retry-context block). **Track A
owns it end-to-end.** B and C request changes rather than editing it; this is
what keeps a three-way merge from landing in the orchestrator loop.

### Sequencing

Track A ships first. Until cross-app state is captured, B and C are measuring
against a moving baseline — and the retry path still discards most of its own
work, so benchmark deltas cannot be distinguished from run-to-run noise
(see below).

### The frozen contract

`BaseAppExecutor` in [app_agents/base.py](app_agents/base.py) is the interface
every specialist inherits:

```python
class BaseAppExecutor:
    app_name: str = ""            # lowercase app key, e.g. "spotify"
    app_system_prompt: str = ""   # appended after REACT_EXECUTOR_SYSTEM
    def build_system_prompt(self) -> str: ...
```

**Do not change this class without agreeing with the other tracks first.** While
it holds, Track B never needs to open `base.py` — specialists are pure subclass
files, and Track A can rewrite the orchestrator freely.

### Per-track starting brief

**Track A — memory.** The ledger already exists in `executor_helpers.py`
(`remember_entity` / `recall_entity` / `all_entities` / `ledger_summary`) and
its visibility bug is fixed. The blocker is **adoption, not capability**:
measured 3/130 code blocks (2.3%) using any helper and **zero** calls to
`remember_entity`, even when the ledger was shown and prompted. Prompting has
been tried and failed. The lead candidate is **passive auto-capture** — populate
the ledger from inside `call_api` as responses come back, rather than asking the
model to write to it. `login_to_app` already does exactly this for tokens and is
the working proof of concept. Measure on a multi-app slice only after it lands.

**Track B — multi-app.** 0/9 at 5+ apps. Establish *why* before fixing: the
plausible causes are (a) step-budget exhaustion (`MAX_REACT_STEPS` in
`config.py` — a 6-app task may simply run out), (b) entities lost between apps
(that is Track A's fix, not B's), (c) plan quality degrading on long cross-app
chains. The diagnosis decides whose problem it is; do it first.

**Track C — reviewer.** 1 rescue / 75 fires. A retry-context change is already
implemented (grader assertions passed through verbatim + anti-repeat on the
previous answer). Its mechanism is verified — 11/11 retries received the
assertions — but it converted nothing on `splitwise-random15` (2/15, 0 rescues,
vs 1/15 baseline; both passing tasks passed on attempt 1, so the change was not
the cause). Two things that run has already established: the fix is **untested
on VALUE tasks** (splitwise is ACTION-shaped, so `previous_answer` was empty on
all 11 retries — a spotify/todoist slice is the fair test), and AppWorld's
failed assertions are **state assertions**, not value assertions ("assert model
changes match splitwise.Expense" names a table, not what was wrong), so
passthrough alone may never be enough — a diff of what the attempt actually
wrote probably is.

### Measurement constraint

Run-to-run variance at n=15-20 is large (the same task has gone 8/8 in 38s and
3/8 in 390s). **A single run is directional only; trust a log-verified mechanism
over a score.** Always attribute a flipped task to whether the changed code path
was even exercised — a "regression" has already turned out to be attempt-1
variance on untouched code. Baselines live in `analysis/runs/*.results.json`
with per-task `reviewer_fired` / `retry_noop` / `failed_asserts`; re-run the
same task IDs rather than resampling, and ask before spending a run (10-40 min,
real API cost).
