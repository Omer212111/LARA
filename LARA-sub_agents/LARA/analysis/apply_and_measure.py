"""
LARA — Apply-and-measure wrapper (loop closer)

Closes the iteration loop:
  pick fix  →  GPT-4.1 writes patch  →  verify  →  apply (git-stash protected)
  →  run pinned slice  →  parse  →  panel  →  optionally revert.

Subcommands:
    list                              List candidate fixes from fix_mappings.json.
    prioritize --slice S              Score & rank all proposed fixes by priority.
    propose-patch <fix_id>            Generate a patch via GPT-4.1; print it; don't apply.
    apply <fix_id> [--accept]         Generate + verify + apply (git-stash protected).
                                      Pauses for human review unless --accept.
    run <slice_name> [--baseline P]   Run the slice + parse + panel (wraps run_slice).
    cycle <fix_id> --slice S          Full loop: stash → apply → verify → run → panel
        [--baseline P] [--revert]     → optionally revert to pre-cycle state.
    auto-cycle --slice S              Automated loop: run baseline → prioritize fixes →
                                      try each fix in priority order → keep if score
                                      improves, revert & try next if not.

Identity of a fix: "<category_code>:<index>" where index is the 0-based position
of the fix entry inside that category's fixes list. Use `list` to see IDs.

Each LLM call appends to analysis/cost_log.jsonl with token + estimated cost.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
LARA_ROOT = HERE.parent
FIX_MAPPINGS_PATH = HERE / "fix_mappings.json"
COST_LOG_PATH = HERE / "cost_log.jsonl"

# Ensure `import analysis.*` works when this script is run directly from LARA/.
if str(LARA_ROOT) not in sys.path:
    sys.path.insert(0, str(LARA_ROOT))


# ── Pricing (USD per 1M tokens) ───────────────────────────────────────────────
# Project has access to: gpt-4.1-mini, gpt-4.1-nano, gpt-5-nano.
# Default to gpt-4.1-mini for patch generation — strong enough for prompt edits
# without using the same nano model the agent itself runs on.
PRICING = {
    "gpt-4.1-mini": {"input_per_1m": 0.40, "output_per_1m": 1.60},
    "gpt-4.1-nano": {"input_per_1m": 0.10, "output_per_1m": 0.40},
    "gpt-5-nano":   {"input_per_1m": 0.05, "output_per_1m": 0.40},
}
DEFAULT_MODEL = "gpt-4.1-mini"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_dotenv():
    """Minimal .env loader so OPENAI_API_KEY is available even without python-dotenv."""
    env_path = LARA_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _load_fix_mappings() -> dict:
    with FIX_MAPPINGS_PATH.open() as f:
        return json.load(f)


def _parse_fix_id(fix_id: str) -> tuple[str, int]:
    if ":" not in fix_id:
        raise SystemExit(f"Bad fix id: {fix_id!r}. Expected '<CATEGORY>:<index>'.")
    code, idx = fix_id.split(":", 1)
    try:
        return code, int(idx)
    except ValueError:
        raise SystemExit(f"Bad fix id: {fix_id!r}. Index must be an integer.")


def _resolve_fix(fix_id: str) -> tuple[dict, dict]:
    """Return (category_entry, fix_entry) or raise."""
    code, idx = _parse_fix_id(fix_id)
    data = _load_fix_mappings()
    for m in data["mappings"]:
        if m["category_code"] == code:
            fixes = m["fixes"]
            if idx < 0 or idx >= len(fixes):
                raise SystemExit(
                    f"Fix index {idx} out of range for {code} (has {len(fixes)} fixes)."
                )
            return m, fixes[idx]
    raise SystemExit(f"Category {code!r} not found in fix_mappings.json.")


# ── Marker extraction / replacement ───────────────────────────────────────────

def _build_marker_re(label: str) -> tuple[re.Pattern, re.Pattern]:
    begin = re.compile(
        rf"=== SURFACE:\s*{re.escape(label)}\s*===\s*BEGIN\s*\n", re.MULTILINE
    )
    end = re.compile(
        rf"\n=== SURFACE:\s*{re.escape(label)}\s*===\s*END", re.MULTILINE
    )
    return begin, end


def _extract_region(file_path: Path, label: str) -> tuple[str, int, int]:
    """Return (region_text, start_offset, end_offset) for the marked region.
    start_offset and end_offset are positions in the file content (UTF-8 chars)."""
    text = file_path.read_text()
    begin_re, end_re = _build_marker_re(label)
    b = begin_re.search(text)
    if not b:
        raise SystemExit(
            f"BEGIN marker for {label!r} not found in {file_path}. "
            f"Mark the editable region with `=== SURFACE: {label} === BEGIN/END`."
        )
    e = end_re.search(text, b.end())
    if not e:
        raise SystemExit(
            f"END marker for {label!r} not found after BEGIN in {file_path}."
        )
    return text[b.end():e.start()], b.end(), e.start()


def _replace_region(file_path: Path, label: str, new_region: str) -> None:
    text = file_path.read_text()
    begin_re, end_re = _build_marker_re(label)
    b = begin_re.search(text)
    e = end_re.search(text, b.end())
    new_text = text[:b.end()] + new_region + text[e.start():]
    file_path.write_text(new_text)


# ── LLM call ──────────────────────────────────────────────────────────────────

PATCH_SYSTEM_PROMPT = """You are an editor for the LARA AppWorld agent's prompts. \
You are given:
  (1) A failure category with a description.
  (2) A proposed fix description: which surface to edit and the change rationale.
  (3) The current text of ONE editable region of a target file, delimited by
      markers. You must return ONLY the NEW text for that region.

Rules:
  - Output ONLY the new region text. NO markdown fences, NO commentary, NO
    sentinel lines (the wrapper re-adds those).
  - Preserve existing structure unless the fix explicitly asks to remove it.
  - Add new rules/examples additively when possible.
  - Keep the same indentation style and line width as the surrounding text.
  - If the fix description is unclear or doesn't apply, return the region UNCHANGED.
"""


def _call_gpt(model: str, system: str, user: str,
              max_completion_tokens: int = 6000) -> tuple[str, dict]:
    """Single GPT call. Returns (content, usage_dict)."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY not set (load failed). Aborting.")

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=max_completion_tokens,
    )
    msg = resp.choices[0].message.content or ""
    usage = {
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
    }
    return msg, usage


def _estimate_cost(model: str, usage: dict) -> float:
    p = PRICING[model]
    return (
        usage["prompt_tokens"] / 1_000_000 * p["input_per_1m"]
        + usage["completion_tokens"] / 1_000_000 * p["output_per_1m"]
    )


def _log_cost(record: dict) -> None:
    with COST_LOG_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")


# ── Patch proposal ────────────────────────────────────────────────────────────

def propose_patch(fix_id: str, model: str = DEFAULT_MODEL,
                  logger: "LoopLogger | None" = None) -> dict:
    """Produce a proposed new-region text for a fix. Does not modify any file."""
    from analysis.surfaces_config import get_surface

    category, fix = _resolve_fix(fix_id)
    surface = get_surface(fix["surface"])
    if surface is None:
        if logger:
            logger.error("stage_3", f"Surface {fix['surface']!r} not registered")
        raise SystemExit(
            f"Surface {fix['surface']!r} is not yet registered with markers. "
            f"Run the marker-bootstrap pass for this surface before applying."
        )

    region_text, _start, _end = _extract_region(surface.file_path, surface.marker_label)

    if logger:
        logger.stage_3_resolve_fix(
            category, fix,
            surface_info={
                "file_path": str(surface.file_path),
                "marker_label": surface.marker_label,
                "old_region_chars": len(region_text),
            },
        )
        logger.stage_4a_propose_start(model=model, region_chars=len(region_text))

    user_msg = (
        f"## Failure category\n"
        f"Code: {category['category_code']}\n"
        f"## Fix description\n"
        f"Surface: {fix['surface']}\n"
        f"Description: {fix['description']}\n"
        f"Rationale: {fix.get('rationale', '')}\n"
        f"## Current region (between markers, exclusive)\n"
        f"---\n{region_text}\n---\n"
        f"## Task\n"
        f"Return ONLY the new region text. No fences, no commentary."
    )

    t0 = time.time()
    new_region, usage = _call_gpt(model, PATCH_SYSTEM_PROMPT, user_msg)
    elapsed = time.time() - t0

    cost = _estimate_cost(model, usage)
    _log_cost({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fix_id": fix_id,
        "phase": "propose_patch",
        "model": model,
        "usage": usage,
        "cost_usd": round(cost, 6),
        "elapsed_s": round(elapsed, 2),
    })

    if logger:
        logger.stage_4a_propose_end(
            model=model, usage=usage, cost_usd=cost,
            new_region_chars=len(new_region), elapsed_s=elapsed,
        )

    return {
        "fix_id": fix_id,
        "category_code": category["category_code"],
        "surface": fix["surface"],
        "file_path": str(surface.file_path),
        "marker_label": surface.marker_label,
        "old_region": region_text,
        "new_region": new_region,
        "usage": usage,
        "cost_usd": cost,
    }


# ── Verification ──────────────────────────────────────────────────────────────

def _verify_region_preservation(old: str, new: str,
                                 min_ratio: float = 0.7) -> str | None:
    """Heuristic check: the new region should preserve most distinctive lines
    from the old. If the new is dramatically shorter or drops major anchors,
    reject.  Returns None if OK, else error message."""
    # Length check — new should not lose more than (1 - min_ratio) of the old.
    if len(new) < min_ratio * len(old):
        return (
            f"New region is {len(new)} chars vs old {len(old)} "
            f"({len(new)/len(old):.0%}); below the {min_ratio:.0%} preservation threshold. "
            f"Likely the LLM truncated content."
        )
    # Anchor check — every line in the old that is "distinctive" (length > 40,
    # not a separator, not a blank) should appear (verbatim or near-verbatim)
    # in the new region.
    distinctive = [
        ln.strip() for ln in old.splitlines()
        if len(ln.strip()) > 40 and not set(ln.strip()) <= set("─=-_ \t")
    ]
    missing = [ln for ln in distinctive if ln not in new]
    drop_ratio = len(missing) / max(len(distinctive), 1)
    if drop_ratio > 0.3:
        return (
            f"{len(missing)} of {len(distinctive)} distinctive lines "
            f"({drop_ratio:.0%}) missing from new region. Examples: "
            f"{missing[:3]}"
        )
    return None


def _verify_python(file_path: Path) -> str | None:
    """Return None if OK, else error message."""
    try:
        compile(file_path.read_text(), str(file_path), "exec")
        return None
    except SyntaxError as e:
        return f"SyntaxError in {file_path}: {e}"


def _verify_json(file_path: Path) -> str | None:
    try:
        json.loads(file_path.read_text())
        return None
    except json.JSONDecodeError as e:
        return f"JSONDecodeError in {file_path}: {e}"


def _verify_changed_file(file_path: Path) -> str | None:
    suffix = file_path.suffix.lower()
    if suffix == ".py":
        return _verify_python(file_path)
    if suffix == ".json":
        return _verify_json(file_path)
    return None


import shutil

ROLLBACK_DIR_BASE = Path("/tmp/lara_rollback")


def _snapshot_file(file_path: Path, label: str = "") -> Path:
    """Copy file_path to a timestamped rollback directory; return the snapshot path.
    The snapshot is the rollback safety net — independent of git."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    snap_dir = ROLLBACK_DIR_BASE / f"{ts}{suffix}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / file_path.name
    shutil.copy2(file_path, snap_path)
    return snap_path


def _restore_from_snapshot(file_path: Path, snapshot_path: Path) -> None:
    """Restore file_path from a previously-taken snapshot."""
    if not snapshot_path.exists():
        raise SystemExit(
            f"Cannot restore {file_path}: snapshot {snapshot_path} missing."
        )
    shutil.copy2(snapshot_path, file_path)


# ── Apply / revert ────────────────────────────────────────────────────────────

def apply_fix(fix_id: str, proposal: dict | None = None,
              accept: bool = False, force_dirty: bool = False,
              logger: "LoopLogger | None" = None) -> dict:
    """Apply a patch: snapshot target, write new region, verify, optionally pause."""
    if proposal is None:
        proposal = propose_patch(fix_id, logger=logger)

    # Structural-preservation check BEFORE asking the user.
    pres_err = _verify_region_preservation(
        proposal["old_region"], proposal["new_region"]
    )
    if logger:
        logger.stage_4b_verify_preservation(
            passed=(pres_err is None), detail=pres_err,
            old_chars=len(proposal["old_region"]),
            new_chars=len(proposal["new_region"]),
        )
    if pres_err and not accept:
        print(f"⚠️  Region-preservation check FAILED: {pres_err}")
        print("Refusing to apply by default. Re-run with --accept to override.")
        return {"applied": False, "preservation_error": pres_err, **proposal}

    if not accept:
        print("=" * 78)
        print(f"Proposed patch for {fix_id}")
        print(f"  file: {proposal['file_path']}")
        print(f"  marker: {proposal['marker_label']}")
        print(f"  estimated cost: ${proposal['cost_usd']:.4f}")
        print("=" * 78)
        print("--- OLD ---")
        print(proposal["old_region"])
        print("--- NEW ---")
        print(proposal["new_region"])
        print("=" * 78)
        reply = input("Apply this patch? [y/N] ").strip().lower()
        if reply != "y":
            print("Aborted.")
            return {"applied": False, **proposal}

    # Snapshot the target BEFORE modifying it — this is the rollback safety net.
    file_path = Path(proposal["file_path"])
    snapshot_path = _snapshot_file(file_path, label=fix_id.replace(":", "_"))
    print(f"Snapshot: {snapshot_path}")
    if logger:
        logger.stage_4c_snapshot(str(file_path), str(snapshot_path))

    # Apply
    _replace_region(file_path, proposal["marker_label"], proposal["new_region"])
    if logger:
        logger.stage_4c_apply(str(file_path))

    # Verify
    err = _verify_changed_file(file_path)
    if logger:
        logger.stage_4c_syntax_check(
            str(file_path), passed=(err is None), error=err,
        )
    if err:
        _restore_from_snapshot(file_path, snapshot_path)
        raise SystemExit(f"Patch failed verification — reverted from snapshot. {err}")

    print(f"Applied patch to {file_path}.")
    return {"applied": True, "snapshot_path": str(snapshot_path), **proposal}


def revert_file(file_path: Path, snapshot_path: Path | str) -> None:
    """Restore file_path from the snapshot taken at apply time."""
    _restore_from_snapshot(file_path, Path(snapshot_path))


# ── Run / measure ─────────────────────────────────────────────────────────────

def run_and_measure(slice_name: str, log_path: str, baseline: str | None,
                    logger: "LoopLogger | None" = None) -> dict:
    """Wrap run_slice.run_slice + parse_run.parse_run + panel.compute_panel."""
    # Ensure analysis is importable.
    if str(LARA_ROOT) not in sys.path:
        sys.path.insert(0, str(LARA_ROOT))

    from analysis.run_slice import run_slice
    from analysis.parse_run import parse_run
    from analysis.panel import compute_panel, render_panel

    # Load slice task_ids so the logger has them.
    task_ids: list[str] = []
    try:
        slices_path = LARA_ROOT / "analysis" / "slices.json"
        slice_def = json.loads(slices_path.read_text())["slices"].get(slice_name, {})
        task_ids = slice_def.get("task_ids", [])
    except Exception:
        pass

    if logger:
        logger.stage_4d_run_start(task_ids=task_ids, log_path=log_path)

    # Tee output ourselves so we can panel on the saved log afterwards.
    # AppWorld's sandbox introspects sys.stdout.fileno() etc., so we must
    # forward unknown attribute access to the real underlying stream.
    real_stdout = sys.stdout
    log_file = open(log_path, "w", buffering=1)

    class _Tee:
        def write(self, data):
            real_stdout.write(data); real_stdout.flush()
            log_file.write(data); log_file.flush()
        def flush(self):
            real_stdout.flush(); log_file.flush()
        def __getattr__(self, name):
            return getattr(real_stdout, name)

    sys.stdout = _Tee()
    t_run = time.time()
    try:
        run_slice(slice_name)
    finally:
        sys.stdout = real_stdout
        log_file.close()
    run_elapsed = time.time() - t_run

    report = parse_run(log_path)
    report_path = log_path.rsplit(".", 1)[0] + ".report.json"
    Path(report_path).write_text(json.dumps(report, indent=2, default=str))

    if logger:
        bs = report.get("benchmark_summary") or {}
        logger.stage_4d_run_end(
            elapsed_s=run_elapsed,
            correct=bs.get("correct", 0),
            total=bs.get("total", len(task_ids)),
        )
        # Per-task close events
        for t in report.get("tasks", []):
            fs = t.get("final_score") or {}
            logger.stage_4d_task_close(
                task_id=t["task_id"],
                status=t.get("status", "unknown"),
                pass_count=fs.get("pass", 0) or 0,
                total=fs.get("total", 0) or 0,
            )
        logger.stage_4d_parse_end(
            report_path=report_path,
            category_counts=report.get("category_counts", {}),
        )

    baseline_report = None
    if baseline:
        baseline_report = json.loads(Path(baseline).read_text())

    panel = compute_panel(report, baseline_report)
    print()
    print(render_panel(panel))

    if logger:
        # Surface retired (was>0, now=0) and NEW (was=0, now>0) categories.
        cats = panel.get("categories", {})
        retired = [k for k, d in cats.items()
                   if d.get("baseline") and d["baseline"] > 0 and d["value"] == 0]
        new_cats = [k for k, d in cats.items()
                    if d.get("baseline") == 0 and d["value"] > 0]
        logger.stage_4d_panel_end(
            scores_summary=panel.get("scores", {}),
            retired_categories=retired,
            new_categories=new_cats,
        )

    return {"log": log_path, "report": report_path, "panel": panel}


# ── Full cycle ────────────────────────────────────────────────────────────────

def cycle(fix_id: str, slice_name: str, baseline: str | None,
          revert: bool = False, accept: bool = False,
          force_dirty: bool = False) -> dict:
    """propose → apply → run → panel → maybe revert."""
    from analysis.loop_logger import LoopLogger

    t0 = time.time()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = f"/tmp/lara_cycle_{fix_id.replace(':','_')}_{timestamp}.log"

    with LoopLogger.for_cycle(
        fix_id=fix_id, slice_name=slice_name, baseline_path=baseline,
    ) as logger:
        logger.cycle_start({
            "fix_id": fix_id, "slice_name": slice_name,
            "baseline": baseline, "revert": revert,
            "accept": accept, "force_dirty": force_dirty,
            "cycle_log_path": log_path,
        })

        proposal = propose_patch(fix_id, logger=logger)
        apply_result = apply_fix(
            fix_id, proposal=proposal, accept=accept,
            force_dirty=force_dirty, logger=logger,
        )
        if not apply_result.get("applied"):
            logger.cycle_end(
                outcome="aborted_at_apply",
                total_cost_usd=proposal.get("cost_usd"),
                notes=apply_result.get("preservation_error"),
            )
            return {"status": "aborted_at_apply", "fix_id": fix_id}

        file_path = Path(proposal["file_path"])
        snapshot_path = apply_result["snapshot_path"]
        try:
            run_result = run_and_measure(slice_name, log_path, baseline,
                                         logger=logger)
        except Exception as e:
            print(f"Run failed: {e}. Reverting {file_path} from snapshot.")
            logger.error("stage_4d_run", str(e), exc=e)
            revert_file(file_path, snapshot_path)
            logger.cycle_end(
                outcome="run_crashed_reverted",
                total_cost_usd=proposal.get("cost_usd"),
            )
            raise

        if revert:
            print(f"--revert: rolling back {file_path} from snapshot.")
            revert_file(file_path, snapshot_path)
            outcome = "reverted_after_run"
        else:
            outcome = "kept"

        elapsed = time.time() - t0
        _log_cost({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "fix_id": fix_id,
            "phase": "cycle_total",
            "elapsed_s": round(elapsed, 2),
        })

        logger.cycle_end(
            outcome=outcome,
            total_cost_usd=proposal.get("cost_usd"),
            total_elapsed_s=elapsed,
        )
        text_path, jsonl_path = logger.paths
        print(f"\nLoop logs: {text_path}")
        print(f"           {jsonl_path}")

    return {"status": "ok", "fix_id": fix_id, "elapsed_s": elapsed, **run_result}


# ── Composite run score ──────────────────────────────────────────────────────
# Fully correct tasks (100% assertions) carry heavy weight — they are the
# benchmark's real success metric.  Partial assertion progress is tracked too
# so that near-misses aren't invisible.
#
#   score = tasks_correct × 10 + assertions_passed_pct
#
# Examples:
#   0 correct, 45% assertions  →  0 + 45   = 45
#   1 correct, 45% assertions  → 10 + 45   = 55   (+10 jump from 1 task)
#   2 correct, 60% assertions  → 20 + 60   = 80

def score_run(report: dict) -> float:
    """Compute a composite success score from a parsed run report."""
    tasks = report.get("tasks", [])
    tasks_correct = sum(1 for t in tasks if t.get("status") == "correct")
    pass_sum = sum(
        (t.get("final_score") or {}).get("pass", 0) or 0 for t in tasks
    )
    total_sum = sum(
        (t.get("final_score") or {}).get("total", 0) or 0 for t in tasks
    )
    pct = (pass_sum / total_sum * 100.0) if total_sum > 0 else 0.0
    return tasks_correct * 10 + pct


# ── Automated Stage 3 — prioritize fixes ─────────────────────────────────────
# priority = impact × 2 + cluster_coverage × 2 + tractability × 3
#
#   impact (1/3/5)           — derived from category_counts in the latest report
#   cluster_coverage (1/3/5) — how many active categories share this fix's surface
#   tractability (1/3/5)     — from fix_mappings.json

def prioritize_fixes(report: dict) -> list[dict]:
    """Score and rank all PROPOSED fixes against the latest run report.

    Returns a list of dicts sorted by descending priority:
        [{fix_id, category_code, priority, impact, cluster, tractability,
          surface, description}, ...]
    """
    from analysis.surfaces_config import get_surface

    data = _load_fix_mappings()
    cat_counts = report.get("category_counts", {})
    total_tasks = len(report.get("tasks", []))

    # Which categories are active (appeared at least once in this run)?
    active_codes = {c for c, n in cat_counts.items() if n > 0}

    # For cluster_coverage: group active categories by surface.
    # A fix on surface X retires all active categories that have a fix on X.
    surface_to_active_cats: dict[str, set[str]] = {}
    for m in data["mappings"]:
        code = m["category_code"]
        if code not in active_codes:
            continue
        for f in m["fixes"]:
            surface_to_active_cats.setdefault(f["surface"], set()).add(code)

    ranked = []
    for m in data["mappings"]:
        code = m["category_code"]
        for i, fix in enumerate(m["fixes"]):
            if fix["status"] != "proposed":
                continue
            if get_surface(fix["surface"]) is None:
                continue

            fix_id = f"{code}:{i}"
            count = cat_counts.get(code, 0)
            if count == 0:
                continue

            # Impact: how many tasks this category hit relative to total
            if total_tasks > 0 and count > 0:
                ratio = count / total_tasks
                if ratio >= 0.5:
                    impact = 5
                elif ratio >= 0.25:
                    impact = 3
                else:
                    impact = 1
            else:
                impact = 0

            # Cluster: how many ACTIVE categories share this fix's surface
            siblings = surface_to_active_cats.get(fix["surface"], set())
            n_siblings = len(siblings)
            if n_siblings >= 3:
                cluster = 5
            elif n_siblings >= 2:
                cluster = 3
            else:
                cluster = 1

            tractability = fix.get("tractability", 3)

            priority = impact * 2 + cluster * 2 + tractability * 3

            ranked.append({
                "fix_id": fix_id,
                "category_code": code,
                "priority": priority,
                "impact": impact,
                "cluster": cluster,
                "tractability": tractability,
                "surface": fix["surface"],
                "description": fix["description"],
                "category_count": count,
            })

    ranked.sort(key=lambda x: x["priority"], reverse=True)
    return ranked


# ── Auto-cycle (Stages 3→4→5 loop) ──────────────────────────────────────────

def auto_cycle(slice_name: str, max_fixes: int = 0) -> dict:
    """Automated improvement loop.

    1. Run the baseline slice, parse, score.
    2. Prioritize all proposed fixes (Stage 3).
    3. For each fix in priority order (Stage 4):
       a. Propose patch → verify → apply.
       b. Re-run the slice, parse, score.
       c. If score improved → keep the fix, update the baseline.
       d. If score did NOT improve → revert and try the next fix.
    4. Print a summary of all attempted fixes and their outcomes.

    max_fixes=0 means try all; >0 limits the number of fixes attempted.
    """
    from analysis.loop_logger import LoopLogger
    from analysis.parse_run import parse_run

    print("=" * 78)
    print("LARA AUTO-CYCLE — Automated improvement loop")
    print("=" * 78)

    # ── Stage 1+2: Run baseline ──────────────────────────────────────────────
    print("\n── STAGE 1+2: Running baseline slice ──")
    ts = time.strftime("%Y%m%d_%H%M%S")
    baseline_log = f"/tmp/lara_autocycle_baseline_{ts}.log"

    baseline_result = run_and_measure(slice_name, baseline_log, baseline=None)
    baseline_report = json.loads(
        Path(baseline_result["report"]).read_text()
    )
    baseline_score = score_run(baseline_report)
    print(f"\nBaseline score: {baseline_score:.1f}")

    # ── Stage 3: Prioritize fixes ────────────────────────────────────────────
    print("\n── STAGE 3: Prioritizing fixes ──")
    ranked = prioritize_fixes(baseline_report)

    if not ranked:
        print("No applicable proposed fixes found. Exiting.")
        return {"status": "no_fixes", "baseline_score": baseline_score}

    if max_fixes > 0:
        ranked = ranked[:max_fixes]

    print(f"Found {len(ranked)} candidate fixes (sorted by priority):")
    for r in ranked:
        print(
            f"  {r['fix_id']:<32} priority={r['priority']:>2}  "
            f"(I={r['impact']} C={r['cluster']} T={r['tractability']})  "
            f"hits={r['category_count']}  {r['description'][:60]}"
        )

    # ── Stages 4+5: Try each fix ─────────────────────────────────────────────
    current_score = baseline_score
    current_report_path = baseline_result["report"]
    results: list[dict] = []
    fixes_kept = 0
    fixes_reverted = 0
    total_cost = 0.0

    for idx, fix_info in enumerate(ranked):
        fix_id = fix_info["fix_id"]
        print(f"\n{'─' * 78}")
        print(
            f"── STAGE 4: Fix {idx + 1}/{len(ranked)} — {fix_id} "
            f"(priority={fix_info['priority']})"
        )

        ts_fix = time.strftime("%Y%m%d_%H%M%S")
        fix_log = f"/tmp/lara_autocycle_{fix_id.replace(':', '_')}_{ts_fix}.log"

        with LoopLogger.for_cycle(
            fix_id=fix_id, slice_name=slice_name,
            baseline_path=current_report_path,
        ) as logger:
            logger.cycle_start({
                "fix_id": fix_id, "slice_name": slice_name,
                "baseline": current_report_path,
                "auto_cycle": True, "fix_rank": idx + 1,
                "current_score": current_score,
            })

            # 4a+4b: Propose and apply
            try:
                proposal = propose_patch(fix_id, logger=logger)
            except SystemExit as e:
                print(f"  ⚠️  Skipped (propose failed): {e}")
                logger.cycle_end(outcome="skipped_propose_failed", notes=str(e))
                results.append({
                    "fix_id": fix_id, "outcome": "skipped",
                    "reason": str(e),
                })
                continue

            total_cost += proposal.get("cost_usd", 0)

            apply_result = apply_fix(
                fix_id, proposal=proposal, accept=True,
                force_dirty=True, logger=logger,
            )
            if not apply_result.get("applied"):
                reason = apply_result.get("preservation_error", "apply refused")
                print(f"  ⚠️  Skipped (apply failed): {reason}")
                logger.cycle_end(
                    outcome="skipped_apply_failed",
                    notes=reason,
                    total_cost_usd=proposal.get("cost_usd"),
                )
                results.append({
                    "fix_id": fix_id, "outcome": "skipped",
                    "reason": reason,
                })
                continue

            file_path = Path(proposal["file_path"])
            snapshot_path = apply_result["snapshot_path"]

            # 4c+4d: Run and measure
            try:
                run_result = run_and_measure(
                    slice_name, fix_log, baseline=current_report_path,
                    logger=logger,
                )
            except Exception as e:
                print(f"  ❌ Run crashed: {e}. Reverting.")
                logger.error("stage_4d_run", str(e), exc=e)
                revert_file(file_path, snapshot_path)
                logger.cycle_end(
                    outcome="run_crashed_reverted",
                    total_cost_usd=proposal.get("cost_usd"),
                )
                results.append({
                    "fix_id": fix_id, "outcome": "reverted",
                    "reason": f"run crashed: {e}",
                })
                fixes_reverted += 1
                continue

            # Parse and score the new run
            new_report = json.loads(Path(run_result["report"]).read_text())
            new_score = score_run(new_report)

            # ── Stage 5: Keep or revert ──────────────────────────────────────
            delta = new_score - current_score
            print(f"\n  Score: {current_score:.1f} → {new_score:.1f} (delta={delta:+.1f})")

            if new_score > current_score:
                print(f"  ✅ KEPT — score improved by {delta:+.1f}")
                current_score = new_score
                current_report_path = run_result["report"]
                outcome = "kept"
                fixes_kept += 1
                logger.cycle_end(
                    outcome="kept",
                    total_cost_usd=proposal.get("cost_usd"),
                    notes=f"score {current_score - delta:.1f} → {current_score:.1f}",
                )
            else:
                print(f"  ❌ REVERTED — score did not improve (delta={delta:+.1f})")
                revert_file(file_path, snapshot_path)
                outcome = "reverted"
                fixes_reverted += 1
                logger.cycle_end(
                    outcome="reverted_score_not_improved",
                    total_cost_usd=proposal.get("cost_usd"),
                    notes=f"score {current_score:.1f} → {new_score:.1f}",
                )

            results.append({
                "fix_id": fix_id,
                "outcome": outcome,
                "score_before": current_score - delta if outcome == "kept" else current_score,
                "score_after": new_score,
                "delta": delta,
            })

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'=' * 78}")
    print("AUTO-CYCLE COMPLETE")
    print(f"{'=' * 78}")
    print(f"Baseline score:  {baseline_score:.1f}")
    print(f"Final score:     {current_score:.1f}")
    print(f"Net improvement: {current_score - baseline_score:+.1f}")
    print(f"Fixes kept:      {fixes_kept}")
    print(f"Fixes reverted:  {fixes_reverted}")
    print(f"Total LLM cost:  ${total_cost:.4f}")
    print()
    print(f"{'Fix ID':<32} {'Outcome':<10} {'Delta':>8}")
    print("─" * 56)
    for r in results:
        delta_str = f"{r.get('delta', 0):+.1f}" if "delta" in r else "n/a"
        print(f"  {r['fix_id']:<30} {r['outcome']:<10} {delta_str:>8}")

    return {
        "status": "ok",
        "baseline_score": baseline_score,
        "final_score": current_score,
        "net_improvement": current_score - baseline_score,
        "fixes_kept": fixes_kept,
        "fixes_reverted": fixes_reverted,
        "total_cost_usd": total_cost,
        "results": results,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cmd_list(args):
    data = _load_fix_mappings()
    for m in data["mappings"]:
        for i, f in enumerate(m["fixes"]):
            fix_id = f"{m['category_code']}:{i}"
            status = f["status"]
            tract = f.get("tractability", "?")
            short = f["description"][:80]
            print(f"  {fix_id:<32} [{status:<8}] tract={tract}  {short}")


def _cmd_prioritize(args):
    from analysis.parse_run import parse_run
    from analysis.run_slice import run_slice as _run_slice

    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = f"/tmp/lara_prioritize_{ts}.log"

    print(f"Running slice '{args.slice_name}' to generate a fresh report...")
    # Use _tee_to from run_slice module to capture output
    import contextlib
    from analysis.run_slice import _tee_to

    with _tee_to(log_path):
        _run_slice(args.slice_name)

    report = parse_run(log_path)
    ranked = prioritize_fixes(report)

    if not ranked:
        print("No applicable proposed fixes found.")
        return

    print(f"\n{'=' * 78}")
    print("PRIORITIZED FIX LIST")
    print(f"{'=' * 78}")
    print(f"{'#':<4} {'Fix ID':<32} {'Pri':>3}  {'I':>1} {'C':>1} {'T':>1}  "
          f"{'Hits':>4}  Description")
    print("─" * 78)
    for i, r in enumerate(ranked, 1):
        print(
            f"  {i:<2} {r['fix_id']:<32} {r['priority']:>3}  "
            f"{r['impact']:>1} {r['cluster']:>1} {r['tractability']:>1}  "
            f"{r['category_count']:>4}  {r['description'][:45]}"
        )


def _cmd_propose(args):
    p = propose_patch(args.fix_id, model=args.model)
    print(f"--- Proposed new region for {args.fix_id} ---")
    print(p["new_region"])
    print(f"--- cost: ${p['cost_usd']:.4f} ({p['usage']}) ---")


def _cmd_apply(args):
    apply_fix(args.fix_id, accept=args.accept, force_dirty=args.force_dirty)


def _cmd_run(args):
    run_and_measure(args.slice_name,
                    log_path=args.log_to or f"/tmp/lara_{int(time.time())}.log",
                    baseline=args.baseline)


def _cmd_cycle(args):
    cycle(args.fix_id, args.slice_name,
          baseline=args.baseline, revert=args.revert,
          accept=args.accept, force_dirty=args.force_dirty)


def _cmd_auto_cycle(args):
    auto_cycle(args.slice_name, max_fixes=args.max_fixes)


def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    s_list = sub.add_parser("list", help="List candidate fixes")
    s_list.set_defaults(func=_cmd_list)

    s_pri = sub.add_parser("prioritize",
                           help="Run a slice and rank all proposed fixes by priority")
    s_pri.add_argument("--slice", dest="slice_name", required=True)
    s_pri.set_defaults(func=_cmd_prioritize)

    s_prop = sub.add_parser("propose-patch", help="Generate a patch via GPT-4.1; don't apply")
    s_prop.add_argument("fix_id")
    s_prop.add_argument("--model", default=DEFAULT_MODEL)
    s_prop.set_defaults(func=_cmd_propose)

    s_app = sub.add_parser("apply", help="Generate + verify + apply (git-stash protected)")
    s_app.add_argument("fix_id")
    s_app.add_argument("--accept", action="store_true",
                       help="Skip the interactive review pause")
    s_app.add_argument("--force-dirty", action="store_true",
                       help="Apply even if the working tree isn't clean")
    s_app.set_defaults(func=_cmd_apply)

    s_run = sub.add_parser("run", help="Run a slice + parse + panel")
    s_run.add_argument("slice_name")
    s_run.add_argument("--baseline")
    s_run.add_argument("--log-to")
    s_run.set_defaults(func=_cmd_run)

    s_cyc = sub.add_parser("cycle", help="Full loop: propose → apply → run → panel")
    s_cyc.add_argument("fix_id")
    s_cyc.add_argument("--slice", dest="slice_name", required=True)
    s_cyc.add_argument("--baseline")
    s_cyc.add_argument("--revert", action="store_true",
                       help="Roll back the patch after the run")
    s_cyc.add_argument("--accept", action="store_true",
                       help="Skip the interactive review pause")
    s_cyc.add_argument("--force-dirty", action="store_true")
    s_cyc.set_defaults(func=_cmd_cycle)

    s_auto = sub.add_parser("auto-cycle",
                            help="Automated loop: baseline → prioritize → "
                                 "try each fix → keep or revert")
    s_auto.add_argument("--slice", dest="slice_name", required=True)
    s_auto.add_argument("--max-fixes", type=int, default=0,
                        help="Max fixes to try (0 = all)")
    s_auto.set_defaults(func=_cmd_auto_cycle)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
