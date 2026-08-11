# Hardcode inventory — AppWorld leaderboard compliance

Date: 2026-08-10 · Code audited: `main` @ `c3c4441` · Branch: `audit/hardcode-inventory-2026-08-10`

## The rule we are being measured against

From the AppWorld README:

> **Not allowed:** "hardcode any API calls into their `agent`'s logic, e.g., login into all apps
> in the first hardcoded execution call and save its access tokens in a variable."
>
> **Allowed:** "tell the agent in the prompt to do so by itself", and "give generic hints
> inferred based on `train` or `dev` failures (not `test` sets)".

Two separate rules, and we break both. The line is: **prompt text is allowed, code that calls
APIs for the model is not** — and **anything learned from a test split is not allowed at all**,
prompt or code.

## How this was measured

Two methods, because they answer different questions.

**Static coverage** (`analysis/hardcode_coverage.py`) — three surfaces decide what they do purely
from the task instruction string, so their reach can be counted exactly over all 732 tasks. No LLM,
no run, no sampling error.

**Runtime trace** (`analysis/hardcode_trace.py`) — records which surface actually fired, per task.
Off unless `LARA_HARDCODE_TRACE` names an output file, so the traced code is the same code that
runs the leaderboard. Run: `broad-20` on train, 20 tasks, **10 correct (50%)**.

```
LARA_HARDCODE_TRACE=hardcode_broad20.jsonl python analysis/run_slice.py broad-20 --log-to broad20_hc.log
python analysis/hardcode_trace.py hardcode_broad20.jsonl
```

---

## Tier 1 — Derived from test data. This is the one that gets a submission rejected.

### H1. `amazon_template_plan` — canned plans that skip the LLM
`explorer.py:44-109`, called at `explorer.py:284`

Regex-matches the task wording and returns a **complete, finished plan**, bypassing the Explorer
LLM entirely. The code comment says so outright: *"we match the instruction and emit a
known-correct plan, skipping the LLM entirely."*

Measured reach across every task in the benchmark:

| split | tasks | matched |
|---|---|---|
| train | 90 | **0** |
| dev | 57 | **0** |
| test_normal | 168 | **0** |
| test_challenge | 417 | **9** (2.2%) |

The three regexes match exactly three scenarios, all of them test_challenge only:
`5238afc` (cart), `0d22252` (wish list), `b3bdcc1` (highest-rated seller). One of them matches
the wording *"using my visa card for my home address"*.

**There are zero Amazon tasks in train and zero in dev.** These templates could not have been
written from train/dev failures. That makes this a violation of the train/dev/test separation
rule, not only the hardcoding rule.

Two consequences worth being precise about:
- It contributed **nothing** to the 54.8 test_normal score — it never fired there. Removing it
  costs us nothing on the score we already have.
- It would have affected up to 9/417 tasks on test_challenge, which we have not run yet.

### H2. Same three flows, in the Explorer prompt
`prompts_explorer.py:109-153` — "AMAZON PATTERNS — match the task to ONE flow"

### H3. Same three flows, in the Amazon specialist prompt
`app_agents/amazon.py:15-51` — "PATTERN A / B / C. **These OVERRIDE the Explorer plan.**"

H1, H2 and H3 are the same test-derived knowledge written three times. Deleting one leaves the
other two working. All three have to go together.

### H4. ACTION-task regex on the task text
`app_agents/base.py:393` — `re.match(r"(place an order|buy me|order all|order the)", task_body)`

| split | matched |
|---|---|
| train | 0 / 90 |
| dev | 0 / 57 |
| test_normal | 0 / 168 |
| test_challenge | **48 / 417** (11.5%) |

Same shape of problem: the wordings only exist in test_challenge. The other branch of that
check — the Explorer plan containing the words "action task" — is legitimate and does the real
work; it fired on tasks in our run. Only the text regex is test-derived.

---

## Tier 2 — Hardcoded API calls in the agent's own logic

This is the category the rule names explicitly.

### H5. `login_to_app` — the rule's literal example
`executor_helpers.py:112-130`

Calls `apis.supervisor.show_profile()`, `apis.supervisor.show_account_passwords()` and
`apis.<app>.login(...)` from our code, then **caches the token in a variable**. The rule's own
example of what is not allowed is "login into all apps ... and save its access tokens in a
variable". The difference in our favour: the model chooses to call it, we do not run it
unprompted. That is a real distinction but it is ours to argue, not a settled one.

**Measured: 20/20 tasks, 84 calls.** Universally load-bearing.

### H6. `find_contact` — hardcodes "a person lookup means the phone app"
`executor_helpers.py:212-231`

Calls `apis.phone.search_contacts` and `apis.phone.show_contacts`, and logs into `phone` on its
own. Beyond the API calls, it encodes a task-solving decision: that resolving a name goes through
the phone app.

**Measured: 0 uses in 20 tasks** — including the nine tasks that were about roommates, siblings
and coworkers. The model never calls it. This one is free to delete.

### H7. The orchestrator executes code the model never asked for
`app_agents/base.py:81-104` (`_read_ledger`)

Every ReAct step on a "multi-app" plan, the orchestrator runs `BOOTSTRAP_CODE + ledger_summary()`
in the AppWorld sandbox itself, to print the ledger back into the prompt.

**Measured: 171 executions across 20/20 tasks.**

20/20 is a bug, not a design choice. `is_multi_app_plan` (`base.py:426-427`) counts the `[supervisor]`
and `[generic]` plan tags as apps, so a pure single-app Spotify task classifies as multi-app:

```
Multi-app plan (['generic', 'spotify', 'supervisor']) — ledger visibility ON
```

Every task in the run hit this. So the ledger machinery — prompt block plus a sandbox round-trip
per step — runs on every task, not on the cross-app tasks it was built for.

### H8. Documentation lookups built by our code — probably fine
`tools.py:122` and `tools.py:148` build `apis.api_docs.show_api_descriptions(...)` /
`show_api_doc(...)` call strings for the Explorer.

**Measured: 57 + 95 = 152 lookups across 20/20 tasks.**

Technically our code composes an API call. But this is the path AppWorld explicitly encourages —
"read documentation, explore, experiment, and figure it all out on its own". I would keep this and
not raise it. It is also the thing that makes Tier 4 fixable (see below).

---

## Tier 3 — Hardcoded AppWorld conventions

No app-specific API call, but protocol knowledge discovered offline and baked into code.

### H9. `call_api` — injects `access_token=` for the model
`executor_helpers.py:133-139`. **Measured: 20/20 tasks, 89 calls.**

### H10. `fetch_all_pages` — the pagination protocol
`executor_helpers.py:142-182`. Hardcodes `page_index` starting at 0, `page_limit=20` (with the
comment "All 63 paginated APIs were checked to accept page_limit=20"), and a 20-page cap.
**Measured: 18/20 tasks, 66 calls.**

### H11. `_APP_KEYWORDS` — keyword table mapping task words to apps
`explorer.py:115-137`. A hand-built table of ~90 keywords across 10 apps, used to pre-inject API
docs into the Explorer prompt. **Measured: fired on 20/20 tasks.** Statically it detects at least
one app in 100% of train, dev and test_challenge tasks, and 98.2% of test_normal.

Note `benchmark.py:24-33` has a *second*, different keyword table for the same job.

---

## Tier 4 — Prompt-embedded app knowledge

Allowed by the letter of the rule ("tell the agent in the prompt"), but it is a lot, and some of
it is closer to a worked solution than to a hint.

Total hand-authored prompt surface: **97,250 characters (~24k tokens).**

| surface | chars | API names cited | of those, in `api_docs` |
|---|---|---|---|
| 10 specialist prompts | 71,614 | 240 | **204** |
| `build_explorer_system` | 20,144 | — | — |
| `REACT_EXECUTOR_SYSTEM` | 5,492 | — | — |

Largest specialists: amazon 12,979 · venmo 10,326 · splitwise 7,594 · simple_note 7,536.

Every specialist follows the same template: EXACT API NAMES → FIELD NAMES → COMMON TASK PATTERNS.
The first two are documentation. The third is worked solutions — e.g. `venmo.py:164-203` gives
complete code for five task shapes.

Runtime usage of the specialist prompts:

| specialist | tasks | ReAct steps | tasks passed |
|---|---|---|---|
| generic (no specialist) | 12 | 12 | 2 |
| spotify | 11 | 80 | 9 |
| phone | 9 | 32 | 1 |
| venmo | 6 | 28 | 1 |
| file_system | 3 | 6 | 1 |
| simple_note | 3 | 13 | 0 |

### The fact that makes Tier 4 replaceable

**204 of the 240 API names cited in specialist prompts appear literally in
`data/api_docs/standard/<app>.json`** — the docs the `api_docs` app serves at runtime. The
remaining 36 are our helper names (`login_to_app`, `call_api`), parameter names, or prose.

And the agent is already reading those docs: 152 runtime lookups across 20/20 tasks. The discovery
path works today and carries real traffic. Moving the API listings out of the prompts has
somewhere to land.

What is *not* re-derivable from docs is the strategy content — which field a task word maps to,
pagination gotchas, ACTION vs VALUE. Most of that is squarely inside "generic hints" and can stay,
provided it came from train/dev.

---

## Tier 5 — Not hardcode, but fix before the repo goes public

- **`config.py:52`** — `OLLAMA_AUTH_PASS = "MTAgroup1"` in plaintext. The submission links this
  repo publicly.
- **`benchmark.py:18`** — `os.environ["APPWORLD_ROOT_ACCESS"] = "1"`. Nothing in the installed
  appworld package reads this variable, so it does nothing — but a reviewer reading the code sees
  an agent granting itself root in the eval harness.
- **`base.py:426`** — the `is_multi_app_plan` bug from H7.

---

## One more measurement that shapes the replacement work

**The model never calls an app API directly.** Across 20 tasks the only direct `apis.*` call it
wrote was `apis.supervisor.complete_task` (20 times, once per task). Every single app API call
went through `call_api` or `fetch_all_pages`.

So the helper layer is not a convenience the model routes around when it wants to — it is the only
path it uses. H5, H9 and H10 cannot simply be deleted; they have to be replaced by prompt
instructions telling the model to do the same thing itself, which is exactly what the rule permits.

## Ledger helpers, for completeness

`remember` / `recall` / `remember_entity` fired on **1 task each, 1 call each** out of 20. No API
calls inside them, so no compliance question — but they are carrying prompt weight for nothing,
which is consistent with the 2.3% adoption already recorded in `CLAUDE.md`.

---

## Summary

| # | surface | tasks touched (of 20) | compliance risk |
|---|---|---|---|
| H1 | `amazon_template_plan` | 0 here, 9 in test_challenge | **disqualifying** |
| H2 | Explorer prompt AMAZON PATTERNS | — | **disqualifying** |
| H3 | Amazon specialist PATTERN A/B/C | — | **disqualifying** |
| H4 | ACTION regex on task text | 0 here, 48 in test_challenge | **disqualifying** |
| H5 | `login_to_app` | 20 | high — the rule's example |
| H6 | `find_contact` | **0** | high, but unused → free |
| H7 | framework-run sandbox code | 20 (171 execs) | high |
| H8 | api_docs lookups | 20 (152 calls) | low — encouraged |
| H9 | `call_api` | 20 | medium |
| H10 | `fetch_all_pages` | 18 | medium |
| H11 | `_APP_KEYWORDS` | 20 | medium |
| H12 | specialist prompts (71.6k chars) | 17 | low-medium |

Next step is deciding the replacement for each, weighed against the 54.8 baseline.
