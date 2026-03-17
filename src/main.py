import os
import sys

from agent.planning_loop import process_goal
from agent.tools import get_current_task_instruction


def main():
    print("=======================================")
    print("  Project LARA - AppWorld Auto-Solver  ")
    print("  Powered by: Google Gemini (Free Tier)")
    print("=======================================")

    if not os.getenv("GEMINI_API_KEY"):
        print("[ERROR] GEMINI_API_KEY is missing from .env!")
        sys.exit(1)

    # שאיבת ההוראות האמיתיות מתוך מסד הנתונים של AppWorld
    instruction = get_current_task_instruction()

    if "Error" in instruction:
        print(f"[FATAL] {instruction}")
        sys.exit(1)

    print("\n[SYSTEM] Loaded AppWorld Task Instruction:")
    print(f"----------------------------------------\n{instruction}\n----------------------------------------")

    print("\n[ACTION] Initiating autonomous execution...")
    # שליחת LARA לפתור את המשימה
    process_goal(instruction)


if __name__ == "__main__":
    main()