# LARA — a multi-agent coding agent for the AppWorld benchmark

LARA solves tasks in **AppWorld** by writing Python. Given an instruction like
*"pay each person in debt_list.csv via Venmo, or file a Splitwise expense if they
have no Venmo account"*, it discovers the right APIs, writes a plan, then writes
and runs code against those APIs until the task is done.

**Current held-out score: TGC 61.9 / SGC 50.0** on `test_normal`
(104/168 tasks, commit `3eb7770`).

---

## What is AppWorld?

[AppWorld](https://appworld.dev) (ACL 2024) is a benchmark of ~11 simulated apps —
Spotify, Gmail, Amazon, Venmo, Splitwise, Todoist, SimpleNote, Phone, FileSystem,
plus a Supervisor app (the user's own accounts and credentials) and API Docs.

Three things make it hard:

**It is a coding benchmark, not a tool-calling one.** The agent writes real Python
into a sandboxed REPL (`world.execute(code)`) — loops, conditionals, data wrangling
across API responses. There is no fixed tool schema to fill in.

**Grading is database-state based.** Passing means the world's database ends in the
right state, checked by unit tests — not that the agent claimed success. Calling
`complete_task()` proves nothing; `world.evaluate()` runs the real tests.

**Tasks span apps.** A single task may read a CSV from FileSystem, look up people in
Phone, pay via Venmo, and file the rest in Splitwise. Difficulty scales with that:
our score is 91.2 on difficulty-1 tasks and 42.9 on difficulty-3.

Two metrics matter:
- **TGC** (Task Goal Completion) — % of individual tasks solved.
- **SGC** (Scenario Goal Completion) — % of *scenarios* where every variant was
  solved. Stricter, and the one that punishes inconsistency.

---

## How LARA works

Four agents pass a single shared state object around a
[LangGraph](https://langchain-ai.github.io/langgraph/) `StateGraph`:

```
            ┌──────────────┐
            │  Supervisor  │  routing only: Explorer / Executor / FINISH
            └──────┬───────┘
        ┌──────────┴──────────┐
        ▼                     ▼
  ┌──────────┐          ┌──────────┐        ┌──────────┐
  │ Explorer │─────────▶│ Executor │───────▶│ Reviewer │
  └──────────┘   plan   └──────────┘  wrong └────┬─────┘
   reads API docs        ReAct loop:     answer  │ diagnosis
   writes numbered       write code,             │
   [app]-tagged plan     run, observe   ◀────────┘  (currently disabled)
```

**Supervisor** — pure routing. Picks the next agent and enforces the hard limits
(`MAX_ITERATIONS`, `MAX_EXECUTOR_RUNS`).

**Explorer** — discovery only, no code execution. Calls the API-docs tools to find
real endpoint and field names, then writes a numbered plan where every step is
tagged with its app:

```
1. [file_system] Read debt_list.csv and parse the rows.
   OUT: debts[] {name, email, amount, description}
2. [venmo] FOR EACH debts[]: search_users to find a Venmo account.
   IN:  debts[]
   OUT: debts[].venmo_id
3. [venmo] FOR EACH debts[] WHERE venmo_id != null: send the payment.
   OUT: debts[].paid, debts[].txn_id
```

The `[app]` tag drives specialist dispatch. `IN:`/`OUT:` declare data flow, so the
Executor is told which facts to record rather than inventing its own bookkeeping.

**Executor** — a ReAct loop. Each step it writes one small Python block, runs it in
the sandbox, reads the output, and decides what to do next. Crucially, it swaps in a
different system prompt per step depending on which app that plan step targets (see
*specialists* below).

**Reviewer** — diagnoses a wrong answer so the Executor can retry.
**Currently disabled** (`ENABLE_REVIEWER_RETRY=False`): measured over 165 tasks it
fired 75 times and rescued 1. Turning it off costs nothing measurable and saves a
full second attempt on ~45% of tasks.

---

## The file map

### The graph

| file | what it does |
|---|---|
| `planning_loop.py` | Builds the `StateGraph` and wires the four nodes together. `process_goal()` runs one task end to end. |
| `state.py` | `AgentState` — the single TypedDict passed between nodes (plan, findings, counters, verdicts). 15 fields. |
| `supervisor.py` | Routing decisions + hard limits. |
| `explorer.py` | Discovery agent. Keyword-detects which apps a task touches, pre-injects their API docs, then calls the LLM with function-calling tools. |
| `executor.py` | Thin entry point — `executor_node` is `AppOrchestrator.node`. Registers the specialist map. |
| `reviewer.py` | Wrong-answer diagnosis (disabled by default). |

### The Executor internals

| file | what it does |
|---|---|
| `app_agents/base.py` | **The heart of the system** (970 lines). `AppOrchestrator` runs the ReAct loop: parses the plan, routes each step to a specialist, injects the ledger view and declared schema, guards against premature `complete_task()`, evaluates. Also defines `BaseAppExecutor`, the frozen interface every specialist inherits. |
| `app_agents/<app>.py` | One specialist per app (amazon, api_docs, file_system, gmail, phone, simple_note, splitwise, spotify, todoist, venmo). Each sets only `app_name` and `app_system_prompt` — a hand-written block of exact API names, field names and calling conventions for that app. |
| `executor_helpers.py` | `BOOTSTRAP_CODE`, prepended to every code block the model runs. Provides `call_api`, `fetch_all_pages`, `filter_results`, `get_field`, `sort_by`, and the cross-app ledger (`remember_entity` / `recall_entity` / `all_entities`). |

### Prompts

| file | consumed by |
|---|---|
| `prompts_explorer.py` | `explorer.py` — `build_explorer_system()`, tool schemas |
| `prompts_executor.py` | `app_agents/base.py` — `REACT_EXECUTOR_SYSTEM`, `build_react_initial_message()` |

Deliberately two files with one importer each, so Explorer and Executor prompt work
never collides in a merge. **Do not reintroduce a shared `prompts.py`.**

### Support

| file | what it does |
|---|---|
| `tools.py` | The LangChain tools: `execute_python_code` (the main one), API-doc lookups, `evaluate_task()`. |
| `config.py` | All runtime constants — limits, model names, backend switch. |
| `logger.py` | Writes `run_log.html`, auto-refreshing every 2s. Open it to watch a run live. |
| `llms.py` | LLM wrappers (Ollama path, used by the Supervisor). |
| `benchmark.py` | Batch runner — `run_official_benchmark(n, dataset)`. |
| `main.py` | Single-task entry point for debugging. |
| `test_ledger.py` | Verifies `BOOTSTRAP_CODE` against a live sandbox. |

### Directories

| dir | contents |
|---|---|
| `app_agents/` | The orchestrator + 10 app specialists |
| `analysis/` | Measurement tooling: slice runners, run parsers, capability studies, the hardcode-compliance audit |
| `data/` | AppWorld's API docs and dataset task-id lists (symlink, read-only) |
| `experiments/outputs/` | Per-run outputs and evaluation reports (gitignored) |

---

## The cross-app ledger

Multi-app tasks are database joins: the CSV gives a name and amount, Venmo gives a
user id, Splitwise gives a group id, and no single app holds the whole row. Before
the ledger that table lived only as printed stdout, so the model re-derived it every
step and lost it entirely between attempts.

`executor_helpers.py` puts a dict in the sandbox namespace instead. The AppWorld
sandbox is **one long-lived IPython shell per task**, so it survives every
`execute()` — including exceptions and retries.

```python
remember_entity('Andrew', amount=42.50)          # from the CSV
remember_entity('Andrew', venmo_id=118)          # from Venmo
recall_entity('Andrew')['venmo_id']              # the join, as a lookup
```

Measured adoption on multi-app tasks: the model uses it in ~82% of attempts.

---

## Running it

```bash
# One task, for debugging
python main.py

# N tasks from a split
python benchmark.py --n 20 --dataset train

# Official scoring after a run
appworld evaluate lara_langchain_agent train
```

`OPENAI_API_KEY` must be in `.env`. There is no test suite or lint step —
correctness is measured only by `world.evaluate()`.

Watch a run live by opening `run_log.html` in a browser.

---

## Rules that constrain development

AppWorld splits its tasks into `train` / `dev` / `test_normal` / `test_challenge`
and restricts what you may learn from each.

**Test splits are single-use.** `test_normal` and `test_challenge` may be run only
to obtain an aggregate score. Opening per-task evaluation reports, doing error
analysis, or tuning a prompt against them is not allowed. All diagnosis happens on
train/dev.

**No hardcoded API calls.** The rules forbid "hardcod[ing] any API calls into their
agent's logic", naming as the example logging into apps and caching the tokens. They
explicitly permit telling the agent to do it *in the prompt*.

LARA complied with this on 2026-08-10: `login_to_app` and `find_contact` were
removed from `BOOTSTRAP_CODE` and replaced by prompt instructions telling the model
to define its own `login()`. Canned Amazon plans and an ACTION-task regex over the
task text were deleted outright — measurement showed they could only have been
written from a test split.

Verified by AST analysis: **zero `apis.*` calls in live code**; every remaining
mention sits inside a prompt string.

Removing the hardcode *improved* the score, 54.8 → 61.9.

See `analysis/HARDCODE-INVENTORY-2026-08-10.md` for the full audit and
`CLAUDE.md` for development conventions.

---

## Known limits

- **Difficulty-3 tasks score 42.9 TGC.** A task needing ~20 sequential correct API
  actions fails if any one is wrong; the failures are mostly partial completions,
  not total misses.
- **The Reviewer does not work.** 1 rescue in 75 fires. Disabled rather than fixed.
- **SGC lags TGC** (50.0 vs 61.9) — solving one variant of a scenario often does not
  mean solving all of them.
