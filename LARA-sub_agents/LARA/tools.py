"""
LARA Tools v2 - Expanded toolkit for AppWorld
==============================================
Key additions vs. v1:
  * execute_python_code  -> main workhorse, lets the agent write real code
  * get_api_details      -> fetch parameter schema for a specific API
  * mark_task_complete   -> properly closes the task in AppWorld
  * Internal _execute_code_raw helper so we don't duplicate env.execute calls
"""

import json
from typing import Optional
from langchain.tools import tool
from appworld import AppWorld

try:
    from analysis import hardcode_trace
except ImportError:      # dev-only tracer — a missing analysis/ must never break a run
    class hardcode_trace:                                    # type: ignore[no-redef]
        note = note_specialist = note_code_block = start_task = end_task = \
            staticmethod(lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Global environment handle (set from main.py / benchmark.py)
# ---------------------------------------------------------------------------

env: Optional[AppWorld] = None


def set_appworld_env(new_env: AppWorld):
    global env
    env = new_env
    print(f"\n[SYSTEM] Tools re-wired to new task ID: {env.task.id}")


def get_current_task_instruction() -> str:
    if not env:
        return "Error: AppWorld environment is offline."
    return env.task.instruction


def evaluate_task() -> dict:
    """
    Returns the real AppWorld evaluation result.
    Mirrors what `appworld evaluate` does internally.
    Returns a dict: {completed, correct, pass_count, total_count, pass_percentage, failures}
    """
    if not env:
        return {"completed": False, "correct": False, "pass_count": 0, "total_count": 0,
                "pass_percentage": 0.0, "failures": []}
    completed = env.task_completed()
    if not completed:
        return {"completed": False, "correct": False, "pass_count": 0, "total_count": 0,
                "pass_percentage": 0.0, "failures": []}
    result = env.evaluate()
    return {
        "completed": True,
        "correct": result.success,
        "pass_count": result.pass_count,
        "total_count": result.total_count,
        "pass_percentage": result.pass_percentage,
        "failures": [f['requirement'] for f in result.failures[:5]],
    }


# ---------------------------------------------------------------------------
# Internal helper: raw code execution (not a @tool, used by other tools)
# ---------------------------------------------------------------------------

def _execute_code_raw(code: str) -> str:
    """Run code inside AppWorld. Returns stringified output or error."""
    if not env:
        return "Error: AppWorld offline."
    try:
        result = env.execute(code)
        return str(result) if result is not None else "[Code executed with no printed output]"
    except Exception as e:
        return f"Execution Failed: {e}"


def _strip_code_fences(code: str) -> str:
    """Remove ```python ... ``` fences if the LLM wrapped its code."""
    code = code.strip()
    if code.startswith("```python"):
        code = code[len("```python"):].strip()
    elif code.startswith("```"):
        code = code[3:].strip()
    if code.endswith("```"):
        code = code[:-3].strip()
    return code


# ---------------------------------------------------------------------------
# TOOL 1: Ping
# ---------------------------------------------------------------------------

@tool
def system_ping(dummy_input: str = "") -> str:
    """Pings the AppWorld engine to verify it is online. Input can be anything or empty."""
    print("\n[ACTION] Pinging AppWorld Environment...")
    return _execute_code_raw(
        "import datetime\nprint(f'System Online. Virtual Time: {datetime.datetime.now()}')"
    )


# ---------------------------------------------------------------------------
# TOOL 2: List apps
# ---------------------------------------------------------------------------

@tool
def list_available_apps(dummy_input: str = "") -> str:
    """Returns a list of all available applications installed in AppWorld.
    Input can be anything or empty."""
    print("\n[ACTION] Fetching list of available apps...")
    return _execute_code_raw("print(apis.api_docs.show_app_descriptions())")


# ---------------------------------------------------------------------------
# TOOL 3: Explore app APIs (high level list)
# ---------------------------------------------------------------------------

@tool
def explore_app_apis(app_name: str) -> str:
    """Returns the list of API methods and short descriptions for a specific application.
    Pass the app name as a simple lowercase string like 'spotify' or 'gmail'."""
    app_name = app_name.replace('"', '').replace("'", "").strip()
    # Documentation discovery at runtime. Traced because the call string is built
    # by our code, but this is the path AppWorld explicitly encourages ("read
    # documentation, explore, experiment") — it is the OPPOSITE of baking the API
    # list into a prompt, so its usage rate is the evidence that removing the
    # specialists' API listings has somewhere to fall back to.
    hardcode_trace.note("tools:explore_app_apis", detail=app_name)
    print(f"\n[ACTION] Fetching API docs for '{app_name}'...")
    code = f"print(apis.api_docs.show_api_descriptions(app_name='{app_name}'))"
    return _execute_code_raw(code)


# ---------------------------------------------------------------------------
# TOOL 4: Get detailed docs for a specific API (parameters + response schema)
# ---------------------------------------------------------------------------

@tool
def get_api_details(json_input: str) -> str:
    """Get detailed documentation for a SPECIFIC API method (parameters + response schema).
    Action Input MUST be a valid JSON string with 'app_name' and 'api_name' keys.
    Example Action Input: {"app_name": "spotify", "api_name": "show_liked_songs"}

    Call this BEFORE executing an API you haven't used — it tells you what parameters it needs
    (e.g., access_token, pagination) and what the response looks like."""
    try:
        data = json.loads(json_input)
        app_name = data.get("app_name")
        api_name = data.get("api_name")
        if not app_name or not api_name:
            return "Error: JSON must contain both 'app_name' and 'api_name'."
    except Exception as e:
        return f"Error: Action Input must be valid JSON. Details: {e}"

    hardcode_trace.note("tools:get_api_details", detail=f"{app_name}.{api_name}")
    print(f"\n[ACTION] Getting detailed docs for {app_name}.{api_name}...")
    code = f"print(apis.api_docs.show_api_doc(app_name='{app_name}', api_name='{api_name}'))"
    return _execute_code_raw(code)


# ---------------------------------------------------------------------------
# TOOL 5: execute_python_code — THE MAIN WORKHORSE
# ---------------------------------------------------------------------------

@tool
def execute_python_code(code: str) -> str:
    """Execute arbitrary Python code inside AppWorld. This is your MAIN tool.
    You have access to the `apis` object which exposes all apps
    (e.g. apis.spotify, apis.gmail, apis.supervisor).
    Use print() to see results. You can chain multiple API calls and process data in ONE call.

    AUTHENTICATION PATTERN (most apps require login first):
        accounts = apis.supervisor.show_account_passwords()
        # accounts is a list of dicts: [{"account_name": "spotify", "username": ..., "password": ...}, ...]
        cred = next(a for a in accounts if a['account_name'] == 'spotify')
        login = apis.spotify.login(username=cred['username'], password=cred['password'])
        token = login['access_token']
        # Pass token to subsequent calls: apis.spotify.show_liked_songs(access_token=token)

    The code can be multi-line and use loops, comprehensions, try/except, etc.
    """
    if not env:
        return "Error: AppWorld offline."

    code = _strip_code_fences(code)

    print(f"\n[ACTION] Executing Python code ({len(code)} chars)...")
    print("----- CODE -----")
    print(code[:800] + ("..." if len(code) > 800 else ""))
    print("----------------")

    try:
        result = env.execute(code)
        output = str(result) if result is not None else "[No printed output]"
        print(f"----- RESULT -----\n{output[:800]}\n------------------")
        return output
    except Exception as e:
        err = f"Execution Failed: {e}"
        print(f"----- ERROR -----\n{err}\n-----------------")
        return err


# ---------------------------------------------------------------------------
# TOOL 6: Mark task complete — closes the task in AppWorld
# ---------------------------------------------------------------------------

@tool
def mark_task_complete(answer: str = "") -> str:
    """Call this ONLY when you have definitively found the answer to the task.
    This notifies AppWorld that the task is finished. Pass the final answer as a string.

    For answer-tasks: mark_task_complete(answer='The Song Title Here')
    For action-tasks (send email etc.): mark_task_complete(answer='done')
    For list answers: mark_task_complete(answer='["item1", "item2"]')
    """
    if not env:
        return "Error: AppWorld offline."

    print(f"\n[ACTION] Marking task complete with answer: {answer[:200]}")
    # Use repr() to safely escape any quotes/newlines in the answer
    code = f"apis.supervisor.complete_task(answer={repr(answer)})\nprint('TASK_MARKED_COMPLETE')"
    try:
        result = env.execute(code)
        return f"Task marked complete. Output: {result}"
    except Exception as e:
        # Fallback: some task types don't accept an answer parameter
        try:
            code2 = "apis.supervisor.complete_task()\nprint('TASK_MARKED_COMPLETE_NO_ANSWER')"
            result = env.execute(code2)
            return f"Task marked complete (no-answer variant). Output: {result}"
        except Exception as e2:
            return f"complete_task failed: {e}. Fallback also failed: {e2}"


# ---------------------------------------------------------------------------
# TOOL 7 (legacy): execute_app_api — kept for backward compatibility
# ---------------------------------------------------------------------------

@tool
def execute_app_api(json_input: str) -> str:
    """Execute ONE specific API method. For anything more complex, use execute_python_code instead.
    Action Input MUST be valid JSON with 'app_name', 'api_method', and optionally 'parameters'.
    Example: {"app_name": "spotify", "api_method": "show_liked_songs",
              "parameters": {"access_token": "xyz"}}
    """
    try:
        data = json.loads(json_input)
        app_name = data.get("app_name")
        api_method = data.get("api_method")
        parameters = data.get("parameters", {})
        if not app_name or not api_method:
            return "Error: JSON must contain both 'app_name' and 'api_method'."
    except Exception as e:
        return f"Error: Action Input must be valid JSON. Details: {e}"

    print(f"\n[ACTION] Executing {app_name}.{api_method} with args: {parameters}")
    kwargs = ", ".join([f"{k}={repr(v)}" for k, v in parameters.items()])
    code = f"res = apis.{app_name}.{api_method}({kwargs})\nprint(res)"
    return _execute_code_raw(code)


# ---------------------------------------------------------------------------
# Export lists
# ---------------------------------------------------------------------------

# Tools for the Explorer agent (discovery only)
explorer_tools = [
    list_available_apps,
    explore_app_apis,
    get_api_details,
]

# Tools for the Executor agent (action)
executor_tools = [
    execute_python_code,
    mark_task_complete,
    execute_app_api,
    system_ping,
]

# Full set
appworld_tools = [
    system_ping,
    list_available_apps,
    explore_app_apis,
    get_api_details,
    execute_python_code,
    mark_task_complete,
    execute_app_api,
]