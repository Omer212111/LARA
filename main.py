import os
import sys
from appworld import AppWorld, load_task_ids

# Import local modules from current project root
from planning_loop import process_goal
from tools import get_current_task_instruction, set_appworld_env


def main():
    print("=======================================")
    print("  Project LARA - AppWorld Auto-Solver  ")
    print("  Powered by: Qwen 2.5 Coder (Ollama)  ") # עדכון המודל החדש
    print("=======================================")

    # הסרנו את בדיקת GEMINI_API_KEY מכיוון ש-Ollama רץ באופן מקומי
    # ואינו דורש מפתח API חיצוני כדי לעבוד.

    # Initialize AppWorld environment first, then wire it into tools.py globals.
    task_ids = load_task_ids("train")
    task_id = task_ids[0]
    experiment_name = "lara_main_runner"

    with AppWorld(task_id=task_id, experiment_name=experiment_name) as world:
        set_appworld_env(world)

        # שאיבת ההוראות האמיתיות מתוך מסד הנתונים של AppWorld
        instruction = get_current_task_instruction()
        if "Error" in instruction:
            print(f"[FATAL] {instruction}")
            sys.exit(1)

        print("\n[SYSTEM] Loaded AppWorld Task Instruction:")
        print(f"----------------------------------------\n{instruction}\n----------------------------------------")

        print("\n[ACTION] Initiating autonomous execution...")
        # שליחת LARA לפתור את המשימה באמצעות המודל המקומי
        process_goal(instruction)


if __name__ == "__main__":
    main()