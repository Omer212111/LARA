# AppWorld leaderboard submission — checklist

Code under test: commit `1c2a803` (single attempt per task, Reviewer + Supervisor
retry both disabled, `fetch_all_pages` `page_limit=20`).

> **The code must not change between the two runs.** The maintainer verifies that
> no changes were made after the last evaluation before merging. If anything in
> the agent changes, both runs are void and must be repeated.

## Both datasets are required

A submission is a PR containing **two** bundles — `test_normal` AND
`test_challenge`. One alone will not be accepted.

| dataset | tasks | status |
|---|---|---|
| `test_normal` | 168 | **DONE** — `lara_test_normal`, TGC 54.8 / SGC 37.5 |
| `test_challenge` | 416 | not started — `lara_test_challenge` |

### test_normal result (2026-08-10, commit `1c2a803`)

```
    type     | task_goal_completion | scenario_goal_completion
-------------+----------------------+-------------------------
 aggregate   |         54.8         |           37.5
difficulty_1 |         82.5         |           63.2
difficulty_2 |         50.0         |           37.5
difficulty_3 |         33.3         |           14.3
```

92/168 tasks correct, 195.5 min wall clock, one Executor attempt per task.
Three tasks ended `not called` (ran 182-213s without submitting) and count as
failures. Reports: `experiments/outputs/lara_test_normal/evaluations/test_normal.{json,txt}`.

TGC falls 2.5x from difficulty 1 to 3, and SGC falls further (63.2 → 14.3):
passing one variant of a scenario rarely means passing all of them.

Experiment names must be alphanumeric with `-`/`_`, must **end with the dataset
name**, and the prefix must match across both. Ours: `lara_test_normal` and
`lara_test_challenge`, prefix `lara`.

## 1. Score each run

```bash
cd /home/omer2/LARA_project/wt-partner/LARA-sub_agents/LARA
appworld evaluate lara_test_normal    test_normal
appworld evaluate lara_test_challenge test_challenge
```

Reports land in `experiments/outputs/<name>/evaluations/<dataset>.{txt,json}`.

Read the AGGREGATE only. Per the AppWorld README, the test sets may not be used
for error analysis or tuning — do not open `tasks/<task_id>/evaluation/report.md`,
and do not change the agent in response to what is in there.

## 2. Pack — same metadata for both

```bash
appworld pack lara_test_normal test_normal \
  "LARA MAS" \
  "Explorer writes an app-tagged plan; per-app specialist executors run a ReAct loop; single attempt per task" \
  "gpt-4.1-mini" \
  "gpt-4.1-mini for all agents (explorer, executor, supervisor)" \
  "https://github.com/Omer212111/LARA"

appworld pack lara_test_challenge test_challenge \
  "LARA MAS" \
  "Explorer writes an app-tagged plan; per-app specialist executors run a ReAct loop; single attempt per task" \
  "gpt-4.1-mini" \
  "gpt-4.1-mini for all agents (explorer, executor, supervisor)" \
  "https://github.com/Omer212111/LARA"
```

Argument order follows `appworld pack --help`: experiment_name, dataset,
method_name, method_tooltip, llm_name, llm_tooltip, url. (The leaderboard repo's
README shows a 4-argument example that omits `llm_tooltip` — trust `--help`.)

Produces `experiments/outputs/<name>/leaderboard.bundle` — encrypted. Never post
these outputs anywhere publicly in unencrypted form.

## 3. Submit the PR

```bash
pip install appworld && appworld install     # if not already
git lfs install                              # required — bundles are LFS-tracked
git clone <appworld-leaderboard repo>        # linked from the leaderboard UI
```

Copy both bundles into the leaderboard repo at:

```
experiments/outputs/lara_test_normal/leaderboard.bundle
experiments/outputs/lara_test_challenge/leaderboard.bundle
```

Open a PR with those two files, then comment (no leading whitespace):

```
/add-to-leaderboard --python 3.11 --appworld <version> lara
```

`<version>` is a PyPI version (e.g. `0.1.3`) or
`"git+https://github.com/stonybrooknlp/appworld.git"`. Check the installed
version with `appworld --version` and match it.

A GitHub workflow runs and posts the resulting leaderboard entry as a comment.
Verify the details, then assign/ping the maintainer (Harsh) to merge.

## Open items before submitting

- [ ] **Run `test_challenge`** — 416 tasks, on commit `1c2a803`, unchanged.
- [ ] **Is the repo public?** `https://github.com/Omer212111/LARA` is the git
      remote; a private repo makes the submission URL useless to reviewers.
- [ ] **Credit Lior and Gilad.** Their fixes are in the commit being scored:
      `simple_note` keyword + `[app]` tag contract (Lior), `call_api` token rule
      + failure-classifier fix (Gilad).
- [ ] **Confirm the method name.** `lara` is the prefix that will show publicly.
- [ ] **Ask the organizers about `login_to_app`.** The rules forbid hardcoding
      API calls, naming "login into all apps ... and save its access tokens in a
      variable" as the example. Ours defines the helper and caches tokens, but
      only once the model chooses to call it — arguably covered by "It is okay to
      tell the agent in the prompt to do so by itself". The specialist prompts
      also carry exact API and field names. Worth a GitHub issue BEFORE
      submitting rather than after.
