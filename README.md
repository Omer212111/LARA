

# LARA — a multi-agent coding agent for AppWorld

** 1st place on the [AppWorld leaderboard](https://appworld.dev/leaderboard)** —
TGC 85.6 on the `test_challenge` split.

LARA solves [AppWorld](https://appworld.dev) tasks by **writing Python**. Given an
instruction like *"pay each person in debt_list.csv via Venmo, or file a Splitwise
expense if they have no Venmo account"*, it discovers the right APIs, writes a plan,
then writes and runs real code against those APIs until the world's database is in
the state the task asked for.

https://github.com/user-attachments/assets/d0790966-2f6c-40dd-8907-d411e012f1f4
---

## The problem

[AppWorld](https://appworld.dev) (ACL 2024) is a benchmark of ~11 simulated apps —
Spotify, Gmail, Amazon, Venmo, Splitwise, Todoist, SimpleNote, Phone, FileSystem,
plus a Supervisor app holding the user's own accounts and credentials.

Three properties make it genuinely hard, and each one shaped a piece of LARA's design:

**It is a coding benchmark, not a tool-calling one.** The agent writes Python into a
sandboxed REPL — loops, conditionals, data wrangling across API responses. There is
no fixed tool schema to fill in, so the model has to get both the *logic* and the
*exact API surface* right at the same time.

**Grading is database-state based.** Passing means the world's database ends in the
correct state, verified by unit tests. Claiming success proves nothing: an agent that
calls `complete_task()` after doing the wrong thing scores zero. This punishes
confident hallucination far more than hesitation.

**Tasks span multiple apps.** One task may read a CSV from FileSystem, look up people
in Phone, pay via Venmo, and file the remainder in Splitwise. The information needed
to finish is scattered across apps, and no single API response holds a whole row.

Two metrics are reported. **TGC** (Task Goal Completion) is the share of individual
tasks solved. **SGC** (Scenario Goal Completion) is the share of *scenarios* where
every variant was solved — much stricter, and the one that punishes inconsistency.

---

## Results

| agent | model | split | tasks | TGC | SGC |
|---|---|---|---|---|---|
| **LARA** | `claude-opus-4-7` | `test_normal` | 168 | **88.7** | **82.1** |
| **LARA** | `claude-opus-4-7` | `test_challenge` | 417 | **85.6** | **77.0** |

Held-out test splits, one Executor attempt per task, scored with the official
`appworld evaluate`. On `test_challenge` this places LARA **2nd of 24 entries**.

### Against the official baseline

AppWorld ships a reference agent — the minimal ReAct loop from its own prompt
template, with no planning stage, no per-app knowledge and no cross-app memory. Run
on `test_normal` under identical conditions (one attempt per task, 16 steps), it is
the starting point LARA was built from:

| agent | model | TGC | SGC | d1 | d2 | d3 |
|---|---|---|---|---|---|---|
| official baseline | `gpt-4.1-mini` | 23.2 | 7.1 | 47.4 | 18.8 | 4.8 |
| official baseline | `claude-opus-4-7` | 54.8 | 46.4 | 87.7 | 52.1 | 27.0 |
| LARA | `gpt-4.1-mini` | 61.9 | 50.0 | — | — | — |
| **LARA** | `claude-opus-4-7` | **88.7** | **82.1** | 98.2 | 89.6 | 79.4 |

Each row pairs an agent with the model that produced it, so the two contributions can
be read separately. **With the model held fixed, the architecture is worth:**

| model | baseline → LARA (TGC) | ratio |
|---|---|---|
| `gpt-4.1-mini` | 23.2 → 61.9 | 2.7× |
| `claude-opus-4-7` | 54.8 → 88.7 | 1.6× |

The architecture helps at both tiers, and helps *more* where the model is weaker —
the stronger model already knows enough API shapes to recover some of what the
Explorer supplies. But it does not become redundant: even on `claude-opus-4-7` the
scaffold is worth 33.9 TGC points, and the SGC gap is wider still (46.4 → 82.1).

The difficulty breakdown is where the scaffold earns most. On difficulty-3 tasks the
`claude-opus-4-7` baseline manages 27.0 TGC against LARA's 79.4, and the
`gpt-4.1-mini` baseline collapses to 4.8 TGC and **0.0 SGC** — never once completing
a full scenario.

70% of the `gpt-4.1-mini` baseline's failures (91 of 129) are step-budget exhaustion
without ever calling `complete_task()`: it spends its budget discovering which APIs
exist. That single failure mode is what the Explorer stage exists to remove.

### Architecture versus model

Because the method is identical across both runs, this pair separates the two
contributions:

| agent | model | `test_normal` TGC | `test_challenge` TGC |
|---|---|---|---|
| LARA | `claude-opus-4-7` | 88.7 | 85.6 |
| LARA | `gpt-4.1-mini` | 61.9 | 37.6 |
| official baseline | `claude-opus-4-7` | 54.8 | — |
| official baseline | `gpt-4.1-mini` | 23.2 | — |

Read down the column and the model is worth 26.8 TGC points (61.9 → 88.7 with LARA);
read across the agent rows and the architecture is worth 33.9 (54.8 → 88.7 on
`claude-opus-4-7`). Neither alone reaches the submitted score. The model gap is widest
on `test_challenge`, where tasks are longest and a single wrong API guess ends the run.

---

## How LARA works



Four agents pass one shared state object around a
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
   [app]-tagged plan     run, observe   ◀────────┘  (disabled — see below)
```

### 1. Separate discovery from execution

The Explorer never runs code. Its only job is to read the API docs and find the
**real** endpoint and field names, then write a numbered plan where every step is
tagged with the app it belongs to:

```
1. [file_system] Read debt_list.csv and parse the rows.
   OUT: debts[] {name, email, amount, description}
2. [venmo] FOR EACH debts[]: search_users to find a Venmo account.
   IN:  debts[]
   OUT: debts[].venmo_id
3. [venmo] FOR EACH debts[] WHERE venmo_id != null: send the payment.
   OUT: debts[].paid, debts[].txn_id
```

This split exists because the dominant failure mode of a single-agent loop is
*inventing* an endpoint that sounds plausible and burning the run on it. Forcing a
docs-reading pass before any code is written removes most of that class.

The `IN:`/`OUT:` annotations declare data flow explicitly, so the Executor is told
which facts to carry forward instead of inventing its own bookkeeping.

### 2. Swap the prompt per app, not per task

The `[app]` tag drives **specialist dispatch**. The Executor runs a ReAct loop —
write one small code block, run it, read the output, decide the next step — but at
each step it swaps in a different system prompt depending on which app that step
targets.

Each of the 10 specialists (`app_agents/<app>.py`) contributes only an `app_name` and
an `app_system_prompt`: a hand-written block of that app's exact API names, field
names, and calling conventions. The model sees Venmo's conventions while working on a
Venmo step, and Splitwise's on the next — instead of one prompt trying to hold all 11
apps at once.

### 3. Give cross-app joins somewhere to live

Multi-app tasks are database joins. The CSV gives a name and an amount, Venmo gives a
user id, Splitwise gives a group id — and no single app holds the whole row.

Without somewhere to put it, that table exists only as printed stdout, so the model
re-derives it at every step and loses it entirely between attempts. LARA puts a dict
in the sandbox namespace instead. The AppWorld sandbox is one long-lived IPython shell
per task, so it survives every `execute()` — including exceptions:

```python
remember_entity('Andrew', amount=42.50)          # from the CSV
remember_entity('Andrew', venmo_id=118)          # from Venmo
recall_entity('Andrew')['venmo_id']              # the join, as a lookup
```

Measured adoption on multi-app tasks: the model uses it in ~82% of attempts.

### 4. Cut what does not pay for itself

The Reviewer diagnoses a wrong answer so the Executor can retry. It is **disabled**.

Measured over 165 tasks, it fired 75 times and rescued 1. A retry costs a Reviewer
call plus a full second Executor attempt — roughly 45% more compute for a 1.3%
conversion rate. The leaderboard runs use exactly **one Executor attempt per task**
(`MAX_EXECUTOR_RUNS = 1`, `ENABLE_REVIEWER_RETRY = False`).

The code is kept, and the measurement that closed it is recorded in
[`config.py`](LARA-sub_agents/LARA/config.py), so the decision can be revisited if a
retry mechanism ever demonstrates it converts on train/dev.

---

## Reproducing the leaderboard run

`config.py` defaults to `gpt-4.1-mini`. The leaderboard run selected
`claude-opus-4-7` at run time through environment overrides rather than by editing
the defaults:

```bash
export OPENAI_BASE_URL=<litellm-gateway-url>   # any OpenAI-compatible endpoint
export OPENAI_API_KEY=<gateway-key>
export EXECUTOR_MODEL=claude-opus-4-7
export EXPLORER_MODEL=claude-opus-4-7

cd LARA-sub_agents/LARA
python run_leaderboard.py test_normal    lara_test_normal
python run_leaderboard.py test_challenge lara_test_challenge
```

Scoring is the stock AppWorld command:

```bash
appworld evaluate lara_test_normal    test_normal
appworld evaluate lara_test_challenge test_challenge
```

Without the overrides the same commands run on `gpt-4.1-mini` and reproduce the
61.9 / 37.6 result instead. Both splits were run back to back through the same
entrypoint with no code changes between them, scored with `appworld` 0.1.3.post1.

---

## Where the code is

Everything lives under **[`LARA-sub_agents/LARA/`](LARA-sub_agents/LARA/)**.

**Start here:** [`LARA-sub_agents/LARA/README.md`](LARA-sub_agents/LARA/README.md) —
the full file map, the state object, and what every module does.

| path | what it is |
|---|---|
| [`planning_loop.py`](LARA-sub_agents/LARA/planning_loop.py) | The LangGraph state machine wiring the four agents |
| [`explorer.py`](LARA-sub_agents/LARA/explorer.py) | Discovery agent — reads API docs, writes the plan |
| [`app_agents/base.py`](LARA-sub_agents/LARA/app_agents/base.py) | The ReAct executor loop and per-app specialist dispatch |
| [`app_agents/`](LARA-sub_agents/LARA/app_agents/) | One specialist per app (spotify, venmo, gmail, …) |
| [`executor_helpers.py`](LARA-sub_agents/LARA/executor_helpers.py) | The cross-app ledger and helpers injected into every code block |
| [`config.py`](LARA-sub_agents/LARA/config.py) | Runtime limits, model selection, retry switches |
| [`run_leaderboard.py`](LARA-sub_agents/LARA/run_leaderboard.py) | Entrypoint used for the held-out leaderboard runs |
| [`analysis/`](LARA-sub_agents/LARA/analysis/) | Measurement tooling and the hardcode-compliance audit |

---

## Compliance with the AppWorld rules

AppWorld forbids hardcoding API calls into the agent's own logic, and forbids
learning anything from the test splits. Both were audited and fixed on 2026-08-10:

- `login_to_app` and `find_contact` — helpers that called concrete endpoints from
  our code — were removed. Authentication moved into the prompt, which the rules
  explicitly permit ("tell the agent in the prompt to do so by itself").
- Canned Amazon plans and an ACTION-task regex over the task text were deleted.
  Coverage measurement showed they matched **zero** train/dev tasks and only
  test_challenge ones, so they could not have had a legal origin.

Verified by AST analysis: **zero `apis.*` calls in live code**. Every remaining
mention sits inside a prompt string. Re-verified on 2026-09-02 against the
current tree.

Full audit:
[`analysis/HARDCODE-INVENTORY-2026-08-10.md`](LARA-sub_agents/LARA/analysis/HARDCODE-INVENTORY-2026-08-10.md)

Removing the hardcode *improved* the score — `test_normal` went from 54.8 to 61.9.
