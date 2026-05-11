import sys
import time
import freezegun

freezegun.configure(extend_ignore_list=["google", "httpx", "grpc", "urllib3", "langchain", "langchain_google_genai"])

from appworld import AppWorld, load_task_ids
from planning_loop import process_goal
from tools import set_appworld_env
import logger

import os
os.environ["APPWORLD_ROOT_ACCESS"] = "1"

def run_official_benchmark(num_tasks=5, dataset="train"):
    experiment_name = "lara_langchain_agent"
    results_summary = []

    try:
        task_ids = load_task_ids(dataset)[:num_tasks]
    except Exception as e:
        logger.error(f"Could not load tasks: {e}")
        sys.exit(1)

    for index, task_id in enumerate(task_ids):
        logger.task_header(task_id, index + 1, num_tasks)
        start_time = time.monotonic()

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

            duration = time.monotonic() - start_time

            # Use world.evaluate() — same as the official appworld evaluate command
            if world.task_completed():
                eval_result = world.evaluate()
                passed = eval_result.pass_count
                total = eval_result.total_count
                pct = eval_result.pass_percentage
                correct = eval_result.success

                if correct:
                    logger.success(
                        f"Task {task_id} CORRECT — {passed}/{total} tests passed ({pct:.0f}%) | {duration:.1f}s"
                    )
                else:
                    fail_reqs = [f['requirement'] for f in eval_result.failures[:3]]
                    logger.error(
                        f"Task {task_id} WRONG — {passed}/{total} tests passed ({pct:.0f}%) | "
                        f"Failed: {fail_reqs} | {duration:.1f}s"
                    )
            else:
                correct = False
                passed, total, pct = 0, "?", 0
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
    run_official_benchmark(20, "train")