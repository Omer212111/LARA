"""
LARA — Summarize a slice run into a structured result set

Parses a run_slice.py log into per-task records and aggregate stats, then emits
both a machine-readable JSON and a human-readable Markdown report.

Unlike analysis/parse_run.py (which targets the behavioral panel), this focuses
on the per-app / per-difficulty capability question: which task shapes is the
agent weak on? Every record is joined against ground-truth metadata
(required_apps, difficulty) so results can be sliced by app and by level.

CLI:
    python analysis/summarize_run.py analysis/runs/spotify-random15.log \\
        --slice spotify-random15 --out-dir analysis/runs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from sample_tasks import apps_for, difficulty, instruction  # noqa: E402

# Result lines, e.g.
#   "✅ Task 287e338_1 CORRECT — 2/2 tests passed (100%) | 23.3s"
#   "❌ Task 396c5a2_1 WRONG — 1/6 tests passed (17%) | Failed: [...] | 38.1s"
# The optional Failed:[...] list sits between the test counts and the duration,
# and may span lines (assertion text contains newlines), so the seconds group
# is anchored to the END of the record rather than the next "|".
_RESULT_RE = re.compile(
    r"Task\s+(?P<tid>[0-9a-f]{7}_\d+)\s+(?P<verdict>CORRECT|WRONG|INCOMPLETE|CRASHED)"
    r"(?:\s*—\s*(?P<passed>\d+)/(?P<total>\d+)\s+tests?\s+passed[^|]*)?"
    r"(?P<failed>\|\s*Failed:\s*\[.*?\]\s*)?"
    r"(?:\|\s*(?P<secs>[\d.]+)s)?",
    re.DOTALL,
)

# The benchmark summary table also reports tasks that never submitted, as
# "<tid>  ❌ WRONG    not called   378.1s". These have no test counts, so
# _RESULT_RE's optional groups all miss and the row must be matched separately —
# otherwise a task that timed out silently vanishes from the report.
_NOT_CALLED_RE = re.compile(
    r"(?P<tid>[0-9a-f]{7}_\d+)\s+\S*\s*(?:WRONG|INCOMPLETE)\s+not called\s+(?P<secs>[\d.]+)s"
)

# Benchmark header, e.g. "Task 3/15: 396c5a2_1" (logger.task_header).
_TASK_HEADER_RE = re.compile(r"^Task\s+\d+/\d+:\s*(?P<tid>[0-9a-f]{7}_\d+)\s*$")

# Failure signatures, checked in order; first match wins. Order matters: the
# environment/infra causes are checked before the reasoning ones, so a task that
# crashed is never misfiled as a merely-wrong answer.
#
# NOTE: do NOT key "no_submit" off `task_signal_complete=False` — that flag is
# also False whenever the run ends via "FINISH (hit MAX_EXECUTOR_RUNS)", which is
# the normal end state for a task that DID submit but submitted a wrong answer.
_FAILURE_SIGNATURES = [
    ("sandbox_timeout",   ["SIGALRM", "sandbox timeout", "Execution timed out"]),
    ("api_error",         ["APIStatusError", "RateLimitError", "Connection error"]),
    ("code_error",        ["Traceback (most recent call last)", "NameError", "AttributeError",
                           "TypeError", "KeyError", "IndexError"]),
    ("budget_exhausted",  ["MAX_REACT_STEPS", "hit max ReAct steps", "recursion_limit"]),
]

# A retry that ends at step 1 was killed by the stale-completion race: the
# premature-submit guard strips its complete_task(), then evaluate_task() reads
# AppWorld's sticky task_completed() flag (still True from attempt 1) and breaks
# the ReAct loop. The corrected answer is computed but never submitted.
_RETRY_NOOP_RE = re.compile(r"Done — attempt (?:[2-9]|\d\d+), 1 steps")
_REVIEWER_FIRED = "Code Reviewer"


def _parse_failed_asserts(raw: str | None) -> list[str]:
    """Pull the individual assertion strings out of a `| Failed: [...]` segment."""
    if not raw:
        return []
    inner = raw.split("[", 1)[-1].rsplit("]", 1)[0]
    # Entries are repr'd Python strings; grab quoted spans, collapsing newlines.
    items = re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", inner)
    return [" ".join((a or b).split()) for a, b in items]


def _classify_failure(task_block: str) -> str:
    """Best-effort failure category from a task's log block."""
    for label, needles in _FAILURE_SIGNATURES:
        if any(n in task_block for n in needles):
            return label
    if "complete_task() called but WRONG" in task_block:
        # An answer was rejected by the test suite. Separate out the case where
        # the Reviewer diagnosed it and the retry was then killed at step 1 by
        # the stale-completion race (see _RETRY_NOOP_RE above).
        if _REVIEWER_FIRED in task_block and _RETRY_NOOP_RE.search(task_block):
            return "retry_killed_stale_eval"
        return "wrong_answer"
    if "complete_task" not in task_block:
        return "no_submit"
    return "wrong_answer"


def _reviewer_stats(task_block: str) -> dict:
    """Did the Reviewer fire, and did the retry actually redo any work?"""
    fired = _REVIEWER_FIRED in task_block
    m = re.search(r"ROOT_CAUSE:\s*(.+)", task_block)
    return {
        "reviewer_fired": fired,
        "reviewer_root_cause": " ".join(m.group(1).split())[:80] if m else None,
        "retry_noop": bool(_RETRY_NOOP_RE.search(task_block)),
        "premature_strips": len(re.findall(r"Stripped premature complete_task", task_block)),
    }


def _split_task_blocks(text: str) -> dict[str, str]:
    """Map task_id -> the slice of the log belonging to that task."""
    lines = text.splitlines()
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _TASK_HEADER_RE.match(line.strip())
        if m:
            starts.append((i, m.group("tid")))

    blocks: dict[str, str] = {}
    for idx, (line_no, tid) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        blocks[tid] = "\n".join(lines[line_no:end])
    return blocks


def parse_log(log_path: Path) -> list[dict]:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    blocks = _split_task_blocks(text)

    records: dict[str, dict] = {}
    for m in _RESULT_RE.finditer(text):
        tid = m.group("tid")
        verdict = m.group("verdict")
        correct = verdict == "CORRECT"
        block = blocks.get(tid, "")

        records[tid] = {
            "task_id":       tid,
            "verdict":       verdict,
            "correct":       correct,
            "tests_passed":  int(m.group("passed")) if m.group("passed") else None,
            "tests_total":   int(m.group("total")) if m.group("total") else None,
            "seconds":       float(m.group("secs")) if m.group("secs") else None,
            "difficulty":    difficulty(tid),
            "required_apps": apps_for(tid)[0],
            "instruction":   instruction(tid),
            "failure_type":  None if correct else _classify_failure(block),
            # Which ground-truth assertions the task failed — the most direct
            # evidence of *what* went wrong, kept verbatim for analysis.
            "failed_asserts": _parse_failed_asserts(m.group("failed")),
            **_reviewer_stats(block),
        }
    # Tasks that never called complete_task never emit a "Task <id> WRONG — n/m
    # tests passed" line; recover them from the summary table.
    for m in _NOT_CALLED_RE.finditer(text):
        tid = m.group("tid")
        if tid in records:
            continue
        block = blocks.get(tid, "")
        records[tid] = {
            "task_id":       tid,
            "verdict":       "NOT_CALLED",
            "correct":       False,
            "tests_passed":  None,
            "tests_total":   None,
            "seconds":       float(m.group("secs")),
            "difficulty":    difficulty(tid),
            "required_apps": apps_for(tid)[0],
            "instruction":   instruction(tid),
            "failure_type":  "no_submit",
            "failed_asserts": [],
            **_reviewer_stats(block),
        }

    # Preserve first-seen order from the log.
    return list(records.values())


def aggregate(records: list[dict]) -> dict:
    n = len(records)
    n_correct = sum(r["correct"] for r in records)

    by_difficulty: dict[str, dict] = {}
    for lvl in (1, 2, 3):
        rows = [r for r in records if r["difficulty"] == lvl]
        if rows:
            by_difficulty[str(lvl)] = {
                "n": len(rows),
                "correct": sum(r["correct"] for r in rows),
                "rate": round(sum(r["correct"] for r in rows) / len(rows), 3),
            }

    by_app_count: dict[str, dict] = {}
    for r in records:
        k = f"{len(r['required_apps'])}-app"
        e = by_app_count.setdefault(k, {"n": 0, "correct": 0})
        e["n"] += 1
        e["correct"] += r["correct"]
    for e in by_app_count.values():
        e["rate"] = round(e["correct"] / e["n"], 3)

    failures = Counter(r["failure_type"] for r in records if not r["correct"])

    fired = [r for r in records if r.get("reviewer_fired")]
    reviewer = {
        "fired": len(fired),
        "rescued": sum(r["correct"] for r in fired),
        "retry_killed": sum(bool(r.get("retry_noop")) for r in fired),
        "root_causes": dict(Counter(
            r["reviewer_root_cause"] for r in fired if r.get("reviewer_root_cause")
        ).most_common()),
    }

    return {
        "reviewer": reviewer,
        "premature_strips": sum(r.get("premature_strips", 0) for r in records),
        "n_tasks": n,
        "n_correct": n_correct,
        "success_rate": round(n_correct / n, 3) if n else 0.0,
        "by_difficulty": by_difficulty,
        "by_app_count": by_app_count,
        "failure_types": dict(failures.most_common()),
        "mean_seconds": round(
            sum(r["seconds"] or 0 for r in records) / n, 1) if n else 0.0,
    }


def render_markdown(slice_name: str, records: list[dict], agg: dict,
                    log_path: Path) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    L: list[str] = []
    L.append(f"# Run report — `{slice_name}`")
    L.append("")
    L.append(f"- **Date:** {ts}")
    L.append(f"- **Log:** `{log_path}`")
    L.append(f"- **Tasks:** {agg['n_tasks']}")
    L.append(f"- **Correct:** {agg['n_correct']} / {agg['n_tasks']} "
             f"(**{agg['success_rate']:.0%}**)")
    L.append(f"- **Mean time/task:** {agg['mean_seconds']}s")
    L.append("")

    L.append("## Success rate by difficulty")
    L.append("")
    L.append("| difficulty | n | correct | rate |")
    L.append("|---|---|---|---|")
    for lvl in ("1", "2", "3"):
        if lvl in agg["by_difficulty"]:
            e = agg["by_difficulty"][lvl]
            L.append(f"| {lvl} | {e['n']} | {e['correct']} | {e['rate']:.0%} |")
    L.append("")

    L.append("## Success rate by task breadth (number of apps involved)")
    L.append("")
    L.append("| apps required | n | correct | rate |")
    L.append("|---|---|---|---|")
    for k in sorted(agg["by_app_count"]):
        e = agg["by_app_count"][k]
        L.append(f"| {k} | {e['n']} | {e['correct']} | {e['rate']:.0%} |")
    L.append("")

    if agg["failure_types"]:
        L.append("## Failure categories")
        L.append("")
        L.append("| category | count |")
        L.append("|---|---|")
        for k, v in agg["failure_types"].items():
            L.append(f"| {k} | {v} |")
        L.append("")

    rv = agg["reviewer"]
    L.append("## Reviewer effectiveness")
    L.append("")
    L.append(f"- Fired on **{rv['fired']}** task(s); rescued **{rv['rescued']}**.")
    L.append(f"- Retries killed at step 1 by the stale-completion race "
             f"(corrected answer computed but never submitted): **{rv['retry_killed']}**.")
    if rv["root_causes"]:
        L.append("- Diagnosed root causes: "
                 + ", ".join(f"`{k}` ×{v}" for k, v in rv["root_causes"].items()))
    L.append(f"- Premature `complete_task` strips across the slice: "
             f"**{agg['premature_strips']}**.")
    L.append("")

    L.append("## Per-task results")
    L.append("")
    L.append("| task | ✓ | d | apps | tests | time | failure | instruction |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in records:
        mark = "✅" if r["correct"] else "❌"
        tests = (f"{r['tests_passed']}/{r['tests_total']}"
                 if r["tests_passed"] is not None else "—")
        secs = f"{r['seconds']:.0f}s" if r["seconds"] else "—"
        apps = ",".join(r["required_apps"])
        fail = r["failure_type"] or ""
        instr = r["instruction"][:60].replace("|", "\\|")
        L.append(f"| `{r['task_id']}` | {mark} | {r['difficulty']} | {apps} | "
                 f"{tests} | {secs} | {fail} | {instr} |")
    L.append("")
    return "\n".join(L)


def _cli() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("log", type=Path, help="Run log produced by run_slice.py --log-to")
    p.add_argument("--slice", dest="slice_name", required=True, help="Slice name")
    p.add_argument("--out-dir", type=Path, default=HERE / "runs")
    args = p.parse_args()

    records = parse_log(args.log)
    if not records:
        raise SystemExit(f"No task results parsed from {args.log} — is the run finished?")

    agg = aggregate(records)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "slice": args.slice_name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "log": str(args.log),
        "aggregate": agg,
        "records": records,
    }
    json_path = args.out_dir / f"{args.slice_name}.results.json"
    json_path.write_text(json.dumps(payload, indent=2))

    md_path = args.out_dir / f"{args.slice_name}.report.md"
    md_path.write_text(render_markdown(args.slice_name, records, agg, args.log))

    print(f"Parsed {len(records)} tasks — {agg['n_correct']}/{agg['n_tasks']} "
          f"correct ({agg['success_rate']:.0%})")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    _cli()
