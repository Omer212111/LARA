# LARA Autonomous Improvement Loop — Engineering Design

> **Status**: v2 (2026-05-25). Fully automated `auto-cycle` loop: baseline → prioritize → try each fix in priority order → keep if score improves, revert & try next if not. Human-in-the-loop mode still available via `cycle`.

This document describes how the LARA autonomous improvement loop works at an engineering level: the five stages, the six artifacts that implement them, the schemas, the verification chain, and the failure modes. Companion documents:
- [`LARA - Documentation.docx`](../LARA%20-%20Documentation.docx) — manual experiment log (human-designed changes).
- [`Autonomous Loop - Experiments.docx`](../Autonomous%20Loop%20-%20Experiments.docx) — loop-generated experiment log.
- [`CLAUDE.md`](../CLAUDE.md) — overall LARA architecture (orchestrator, specialists, sandbox).

---

## 1. Loop overview

The loop closes a five-stage cycle:

```
   ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌──────────────┐   ┌──────────────┐
   │ 1. RUN slice │ → │ 2. ANALYZE   │ → │ 3. PRIORITIZE    │ → │ 4. APPLY +   │ → │ 5. EVALUATE  │
   │ (baseline)   │   │ (per-task    │   │ (ranked fix      │   │  RE-RUN      │   │ (keep or     │
   │              │   │  failures)   │   │  list)           │   │  (delta)     │   │  revert)     │
   └──────────────┘   └──────────────┘   └──────────────────┘   └──────────────┘   └──────┬───────┘
                                                                                          │
                                                ┌─────────────────────────────────────────┘
                                                │
                                     score improved? ─── YES → keep fix, update baseline,
                                                │              try next fix from Stage 3 list
                                                │
                                                └── NO → revert fix, try next fix from Stage 3 list
```

Each stage produces a structured artifact that the next stage consumes. The aim is that humans can step in at any stage, and the loop can also run end-to-end autonomously via `auto-cycle`.

There are **two modes** of operation, by design:

1. **Manual discovery phase** — when LARA encounters a substantively new failure family or there was a drastic change in the LARA code (new app, new task type, new model), we run the slice manually, read the traces, and **populate the analysis files** (the category dictionary, the behavioral signals, the fix mappings). The loop *cannot improvise vocabulary*; it works with what we've taught it.

2. **Automated improvement phase** — once the analysis files cover the failure family, the loop runs the same slice repeatedly, picks the highest-priority fix using the scored framework, generates the patch via an LLM, verifies it, applies it, re-measures. Humans monitor but don't drive each iteration.

The split is intentional: discovery is creative work that benefits from human judgment; iteration is mechanical work that benefits from determinism.

---

## 2. The six artifacts

All six live in [`analysis/`](.). Each is owned by one of the four stages.

| # | Artifact | Stage | Type | Purpose |
|---|---|---|---|---|
| 1 | [`error_categories.json`](error_categories.json) | 2 | Data | Canonical vocabulary of failure modes |
| 2 | [`parse_run.py`](parse_run.py) | 2 | Code | Extract structured per-task reports from a run log |
| 3a | [`behavioral_signals.json`](behavioral_signals.json) | 4 | Data | Counters tracked across runs |
| 3b | [`panel.py`](panel.py) | 4 | Code | Uniform delta table (current vs baseline) |
| 4 | [`fix_mappings.json`](fix_mappings.json) | 3 | Data | Candidate fixes per category, with tractability |
| 5a | [`slices.json`](slices.json) | 1 | Data | Pinned task slices for reproducibility |
| 5b | [`run_slice.py`](run_slice.py) | 1 | Code | Run a named slice (+ optional auto-parse/auto-panel) |
| 6a | [`surfaces_config.py`](surfaces_config.py) | 4 | Code | File-region registry (which marker maps to which surface) |
| 6b | [`apply_and_measure.py`](apply_and_measure.py) | 3+4 | Code | LLM-driven patch + verify + apply + cycle |
| 6c | [`loop_logger.py`](loop_logger.py) | 3+4 | Code | Per-cycle dual-output logger (human text + JSONL) recording every stage event |

Supporting memories (in the user's `~/.claude/projects/.../memory/`):
- `project_iteration_loop.md` — high-level description of the loop's 4 stages.
- `project_fix_prioritization.md` — scoring framework (impact×2, cluster×2, tractability×3 under the safety-driven profile).
- `feedback_general_fixes.md` — every fix solves a general failure class.
- `feedback_consult_on_forks.md` — humans consulted on every design fork.

---

## 3. Stage 1 — RUN

### What it does
Execute a pinned set of AppWorld benchmark tasks with stable parameters so deltas across iterations are comparable.

### Why slices?
Raw `python benchmark.py --app venmo --n 5 --dataset train` is not stable: the underlying keyword filter can drift if specialist app names change. A *slice* freezes a named set of task IDs + the runtime parameters.

### Schema: [`slices.json`](slices.json)
```json
{
  "schema_version": 1,
  "slices": {
    "<slice_name>": {
      "purpose": "<human description of why this slice exists>",
      "dataset": "train|test_normal|test_challenge",
      "task_ids": ["<id1>", "<id2>", ...],
      "params": {
        "max_iterations": <int>,
        "max_executor_runs": <int>,
        "temperature": <float>,
        "executor_model": "<openai_model_id>",
        "explorer_model": "<openai_model_id>"
      },
      "expected_runtime_s_range": [<lo>, <hi>],
      "created_in_run": "<run_id>",
      "change_log": [
        {"date": "<YYYY-MM-DD>", "note": "<change rationale>"}
      ]
    }
  }
}
```

### CLI: [`run_slice.py`](run_slice.py)

```bash
# List available slices
python analysis/run_slice.py --list

# Show what would run, without executing
python analysis/run_slice.py venmo-smoke-5 --dry-run

# Run, tee log to file
python analysis/run_slice.py venmo-smoke-5 --log-to /tmp/lara_run.log

# Run + parse + panel against a baseline — full Stage 4 in one shot
python analysis/run_slice.py venmo-smoke-5 \
    --log-to /tmp/lara_run.log \
    --auto-parse --auto-panel \
    --baseline /tmp/baseline_report.json
```

The wrapper imports `benchmark.run_official_benchmark` directly; it does not shell out. This keeps the slice runner cheap and aligned with the existing entry point.

### Current slices
- **`venmo-smoke-5`** — 5 tasks (`2a163ab_1..3`, `afc0fce_1..2`) used during the 2026-05-21..22 iteration on venmo + phone failures. Runtime: 60–180s.

---

## 4. Stage 2 — ANALYZE

### What it does
Convert a run's raw text log into a structured per-task report with categorical failure tags.

### Why a category dictionary?
Without a canonical vocabulary, every analyst (human or machine) invents codes ad hoc. Scoring becomes incomparable across runs. The dictionary pins 18 specific failure modes observed in real traces.

### Schema: [`error_categories.json`](error_categories.json)
```json
{
  "schema_version": 1,
  "stages": ["plan", "execution", "recovery", "submission"],
  "categories": [
    {
      "code": "E-WRONG-ENTITY",
      "description": "Plan picked the wrong entity type ...",
      "stage": "plan",
      "signatures": ["show_received_payment_requests", "payment_request_id"],
      "example": {"task_id": "afc0fce_1", "snippet": "..."},
      "candidate_fix_surfaces": ["explorer_prompt", "venmo_specialist"],
      "seen_in_tasks": ["afc0fce_1", "afc0fce_2"],
      "count": 2,
      "signature_notes": "Optional — explains structural detection rules"
    }
  ]
}
```

**Fields:**
- `code` — stable identifier (e.g. `E-WRONG-ENTITY`).
- `description` — one-sentence definition the loop can quote in reports.
- `stage` — when in execution the failure surfaces.
- `signatures` — substring matches against the run trace. Empty means structural detection.
- `example` — one canonical real-world instance from a run.
- `candidate_fix_surfaces` — short list of file types where fixes typically land.
- `seen_in_tasks` + `count` — lifetime occurrence tracking.

**Two detection modes:**
- **Signature-based (10 categories)** — substring search across the task's full trace.
- **Structural (8 categories)** — custom rules in [`parse_run.py`](parse_run.py)'s `_tag_structural_categories`. E.g. `E-PLAN-DATE-NOT-WIRED`: plan contains `get_current_date_and_time` AND no later step mentions `min_created_at`/`max_created_at`.

### CLI: [`parse_run.py`](parse_run.py)

```bash
# Human summary
python analysis/parse_run.py /tmp/lara_run.log --summary

# Machine JSON
python analysis/parse_run.py /tmp/lara_run.log --out /tmp/report.json
```

### Output schema (per-task report)
```json
{
  "input_path": "...",
  "slice_task_ids": ["..."],
  "benchmark_summary": {"correct": 0, "total": 5},
  "tasks": [
    {
      "task_id": "2a163ab_1",
      "instruction": "...",
      "plan": "APP: venmo, phone\nREASONING: ...\nPLAN: ...",
      "react_steps": [
        {
          "step": 1, "attempt": 1,
          "code": "...", "output": "...",
          "had_error": false,
          "specialist": "PhoneExecutor"
        }
      ],
      "attempts": [
        {"attempt": 1, "steps": 10, "completed": true, "correct": false, "had_error": false}
      ],
      "final_score": {
        "status": "wrong",
        "pass": 4, "total": 6, "pct": 66.7,
        "failures": ["assert ..."], "time_s": 39.1
      },
      "flow_crash": null,
      "status": "wrong|correct|incomplete",
      "tagged_categories": ["E-EXEC-INVENT-API", "E-PLAN-WRONG-API", ...]
    }
  ],
  "category_counts": {"E-EXEC-INVENT-API": 3, ...},
  "category_to_tasks": {"E-EXEC-INVENT-API": ["2a163ab_1", ...]}
}
```

### Markers the parser relies on
The orchestrator ([`app_agents/base.py`](../app_agents/base.py)) emits these lines deterministically:
- `Task <N>/<M>: <task_id>` — per-task boundary.
- `📋 Instruction: <text>` — instruction.
- `[OUTPUT — 📋 Explorer Plan]` … blank — plan body.
- `[Orchestrator] Step <N>: dispatching to <Specialist>` — per-step dispatch.
- `[CODE — ReAct step <N> / attempt <M>]` — code block header.
- `[OUTPUT — ReAct step <N> / attempt <M>]` — output header.
- `❌ complete_task() called but WRONG — N/M tests passed` — per-attempt failure summary.
- `[Orchestrator] Done — attempt <N>, <K> steps, completed=<bool>, correct=<bool>` — per-attempt close.
- `❌ Task <id> WRONG — N/M tests passed (P%) | Failed: [...]` — per-task close.
- `✅ ... CORRECT` — successful close.
- `BENCHMARK COMPLETE — N/M tasks correct` — overall summary.

If the orchestrator changes any of these strings, [`parse_run.py`](parse_run.py) must be updated.

---

## 5. Stage 3 — PRIORITIZE

### What it does
Given the categories that fired in the latest run, deterministically rank candidate fixes and propose the top one.

### Why a fix mapping?
The category dictionary says *what* went wrong. The fix mapping says *where to edit and how*. Splitting them keeps the dictionary lean (definitions only) and makes proposed fixes reviewable as a separate concern.

### Schema: [`fix_mappings.json`](fix_mappings.json)
```json
{
  "schema_version": 1,
  "mappings": [
    {
      "category_code": "E-WRONG-ENTITY",
      "fixes": [
        {
          "surface": "explorer_prompt",
          "description": "Add a VENMO PATTERNS block disambiguating ...",
          "tractability": 5,
          "status": "proposed",
          "rationale": "Highest priority outstanding fix ..."
        },
        {
          "surface": "venmo_specialist",
          "description": "...",
          "tractability": 5,
          "status": "proposed",
          "rationale": "Backup at execution time ..."
        }
      ]
    }
  ]
}
```

**Surface keys** (the editing target):
- `explorer_prompt` — `prompts.py` Explorer system prompt.
- `venmo_specialist`, `phone_specialist`, etc. — per-app specialist prompts in `app_agents/`.
- `executor_react_prompt` — generic ReAct executor prompt.
- `orchestrator_guard`, `orchestrator_recovery` — code-level guards in `app_agents/base.py`.
- `bootstrap_helpers` — `executor_helpers.py`.
- `specialist_prompts` — change to apply across all specialists.

**Tractability scale** (used by the prioritization framework):
- **5** — prompt-only additive change, easy revert.
- **3** — prompt rewrite, or one orchestrator behavior change.
- **1** — multi-file or contract-changing, hard to revert.

**Status:** `applied` (with `applied_in_run` + `applied_in_change`) or `proposed`.

### Prioritization framework (automated since v2)

Weighted scoring (safety-driven profile, set 2026-05-22, automated 2026-05-25):

```
priority = impact × 2 + cluster_coverage × 2 + tractability × 3
```

- **Impact (1/3/5)** — derived from `category_counts` in the parsed report. 5 = category hit ≥50% of tasks, 3 = ≥25%, 1 = isolated.
- **Cluster coverage (1/3/5)** — how many *active* categories (count > 0 in this run) share the same fix surface. 5 = 3+, 3 = 2, 1 = 1.
- **Tractability (1/3/5)** — from `fix_mappings.json`; same scale as before.

Implemented in `prioritize_fixes(report)` in [`apply_and_measure.py`](apply_and_measure.py). Filters:
- Only `status: "proposed"` fixes (already-applied fixes are skipped).
- Only fixes whose surface is registered in `surfaces_config.py` (unmarkered surfaces can't be auto-patched).
- Only categories that actually fired in the current run (count > 0).

CLI: `python analysis/apply_and_measure.py prioritize --slice venmo-smoke-5`

### Disqualifiers (auto-deprioritize regardless of priority)
- Requires changing AppWorld APIs / world data → out of scope.
- Breaks an existing passing pattern → regression risk.
- Speculative — no failure observed in actual logs.

### Tie-breakers (only when totals match within 2 points)
1. **Generality** — solves a class beats a per-task patch.
2. **Recency of evidence** — most recent run > older inferences.
3. **Independence** — doesn't interact with other pending fixes.

---

## 6. Stage 4 — APPLY + MEASURE

### What it does
Take a chosen fix, generate the patch via an LLM, verify, apply (git-stash-protected), re-run the slice, compute the delta panel.

### Why an LLM step?
The fix mapping stores fix **descriptions** ("add a VENMO PATTERNS block disambiguating ..."), not literal diffs. To go fully autonomous, the wrapper must translate description → patch. The current choice is `gpt-4.1-mini` (chosen 2026-05-22) — strong enough for prompt edits, cheap enough to make 100 iterations cost ~$2.50.

### The four sub-steps of Stage 4

**4a — Propose patch.** The wrapper:
1. Resolves `<fix_id>` (format: `<CATEGORY_CODE>:<index>`) to a category + fix entry.
2. Looks up the surface in [`surfaces_config.py`](surfaces_config.py) → file path + marker label.
3. Extracts the marked region from the file via `=== SURFACE: <label> === BEGIN/END` sentinels.
4. Calls the LLM with a system prompt + the fix description + the current region.
5. Parses the LLM response as the new region text (no fences, no commentary).
6. Logs cost to `analysis/cost_log.jsonl`.

**4b — Verify.** Before any file change:
1. **Region preservation check.** New region must be ≥70% the length of the old AND must contain ≥70% of the distinctive lines (length > 40, non-separator) from the old. Catches LLM truncation.
2. **Syntax check.** `compile()` for `.py`, `json.loads()` for `.json`. Run AFTER the file is written.

**4c — Apply.** Git-stash-protected:
1. Refuse to apply unless `git status --porcelain` is empty (or `--force-dirty`).
2. Replace the marked region in-place.
3. Run the syntax check.
4. On failure, `git checkout -- <file>` to revert.
5. Optionally pause for human review (unless `--accept`).

**4d — Run + measure.** Wraps `run_slice` + `parse_run` + `compute_panel`:
1. Run the named slice with stdout teed to a log file.
2. Parse the log into a JSON report.
3. Compute the panel against an optional baseline report.
4. Render and print the delta table.

### Schema: [`surfaces_config.py`](surfaces_config.py)
A simple `dict[surface_key, Surface]` where `Surface = (surface_key, file_path, marker_label, description)`. Currently only `explorer_prompt` is registered. Other surfaces (Venmo specialist, executor ReAct prompt, etc.) need marker bootstrapping before the wrapper can edit them.

### Markers in target files
Each editable region is delimited by sentinel comments inside the target file:
```python
=== SURFACE: explorer_prompt:semantic_api_selection === BEGIN
SEMANTIC API SELECTION — common task patterns:
  "songs in my playlists"        → show_playlist_library → ...
  ...
=== SURFACE: explorer_prompt:semantic_api_selection === END
```
The markers are inside the prompt's triple-quoted string, so they survive to runtime and are visible to the parser. They are not interpreted by Python.

### Schema: [`behavioral_signals.json`](behavioral_signals.json)
```json
{
  "schema_version": 1,
  "counters": [
    {
      "name": "phone_login_401",
      "description": "Phone login 401 errors. Should be 0 after the username-routing fix.",
      "kind": "antipattern|good_pattern|neutral",
      "scope": "all_outputs|all_code|all_plans|all_traces|react_metadata",
      "pattern_type": "substring|regex",
      "patterns": ["Invalid credentials"],
      "added_in_run": "<run_id>",
      "added_for": "<rationale>"
    }
  ]
}
```

The **kind** field drives the panel's rendering (🚫 for antipatterns we want to retire, ✓ for good patterns we want to grow, · for neutral observation). The **scope** field tells [`panel.py`](panel.py) which slice of the parsed report to search.

### Counters live in a config, not code
We chose config over hardcode (2026-05-22) because:
- Each substantial code change or new task family discovers new signals.
- Hardcoded counters would drift between iterations.
- The autonomous loop reads the config to compute uniform deltas; humans extend the config during manual discovery phases.

### CLI: [`panel.py`](panel.py)
```bash
# Single-run mode (no deltas)
python analysis/panel.py /tmp/report.json

# Delta vs baseline
python analysis/panel.py /tmp/report.json --baseline /tmp/baseline_report.json

# Machine JSON
python analysis/panel.py /tmp/report.json --json --out /tmp/panel.json
```

### CLI: [`apply_and_measure.py`](apply_and_measure.py)
```bash
# List candidate fixes (with applied/proposed status + tractability)
python analysis/apply_and_measure.py list

# Run a slice and rank proposed fixes by priority (automated Stage 3)
python analysis/apply_and_measure.py prioritize --slice venmo-smoke-5

# Generate a patch via LLM; print it; don't apply
python analysis/apply_and_measure.py propose-patch E-WRONG-ENTITY:0

# Generate + verify + apply (pauses for human review)
python analysis/apply_and_measure.py apply E-WRONG-ENTITY:0

# Apply non-interactively (skip the pause)
python analysis/apply_and_measure.py apply E-WRONG-ENTITY:0 --accept

# Run a slice + parse + panel
python analysis/apply_and_measure.py run venmo-smoke-5 \
    --baseline /tmp/baseline.json

# Full cycle: propose → verify → apply → run → panel (single fix)
python analysis/apply_and_measure.py cycle E-WRONG-ENTITY:0 \
    --slice venmo-smoke-5 \
    --baseline /tmp/baseline.json \
    [--revert] [--accept] [--force-dirty]

# ── AUTO-CYCLE (fully automated loop) ──
# Runs all 5 stages end-to-end:
#   1+2: baseline run + parse
#   3:   rank all proposed fixes by priority
#   4:   for each fix: propose patch → apply → re-run → measure
#   5:   if score improved → keep; if not → revert and try next fix
python analysis/apply_and_measure.py auto-cycle --slice venmo-smoke-5

# Limit to the top N fixes
python analysis/apply_and_measure.py auto-cycle --slice venmo-smoke-5 --max-fixes 3
```

## 7. Stage 5 — EVALUATE (keep or revert)

### What it does
After Stage 4 applies a fix and re-runs the slice, Stage 5 compares the new run's **composite score** to the baseline score. If the score improved, the fix is kept and becomes the new baseline for the next fix attempt. If the score did not improve, the fix is reverted and the loop moves to the next fix in the ranked list from Stage 3.

### Composite score formula
```
score = tasks_correct × 10 + assertions_passed_pct
```

Fully correct tasks (100% assertions) carry heavy weight (×10) because they are the benchmark's real success metric. Partial assertion improvements are also tracked so near-misses contribute.

Examples:
- 0 correct, 45% assertions → 0 + 45 = **45**
- 1 correct, 45% assertions → 10 + 45 = **55** (one full task = +10 jump)
- 2 correct, 60% assertions → 20 + 60 = **80**

Implemented in `score_run(report)` in [`apply_and_measure.py`](apply_and_measure.py).

### Decision rule
`new_score > current_score` → **keep**. Strictly greater — ties are reverted (same-score patches carry risk for no benefit).

### Cost log
Every LLM call appends one line to `analysis/cost_log.jsonl`:
```json
{
  "ts": "2026-05-22T18:30:11",
  "fix_id": "E-WRONG-ENTITY:0",
  "phase": "propose_patch",
  "model": "gpt-4.1-mini",
  "usage": {"prompt_tokens": 2042, "completion_tokens": 1818},
  "cost_usd": 0.003729,
  "elapsed_s": 6.42
}
```

Plus a `cycle_total` record per full cycle. Lets us compute total spend with one command:
```bash
jq -s 'map(.cost_usd // 0) | add' analysis/cost_log.jsonl
```

---

## 7. End-to-end walkthrough

Here is how a single autonomous improvement iteration looks in practice.

### Setup
- The user has run a baseline (e.g. `bv1ew2sc3`) and saved its report at `/tmp/baseline.json`.
- The user identifies the highest-priority outstanding fix (e.g. `E-WRONG-ENTITY:0`).

### Command
```bash
cd LARA-sub_agents/LARA
python analysis/apply_and_measure.py cycle E-WRONG-ENTITY:0 \
    --slice venmo-smoke-5 \
    --baseline /tmp/baseline.json
```

### Sequence
1. **Wrapper resolves fix.** Reads `fix_mappings.json`, finds `E-WRONG-ENTITY`'s `fixes[0]`. Surface: `explorer_prompt`.
2. **Surface lookup.** Reads [`surfaces_config.py`](surfaces_config.py) — finds `prompts.py` + marker `explorer_prompt:semantic_api_selection`.
3. **Region extraction.** Reads the file, finds the BEGIN/END sentinels, extracts the text between them.
4. **LLM call.** Sends system prompt + fix description + region to `gpt-4.1-mini`. Receives the patched region.
5. **Cost logged.** ~$0.004, ~10s elapsed.
6. **Preservation check.** New region length ≥ 70% old; ≥ 70% of distinctive lines preserved. Pass.
7. **Git-clean check.** `git status --porcelain` is empty. Pass.
8. **Human review pause.** Prints old/new diff. User types `y`.
9. **Apply.** Writes new region into `prompts.py`.
10. **Syntax check.** `python -c 'import prompts; prompts.build_explorer_system("test")'`. Pass.
11. **Run slice.** Tees stdout to `/tmp/lara_cycle_E-WRONG-ENTITY_0_<timestamp>.log`. ~2 min.
12. **Parse log.** Writes structured report to `/tmp/lara_cycle_..._report.json`.
13. **Compute panel.** Loads baseline + current report; computes deltas; prints the panel.
14. **(Optional) Revert.** If `--revert` was passed, `git checkout -- prompts.py`.

### Output
- Panel showing scores, category deltas, behavioral counter deltas.
- All artifacts (log, report, panel) persisted with timestamped names so the run is reproducible / auditable.
- One entry to be appended to `Autonomous Loop - Experiments.docx` with the fix ID, panel summary, and outcome.

---

## 8. Schemas at a glance

| Artifact | Schema version | Owns key |
|---|---|---|
| `error_categories.json` | 1 | `code` |
| `behavioral_signals.json` | 1 | `name` |
| `fix_mappings.json` | 1 | `category_code` |
| `slices.json` | 1 | (slice name) |

All schemas are versioned. A schema change requires updating consumers (parser, panel, wrapper).

---

## 9. Failure modes and what handles them

### LLM produces a bad patch
- **Truncation** — preservation check (region must be ≥70% old length).
- **Loss of important rules** — preservation check (≥70% of distinctive lines must remain).
- **Wrong file affected** — surfaces_config restricts the region; the LLM only sees the marked region.
- **Syntax error** — `compile()` / `json.loads()` after write; auto-revert via `git checkout`.

### Benchmark crashes mid-run
- The parser includes a `status="incomplete"` task entry with whatever it could read.
- `flow_crash` field captures the LangGraph recursion_limit / exception text.
- The panel still renders; incomplete tasks are tracked separately in the scores section.

### Working tree was already dirty
- The wrapper refuses to apply unless `git status --porcelain` is empty.
- `--force-dirty` overrides, but the rollback may be partial.

### Category drift
- Adding/renaming a category in the dictionary changes what the parser tags.
- Reports parsed with different dictionary versions are **not directly comparable**. The baseline used in a delta should have been parsed with the SAME dictionary version as the current run.
- For now this is a manual discipline. Future: include the dictionary's `last_updated` field in each report and warn on mismatch.

### Signature false-positives
- A counter or category signature might match incidental text (e.g. `datetime.now()` mentioned in a comment).
- Mitigation: regex patterns can be tightened. Verified by reading the panel output and re-checking the trace.

---

## 10. Limitations (v2)

### Only one surface registered
[`surfaces_config.py`](surfaces_config.py) only has `explorer_prompt`. To apply fixes targeting `venmo_specialist`, `phone_specialist`, `executor_react_prompt`, `bootstrap_helpers`, `orchestrator_guard`, etc., you must first mark up those files with `=== SURFACE: <label> === BEGIN/END` sentinels and add entries to `SURFACES`. This limits `auto-cycle` to fixes on the explorer_prompt surface.

### No multi-file patches
Each fix entry maps to one surface, hence one file. Fixes that need to change a specialist prompt AND a bootstrap helper together (e.g. some E-EXEC-WRONG-TOKEN proposals) must be split into two fix entries.

### No retry on preservation failure
If the LLM returns a truncated patch, the wrapper rejects and skips to the next fix. A future enhancement could retry once with a stricter prompt.

### No per-task regression guard
Stage 5 compares the composite score (tasks_correct × 10 + assertions_pct). A fix could improve one task while regressing another and still get kept if the net score is positive. A stricter variant would also require no previously-correct task to regress.

### Slice config has no parameter enforcement
The `params` field in `slices.json` documents what params were used, but the slice runner does not enforce them at runtime. Today the params come from `config.py`. To enforce, we'd need the wrapper to override `config.py` values when running a slice.

### Positional variance on small slices
As discovered in the E-WRONG-ENTITY:0 experiment (2026-05-24), gpt-4.1-nano is positionally sensitive — adding a few lines to a prompt can change behavior on unrelated tasks. On 5-task slices this creates noise. Larger slices (10-20 tasks) would give cleaner A/B signals.

---

## 11. How to extend the loop

### Adding a new failure category
1. Identify the failure mode in a real run trace.
2. Add an entry to `error_categories.json` with a stable `code`, description, stage, and signature (substring or structural rule).
3. If structural, add the detection rule to `parse_run.py`'s `_tag_structural_categories`.
4. Add a corresponding entry to `fix_mappings.json` with ≥1 candidate fix.
5. Re-parse historical runs (their reports become richer; baseline comparability resets).

### Adding a new behavioral counter
1. Identify the signal you want to track (an antipattern, good pattern, or neutral observation).
2. Add an entry to `behavioral_signals.json` with: name, kind, scope, pattern_type, patterns, added_in_run, added_for.
3. Patterns are substring (literal) or regex (Python `re`).
4. The panel auto-includes the new counter on the next run; no code change needed.

### Adding a new surface
1. Pick the file (e.g. `app_agents/venmo.py`).
2. Identify the editable region (e.g. the `app_system_prompt` body).
3. Add `=== SURFACE: <surface_key>:<label> === BEGIN/END` sentinels.
4. Register the surface in `surfaces_config.py` `SURFACES` dict.
5. Now fixes with `surface = <surface_key>` can be applied via the wrapper.

### Adding a new slice
1. Add an entry to `slices.json`: name, dataset, task_ids, params, purpose, created_in_run.
2. The slice is now invocable via `python analysis/run_slice.py <name>`.
3. To find candidate task IDs: `python -c "from benchmark import find_tasks_by_app; print(find_tasks_by_app('gmail'))"`.

### Changing the prioritization weights
Edit `~/.claude/projects/.../memory/project_fix_prioritization.md` and update the "Safety-driven weights" line. Re-score outstanding fixes by hand. (Future: move into a computed function.)

---

## 12. Glossary

- **Slice** — a pinned, named set of task IDs + runtime parameters. Reproducible across sessions.
- **Surface** — the editing target of a fix (e.g. `explorer_prompt`). Maps 1:1 to a file region with markers.
- **Fix entry** — one candidate change for one category, with a description, surface, tractability, and status.
- **Fix ID** — `<CATEGORY_CODE>:<index>` (e.g. `E-WRONG-ENTITY:0`). Stable across sessions if the mapping isn't reordered.
- **Category** — a named failure mode (e.g. `E-WRONG-ENTITY`).
- **Counter** — a behavioral signal (e.g. `phone_login_401`). Has a kind (antipattern / good_pattern / neutral) and a scope.
- **Panel** — the delta table (scores + categories + counters) emitted by `panel.py`.
- **Cycle** — one full pass through Stages 3+4: propose → apply → run → measure.
- **Iteration** — one execution of the slice within a cycle.
- **Manual discovery** — adding categories/counters/fixes from human inspection of new traces.
- **Automated improvement** — running cycles against existing categories/counters/fixes without human-in-the-loop on each decision.

---

## 13. Quick reference — full command flow

### Fully automated (recommended)
```bash
# One command does everything: baseline → prioritize → try each fix → keep/revert
python analysis/apply_and_measure.py auto-cycle --slice venmo-smoke-5

# Limit to the top 3 fixes
python analysis/apply_and_measure.py auto-cycle --slice venmo-smoke-5 --max-fixes 3
```

### Manual (step by step)
```bash
# 1. Run a baseline
python analysis/run_slice.py venmo-smoke-5 \
    --log-to /tmp/baseline.log \
    --auto-parse
# → produces /tmp/baseline.report.json

# 2. See what's broken
python analysis/parse_run.py /tmp/baseline.log --summary

# 3. Prioritize fixes automatically
python analysis/apply_and_measure.py prioritize --slice venmo-smoke-5

# 4. List all candidate fixes (raw, no scoring)
python analysis/apply_and_measure.py list

# 5. Inspect a proposed patch (cheap; no apply)
python analysis/apply_and_measure.py propose-patch E-WRONG-ENTITY:0

# 6. Apply a fix interactively
python analysis/apply_and_measure.py apply E-WRONG-ENTITY:0

# 7. Run the slice again and see the delta
python analysis/run_slice.py venmo-smoke-5 \
    --log-to /tmp/post_fix.log \
    --auto-parse --auto-panel \
    --baseline /tmp/baseline.report.json

# Or, single fix in one command:
python analysis/apply_and_measure.py cycle E-WRONG-ENTITY:0 \
    --slice venmo-smoke-5 \
    --baseline /tmp/baseline.report.json

# Total cost: ~$0.025 per cycle (patch ~$0.004 + benchmark ~$0.02).
# Auto-cycle with N fixes: ~$0.025 × (N+1) (one baseline + N fix runs).
```

---

*Last updated: 2026-05-25 — v2: automated Stage 3 + auto-cycle + Stage 5 evaluate.*
