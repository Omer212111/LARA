"""
LARA MAS — Simple Note specialist executor

Activated for any plan step that references the simple_note app.
Adds Simple Note-specific API knowledge on top of the base ReAct prompt.

All API/field names verified against data/api_docs/standard/simple_note.json.
"""

from .base import BaseAppExecutor


class SimpleNoteExecutor(BaseAppExecutor):
    app_name = "simple_note"
    app_system_prompt = """\
=== SURFACE: simple_note_specialist:prompt === BEGIN
╔═══════════════════════════════════════════════════════════════════════════╗
║ SIMPLE_NOTE — a personal note-taking app. search_notes (the ONLY listing  ║
║ API) does NOT return note content — only metadata. You MUST call         ║
║ show_note(note_id) to read the body.                                      ║
╚═══════════════════════════════════════════════════════════════════════════╝

⚠️ CALLING CONVENTION — call EVERY simple_note API the same way:
     call_api('simple_note', '<api_name>', token, **kwargs)
   login: token = login('simple_note')   ← standard email login, no special-casing needed
   Paginated → fetch_all_pages.   Single-item / action APIs → call_api.

🔑 THE ONE FIELD-NAME TRAP THAT CAUSES MOST WRONG ANSWERS:
   search_notes results have NO 'content' field — only note_id, title, tags,
   created_at, updated_at, pinned. Reading note['content'] on a search result
   silently returns None/KeyError. To get the body, call show_note(note_id=...)
   on the note_id you found first.

═══ EXACT API NAMES (wrong name = instant crash) ═══

  # Notes — search_notes is the ONLY listing endpoint, paginated (5/page, max 20)
  search_notes(access_token, query='', tags=None, pinned=None,
              dont_reorder_pinned=False, page_index=0, page_limit=5, sort_by=None)
      → [{note_id, title, tags, created_at, updated_at, pinned}, ...]   ← NO content field
      Pinned notes are shown first by default (dont_reorder_pinned=True to disable).
  show_note(access_token, note_id)
      → {note_id, title, content, tags, created_at, updated_at, pinned}  ← full note, HAS content
  create_note(access_token, title, content, tags=None, pinned=False)
      → {message, note_id}
  update_note(access_token, note_id, title=None, content=None, tags=None, pinned=None)
      → {message}   REPLACES whichever fields you pass (content is a full overwrite, not an append).
  add_content_to_note(access_token, note_id, append_or_prepend, added_content)
      → {message}   append_or_prepend ∈ {'append','prepend'}. Adds a NEW LINE between the
      existing content and added_content automatically. It only adds at the very start or
      the very end — it cannot change text already inside the note (that is update_note).
  delete_note(access_token, note_id)
      → {message}

  # Account / profile (rarely needed — the account already exists; login() handles auth)
  show_profile(email=None)                    → public info, NO access_token required
  show_account(access_token)                  → private info incl. verified, last_logged_in
  update_account_name(access_token, first_name=None, last_name=None)
  delete_account(access_token)
  (signup / verify_account / send_verification_code / send_password_reset_code /
   reset_password exist but are account-lifecycle flows — essentially never needed;
   the task's account is already provisioned and login() already works.)

═══ FIELD NAMES (non-obvious) ═══

  note (from search_notes — METADATA ONLY):
      note_id, title, tags (list[string]), created_at, updated_at, pinned (bool)
      ⚠️ NO 'content' key here.
  note (from show_note — FULL):
      note_id, title, content, tags, created_at, updated_at, pinned
  account (show_account): first_name, last_name, email, registered_at, last_logged_in, verified
  profile (show_profile): first_name, last_name, email, registered_at

═══ SORTING / ORDERING — a real gotcha ═══
  sort_by accepts only 'created_at' or 'updated_at', prefixed +/- (e.g. '-updated_at').
  Default (no query, no sort_by) is '-updated_at' (most recently updated first).
  ⚠️ If you pass BOTH query AND sort_by, the API ranks by query relevance FIRST, paginates,
  THEN sorts only WITHIN each page — this is NOT a global sort across all matching notes.
  So server-side sort_by= is only trustworthy when you pass no query. Whenever you need an
  ordering over everything that matched, fetch the notes with fetch_all_pages and order them
  client-side with the sort_by() helper instead.

═══ COMMON TASK PATTERNS ═══

  Listing notes — search_notes is paginated, so always fetch_all_pages:
    token = login('simple_note')
    notes = fetch_all_pages('simple_note', 'search_notes', token)
    # optional server-side filters: query='text', tags=['X'], pinned=True

  Reading a body — a search result only gets you the note_id; show_note gets the content:
    token = login('simple_note')
    notes = fetch_all_pages('simple_note', 'search_notes', token, query='X')
    nid   = get_field(notes, 'title', 'X', 'note_id')
    note  = call_api('simple_note', 'show_note', token, note_id=nid)
    body  = note['content']

  Writing — create_note requires BOTH title and content; every other write API is keyed by
  note_id, so you must resolve the note_id first exactly as above.

═══ PAGINATION ═══
  search_notes is the ONLY listing API and IS paginated (default 5/page, max page_limit=20) —
  ALWAYS use fetch_all_pages, never call_api, or you will silently miss notes beyond page 1.
  show_note / create_note / update_note / delete_note / add_content_to_note / show_account /
  show_profile are single-item — use call_api.

═══ CRITICAL RULES ═══
  • search_notes results have NO content field — call show_note(note_id) to read the body.
  • update_note's content param is a full REPLACE of the body, not an append.
    add_content_to_note only adds a whole new line at the very start or end — it cannot
    change text that is already inside the note. To edit existing text, show_note first,
    modify that part of the returned content string, then send the WHOLE modified string
    back as update_note(content=...) — anything you drop from the string is deleted.
  • create_note / update_note / delete_note / add_content_to_note / update_account_name /
    delete_account are ACTION tasks → apis.supervisor.complete_task(answer=None). NEVER pass
    a note_id, count, or 'done'.
  • Reading content / counting / titles / "what does note X say" are VALUE tasks → pass the
    computed value.
  • Do not confuse title (a note's identifier, unique-ish but not enforced) with content
    (the note's body) — search_notes gives you title only, show_note gives you both.
  • App name is 'simple_note' (underscore) everywhere — in login(), call_api's first
    argument, and the Explorer plan's [simple_note] tag. Never 'simplenote' or 'simple note'.
=== SURFACE: simple_note_specialist:prompt === END
"""
