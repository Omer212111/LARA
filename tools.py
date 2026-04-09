import json
from typing import Optional
from langchain.tools import tool
from appworld import AppWorld

env: Optional[AppWorld] = None


def set_appworld_env(new_env: AppWorld):
    global env
    env = new_env
    print(f"\n[SYSTEM] Tools re-wired to new task ID: {env.task.id}")


def get_current_task_instruction() -> str:
    if not env: return "Error: AppWorld environment is offline."
    return env.task.instruction


@tool
def system_ping(dummy_input: str = "") -> str:
    """Pings the AppWorld engine to verify it is online. Input can be anything or empty."""
    print("\n[ACTION] Pinging AppWorld Environment...")
    if not env: return "Error: AppWorld offline."
    code = "import datetime\nprint(f'System Online. Virtual Time: {datetime.datetime.now()}')"
    return str(env.execute(code))


@tool
def list_available_apps(dummy_input: str = "") -> str:
    """Returns a list of all available applications installed. Input can be anything or empty."""
    print("\n[ACTION] Fetching list of available apps...")
    if not env: return "Error: AppWorld offline."
    code = "print(apis.api_docs.show_app_descriptions())"
    try:
        return str(env.execute(code))
    except Exception as e:
        return f"Error listing apps: {e}"


@tool
def explore_app_apis(app_name: str) -> str:
    """Returns the API documentation and available methods for a specific application."""
    # STRIP QUOTES: Fixes Qwen's unterminated string literal errors
    app_name = app_name.replace('"', '').replace("'", "").strip()
    print(f"\n[ACTION] Fetching API docs for '{app_name}'...")
    if not env: return "Error: AppWorld offline."

    code = f"print(apis.api_docs.show_api_descriptions(app_name='{app_name}'))"
    try:
        return str(env.execute(code))
    except Exception as e:
        return f"Error retrieving docs: {e}"


@tool
def execute_app_api(json_input: str) -> str:
    """Executes a specific API method.
    Action Input MUST be a valid JSON dictionary string containing 'app_name', 'api_method', and optionally 'parameters'.
    Example Action Input: {"app_name": "spotify", "api_method": "show_song", "parameters": {"song_id": "123"}}
    """
    if not env: return "Error: AppWorld offline."

    try:
        # MANUAL PARSING: Bypasses LangChain's crash loop
        data = json.loads(json_input)
        app_name = data.get("app_name")
        api_method = data.get("api_method")
        parameters = data.get("parameters", {})
    except Exception as e:
        return f"Error: Action Input must be valid JSON format. Details: {e}"

    print(f"\n[ACTION] Executing {app_name}.{api_method} with args: {parameters}")
    kwargs = ", ".join([f"{k}={repr(v)}" for k, v in parameters.items()])
    code = f"import datetime\nres = apis.{app_name}.{api_method}({kwargs})\nprint(res)"

    try:
        response = env.execute(code)
        return str(response)
    except Exception as e:
        return f"API Execution Failed: {e}"


appworld_tools = [
    system_ping,
    list_available_apps,
    explore_app_apis,
    execute_app_api
]