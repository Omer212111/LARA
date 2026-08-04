"""
LARA Executor Helpers
=====================
BOOTSTRAP_CODE is prepended to every code block the Executor runs.
These functions handle the most common AppWorld patterns so Qwen writes minimal code.

Available helpers (always in scope inside generated code):
  login_to_app(app_name)                              → access_token (cached in the ledger)
  call_api(app_name, api_name, token, **kwargs)       → API response (dict/list) — single call only
  fetch_all_pages(app_name, api_name, token, **kwargs)→ ALL pages merged — use for listing APIs!
  filter_results(items, field, value, partial=False)  → filtered list
  get_field(items, mf, mv, rf, default=None)          → single field value
  sort_by(items, field, reverse=False)                → sorted list
  find_contact(name)                                  → contact dict or None

Cross-app ledger (persists across ReAct steps AND across Executor attempts):
  remember(key, value) / recall(key, default)         → arbitrary intermediate values
  remember_entity(name, **fields) / recall_entity(name)→ per-person/thing cross-app record
  all_entities()                                      → list of every entity recorded
  ledger_summary()                                    → compact printable view

Why the ledger exists
---------------------
Multi-app tasks are database joins: "for each person in the CSV, if they have a
Venmo account send money, else add a Splitwise expense" needs a correspondence
table (name ↔ venmo_id ↔ splitwise_email ↔ amount). Before the ledger that table
had nowhere to live — it existed only as printed stdout in the conversation, so
the model re-derived it from its own prose every single step, and across attempts
only a 1500-char truncation of raw output survived. Tasks spanning 5+ apps scored
0/9 in the 2026-07-20 capability study.

The AppWorld sandbox is a single long-lived IPython shell per task
(environment.py: InteractiveShellEmbed, one per AppWorld context), so a dict in
its namespace survives every env.execute() — verified to survive ReAct steps,
raised exceptions, syntax errors, partially-failed blocks, and reviewer retries.
"""

BOOTSTRAP_CODE = '''\
# ── LARA Helpers (auto-injected) ─────────────────────────────────────────────

# ── Cross-app ledger ─────────────────────────────────────────────────────────
# Defined ONCE per task. The `except NameError` guard is essential: this whole
# block is re-injected ahead of EVERY code block, and an unguarded `def` would
# rebind _lara_store to a fresh object each step and silently drop everything
# stored so far. The data lives in a module-level cell rather than on the alias
# below, so that a stray `LARA_LEDGER = {...}` in generated code cannot destroy
# accumulated state.
try:
    _lara_store
except NameError:
    def _lara_store():
        """The ledger's real home — reachable only through these accessors."""
        return _LARA_STORE_DATA
    _LARA_STORE_DATA = {"entities": {}, "tokens": {}, "artifacts": {}}

LARA_LEDGER = _lara_store()   # read-only convenience view; use the accessors to write


def remember(key, value):
    """Store an intermediate value so later steps need not recompute it.
    Returns the value, so it chains: rows = remember('csv_rows', parsed)"""
    _lara_store()["artifacts"][key] = value
    return value


def recall(key, default=None):
    """Read back a value stored with remember(). Returns default if absent."""
    return _lara_store()["artifacts"].get(key, default)


def remember_entity(name, **fields):
    """Record what you learned about a PERSON or THING, keyed by name.
    MERGES — later calls add fields without erasing earlier ones, so you can
    build a row up across apps:
        remember_entity('Andrew', amount=42.50)          # from the CSV
        remember_entity('Andrew', venmo_id=118)          # from Venmo
        remember_entity('Andrew', splitwise_email='a@x') # from Splitwise
    Name matching is case/whitespace-insensitive. None values are ignored."""
    rec = _lara_store()["entities"].setdefault(str(name).strip().lower(), {"name": name})
    rec.update({k: v for k, v in fields.items() if v is not None})
    return rec


def recall_entity(name, default=None):
    """Everything known about a person/thing, as a dict. This turns a cross-app
    join into a lookup: recall_entity('Andrew')['venmo_id']"""
    return _lara_store()["entities"].get(str(name).strip().lower(), default)


def all_entities():
    """Every entity recorded so far, as a list of dicts. Iterate this to do the
    per-person work of a multi-app task."""
    return list(_lara_store()["entities"].values())


def ledger_summary():
    """Compact printable view of the ledger — print this to re-orient yourself."""
    st = _lara_store()
    ents, arts = st["entities"], st["artifacts"]
    lines = ["LEDGER: %d entities, %d artifacts, tokens for %s"
             % (len(ents), len(arts), sorted(st["tokens"]) or "none")]
    for k, v in list(ents.items())[:25]:
        lines.append("  %s -> %s" % (k, {a: b for a, b in v.items() if a != "name"}))
    for k, v in list(arts.items())[:15]:
        prev = str(v)
        if len(prev) > 120:
            prev = prev[:120] + "..."
        lines.append("  [%s] %s" % (k, prev))
    return "\\n".join(lines)


def login_to_app(app_name):
    """Login to any AppWorld app. Returns access_token string.
    Handles credential lookup + login automatically.
    Most apps authenticate by email; the phone app uses phone_number as the username.
    Tokens are cached in the ledger, so calling this again in a later step is free —
    it costs no API round-trip."""
    cached = _lara_store()["tokens"].get(app_name)
    if cached:
        return cached
    profile = apis.supervisor.show_profile()
    username = profile['phone_number'] if app_name == 'phone' else profile['email']
    accounts = apis.supervisor.show_account_passwords()
    cred = next((a for a in accounts if a['account_name'] == app_name), None)
    if not cred:
        raise ValueError(f"No credentials found for app '{app_name}'")
    result = getattr(apis, app_name).login(username=username, password=cred['password'])
    token = result['access_token']
    _lara_store()["tokens"][app_name] = token
    return token


def call_api(app_name, api_name, token, **kwargs):
    """Call any AppWorld API with access_token injected.
    Works for both read and write/update operations.
    Example: songs = call_api('spotify', 'show_liked_songs', token)
    Example: call_api('spotify', 'like_song', token, song_id=123)"""
    func = getattr(getattr(apis, app_name), api_name)
    return func(access_token=token, **kwargs)


def fetch_all_pages(app_name, api_name, token, **kwargs):
    """Fetch ALL pages from a paginated AppWorld API.
    MANY listing APIs (show_playlist_library, show_order_history, show_inbox, etc.)
    are paginated and return only 5 results per page by default.
    Always use this instead of call_api when fetching a full list.
    Example: playlists = fetch_all_pages('spotify', 'show_playlist_library', token)
    Example: emails    = fetch_all_pages('gmail', 'show_inbox', token)
    Uses page_index parameter starting from 0 (AppWorld convention).

    Safe on NON-paginated endpoints too:
    - if the API returns a dict (e.g. show_cart) → returns that dict unchanged.
    - if the API ignores page_index and returns the SAME list every page
      (e.g. show_wish_list) → returns it once, no duplication."""
    func = getattr(getattr(apis, app_name), api_name)
    results = []
    first_page = None
    page_index = 0
    while page_index < 20:  # safety cap
        page_data = func(access_token=token, page_index=page_index, **kwargs)
        # Non-paginated dict endpoint (show_cart, show_order, ...) — return as-is.
        if isinstance(page_data, dict):
            return page_data
        if not page_data:
            break
        # Non-paginated list endpoint returns the SAME list for every page_index.
        if page_index == 0:
            first_page = page_data
        elif page_data == first_page:
            break
        results.extend(page_data)
        page_index += 1
    return results


def filter_results(items, field, value, partial=False):
    """Filter a list of dicts where item[field] == value.
    partial=True: case-insensitive substring match.
    Example: liked = filter_results(txns, 'liked', True)
    Example: hits  = filter_results(songs, 'title', 'silver', partial=True)"""
    if partial:
        return [x for x in items if str(value).lower() in str(x.get(field, '')).lower()]
    return [x for x in items if x.get(field) == value]


def get_field(items, match_field, match_value, return_field, default=None):
    """From a list of dicts, find the first item where item[match_field] == match_value,
    then return item[return_field]. Returns default if not found.
    Example: song_id = get_field(songs, 'title', 'Silver Lining', 'song_id')"""
    for item in items:
        if item.get(match_field) == match_value:
            return item.get(return_field, default)
    return default


def sort_by(items, field, reverse=False):
    """Sort a list of dicts by a numeric or string field.
    reverse=True → descending (highest first), good for 'most liked', 'latest', etc.
    Example: top = sort_by(songs, 'like_count', reverse=True)[0]"""
    return sorted(items, key=lambda x: (x.get(field) or 0), reverse=reverse)


def find_contact(name):
    """Look up a person by name in the phone app contacts.
    Handles roommates, coworkers, friends, siblings — any relationship-based lookup.
    Returns the full contact dict (has 'email', 'phone_number', etc.) or None.
    Example: contact = find_contact('Alice')
             email   = contact['email']"""
    token = login_to_app('phone')
    name_lower = name.lower()
    # Try dedicated search API first (faster)
    try:
        results = apis.phone.search_contacts(access_token=token, query=name)
        if results:
            return results[0]
    except Exception:
        pass
    # Fallback: fetch all contacts and filter by name substring
    all_contacts = apis.phone.show_contacts(access_token=token)
    matches = [c for c in all_contacts
               if name_lower in str(c.get('name') or c.get('full_name') or '').lower()]
    return matches[0] if matches else None

# ─────────────────────────────────────────────────────────────────────────────
'''
