import sys
import time

from dotenv import load_dotenv
load_dotenv()

import freezegun

freezegun.configure(extend_ignore_list=["google", "httpx", "grpc", "urllib3", "langchain", "langchain_google_genai"])

from appworld import AppWorld, load_task_ids
from planning_loop import process_goal
from tools import set_appworld_env
import logger

import os
os.environ["APPWORLD_ROOT_ACCESS"] = "1"

# Keywords that identify what a task is ABOUT, matched against the task
# instruction. We match the instruction (not evaluation.py) because evaluation
# files list every model a solution touches as a side effect — e.g. an Amazon
# order also writes an invoice file, so its eval mentions file_system.File even
# though the task is purely an Amazon task.
_APP_INSTRUCTION_KEYWORDS = {
    "file_system": ("file", "folder", "directory", "directories", "subdirectory"),
    "amazon":      ("amazon",),
    "spotify":     ("spotify", "song", "playlist", "album"),
    "gmail":       ("gmail", "email", "inbox"),
    "venmo":       ("venmo", "owed money"),
    "splitwise":   ("splitwise",),
    "todoist":     ("todoist", "to-do", "todo list"),
    "simplenote":  ("simplenote", "simple note"),
}


def find_tasks_by_app(app_keyword: str, dataset="train") -> list:
    """Return task IDs (from the dataset) whose INSTRUCTION is about the given app.
    Reads specs.json on disk — no AppWorld needed, instant."""
    import json
    import os
    from appworld import load_task_ids

    keywords = _APP_INSTRUCTION_KEYWORDS.get(app_keyword.lower(), (app_keyword.lower(),))
    all_ids = load_task_ids(dataset)
    matched = []
    for task_id in all_ids:
        specs_path = os.path.join("data", "tasks", task_id, "specs.json")
        try:
            with open(specs_path, "r", encoding="utf-8") as f:
                instruction = json.load(f).get("instruction", "").lower()
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if any(kw in instruction for kw in keywords):
            matched.append(task_id)
    return matched


def run_official_benchmark(num_tasks=5, dataset="train", task_ids=None):
    experiment_name = "lara_langchain_agent"
    results_summary = []

    try:
        if task_ids is None:
            task_ids = load_task_ids(dataset)[:num_tasks]
        else:
            task_ids = list(task_ids)[:num_tasks]
    except Exception as e:
        logger.error(f"Could not load tasks: {e}")
        sys.exit(1)

    for index, task_id in enumerate(task_ids):
        logger.task_header(task_id, index + 1, num_tasks)
        start_time = time.monotonic()

        correct = False
        completed = False
        passed, total, pct = 0, "?", 0
        fail_reqs = []

        with AppWorld(task_id=task_id, experiment_name=experiment_name) as world:
            set_appworld_env(world)

            supervisor = world.task.supervisor
            enriched_instruction = (
                f"My name is: {supervisor.first_name} {supervisor.last_name}. "
                f"My personal email is {supervisor.email} and phone number is {supervisor.phone_number}.\n\n"
                f"Task: {world.task.instruction}"
            )
            logger.task_instruction(world.task.instruction)

            try:
                process_goal(enriched_instruction, task_id=task_id)
            except Exception as e:
                logger.error(f"Task {task_id} crashed: {e}")

            # Use world.evaluate() — same as the official appworld evaluate command
            completed = world.task_completed()
            if completed:
                eval_result = world.evaluate()
                passed = eval_result.pass_count
                total = eval_result.total_count
                pct = eval_result.pass_percentage
                correct = eval_result.success
                if not correct:
                    fail_reqs = [f['requirement'] for f in eval_result.failures[:3]]

        # Compute duration AFTER the AppWorld context exits — inside it, AppWorld's
        # freezegun freezes the clock (incl. time.monotonic) to the task's virtual
        # date, which would make this a frozen timestamp instead of real elapsed time.
        duration = time.monotonic() - start_time

        if completed and correct:
            logger.success(
                f"Task {task_id} CORRECT — {passed}/{total} tests passed ({pct:.0f}%) | {duration:.1f}s"
            )
        elif completed:
            logger.error(
                f"Task {task_id} WRONG — {passed}/{total} tests passed ({pct:.0f}%) | "
                f"Failed: {fail_reqs} | {duration:.1f}s"
            )
        else:
            logger.warning(f"Task {task_id} — complete_task() never called | {duration:.1f}s")

        results_summary.append({
            "id": task_id,
            "correct": correct,
            "passed": passed,
            "total": total,
            "pct": pct,
            "time": f"{duration:.1f}s",
        })

        logger.separator()

    # Final summary
    total_correct = sum(1 for r in results_summary if r["correct"])
    print("\n" + "=" * 50)
    print(f"BENCHMARK COMPLETE — {total_correct}/{num_tasks} tasks correct")
    print("=" * 50)
    print(f"{'Task ID':<20} {'Result':<10} {'Tests':<12} {'Time'}")
    for r in results_summary:
        status = "✅ CORRECT" if r["correct"] else "❌ WRONG"
        tests = f"{r['passed']}/{r['total']} ({r['pct']:.0f}%)" if r["total"] != "?" else "not called"
        print(f"{r['id']:<20} {status:<10} {tests:<12} {r['time']}")

    print(f"\nOfficial score: appworld evaluate {experiment_name} {dataset}")
    logger.done()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default=None, help="Filter tasks by app keyword (e.g. 'amazon')")
    parser.add_argument("--n", type=int, default=20, help="Max tasks to run")
    parser.add_argument("--dataset", default="train")
    args = parser.parse_args()

    if args.app:
        print(f"Scanning for '{args.app}' tasks...")
        ids = find_tasks_by_app(args.app, dataset=args.dataset)
        print(f"Found {len(ids)} tasks: {ids}")
        run_official_benchmark(num_tasks=args.n, dataset=args.dataset, task_ids=ids)
    else:
        run_official_benchmark(args.n, args.dataset)