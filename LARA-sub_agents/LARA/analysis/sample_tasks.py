"""
LARA — Ground-truth task sampler

Samples task IDs from the installed AppWorld data using the *ground truth*
metadata rather than instruction keyword matching:

    data/tasks/<id>/ground_truth/required_apps.json  -> exact app labels
    data/tasks/<id>/ground_truth/metadata.json       -> difficulty (1/2/3)

This is strictly more reliable than benchmark.find_tasks_by_app(), which greps
the instruction text and mislabels tasks that mention an app without using it.

Only train+dev carry required_apps.json. The test_* splits withhold it (and
solution.py) but DO ship evaluation.py, test_data.json and private_data.json —
so test tasks are fully scorable by world.evaluate(); they simply carry no app
label. For those, `infer_apps()` derives the label from the instruction text plus
the shipped ground-truth files. Validated against the 147 train+dev tasks where
the true label is known: 84% of tasks get a label set that covers the truth,
with occasional over-prediction and never a wrong app.

Over-prediction is acceptable for *sampling* — a task labelled splitwise that
turns out to also need venmo is still a valid splitwise test — so app sampling
draws from all four splits, using ground truth where available and inference
otherwise. Use `--trusted-only` to restrict to train+dev exact labels.

CLI:
    python analysis/sample_tasks.py --app venmo --n 15 --seed 20260720
    python analysis/sample_tasks.py --app splitwise --n 15 --seed 20260720
    python analysis/sample_tasks.py --difficulty 1 --n 15 --seed 20260720
    python analysis/sample_tasks.py --coverage
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

HERE = Path(__file__).parent
LARA_ROOT = HERE.parent
TASKS_DIR = LARA_ROOT / "data" / "tasks"
DATASETS_DIR = LARA_ROOT / "data" / "datasets"

# Infrastructure apps present in every task; never the subject of a task.
_INFRA_APPS = {"admin", "supervisor"}

# Splits that ship ground_truth/required_apps.json (exact app labels).
LABELLED_SPLITS = ("train", "dev")
# Splits that withhold required_apps.json but are still scorable via evaluation.py.
INFERRED_SPLITS = ("test_normal", "test_challenge")
ALL_SPLITS = LABELLED_SPLITS + INFERRED_SPLITS

# Back-compat alias — earlier runs sampled from train+dev only.
SCORABLE_SPLITS = LABELLED_SPLITS

ALL_APPS = [
    "amazon", "api_docs", "file_system", "gmail", "phone",
    "simple_note", "splitwise", "spotify", "todoist", "venmo",
]

# Surface forms that imply an app when it is not named outright. AppWorld
# instructions say "text message" far more often than "phone", so a bare
# app-name search under-detects phone by ~50%.
_APP_PATTERNS: dict[str, list[str]] = {
    "phone":       [r"\bphone\b", r"text message", r"voice message", r"\bsms\b",
                    r"phone_number", r"contact book", r"\balarm\b"],
    "simple_note": [r"simple[_ ]note", r"\bnotes?\b"],
    "file_system": [r"file[_ ]system", r"\bfolder\b", r"\bdirectory\b",
                    r"\bdownload", r"~/", r"\.csv\b", r"\bfile\b"],
    "gmail":       [r"\bgmail\b", r"\bemail\b", r"\binbox\b"],
    "todoist":     [r"\btodoist\b", r"\btask list\b", r"\bto-?do\b"],
    "api_docs":    [r"api[_ ]docs", r"\bapi documentation\b", r"how many apis"],
    "amazon":      [r"\bamazon\b"],
    "splitwise":   [r"\bsplitwise\b"],
    "spotify":     [r"\bspotify\b"],
    "venmo":       [r"\bvenmo\b"],
}

# Ground-truth files shipped for EVERY task, including the test splits.
_EVIDENCE_FILES = ("evaluation.py", "private_data.json",
                   "test_data.json", "public_data.json")


def _read_ids(split: str) -> list[str]:
    path = DATASETS_DIR / f"{split}.txt"
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def required_apps(task_id: str) -> list[str] | None:
    """Ground-truth app labels for a task, or None when ground truth is withheld."""
    path = TASKS_DIR / task_id / "ground_truth" / "required_apps.json"
    if not path.exists():
        return None
    apps = json.loads(path.read_text())
    return [a for a in apps if a not in _INFRA_APPS]


def infer_apps(task_id: str) -> list[str]:
    """Best-effort app labels for a task whose required_apps.json is withheld.

    Scans the instruction plus every shipped ground-truth file (evaluation.py
    names the models it asserts on, e.g. "venmo.Friendship"). Errs toward
    over-prediction: a superset is fine for sampling, a miss is not.
    """
    blob = instruction(task_id)
    gt_dir = TASKS_DIR / task_id / "ground_truth"
    for name in _EVIDENCE_FILES:
        path = gt_dir / name
        if path.exists():
            blob += "\n" + path.read_text(errors="replace")
    blob = blob.lower()
    return sorted(
        app for app, patterns in _APP_PATTERNS.items()
        if any(re.search(p, blob) for p in patterns)
    )


def apps_for(task_id: str) -> tuple[list[str], bool]:
    """(apps, is_exact) — ground truth when shipped, inference otherwise."""
    exact = required_apps(task_id)
    if exact is not None:
        return exact, True
    return infer_apps(task_id), False


def difficulty(task_id: str) -> int | None:
    """Ground-truth difficulty (1=easy, 2=medium, 3=hard), or None if absent."""
    path = TASKS_DIR / task_id / "ground_truth" / "metadata.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("difficulty")


def instruction(task_id: str) -> str:
    path = TASKS_DIR / task_id / "specs.json"
    if not path.exists():
        return ""
    return json.loads(path.read_text()).get("instruction", "")


def _pool(splits=SCORABLE_SPLITS) -> list[tuple[str, str]]:
    """[(task_id, split)] for every task in the given splits."""
    return [(tid, s) for s in splits for tid in _read_ids(s)]


def sample_by_app(app: str, n: int, seed: int,
                  splits=ALL_SPLITS, solo_only: bool = False,
                  trusted_only: bool = False) -> list[str]:
    """Random sample of n task IDs that require `app`.

    Uses ground-truth labels on train+dev and inferred labels on the test splits
    (see infer_apps). trusted_only=True restricts to exactly-labelled tasks.

    solo_only=True restricts to single-app tasks, isolating one specialist;
    the default includes multi-app tasks, which is the realistic setting.
    """
    matches = []
    for tid, _split in _pool(splits):
        apps, is_exact = apps_for(tid)
        if trusted_only and not is_exact:
            continue
        if app not in apps:
            continue
        if solo_only and len(apps) != 1:
            continue
        matches.append(tid)

    matches.sort()  # deterministic order before seeding
    rng = random.Random(seed)
    if n >= len(matches):
        return matches
    return sorted(rng.sample(matches, n))


def sample_by_difficulty(level: int, n: int, seed: int,
                         splits=LABELLED_SPLITS) -> list[str]:
    """Random sample of n task IDs at the given difficulty level."""
    matches = [tid for tid, _ in _pool(splits) if difficulty(tid) == level]
    matches.sort()
    rng = random.Random(seed)
    if n >= len(matches):
        return matches
    return sorted(rng.sample(matches, n))


def coverage(splits=ALL_SPLITS) -> dict:
    """App -> {'total', 'solo', 'exact', 'by_difficulty'} over the given splits."""
    stats: dict[str, dict] = {}
    for tid, _ in _pool(splits):
        apps, is_exact = apps_for(tid)
        if not apps:
            continue
        d = difficulty(tid)
        for a in apps:
            entry = stats.setdefault(
                a, {"total": 0, "solo": 0, "exact": 0, "by_difficulty": {}})
            entry["total"] += 1
            entry["exact"] += int(is_exact)
            if len(apps) == 1:
                entry["solo"] += 1
            if d is not None:
                entry["by_difficulty"][d] = entry["by_difficulty"].get(d, 0) + 1
    return stats


def _print_coverage() -> None:
    stats = coverage()
    print(f"Coverage over splits {ALL_SPLITS} "
          f"({sum(len(_read_ids(s)) for s in ALL_SPLITS)} tasks)")
    print("'exact' = label from ground_truth/required_apps.json; "
          "the rest are inferred.\n")
    print(f"{'app':14}{'total':>7}{'exact':>7}{'solo':>7}{'d1':>6}{'d2':>6}{'d3':>6}")
    for app, e in sorted(stats.items(), key=lambda kv: -kv[1]["total"]):
        bd = e["by_difficulty"]
        print(f"{app:14}{e['total']:>7}{e['exact']:>7}{e['solo']:>7}"
              f"{bd.get(1, 0):>6}{bd.get(2, 0):>6}{bd.get(3, 0):>6}")

    print("\nDifficulty totals:")
    for lvl in (1, 2, 3):
        ids = [t for t, _ in _pool(LABELLED_SPLITS) if difficulty(t) == lvl]
        print(f"  difficulty {lvl}: {len(ids)}")


def _cli() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--app", help="Sample tasks requiring this app")
    p.add_argument("--difficulty", type=int, choices=(1, 2, 3),
                   help="Sample tasks at this difficulty level")
    p.add_argument("--n", type=int, default=15, help="Sample size (default 15)")
    p.add_argument("--seed", type=int, default=20260720, help="RNG seed")
    p.add_argument("--solo-only", action="store_true",
                   help="With --app: restrict to single-app tasks")
    p.add_argument("--trusted-only", action="store_true",
                   help="With --app: only tasks with exact ground-truth labels")
    p.add_argument("--coverage", action="store_true", help="Print app/difficulty coverage")
    p.add_argument("--json", action="store_true", help="Emit a JSON list of IDs")
    args = p.parse_args()

    if args.coverage:
        _print_coverage()
        return

    if args.app:
        ids = sample_by_app(args.app, args.n, args.seed,
                            solo_only=args.solo_only,
                            trusted_only=args.trusted_only)
    elif args.difficulty:
        ids = sample_by_difficulty(args.difficulty, args.n, args.seed)
    else:
        p.error("Pass --app, --difficulty, or --coverage.")

    if args.json:
        print(json.dumps(ids))
        return

    label = args.app or f"difficulty-{args.difficulty}"
    print(f"=== {label}: {len(ids)} tasks (seed={args.seed}) ===")
    for tid in ids:
        apps, is_exact = apps_for(tid)
        mark = " " if is_exact else "~"
        print(f"  {tid:14}{mark}d{difficulty(tid)}  apps={','.join(apps):32} "
              f"{instruction(tid)[:64]}")


if __name__ == "__main__":
    _cli()
