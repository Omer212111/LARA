# LARA — a multi-agent coding agent for AppWorld

<div align="center">

## 🥇 &nbsp;1st place on the AppWorld leaderboard

**85.6** TGC on `test_challenge` — a **12.2-point** lead over 2nd place

[![leaderboard](https://img.shields.io/badge/AppWorld_Leaderboard-%231-FFD700?style=for-the-badge&labelColor=1a1a1a)](https://appworld.dev/appworld/leaderboard)
&nbsp;
[![TGC](https://img.shields.io/badge/test__challenge_TGC-85.6-2a78d6?style=for-the-badge&labelColor=1a1a1a)](https://appworld.dev/appworld/leaderboard)
&nbsp;
[![TGC](https://img.shields.io/badge/test__normal_TGC-88.7-1baf7a?style=for-the-badge&labelColor=1a1a1a)](https://appworld.dev/appworld/leaderboard)

*Standings as of 6 September 2026 — [verify on the live leaderboard](https://appworld.dev/appworld/leaderboard)*

<img width="720" height="405" alt="intro-map" src="https://github.com/user-attachments/assets/64563b03-4ee8-44e8-afb8-3376572cd00b" />

</div>

LARA solves [AppWorld](https://appworld.dev) tasks by **writing Python**. Given an
instruction like *"pay each person in debt_list.csv via Venmo, or file a Splitwise
expense if they have no Venmo account"*, it discovers the right APIs, writes a plan,
then writes and runs real code against those APIs until the world's database is in
the state the task asked for.

---

## The problem

Language models are strong at producing a *single* correct answer and weak at
carrying out a *long chain* of actions to reach one. Real digital work is the second
kind: paying everyone in a spreadsheet, reconciling a bill across a payments app and
a split-expense app, tidying a music library against a set of rules. These take
dozens of dependent steps, spread over several applications, where the information
needed at step 12 was produced at step 3 and no single service holds the whole
picture.

That is where models break down. A wrong assumption early is not corrected later, it
is *built on*. State has to be carried across applications that share no schema.
Actions are irreversible — a payment sent twice cannot be un-sent — so the agent has
to be right the first time rather than iterate toward correctness. And because
success is judged by the end state of the world rather than by what the agent claims,
a confident wrong answer scores exactly zero.

AppWorld exists to measure that gap directly, which is what makes it a hard target
and an honest one.

## The benchmark

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
`appworld evaluate`. On `test_challenge` this places LARA **1st on the
[AppWorld leaderboard](https://appworld.dev/appworld/leaderboard)** as of
6 September 2026, 12.2 TGC points ahead of second place.

### Against the official baseline

AppWorld ships a reference agent — the minimal ReAct loop from its own prompt
template, with no planning stage, no per-app knowledge and no cross-app memory. Run
on `test_normal` under identical conditions (one attempt per task, 16 steps), it is
the starting point LARA was built from:

**`test_normal`** (168 tasks):

| agent | model | TGC | SGC | d1 | d2 | d3 |
|---|---|---|---|---|---|---|
| official baseline | `gpt-4.1-mini` | 23.2 | 7.1 | 47.4 | 18.8 | 4.8 |
| official baseline | `claude-opus-4-7` | 54.8 | 46.4 | 87.7 | 52.1 | 27.0 |
| LARA | `gpt-4.1-mini` | 61.9 | 50.0 | 91.2 | 52.1 | 42.9 |
| **LARA** | `claude-opus-4-7` | **88.7** | **82.1** | 98.2 | 89.6 | 79.4 |

**`test_challenge`** (417 tasks):

| agent | model | TGC | SGC | d1 | d2 | d3 |
|---|---|---|---|---|---|---|
| official baseline | `gpt-4.1-mini` | 9.8 | 3.6 | 36.1 | 8.0 | 1.5 |
| official baseline | `claude-opus-4-7` | 27.3 | 18.7 | 75.0 | 26.7 | 10.3 |
| LARA | `gpt-4.1-mini` | 37.6 | 20.1 | 72.2 | 36.0 | 26.2 |
| **LARA** | `claude-opus-4-7` | **85.6** | **77.0** | 91.7 | 84.7 | 84.1 |

Each row pairs an agent with the model that produced it, so the two contributions can
be read separately. **With the model held fixed, the architecture is worth:**

| split | model | baseline → LARA (TGC) | ratio | +pts |
|---|---|---|---|---|
| `test_normal` | `gpt-4.1-mini` | 23.2 → 61.9 | 2.7× | +38.7 |
| `test_normal` | `claude-opus-4-7` | 54.8 → 88.7 | 1.6× | +33.9 |
| `test_challenge` | `gpt-4.1-mini` | 9.8 → 37.6 | 3.8× | +27.8 |
| `test_challenge` | `claude-opus-4-7` | 27.3 → 85.6 | **3.1×** | **+58.3** |

**The architecture matters most exactly where the benchmark is hardest.** On the
easier split a strong model recovers much of what the scaffold provides (1.6× on
`test_normal`). On `test_challenge` it does not: the same `claude-opus-4-7` collapses
to 27.3 without the scaffold while LARA holds 85.6 — **+58.3 TGC points, the largest
gap of any configuration measured.**

Between the two splits the baseline loses half its score (54.8 → 27.3) while LARA
loses 3.5% (88.7 → 85.6). Long multi-app tasks are where an unaided model runs out of
steps rediscovering APIs, and where planning plus per-app knowledge pays off most.

The difficulty breakdown sharpens it further. On `test_challenge` difficulty-3 the
`gpt-4.1-mini` baseline scores **1.5 TGC and 0.0 SGC** — three tasks out of ~200,
never once completing a full scenario — and even the `claude-opus-4-7` baseline
reaches only 10.3, where LARA on the same model holds **84.1 / 75.4**.

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
| official baseline | `claude-opus-4-7` | 54.8 | 27.3 |
| official baseline | `gpt-4.1-mini` | 23.2 | 9.8 |

Read down the column and the model is worth 26.8 TGC points (61.9 → 88.7 with LARA);
read across the agent rows and the architecture is worth 33.9 (54.8 → 88.7 on
`claude-opus-4-7`). Neither alone reaches the submitted score. The model gap is widest
on `test_challenge`, where tasks are longest and a single wrong API guess ends the run.

> 📄 **We wrote this up properly.** Filling the full model × architecture × difficulty
> grid shows the two contributions trade off with task difficulty: on easy tasks a
> strong model is nearly self-sufficient (+10.5 TGC from the architecture); on the
> hardest tasks the same strong model collapses without it and LARA rescues +73.8
> points. Full paper:
> [**Model Quality vs. the LARA Harness and Architecture**](docs/LARA_Model_vs_Architecture_Paper.pdf).

---

## How LARA works

> 📄 **We also tested the two-agent split itself.** Is a dedicated Explorer stage
> worth the engineering cost over one agent that plans and executes in a single loop?
> Holding knowledge, tools, and step budget fixed as much as possible, the two-stage
> design scores 73.3% against a knowledge-matched single agent's 42.2% on the same
> paired task slice (p = 0.0043). Full paper:
> [**Does Separating Planning from Execution Help LLM Agents Solve Multi-App
> Tasks?**](docs/PLANNING_SEPARATION_PAPER_2026-09-06.md)
> ([PDF](docs/PLANNING_SEPARATION_PAPER_2026-09-06.pdf)) · technical report:
> [`docs/PLANNING_SEPARATION_ABLATION_2026-09-06.md`](docs/PLANNING_SEPARATION_ABLATION_2026-09-06.md)

> 🎥 **[Watch the LARA explainer](https://github.com/user-attachments/assets/f0e58856-26b2-445d-bdbf-82caa714a229)** —
> a short walkthrough of the pipeline end to end.

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

> 📄 **We measured this.** A four-arm ablation varying how much per-app knowledge the
> Executor sees, and how it is delivered, found that the *knowledge* matters
> (64.4 → 82.2 TGC) while the *routing* does not — what per-step dispatch buys is
> 2.44× lower token cost at equal accuracy. Full study:
> [**Specialist-dispatch ablation**](docs/SPECIALIST_DISPATCH_ABLATION_2026-09-04.md)
> ([PDF](docs/SPECIALIST_DISPATCH_ABLATION_2026-09-04.pdf)) · all results:
> [`docs/RESULTS_SUMMARY.md`](docs/RESULTS_SUMMARY.md)

### 3. Cut what does not pay for itself

The Reviewer diagnoses a wrong answer so the Executor can retry. It is **disabled**.

Measured over 165 tasks, it fired 75 times and rescued 1. A retry costs a Reviewer
call plus a full second Executor attempt — roughly 45% more compute for a 1.3%
conversion rate. The leaderboard runs use exactly **one Executor attempt per task**
(`MAX_EXECUTOR_RUNS = 1`, `ENABLE_REVIEWER_RETRY = False`).

The code is kept, and the measurement that closed it is recorded in
[`config.py`](LARA-sub_agents/LARA/config.py), so the decision can be revisited if a
retry mechanism ever demonstrates it converts on train/dev.

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
