"""
LARA — Difficulty probe: why do hard tasks fail?

Joins a run's per-task outcomes with (a) execution-effort signals recovered from
the log and (b) the ground-truth cost of the task, to distinguish the ways a task
can be "hard":

    gave up early      steps used << plan steps, few API calls  -> under-exploration
    ran out of room    hit MAX_REACT_STEPS / budget             -> length limit
    wrong from start   very low pass ratio                      -> misunderstood task
    right until the end high pass ratio, one assertion short    -> detail slip

Ground-truth effort comes from ground_truth/metadata.json (num_api_calls,
num_solution_code_lines) — i.e. how much work the reference solution needed.
Comparing the agent's API-call count against that number detects
under-exploration directly.

CLI:
    python analysis/difficulty_probe.py analysis/runs/difficulty1-single-20.log \\
        --slice difficulty1-single-20
    python analysis/difficulty_probe.py --compare difficulty1-single-20 \\
        difficulty2-single-20 difficulty3-single-20
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
LARA_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from sample_tasks import difficulty, instruction  # noqa: E402
from summarize_run import _split_task_blocks, parse_log  # noqa: E402

RUNS_DIR = HERE / "runs"

# "[CODE — ReAct step 7 / attempt 1]"
_STEP_RE = re.compile(r"ReAct step (\d+) / attempt (\d+)")
# The orchestrator's own plan-step counter (base.py:_PLAN_STEP_RE) — numbered
# top-level lines in the Explorer plan. The plan is echoed to the log under
# "[OUTPUT — 📋 Explorer Plan]"; the "Plan progress:" line the orchestrator can
# print is absent from these runs, so count the plan block directly instead.
_PLAN_STEP_RE = re.compile(r"^\s*(\d+)[.)]\s+", re.MULTILINE)
_PLAN_BLOCK_RE = re.compile(
    r"\[OUTPUT — 📋 Explorer Plan[^\]]*\]\n(.*?)(?=\n\[|\n🧭|\n⚙️|\Z)", re.DOTALL
)
# Fallback if the orchestrator did print progress lines.
_PLAN_STEPS_RE = re.compile(r"of ~(\d+) plan steps")


def _count_plan_steps(block: str) -> int:
    """Largest numbered-step count across the Explorer plans in this task block."""
    counts = [len(_PLAN_STEP_RE.findall(m)) for m in _PLAN_BLOCK_RE.findall(block)]
    counts += [int(n) for n in _PLAN_STEPS_RE.findall(block)]
    return max(counts, default=0)


# Any call_api('app', 'endpoint') or apis.app.endpoint( the agent executed.
_API_CALL_RE = re.compile(r"call_api\(\s*'[a-z_]+'\s*,\s*'[a-z_]+'|apis\.[a-z_]+\.[a-z_]+\(")


def _gt_metadata(task_id: str) -> dict:
    path = LARA_ROOT / "data" / "tasks" / task_id / "ground_truth" / "metadata.json"
    return json.loads(path.read_text()) if path.exists() else {}


def probe_task(task_id: str, block: str, record: dict) -> dict:
    """Effort + break-point signals for one task."""
    steps = [(int(s), int(a)) for s, a in _STEP_RE.findall(block)]
    max_step = max((s for s, _ in steps), default=0)
    attempts = max((a for _, a in steps), default=0)
    plan_steps = _count_plan_steps(block)

    gt = _gt_metadata(task_id)
    gt_calls = gt.get("num_api_calls", 0)
    agent_calls = len(_API_CALL_RE.findall(block))

    passed, total = record.get("tests_passed"), record.get("tests_total")
    pass_ratio = (passed / total) if passed is not None and total else None

    # How the task ended, in plain terms.
    if record["correct"]:
        mode = "solved"
    elif record.get("failure_type") == "retry_killed_stale_eval":
        mode = "retry_killed"
    elif "MAX_REACT_STEPS" in block or max_step >= 16:
        mode = "out_of_steps"
    elif pass_ratio is not None and pass_ratio >= 0.8:
        mode = "near_miss"
    elif pass_ratio is not None and pass_ratio <= 0.34:
        mode = "wrong_from_start"
    else:
        mode = "partial"

    return {
        "task_id":        task_id,
        "correct":        record["correct"],
        "difficulty":     difficulty(task_id),
        "mode":           mode,
        "pass_ratio":     round(pass_ratio, 2) if pass_ratio is not None else None,
        "steps_used":     max_step,
        "attempts":       attempts,
        "plan_steps":     plan_steps,
        # <1 means the agent stopped short of the plan it wrote for itself.
        "step_coverage":  round(max_step / plan_steps, 2) if plan_steps else None,
        "agent_api_calls": agent_calls,
        "gt_api_calls":   gt_calls,
        # <1 means the agent explored less than the reference solution needed.
        "call_ratio":     round(agent_calls / gt_calls, 2) if gt_calls else None,
        "gt_sol_lines":   gt.get("num_solution_code_lines", 0),
        "seconds":        record.get("seconds"),
        "instruction":    instruction(task_id)[:70],
    }


def probe_run(log_path: Path) -> list[dict]:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    blocks = _split_task_blocks(text)
    return [
        probe_task(r["task_id"], blocks.get(r["task_id"], ""), r)
        for r in parse_log(log_path)
    ]


def _mean(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    failed = [r for r in rows if not r["correct"]]
    modes: dict[str, int] = {}
    for r in rows:
        modes[r["mode"]] = modes.get(r["mode"], 0) + 1
    return {
        "n": n,
        "correct": sum(r["correct"] for r in rows),
        "rate": round(sum(r["correct"] for r in rows) / n, 3) if n else 0.0,
        "modes": dict(sorted(modes.items(), key=lambda kv: -kv[1])),
        "mean_steps_used": _mean(rows, "steps_used"),
        "mean_plan_steps": _mean(rows, "plan_steps"),
        "mean_step_coverage": _mean(rows, "step_coverage"),
        "mean_agent_api_calls": _mean(rows, "agent_api_calls"),
        "mean_gt_api_calls": _mean(rows, "gt_api_calls"),
        "mean_call_ratio": _mean(rows, "call_ratio"),
        "mean_gt_sol_lines": _mean(rows, "gt_sol_lines"),
        "mean_pass_ratio_when_failed": _mean(failed, "pass_ratio"),
        "mean_seconds": _mean(rows, "seconds"),
    }


def render_comparison(slices: list[str]) -> str:
    data = {}
    for name in slices:
        path = RUNS_DIR / f"{name}.probe.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        data[name] = payload["summary"]
    if not data:
        return "No probe files found — run the probe on each slice first."

    L = ["# Difficulty probe — controlled comparison", ""]
    L.append("App-count is held at 1 across all slices, so differences reflect task")
    L.append("complexity (solution length, API-call volume), not multi-app coordination.")
    L.append("")
    metrics = [
        ("rate", "success rate"),
        ("mean_gt_sol_lines", "GT solution lines"),
        ("mean_gt_api_calls", "GT API calls needed"),
        ("mean_agent_api_calls", "agent API calls made"),
        ("mean_call_ratio", "call ratio (agent/GT)"),
        ("mean_plan_steps", "plan steps written"),
        ("mean_steps_used", "ReAct steps used"),
        ("mean_step_coverage", "step coverage"),
        ("mean_pass_ratio_when_failed", "pass ratio when failed"),
        ("mean_seconds", "mean seconds"),
    ]
    L.append("| metric | " + " | ".join(data) + " |")
    L.append("|---" * (len(data) + 1) + "|")
    for key, label in metrics:
        cells = [str(data[s].get(key)) for s in data]
        L.append(f"| {label} | " + " | ".join(cells) + " |")
    L.append("")

    L.append("## Failure modes")
    L.append("")
    all_modes = sorted({m for s in data.values() for m in s["modes"]})
    L.append("| mode | " + " | ".join(data) + " |")
    L.append("|---" * (len(data) + 1) + "|")
    for m in all_modes:
        L.append(f"| {m} | " + " | ".join(str(data[s]["modes"].get(m, 0)) for s in data) + " |")
    return "\n".join(L)


def _cli() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("log", nargs="?", type=Path)
    p.add_argument("--slice", dest="slice_name")
    p.add_argument("--compare", nargs="+", metavar="SLICE")
    args = p.parse_args()

    if args.compare:
        print(render_comparison(args.compare))
        return

    if not args.log or not args.slice_name:
        p.error("Pass a log and --slice, or use --compare.")

    rows = probe_run(args.log)
    summary = summarize(rows)
    out = RUNS_DIR / f"{args.slice_name}.probe.json"
    out.write_text(json.dumps({"slice": args.slice_name,
                               "summary": summary, "tasks": rows}, indent=2))

    print(f"{args.slice_name}: {summary['correct']}/{summary['n']} "
          f"({summary['rate']:.0%})")
    print(f"  modes: {summary['modes']}")
    print(f"  steps used {summary['mean_steps_used']} / plan {summary['mean_plan_steps']} "
          f"(coverage {summary['mean_step_coverage']})")
    print(f"  API calls {summary['mean_agent_api_calls']} vs GT "
          f"{summary['mean_gt_api_calls']} (ratio {summary['mean_call_ratio']})")
    print(f"  wrote {out}")


if __name__ == "__main__":
    _cli()
