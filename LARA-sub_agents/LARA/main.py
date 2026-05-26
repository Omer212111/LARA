"""
LARA v2 - AppWorld Auto-Solver
Entry point for running a single task (for debugging / development).
For benchmarks, use benchmark.py.
"""

import sys

from dotenv import load_dotenv
load_dotenv()

from appworld import AppWorld, load_task_ids

from planning_loop import process_goal
from tools import get_current_task_instruction, set_appworld_env
import logger


def main():
    task_ids = load_task_ids("train")
    task_id = task_ids[0]
    experiment_name = "lara_mas_runner"

    logger.task_header(task_id, 1, len(task_ids))

    with AppWorld(task_id=task_id, experiment_name=experiment_name) as world:
        set_appworld_env(world)

        instruction = get_current_task_instruction()
        if "Error" in instruction:
            logger.error(f"Fatal: {instruction}")
            sys.exit(1)

        supervisor = world.task.supervisor
        enriched_instruction = (
            f"My name is: {supervisor.first_name} {supervisor.last_name}. "
            f"My personal email is {supervisor.email} and phone number is "
            f"{supervisor.phone_number}.\n\n"
            f"Task: {instruction}"
        )

        logger.task_instruction(instruction)

        success = process_goal(enriched_instruction, task_id=task_id)

        if world.task_completed():
            eval_result = world.evaluate()
            passed = eval_result.pass_count
            total = eval_result.total_count
            pct = eval_result.pass_percentage
            if eval_result.success:
                logger.success(
                    f"Task {task_id} CORRECT! ({passed}/{total} tests passed, {pct:.0f}%)"
                )
            else:
                fail_reqs = [f['requirement'] for f in eval_result.failures[:3]]
                logger.error(
                    f"Task {task_id}: complete_task() called but WRONG answer. "
                    f"({passed}/{total} passed, {pct:.0f}%). Failed: {fail_reqs}"
                )
        else:
            logger.warning(f"Task {task_id}: complete_task() was never called.")

    logger.separator()
    logger.done()


if __name__ == "__main__":
    main()