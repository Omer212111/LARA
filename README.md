# LARA — a multi-agent coding agent for AppWorld

LARA solves [AppWorld](https://appworld.dev) tasks by writing Python. Given an
instruction like *"pay each person in debt_list.csv via Venmo, or file a Splitwise
expense if they have no Venmo account"*, it discovers the right APIs, writes a plan,
then writes and runs code against those APIs until the task is done.

## Results

| split | tasks | Task Goal Completion | Scenario Goal Completion |
|---|---|---|---|
| `test_normal` | 168 | **88.7** | **82.1** |
| `test_challenge` | 417 | **85.6** | **77.0** |

One Executor attempt per task, `claude-opus-4-7` served over an
OpenAI-compatible LiteLLM gateway, scored with `appworld` 0.1.3.post1.

An earlier run of the same method on `gpt-4.1-mini` scored 61.9 / 50.0 on
`test_normal` and 37.6 / 20.1 on `test_challenge`.

## Reproducing the leaderboard run

`config.py` defaults to `gpt-4.1-mini`. The leaderboard run used
`claude-opus-4-7` served over an OpenAI-compatible LiteLLM gateway, selected at
run time through environment overrides rather than by editing the defaults:

```bash
export OPENAI_BASE_URL=<litellm-gateway-url>   # OpenAI-compatible endpoint
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

Without the `EXECUTOR_MODEL` / `EXPLORER_MODEL` / `OPENAI_BASE_URL` overrides the
same commands run on `gpt-4.1-mini` and reproduce the earlier 61.9 / 37.6 result
instead.

Single attempt per task is enforced in [`config.py`](LARA-sub_agents/LARA/config.py):
`MAX_EXECUTOR_RUNS = 1` and `ENABLE_REVIEWER_RETRY = False` — the Reviewer and the
Supervisor retry path are both closed. Both splits were run back to back through the
same entrypoint with no code changes between them.

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
mention sits inside a prompt string. Re-verified on 2026-09-02 against the
current tree.

Full audit:
[`analysis/HARDCODE-INVENTORY-2026-08-10.md`](LARA-sub_agents/LARA/analysis/HARDCODE-INVENTORY-2026-08-10.md)

Removing the hardcode *improved* the score — `test_normal` went from 54.8 to 61.9.
