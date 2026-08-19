# LARA — a multi-agent coding agent for AppWorld

LARA solves [AppWorld](https://appworld.dev) tasks by writing Python. Given an
instruction like *"pay each person in debt_list.csv via Venmo, or file a Splitwise
expense if they have no Venmo account"*, it discovers the right APIs, writes a plan,
then writes and runs code against those APIs until the task is done.

## Results

| split | Task Goal Completion | Scenario Goal Completion |
|---|---|---|
| `test_normal` | **61.9** | **50.0** |
| `test_challenge` | **37.6** | **20.1** |

Both on commit [`3eb7770`](../../tree/3eb7770), one Executor attempt per task,
`gpt-4.1-mini` for all agents.

## Where the code is

Everything lives under **[`LARA-sub_agents/LARA/`](LARA-sub_agents/LARA/)**.

**Start here:** [`LARA-sub_agents/LARA/README.md`](LARA-sub_agents/LARA/README.md) —
what AppWorld is, how the four agents work, and what every file does.

Quick map:

| path | what it is |
|---|---|
| [`planning_loop.py`](LARA-sub_agents/LARA/planning_loop.py) | The LangGraph state machine wiring the four agents |
| [`explorer.py`](LARA-sub_agents/LARA/explorer.py) | Discovery agent — reads API docs, writes the plan |
| [`app_agents/base.py`](LARA-sub_agents/LARA/app_agents/base.py) | The ReAct executor loop and per-app specialist dispatch |
| [`app_agents/`](LARA-sub_agents/LARA/app_agents/) | One specialist per app (spotify, venmo, gmail, …) |
| [`executor_helpers.py`](LARA-sub_agents/LARA/executor_helpers.py) | Generic helpers injected into every code block |
| [`analysis/`](LARA-sub_agents/LARA/analysis/) | Measurement tooling and the hardcode-compliance audit |

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
mention sits inside a prompt string.

Full audit:
[`analysis/HARDCODE-INVENTORY-2026-08-10.md`](LARA-sub_agents/LARA/analysis/HARDCODE-INVENTORY-2026-08-10.md)

Removing the hardcode *improved* the score — `test_normal` went from 54.8 to 61.9.
