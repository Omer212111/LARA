"""
LARA — Loop logger

Records the autonomous improvement loop's progress through its four stages.
Each cycle gets two files in analysis/logs/:

    <timestamp>_<fix_id>.log       — human-readable text (one event per line)
    <timestamp>_<fix_id>.events.jsonl — structured JSON Lines (same events)

Usage:
    from analysis.loop_logger import LoopLogger
    log = LoopLogger.for_cycle(fix_id="E-WRONG-ENTITY:0",
                               slice_name="venmo-smoke-5",
                               baseline_path="/tmp/baseline.json")
    log.cycle_start(args)
    log.stage_3_resolve_fix(category, fix, surface)
    log.stage_4a_propose_start(model)
    log.stage_4a_propose_end(usage, cost_usd, new_region_chars, elapsed_s)
    log.stage_4b_verify_preservation(passed=True, detail=...)
    log.stage_4c_snapshot(file_path, snapshot_path)
    log.stage_4c_apply(file_path)
    log.stage_4c_syntax_check(passed=True)
    log.stage_4d_run_start(task_ids)
    log.stage_4d_task_close(task_id, status, pass_count, total)
    log.stage_4d_run_end(elapsed_s)
    log.stage_4d_parse_end(report_path)
    log.stage_4d_panel_end(scores_summary)
    log.cycle_end(outcome="kept"|"reverted"|"aborted", total_cost, total_elapsed)
    log.close()

Or use as a context manager so close() is automatic:
    with LoopLogger.for_cycle(fix_id=..., slice_name=...) as log:
        ...
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
LOG_DIR = HERE / "logs"


# Event vocabulary — keep these stable; downstream tooling may key on them.
EV_CYCLE_START         = "CYCLE-START"
EV_STAGE_3_RESOLVE     = "STAGE-3-RESOLVE"
EV_STAGE_4A_START      = "STAGE-4A-PROPOSE-START"
EV_STAGE_4A_END        = "STAGE-4A-PROPOSE-END"
EV_STAGE_4B_PRESERVE   = "STAGE-4B-VERIFY-PRESERVE"
EV_STAGE_4C_SNAPSHOT   = "STAGE-4C-SNAPSHOT"
EV_STAGE_4C_APPLY      = "STAGE-4C-APPLY"
EV_STAGE_4C_SYNTAX     = "STAGE-4C-SYNTAX"
EV_STAGE_4D_RUN_START  = "STAGE-4D-RUN-START"
EV_STAGE_4D_TASK_CLOSE = "STAGE-4D-TASK-CLOSE"
EV_STAGE_4D_RUN_END    = "STAGE-4D-RUN-END"
EV_STAGE_4D_PARSE_END  = "STAGE-4D-PARSE-END"
EV_STAGE_4D_PANEL_END  = "STAGE-4D-PANEL-END"
EV_CYCLE_END           = "CYCLE-END"
EV_ERROR               = "ERROR"


class LoopLogger:
    """Per-cycle dual-output logger (human text + JSONL)."""

    def __init__(self, text_path: Path, jsonl_path: Path,
                 fix_id: str, slice_name: str):
        self.text_path = text_path
        self.jsonl_path = jsonl_path
        self.fix_id = fix_id
        self.slice_name = slice_name
        self._text_f = text_path.open("w", buffering=1)  # line-buffered
        self._jsonl_f = jsonl_path.open("w", buffering=1)
        self._t_start = time.time()

    @classmethod
    def for_cycle(cls, fix_id: str, slice_name: str,
                  baseline_path: str | None = None) -> "LoopLogger":
        """Create paired log files in analysis/logs/."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        slug = fix_id.replace(":", "_").replace("/", "_")
        text_path = LOG_DIR / f"{ts}_{slug}.log"
        jsonl_path = LOG_DIR / f"{ts}_{slug}.events.jsonl"
        return cls(text_path, jsonl_path, fix_id=fix_id, slice_name=slice_name)

    # ── Core writer ────────────────────────────────────────────────────────

    def _emit(self, event: str, line: str, data: dict[str, Any]) -> None:
        """Write one event to both outputs. `line` is the human form;
        `data` is everything except the boilerplate (fix_id, ts) added here."""
        now = datetime.now()
        ts_iso = now.isoformat(timespec="seconds")
        ts_short = now.strftime("%H:%M:%S")
        elapsed = round(time.time() - self._t_start, 2)
        self._text_f.write(f"{ts_short} [{event:<24}] {line}\n")
        record = {
            "ts": ts_iso,
            "elapsed_s": elapsed,
            "event": event,
            "fix_id": self.fix_id,
            "slice": self.slice_name,
            **data,
        }
        self._jsonl_f.write(json.dumps(record, default=str) + "\n")

    # ── Stage helpers ──────────────────────────────────────────────────────

    def cycle_start(self, args: dict[str, Any]) -> None:
        self._emit(
            EV_CYCLE_START,
            f"fix={self.fix_id} slice={self.slice_name} "
            f"baseline={args.get('baseline') or 'none'} "
            f"accept={args.get('accept', False)} revert={args.get('revert', False)}",
            {"args": args},
        )

    def stage_3_resolve_fix(self, category: dict, fix: dict, surface_info: dict) -> None:
        self._emit(
            EV_STAGE_3_RESOLVE,
            f"category={category['category_code']} surface={fix['surface']} "
            f"tractability={fix.get('tractability')} status={fix.get('status')} "
            f"file={surface_info.get('file_path')} marker={surface_info.get('marker_label')}",
            {
                "category_code": category["category_code"],
                "category_description": category.get("description"),
                "fix_description": fix.get("description"),
                "fix_surface": fix["surface"],
                "fix_tractability": fix.get("tractability"),
                "fix_status": fix.get("status"),
                "file_path": surface_info.get("file_path"),
                "marker_label": surface_info.get("marker_label"),
                "old_region_chars": surface_info.get("old_region_chars"),
            },
        )

    def stage_4a_propose_start(self, model: str, region_chars: int) -> None:
        self._emit(
            EV_STAGE_4A_START,
            f"model={model} region_chars={region_chars} ≈{region_chars // 4} tokens",
            {"model": model, "region_chars": region_chars},
        )

    def stage_4a_propose_end(self, model: str, usage: dict, cost_usd: float,
                             new_region_chars: int, elapsed_s: float) -> None:
        self._emit(
            EV_STAGE_4A_END,
            f"model={model} tokens_in={usage.get('prompt_tokens')} "
            f"tokens_out={usage.get('completion_tokens')} "
            f"cost=${cost_usd:.4f} elapsed={elapsed_s:.1f}s "
            f"new_region_chars={new_region_chars}",
            {
                "model": model,
                "usage": usage,
                "cost_usd": cost_usd,
                "new_region_chars": new_region_chars,
                "elapsed_s": elapsed_s,
            },
        )

    def stage_4b_verify_preservation(self, passed: bool, detail: str | None = None,
                                     old_chars: int | None = None,
                                     new_chars: int | None = None) -> None:
        msg = (
            f"PASS old={old_chars} new={new_chars}"
            if passed
            else f"FAIL — {detail}"
        )
        self._emit(
            EV_STAGE_4B_PRESERVE,
            msg,
            {"passed": passed, "detail": detail,
             "old_chars": old_chars, "new_chars": new_chars},
        )

    def stage_4c_snapshot(self, file_path: str, snapshot_path: str) -> None:
        self._emit(
            EV_STAGE_4C_SNAPSHOT,
            f"snapshot {file_path} → {snapshot_path}",
            {"file_path": file_path, "snapshot_path": snapshot_path},
        )

    def stage_4c_apply(self, file_path: str) -> None:
        self._emit(
            EV_STAGE_4C_APPLY,
            f"wrote new region to {file_path}",
            {"file_path": file_path},
        )

    def stage_4c_syntax_check(self, file_path: str, passed: bool,
                              error: str | None = None) -> None:
        msg = "PASS" if passed else f"FAIL — {error}"
        self._emit(
            EV_STAGE_4C_SYNTAX,
            f"{file_path} {msg}",
            {"file_path": file_path, "passed": passed, "error": error},
        )

    def stage_4d_run_start(self, task_ids: list[str], log_path: str) -> None:
        self._emit(
            EV_STAGE_4D_RUN_START,
            f"running {len(task_ids)} tasks tee→{log_path}",
            {"task_ids": task_ids, "log_path": log_path},
        )

    def stage_4d_task_close(self, task_id: str, status: str,
                            pass_count: int, total: int) -> None:
        self._emit(
            EV_STAGE_4D_TASK_CLOSE,
            f"{task_id} {status} {pass_count}/{total}",
            {"task_id": task_id, "status": status,
             "pass_count": pass_count, "total": total},
        )

    def stage_4d_run_end(self, elapsed_s: float, correct: int, total: int) -> None:
        self._emit(
            EV_STAGE_4D_RUN_END,
            f"benchmark complete {correct}/{total} correct elapsed={elapsed_s:.1f}s",
            {"elapsed_s": elapsed_s, "correct": correct, "total": total},
        )

    def stage_4d_parse_end(self, report_path: str,
                           category_counts: dict[str, int]) -> None:
        top = sorted(category_counts.items(), key=lambda x: -x[1])[:5]
        top_str = ", ".join(f"{k}:{v}" for k, v in top)
        self._emit(
            EV_STAGE_4D_PARSE_END,
            f"report={report_path} top_categories=[{top_str}]",
            {"report_path": report_path, "category_counts": category_counts},
        )

    def stage_4d_panel_end(self, scores_summary: dict,
                           retired_categories: list[str],
                           new_categories: list[str]) -> None:
        pp = scores_summary.get("assertions_passed", {})
        pt = scores_summary.get("assertions_total", {})
        pp_v, pp_b = pp.get("value"), pp.get("baseline")
        pt_v, pt_b = pt.get("value"), pt.get("baseline")
        msg = (
            f"assertions {pp_v}/{pt_v} (was {pp_b}/{pt_b}) "
            f"retired={retired_categories} new={new_categories}"
        )
        self._emit(
            EV_STAGE_4D_PANEL_END,
            msg,
            {
                "scores_summary": scores_summary,
                "retired_categories": retired_categories,
                "new_categories": new_categories,
            },
        )

    def cycle_end(self, outcome: str, total_cost_usd: float | None = None,
                  total_elapsed_s: float | None = None,
                  notes: str | None = None) -> None:
        if total_elapsed_s is None:
            total_elapsed_s = time.time() - self._t_start
        cost_str = f"${total_cost_usd:.4f}" if total_cost_usd is not None else "n/a"
        self._emit(
            EV_CYCLE_END,
            f"outcome={outcome} total_cost={cost_str} "
            f"total_elapsed={total_elapsed_s:.1f}s"
            + (f" notes={notes}" if notes else ""),
            {"outcome": outcome, "total_cost_usd": total_cost_usd,
             "total_elapsed_s": total_elapsed_s, "notes": notes},
        )

    def error(self, stage: str, message: str, exc: BaseException | None = None) -> None:
        exc_repr = f"{type(exc).__name__}: {exc}" if exc else None
        self._emit(
            EV_ERROR,
            f"stage={stage} message={message}"
            + (f" exc={exc_repr}" if exc_repr else ""),
            {"stage": stage, "message": message, "exc": exc_repr},
        )

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def close(self) -> None:
        if not self._text_f.closed:
            self._text_f.close()
        if not self._jsonl_f.closed:
            self._jsonl_f.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            self.error(stage="__exit__", message="unhandled exception", exc=exc)
        self.close()
        return False  # don't suppress

    # Convenience: where are the files?
    @property
    def paths(self) -> tuple[Path, Path]:
        return (self.text_path, self.jsonl_path)
