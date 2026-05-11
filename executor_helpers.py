"""
LARA Executor Helpers
=====================
BOOTSTRAP_CODE is prepended to every code block the Executor runs.
These functions handle the most common AppWorld patterns so Qwen writes minimal code.

Available helpers (always in scope inside generated code):
  login_to_app(app_name)                              → access_token
  call_api(app_name, api_name, token, **kwargs)       → API response (dict/list)
  fetch_all(app_name, api_name, token, **kwargs)      → all pages combined into one list
  filter_results(items, field, value, partial=False)  → filtered list
  get_field(items, mf, mv, rf, default=None)          → single field value
  sort_by(items, field, reverse=False)                → sorted list
  find_contact(name)                                  → contact dict or None
"""

BOOTSTRAP_CODE = '''\
# ── LARA Helpers (auto-injected) ─────────────────────────────────────────────

def login_to_app(app_name):
    """Login to any AppWorld app. Returns access_token string.
    Handles email lookup + credential lookup + login automatically."""
    email = apis.supervisor.show_profile()['email']
    accounts = apis.supervisor.show_account_passwords()
    cred = next((a for a in accounts if a['account_name'] == app_name), None)
    if not cred:
        raise ValueError(f"No credentials found for app '{app_name}'")
    result = getattr(apis, app_name).login(username=email, password=cred['password'])
    return result['access_token']


def call_api(app_name, api_name, token, **kwargs):
    """Call any AppWorld API with access_token injected.
    Works for both read and write/update operations.
    Example: songs = call_api('spotify', 'show_liked_songs', token)
    Example: call_api('spotify', 'like_song', token, song_id='123')"""
    func = getattr(getattr(apis, app_name), api_name)
    return func(access_token=token, **kwargs)


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


def fetch_all(app_name, api_name, token, page_limit=20, **kwargs):
    """Fetch ALL pages from a paginated list API.
    Use instead of call_api whenever the result might span multiple pages.
    Example: playlists = fetch_all('spotify', 'show_playlist_library', token)
    Example: songs     = fetch_all('spotify', 'show_liked_songs', token)"""
    all_items = []
    for page in range(50):
        batch = call_api(app_name, api_name, token, page_index=page, page_limit=page_limit, **kwargs)
        if not batch:
            break
        all_items.extend(batch)
        if len(batch) < page_limit:
            break
    return all_items


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
