def filter_results(data: list, key: str, value) -> list:
    """
    Filters a list of dicts. Returns items where key contains value (case-insensitive).
    Example: filter_results(all_emails, 'subject', 'meeting')
    """
    if not isinstance(data, list):
        raise TypeError(f"filter_results expects a list, got {type(data).__name__}")
    value_lower = str(value).lower()
    return [item for item in data if value_lower in str(item.get(key, "")).lower()]


def find_one(data: list, key: str, value) -> dict | None:
    """
    Returns the first item where key contains value (case-insensitive), or None.
    Example: email = find_one(all_emails, 'subject', 'invoice')
    """
    results = filter_results(data, key, value)
    return results[0] if results else None


def get_by_id(data: list, id_key: str, id_value) -> dict | None:
    """
    Returns the first item where data[id_key] == id_value (exact match), or None.
    Example: contact = get_by_id(contacts, 'id', 42)
    """
    if not isinstance(data, list):
        raise TypeError(f"get_by_id expects a list, got {type(data).__name__}")
    for item in data:
        if item.get(id_key) == id_value:
            return item
    return None


def sort_results(data: list, key, reverse: bool = False) -> list:
    """
    Sorts a list of dicts by key. Returns a new sorted list.
    key can be a string field name OR a callable (lambda).
    Example (string):   sort_results(emails, 'date', reverse=True)
    Example (callable): sort_results(songs, lambda x: x.get('like_count', 0), reverse=True)
    """
    if not isinstance(data, list):
        raise TypeError(f"sort_results expects a list, got {type(data).__name__}")
    if callable(key):
        return sorted(data, key=key, reverse=reverse)
    return sorted(data, key=lambda x: x.get(key) or "", reverse=reverse)


def list_app_apis(app_name: str) -> list:
    """
    Returns all available API names and short descriptions for an app.

    Use this when:
      - You don't know which API to call for a given action.
      - You got 'No API named X found' — call this to see the real names.

    Example: list_app_apis('spotify')
    → [{"name": "show_playlist_library", "description": "..."}, ...]
    """
    return apis.api_docs.show_api_descriptions(app_name=app_name)


def get_api_doc(app_name: str, api_name: str) -> dict:
    """
    Returns the FULL specification for a specific API:
    exact parameter names, types, required/optional, and response field names.

    Use this BEFORE calling any API you haven't verified yet — it tells you:
      - Which parameter names to pass (e.g. 'playlist_id', not 'id')
      - What fields the response contains (e.g. 'song_id', not 'id')

    If the api_name doesn't exist, automatically falls back to list_app_apis()
    so you can pick the correct name.

    Example: get_api_doc('spotify', 'show_playlist_library')
    """
    try:
        return apis.api_docs.show_api_doc(app_name=app_name, api_name=api_name)
    except Exception as e:
        # API name is wrong — return the real list so the caller can pick correctly
        try:
            available = list_app_apis(app_name)
            return {
                "error": f"No API named '{api_name}' in '{app_name}'.",
                "hint": "Choose the correct name from 'available_apis' below.",
                "available_apis": available,
            }
        except Exception:
            return {"error": str(e)}


class Blackboard:
    """
    Shared communication channel between PlannerAgent and ExecutorAgent.

    Planner writes to it during discovery and planning:
        blackboard.add_apis('spotify', filtered_apis)
        blackboard.set_plan(["Step 1: ...", "Step 2: ..."], status="complete")
        print(blackboard)   # always print so the output is visible

    Executor reads the plan and marks progress:
        print(blackboard.plan_text())   # read the full plan at any time
        blackboard.mark_done(1)         # mark step 1 complete after finishing it
    """

    def __init__(self):
        self.discovered_apps = []    # list of relevant app names
        self.discovered_apis = {}    # {app_name: [api_name, ...]}
        self.plan_steps      = []    # ordered list of step strings
        self.plan_status     = ""    # "complete" | "incomplete"
        self.completed_steps = []    # step numbers finished by executor
        self.notes           = ""    # free-form notes from either agent

    def add_apis(self, app_name: str, apis_list: list) -> None:
        """Store filtered API names for an app after discovery."""
        self.discovered_apis[app_name] = [
            a["name"] if isinstance(a, dict) else str(a) for a in apis_list
        ]

    def set_plan(self, steps: list, status: str = "complete") -> None:
        """Planner calls this as its FINAL step to submit the execution plan."""
        self.plan_steps  = [str(s) for s in steps]
        self.plan_status = status

    def mark_done(self, step_num: int) -> None:
        """Executor calls this after completing each step."""
        if step_num not in self.completed_steps:
            self.completed_steps.append(step_num)

    def plan_text(self) -> str:
        """Returns the plan as a numbered string."""
        if not self.plan_steps:
            return "(no plan)"
        return "\n".join(f"# Step {i+1}: {s}" for i, s in enumerate(self.plan_steps))

    def __repr__(self) -> str:
        steps_str = "\n".join(f"    {i+1}. {s}" for i, s in enumerate(self.plan_steps)) or "    (none)"
        return (
            f"Blackboard(\n"
            f"  status   = {self.plan_status!r}\n"
            f"  apps     = {self.discovered_apps}\n"
            f"  plan     =\n{steps_str}\n"
            f"  done     = {self.completed_steps}\n"
            f")"
        )


blackboard = Blackboard()


def filter_apis(apis_list: list, keywords: list) -> list:
    """
    Filters an API description list to only entries whose name or description
    contains at least one of the given keywords (case-insensitive).
    Use this right after show_api_descriptions to cut a large API list down to
    only the APIs relevant to your task before printing or planning.
    Example: relevant = filter_apis(all_apis, ['playlist', 'create', 'song'])
             print(relevant)
    """
    if not isinstance(apis_list, list):
        raise TypeError(f"filter_apis expects a list, got {type(apis_list).__name__}")
    keywords_lower = [str(k).lower() for k in keywords]
    return [
        api for api in apis_list
        if any(
            kw in api.get("name", "").lower() or kw in api.get("description", "").lower()
            for kw in keywords_lower
        )
    ]


def paginate_all(api_fn, page_size: int = 20,
                 page_key: str = "page_index", size_key: str = "page_limit",
                 **kwargs) -> list:
    """
    Collects all pages from a paginated API. Stops when an empty page is returned.
    Defaults match AppWorld convention: page_index (0-based) + page_limit.
    Example: all_playlists = paginate_all(apis.spotify.show_playlist_library, access_token=token)
    For APIs with different param names: paginate_all(fn, page_key="page", size_key="limit", ...)
    """
    results = []
    page = 0  # AppWorld uses 0-based page indexing
    while True:
        data = api_fn(**{page_key: page, size_key: page_size, **kwargs})
        if not data:
            break
        results.extend(data)
        if len(data) < page_size:
            break
        page += 1
    return results


# ── High-level helpers (reduce boilerplate in executor code) ──────────────────

def login_to_app(app_name: str) -> str:
    """
    Login to any AppWorld app in one call. Returns access_token.
    Handles supervisor email lookup + credential lookup + login automatically.
    Example: token = login_to_app('spotify')
    """
    email = apis.supervisor.show_profile()['email']
    accounts = apis.supervisor.show_account_passwords()
    cred = find_one(accounts, 'account_name', app_name)
    if not cred:
        raise ValueError(f"No credentials found for app '{app_name}'")
    result = getattr(apis, app_name).login(username=email, password=cred['password'])
    return result['access_token']


def call_api(app_name: str, api_name: str, token: str, **kwargs):
    """
    Call any AppWorld API with access_token injected automatically.
    Works for both read and write/update operations.
    Example: songs  = call_api('spotify', 'show_liked_songs', token)
    Example: call_api('spotify', 'rate_song', token, song_id=123, rating=5)
    """
    func = getattr(getattr(apis, app_name), api_name)
    return func(access_token=token, **kwargs)


def get_field(data: list, match_key: str, match_value, return_key: str, default=None):
    """
    From a list of dicts, return return_key of the first item where item[match_key] == match_value.
    Returns default if not found.
    Example: song_id = get_field(songs, 'title', 'Silver Lining', 'song_id')
    """
    for item in data:
        if item.get(match_key) == match_value:
            return item.get(return_key, default)
    return default


def find_contact(name: str) -> dict | None:
    """
    Look up a person by name in the phone app contacts.
    Use for roommates, coworkers, friends, siblings — any relationship-based lookup.
    Returns the full contact dict (has 'email', 'phone_number', etc.) or None.
    Example: contact = find_contact('Alice')
             email   = contact['email']
    """
    token = login_to_app('phone')
    try:
        results = apis.phone.search_contacts(access_token=token, query=name)
        if results:
            return results[0]
    except Exception:
        pass
    all_contacts = apis.phone.show_contacts(access_token=token)
    name_lower = name.lower()
    matches = [c for c in all_contacts
               if name_lower in str(c.get('name') or c.get('full_name') or '').lower()]
    return matches[0] if matches else None
