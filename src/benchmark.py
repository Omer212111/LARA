import os
import sys

import freezegun
freezegun.configure(extend_ignore_list=["google", "httpx", "grpc", "urllib3", "langchain", "langchain_google_genai"])

from appworld import AppWorld, load_task_ids
from agent.planning_loop import process_goal
from agent.tools import set_appworld_env


def run_official_benchmark(num_tasks=5, dataset="dev"):
    print(f"========== STARTING OFFICIAL APPWORLD BENCHMARK ({num_tasks} Tasks) ==========")

    # השם תחתיו AppWorld ישמור את הלוגים שלנו (קריטי להערכת ציונים)
    experiment_name = "lara_langchain_agent"

    try:
        task_ids = load_task_ids(dataset)[:num_tasks]
    except Exception as e:
        print(f"[ERROR] Could not load tasks. Ensure AppWorld data is downloaded. {e}")
        sys.exit(1)

    for index, task_id in enumerate(task_ids):
        print(f"\n" + "=" * 50)
        print(f"[*] Running Task {index + 1}/{num_tasks} | ID: {task_id}")
        print("=" * 50)

        # שימוש במנהל ההקשר של AppWorld שומר לוגים ומנקה זיכרון אוטומטית!
        with AppWorld(task_id=task_id, experiment_name=experiment_name) as world:

            # חיבור הסביבה החדשה לכלים של LARA (התיקון שלנו משלב 1)
            set_appworld_env(world)

            # [PROMPT ENGINEERING]: הזרקת נתוני ה-Supervisor (כפי שהומלץ במחברת) כדי לחסוך קריאות API
            supervisor = world.task.supervisor
            enriched_instruction = (
                f"My name is: {supervisor.first_name} {supervisor.last_name}. "
                f"My personal email is {supervisor.email} and phone number is {supervisor.phone_number}.\n\n"
                f"Task: {world.task.instruction}"
            )

            print(f"[SYSTEM] Enriched Task Input:\n{enriched_instruction}")

            try:
                # הרצת הלולאה שלנו
                process_goal(enriched_instruction)
            except Exception as e:
                print(f"[BENCHMARK ERROR] Task {task_id} failed abruptly: {e}")

            if world.task_completed():
                print(f"\n[SUCCESS] AppWorld registered task {task_id} as COMPLETE!")
            else:
                print(f"\n[FAILED] AppWorld registered task {task_id} as INCOMPLETE.")

    print("\n========== BENCHMARK COMPLETE ==========")
    print(f"To see your official accuracy score, run the following command in your terminal:")
    print(f"appworld evaluate {experiment_name} {dataset}")


if __name__ == "__main__":
    # שימו לב לבדוק שקיים משתנה סביבה עבור Gemini לפני ההרצה
    if not os.getenv("GEMINI_API_KEY"):
        print("[ERROR] GEMINI_API_KEY is missing from .env!")
        sys.exit(1)

    run_official_benchmark(5, "train")  # מתחילים מ-5 משימות אימון קצרות