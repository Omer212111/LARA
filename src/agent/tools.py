import json
from typing import Optional
from langchain.tools import tool
from appworld import AppWorld

# המשתנה שיחזיק את הסביבה שלנו - עכשיו הוא דינאמי
env: Optional[AppWorld] = None

def set_appworld_env(new_env: AppWorld):
    """
    [TECH LEAD FIX]:
    Updates the global environment for the tools.
    This is crucial so the Benchmark script can switch tasks in a loop!
    """
    global env
    env = new_env
    print(f"\n[SYSTEM] Tools re-wired to new task ID: {env.task.id}")

def get_current_task_instruction() -> str:
    if not env:
        return "Error: AppWorld environment is offline."
    return env.task.instruction

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