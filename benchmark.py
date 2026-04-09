import os
import sys
import time  # Added for metrics tracking
import freezegun

freezegun.configure(extend_ignore_list=["google", "httpx", "grpc", "urllib3", "langchain", "langchain_google_genai"])

from appworld import AppWorld, load_task_ids
from planning_loop import process_goal
from tools import set_appworld_env


def run_official_benchmark(num_tasks=20, dataset="train"):  # Updated to 20 tasks
    print(f"========== STARTING OFFICIAL APPWORLD BENCHMARK ({num_tasks} Tasks) ==========")

    experiment_name = "lara_langchain_agent"
    results_summary = []

    try:
        # Loading the first 20 tasks as requested
        task_ids = load_task_ids(dataset)[:num_tasks]
    except Exception as e:
        print(f"[ERROR] Could not load tasks: {e}")
        sys.exit(1)

    for index, task_id in enumerate(task_ids):
        print(f"\n" + "=" * 50)
        print(f"[*] Running Task {index + 1}/{num_tasks} | ID: {task_id}")
        print("=" * 50)

        start_time = time.monotonic()  # Start timer for the experiment log

        with AppWorld(task_id=task_id, experiment_name=experiment_name) as world:
            set_appworld_env(world)

            supervisor = world.task.supervisor
            enriched_instruction = (
                f"My name is: {supervisor.first_name} {supervisor.last_name}. "
                f"My personal email is {supervisor.email} and phone number is {supervisor.phone_number}.\n\n"
                f"Task: {world.task.instruction}"
            )

            try:
                # Execution
                success_flag = process_goal(enriched_instruction)
            except Exception as e:
                print(f"[BENCHMARK ERROR] Task {task_id} failed: {e}")
                success_flag = False

            duration = time.monotonic() - start_time # AND HERE
            is_complete = world.task_completed()

            # Store results for the final summary table
            results_summary.append({
                "id": task_id,
                "status": "✅" if is_complete else "❌",
                "time": f"{duration:.2f}s"
            })

            print(f"\n[METRICS] Time: {duration:.2f}s | Result: {'COMPLETE' if is_complete else 'INCOMPLETE'}")

    # Final summary to easily copy-paste into your Google Doc template
    print("\n" + "=" * 30)
    print("FINAL EXPERIMENT SUMMARY")
    print("=" * 30)
    print("Task ID | Status | Time")
    for res in results_summary:
        print(f"{res['id']} | {res['status']} | {res['time']}")

    print("\nTo see official accuracy: appworld evaluate", experiment_name, dataset)


if __name__ == "__main__":
    run_official_benchmark(20, "train")