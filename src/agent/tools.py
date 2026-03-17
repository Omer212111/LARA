# --- להעתיק את הקוד הזה לראש הקובץ tools.py ---
import json
from typing import Optional
from langchain.tools import tool
import freezegun # <-- התוספת שלנו

# הגנה על ספריות התקשורת מפני קפיאת הזמן של הסימולטור
freezegun.configure(extend_ignore_list=["google", "httpx", "grpc", "urllib3", "langchain", "langchain_google_genai"])

from appworld import AppWorld, load_task_ids

print("\n[SYSTEM] Booting up REAL AppWorld Simulator Engine...")
try:
    real_task_id = load_task_ids("dev")[0]
    print(f"[SYSTEM] Loading Task ID: {real_task_id}")
    env = AppWorld(task_id=real_task_id)
except Exception as e:
    print(f"\n[ERROR] AppWorld Initialization failed. Error: {e}")
    env = None


@tool
def system_ping() -> str:
    """Pings the AppWorld engine to verify it is online and returns the current virtual time."""
    print("\n[ACTION] Pinging AppWorld Environment...")
    if not env: return "Error: AppWorld offline."
    code = "import datetime\nprint(f'System Online. Virtual Time: {datetime.datetime.now()}')"
    return str(env.execute(code))


@tool
def list_available_apps() -> str:
    """Returns a list of all available applications installed in the AppWorld environment with their descriptions."""
    print("\n[ACTION] Fetching list of available apps...")
    if not env: return "Error: AppWorld offline."
    # שימוש בדרך הרשמית של AppWorld לשלוף את רשימת האפליקציות המותקנות
    code = "print(apis.api_docs.show_app_descriptions())"
    try:
        return str(env.execute(code))
    except Exception as e:
        return f"Error listing apps: {e}"


@tool
def explore_app_apis(app_name: str) -> str:
    """Retrieves the API documentation and available methods for a specific application."""
    print(f"\n[ACTION] Fetching API docs for '{app_name}'...")
    if not env: return "Error: AppWorld offline."
    # קריאה רשמית לדוקומנטציה של אפליקציה ספציפית
    code = f"print(apis.api_docs.show_api_descriptions(app_name='{app_name}'))"
    try:
        return str(env.execute(code))
    except Exception as e:
        return f"Error retrieving docs: {e}"


@tool
def execute_app_api(app_name: str, api_method: str, parameters: Optional[dict] = None) -> str:
    """Executes a specific API method within an AppWorld application."""
    if parameters is None:
        parameters = {}

    print(f"\n[ACTION] Executing {app_name}.{api_method} with args: {parameters}")
    if not env: return "Error: AppWorld offline."

    kwargs = ", ".join([f"{k}={repr(v)}" for k, v in parameters.items()])
    # הזרקת datetime לתוך סביבת הריצה של הקוד
    code = f"import datetime\nres = apis.{app_name}.{api_method}({kwargs})\nprint(res)"

    try:
        response = env.execute(code)
        return str(response)
    except Exception as e:
        return f"API Execution Failed: {str(e)}"



appworld_tools = [system_ping, list_available_apps, explore_app_apis, execute_app_api]

def get_current_task_instruction() -> str:
    """Returns the text instruction of the currently loaded AppWorld task."""
    if not env:
        return "Error: AppWorld environment is offline."
    return env.task.instruction