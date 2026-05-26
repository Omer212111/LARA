"""
LARA — Behavioral-signal panel

Reads a parsed run report (the JSON emitted by parse_run.py) plus an optional
baseline report, and produces a uniform delta table covering:
  • Scores (tasks correct, assertions passed/total).
  • Error-category counts (from the dictionary).
  • Behavioral counters (from analysis/behavioral_signals.json).

CLI:
    python analysis/panel.py <current_report.json> [--baseline <baseline.json>] [--out panel.json]

Module:
    from analysis.panel import compute_panel
    panel = compute_panel(current_report, baseline_report=None)
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "behavioral_signals.json"


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return json.load(f)


def _load_report(path: str | Path) -> dict:
    with Path(path).open() as f:
        return json.load(f)


# ── Scope assembly ────────────────────────────────────────────────────────────

def _gather_scope(task: dict, scope: str) -> str:
    """Return the text region for a given counter scope. Per-task — the panel
    runs this on every task and aggregates."""
    if scope == "all_outputs":
        return "\n".join(s.get("output", "") for s in task.get("react_steps", []))
    if scope == "all_code":
        return "\n".join(s.get("code", "") for s in task.get("react_steps", []))
    if scope == "all_plans":
        return task.get("plan", "")
    if scope == "all_traces":
        # Plan + code + output for every step. Also include any flow_crash info.
        parts = [task.get("plan", "")]
        for s in task.get("react_steps", []):
            parts.append(s.get("code", ""))
            parts.append(s.get("output", ""))
        return "\n".join(parts)
    if scope == "react_metadata":
        # One line per ReAct step exposing step-level fields the parser captured.
        # Format: "step=N attempt=M specialist=<name> had_error=<bool>"
        lines = []
        for s in task.get("react_steps", []):
            lines.append(
                f"step={s.get('step')} attempt={s.get('attempt')} "
                f"specialist={s.get('specialist', 'unknown')} "
                f"had_error={s.get('had_error', False)}"
            )
        return "\n".join(lines)
    raise ValueError(f"Unknown scope: {scope}")


# ── Counter evaluation ────────────────────────────────────────────────────────

def _count_in_text(text: str, counter: dict) -> int:
    """Return the number of pattern occurrences in `text` for a single counter."""
    total = 0
    for p in counter["patterns"]:
        if counter["pattern_type"] == "substring":
            total += text.count(p)
        elif counter["pattern_type"] == "regex":
            total += len(re.findall(p, text))
        else:
            raise ValueError(f"Unknown pattern_type: {counter['pattern_type']}")
    return total


def _evaluate_counters(report: dict, config: dict) -> dict:
    """For each counter, return {total: N, per_task: K} across the report."""
    counters = config["counters"]
    out = {}
    for c in counters:
        total = 0
        per_task = 0
        for task in report.get("tasks", []):
            text = _gather_scope(task, c["scope"])
            n = _count_in_text(text, c)
            total += n
            if n > 0:
                per_task += 1
        out[c["name"]] = {
            "total": total,
            "per_task": per_task,
            "kind": c["kind"],
            "description": c["description"],
        }
    return out


# ── Score aggregation ─────────────────────────────────────────────────────────

def _aggregate_scores(report: dict) -> dict:
    tasks = report.get("tasks", [])
    correct = sum(1 for t in tasks if t.get("status") == "correct")
    wrong = sum(1 for t in tasks if t.get("status") == "wrong")
    incomplete = sum(1 for t in tasks if t.get("status") == "incomplete")
    pass_sum = sum((t.get("final_score") or {}).get("pass", 0) or 0 for t in tasks)
    total_sum = sum((t.get("final_score") or {}).get("total", 0) or 0 for t in tasks)
    pct = (pass_sum / total_sum * 100.0) if total_sum > 0 else 0.0
    return {
        "tasks_total": len(tasks),
        "tasks_correct": correct,
        "tasks_wrong": wrong,
        "tasks_incomplete": incomplete,
        "assertions_passed": pass_sum,
        "assertions_total": total_sum,
        "assertions_pct": round(pct, 1),
    }


# ── Delta computation ─────────────────────────────────────────────────────────

def _delta(current: int | float, baseline: int | float | None) -> dict:
    if baseline is None:
        return {"value": current, "baseline": None, "delta": None, "arrow": ""}
    diff = current - baseline
    if diff > 0:
        arrow = "↑"
    elif diff < 0:
        arrow = "↓"
    else:
        arrow = "→"
    return {"value": current, "baseline": baseline, "delta": diff, "arrow": arrow}


# ── Top-level panel ───────────────────────────────────────────────────────────

def compute_panel(current_report: dict, baseline_report: dict | None = None) -> dict:
    config = _load_config()

    cur_scores = _aggregate_scores(current_report)
    base_scores = _aggregate_scores(baseline_report) if baseline_report else None

    cur_categories = current_report.get("category_counts", {})
    base_categories = baseline_report.get("category_counts", {}) if baseline_report else None

    cur_counters = _evaluate_counters(current_report, config)
    base_counters = _evaluate_counters(baseline_report, config) if baseline_report else None

    # Score deltas
    score_panel = {}
    for k, v in cur_scores.items():
        base_v = (base_scores or {}).get(k) if base_scores else None
        score_panel[k] = _delta(v, base_v)

    # Category deltas — union of category keys across current and baseline
    all_cat_keys = set(cur_categories.keys())
    if base_categories:
        all_cat_keys |= set(base_categories.keys())
    category_panel = {}
    for cat in sorted(all_cat_keys):
        category_panel[cat] = _delta(
            cur_categories.get(cat, 0),
            (base_categories or {}).get(cat, 0) if base_categories is not None else None,
        )

    # Counter deltas
    counter_panel = {}
    for name, cur in cur_counters.items():
        base = (base_counters or {}).get(name) if base_counters else None
        counter_panel[name] = {
            "kind": cur["kind"],
            "description": cur["description"],
            "total": _delta(cur["total"], (base or {}).get("total")),
            "per_task": _delta(cur["per_task"], (base or {}).get("per_task")),
        }

    return {
        "schema_version": 1,
        "current_path": current_report.get("input_path"),
        "baseline_path": (baseline_report or {}).get("input_path"),
        "scores": score_panel,
        "categories": category_panel,
        "counters": counter_panel,
    }


# ── Human-readable rendering ──────────────────────────────────────────────────

def _fmt_delta(d: dict) -> str:
    if d["baseline"] is None:
        return f"{d['value']}"
    if d["delta"] == 0:
        return f"{d['value']:>6}   {d['arrow']} (={d['baseline']})"
    if isinstance(d["delta"], float):
        sign = "+" if d["delta"] > 0 else ""
        return f"{d['value']:>6}   {d['arrow']} {sign}{d['delta']:.1f}   (was {d['baseline']})"
    return f"{d['value']:>6}   {d['arrow']} {d['delta']:+d}   (was {d['baseline']})"


def render_panel(panel: dict) -> str:
    lines = []
    lines.append("=" * 78)
    lines.append("LARA BEHAVIORAL PANEL")
    lines.append("=" * 78)
    lines.append(f"current : {panel['current_path']}")
    if panel["baseline_path"]:
        lines.append(f"baseline: {panel['baseline_path']}")
    lines.append("")

    # Scores
    lines.append("── SCORES " + "─" * 67)
    for k, d in panel["scores"].items():
        lines.append(f"  {k:<22} {_fmt_delta(d)}")
    lines.append("")

    # Categories
    lines.append("── ERROR CATEGORIES " + "─" * 57)
    for cat, d in panel["categories"].items():
        marker = ""
        if d["baseline"] is not None:
            if d["baseline"] > 0 and d["value"] == 0:
                marker = "  ✅ retired"
            elif d["baseline"] == 0 and d["value"] > 0:
                marker = "  ⚠️  NEW"
        lines.append(f"  {cat:<32} {_fmt_delta(d)}{marker}")
    lines.append("")

    # Counters
    lines.append("── BEHAVIORAL COUNTERS " + "─" * 54)
    for name, d in panel["counters"].items():
        kind = d["kind"]
        kind_marker = {"antipattern": "🚫", "good_pattern": "✓ ", "neutral": "· "}.get(kind, "  ")
        lines.append(
            f"  {kind_marker} {name:<33} "
            f"total={_fmt_delta(d['total'])} | "
            f"per_task={_fmt_delta(d['per_task'])}"
        )
    lines.append("")
    lines.append("=" * 78)
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", help="Current run report JSON (from parse_run.py)")
    parser.add_argument("--baseline", help="Baseline run report JSON for delta comparison")
    parser.add_argument("--out", help="Path to write panel JSON (default: stdout)")
    parser.add_argument(
        "--json", action="store_true",
        help="Print machine JSON instead of human table",
    )
    args = parser.parse_args()

    current = _load_report(args.current)
    baseline = _load_report(args.baseline) if args.baseline else None
    panel = compute_panel(current, baseline)

    if args.json:
        out = json.dumps(panel, indent=2)
    else:
        out = render_panel(panel)

    if args.out:
        Path(args.out).write_text(out)
        print(f"Wrote {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    _cli()
