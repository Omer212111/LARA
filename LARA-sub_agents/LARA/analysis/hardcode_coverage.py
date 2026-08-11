"""
Static coverage of the text-matching hardcode
=============================================
Three surfaces decide their behaviour purely from the task instruction string, so
their reach can be measured EXACTLY, over every task, for free — no LLM calls, no
AppWorld, no run:

  1. explorer.amazon_template_plan   — regex → a complete canned plan, LLM skipped
  2. base.is_action_task             — regex → forces answer=None
  3. explorer._APP_KEYWORDS          — keyword table → which apps the planner is shown

This is the number that says how much score each surface can possibly be carrying.
A benchmark run can only sample; this enumerates.

    python analysis/hardcode_coverage.py [dataset ...]     # default: every dataset on disk
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from explorer import _APP_KEYWORDS  # noqa: E402

try:                                            # removed from explorer.py on 2026-08-10
    from explorer import amazon_template_plan   # noqa: E402
    TEMPLATE_STATUS = "live"
except ImportError:
    TEMPLATE_STATUS = "removed"

    def amazon_template_plan(_task_text: str) -> str | None:
        return None

TASKS_DIR = Path(__file__).parent.parent / "data" / "tasks"

# The ACTION-task regex that used to live inline in AppOrchestrator.node. It was
# deleted on 2026-08-10 (0 matches in train/dev/test_normal, 48 in test_challenge —
# it could only have come from a test split). The literal is kept HERE, in the
# measurement tool, so the finding stays reproducible after the agent stopped using it.
_ACTION_RE = re.compile(r"(place an order|buy me|order all|order the)")
ACTION_RE_STATUS = "removed from base.py 2026-08-10"


def _instruction(task_id: str) -> str | None:
    p = TASKS_DIR / task_id / "specs.json"
    try:
        with p.open(encoding="utf-8") as fh:
            return json.load(fh).get("instruction", "")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _datasets() -> list[str]:
    """Dataset names that actually have their task dirs on disk."""
    from appworld import load_task_ids
    found = []
    for name in ("train", "dev", "test_normal", "test_challenge"):
        try:
            ids = load_task_ids(name)
        except Exception:
            continue
        if ids and (TASKS_DIR / ids[0]).exists():
            found.append(name)
    return found


def analyse(dataset: str) -> dict:
    from appworld import load_task_ids

    ids = load_task_ids(dataset)
    total = 0
    template_hits: list[tuple[str, str]] = []
    action_hits = 0
    app_hits: Counter = Counter()
    apps_per_task: Counter = Counter()
    no_app_detected: list[str] = []

    for task_id in ids:
        instruction = _instruction(task_id)
        if instruction is None:
            continue
        total += 1

        # 1. Canned Amazon plan. amazon_template_plan splits on "Task:" itself, and
        # a bare instruction has no such prefix, so it sees the whole string —
        # exactly what it sees in production after the supervisor preamble is cut.
        plan = amazon_template_plan(instruction)
        if plan:
            template_hits.append((task_id, instruction[:110]))

        body = instruction.lower()
        if _ACTION_RE.match(body):
            action_hits += 1

        detected = [a for a, kws in _APP_KEYWORDS.items()
                    if any(kw in body for kw in kws)]
        apps_per_task[len(detected)] += 1
        for a in detected:
            app_hits[a] += 1
        if not detected:
            no_app_detected.append(task_id)

    return {
        "dataset": dataset,
        "total": total,
        "template_hits": template_hits,
        "action_hits": action_hits,
        "app_hits": app_hits,
        "apps_per_task": apps_per_task,
        "no_app_detected": no_app_detected,
    }


def render(r: dict) -> str:
    n = r["total"] or 1
    out = [
        f"=== {r['dataset']} — {r['total']} tasks with specs on disk ===",
        "",
        f"1. amazon_template_plan [{TEMPLATE_STATUS}] (canned plan, LLM skipped): "
        f"{len(r['template_hits'])} tasks ({100.0 * len(r['template_hits']) / n:.1f}%)"
        + ("   ← surface deleted; 0 is expected" if TEMPLATE_STATUS == "removed" else ""),
    ]
    for task_id, ins in r["template_hits"][:25]:
        out.append(f"     {task_id}  {ins}")
    if len(r["template_hits"]) > 25:
        out.append(f"     ... and {len(r['template_hits']) - 25} more")

    out += [
        "",
        f"2. ACTION-task regex on task text [{ACTION_RE_STATUS}]: "
        f"{r['action_hits']} tasks ({100.0 * r['action_hits'] / n:.1f}%)",
        "   (note: the OTHER branch of that check — 'action task' appearing in the "
        "Explorer plan — fires far more often and is not measurable statically)",
        "",
        f"3. _APP_KEYWORDS detection:",
    ]
    for app, c in r["app_hits"].most_common():
        out.append(f"     {app:<14} {c:>4} tasks ({100.0 * c / n:>4.1f}%)")
    out += [
        "",
        "   apps detected per task:",
    ]
    for k in sorted(r["apps_per_task"]):
        c = r["apps_per_task"][k]
        out.append(f"     {k} app(s): {c:>4} tasks ({100.0 * c / n:>4.1f}%)")
    out.append(
        f"   tasks where the keyword table detected NOTHING: "
        f"{len(r['no_app_detected'])} ({100.0 * len(r['no_app_detected']) / n:.1f}%)"
    )
    return "\n".join(out)


if __name__ == "__main__":
    targets = sys.argv[1:] or _datasets()
    if not targets:
        print("No datasets found on disk under data/tasks/")
        raise SystemExit(1)
    for ds in targets:
        print(render(analyse(ds)))
        print()
