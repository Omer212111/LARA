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

