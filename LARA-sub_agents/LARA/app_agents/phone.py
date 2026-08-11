"""
LARA MAS — Phone specialist executor

Activated for any plan step that references the phone app.
The phone app is the ONLY source of relationship info (roommate, sibling, coworker, ...)
and the ONLY trustworthy clock in the sandbox.
"""

from .base import BaseAppExecutor


class PhoneExecutor(BaseAppExecutor):
    app_name = "phone"
    app_system_prompt = """\
=== SURFACE: phone_specialist:prompt === BEGIN
╔═══════════════════════════════════════════════════════════════════════════╗
║ PHONE — contacts (with relationships), text/voice messages, alarms,       ║
║ and the sandbox clock. Use this app whenever a task mentions a group      ║
║ ("my roommates / siblings / coworkers") or a relative date ("yesterday").  ║
╚═══════════════════════════════════════════════════════════════════════════╝

⚠️ CALLING CONVENTION
   call_api('phone', '<api_name>', token, **kwargs)
   token = login('phone')        ← the login() you defined in your first code block
   Paginated → fetch_all_pages.   Non-paginated → call_api.

═══ EXACT API NAMES ═══

  # Contacts (this is the high-value surface — group resolution lives here)
  show_contact_relationships(token)                → list[str]: AVAILABLE relationship types
  search_contacts(token, query='', relationship=None, page_index=0, page_limit=5)
                                                   → paginated list of contact dicts
  add_contact(token, first_name, last_name, phone_number, email=None,
              relationships=None, birthday=None, home_address=None, work_address=None)
  update_contact(token, contact_id, **fields)
  delete_contact(token, contact_id)

  # Date / time — the sandbox clock (NOT today's real date)
  get_current_date_and_time(token)                 → {'date': 'YYYY-MM-DD', 'time': 'HH:MM:SS'}

  # Text & voice messages  (phone_number= is how you filter by the other party)
  show_text_message_window(token, phone_number, min_datetime='1500-01-01|00:00:00',
                           max_datetime='3000-01-01|00:00:00',
                           pagination_order='descending',
                           page_index=0, page_limit=5) → paginated
                           # min/max_datetime format is 'YYYY-MM-DD|HH:MM:SS' (pipe, not space)
  search_text_messages(token, query='', phone_number=None, only_latest_per_contact=False,
                       page_index=0, page_limit=5, sort_by=None) → paginated
  show_text_message(token, text_message_id)
  send_text_message(token, phone_number, message)  → {message, text_message_id}
  delete_text_message(token, text_message_id)
  show_voice_message_window(token, phone_number, ...)  → mirror of text_message_window
  search_voice_messages(token, query='', phone_number=None, ...) → paginated
  show_voice_message(token, voice_message_id)
  send_voice_message(token, phone_number, message) → {message, voice_message_id}
  delete_voice_message(token, voice_message_id)

  # Alarms
  show_alarms(token, page_index=0, page_limit=5)   → paginated
  show_alarm(token, alarm_id)
  create_alarm(token, time, repeat_days=None, label=None, enabled=True,
               snooze_minutes=15, vibration=True) → {message, alarm_id}
  update_alarm(token, alarm_id, **fields)          → {message}
  delete_alarm(token, alarm_id)

═══ FIELD NAMES (non-obvious) ═══

  contact:
      contact_id, first_name, last_name, email, phone_number,
      relationships (list[str], e.g. ['roommate'], ['manager','coworker']),
      birthday, home_address, work_address, created_at

  text/voice message:
      text_message_id (or voice_message_id), message, sent_at,
      sender / receiver → NESTED DICTS {contact_id, name, phone_number}, not strings.
                          Use msg['sender']['phone_number'], never msg['sender'].

  alarm:
      alarm_id, time, repeat_days, label, enabled, snooze_minutes, vibration,
      created_at, user {name, phone_number}

═══ EASY TO CONFUSE ═══

  show_contact_relationships  → list of relationship TYPES available
                                (e.g. ['roommate','sibling','coworker',...]).
                                It does NOT return people. Useful only to confirm a type exists.
  search_contacts(relationship=X) → returns the PEOPLE who have that relationship.
                                    THIS is the call to get emails / phone numbers.
  search_contacts(query=name)     → returns people whose name matches; useful for one-person tasks.

═══ COMMON TASK PATTERNS ═══

  # 1) Resolve a GROUP → list of emails (the dominant use case)
  # Use this whenever a task says "my roommates / siblings / coworkers / friends / parents".
  token = login('phone')
  group = fetch_all_pages('phone', 'search_contacts', token, relationship='roommate')
  emails       = [c['email']        for c in group]
  phone_numbers = [c['phone_number'] for c in group]

  # 2) Resolve ONE person by name → email/phone (single-person tasks)
  token = login('phone')
  hits = fetch_all_pages('phone', 'search_contacts', token, query='Alice')
  print(hits)          # `query` is a plain text search: the API promises no ranking and
                       # no uniqueness, so check the name before trusting hits[0].
  alice = hits[0]
  email, phone = alice['email'], alice['phone_number']

  # 3) Confirm a relationship type exists before searching
  token = login('phone')
  types = call_api('phone', 'show_contact_relationships', token)
  print(types)   # THIS account's actual relationship strings. Pass one of the returned
                 # values verbatim to search_contacts(relationship=...); never guess a word.

  # 4) Sandbox clock — "yesterday" / "last 5 days" / "today"
  # NEVER use datetime.now() — the sandbox clock is not the wall clock.
  from datetime import datetime, timedelta
  token = login('phone')
  now   = call_api('phone', 'get_current_date_and_time', token)   # {'date': ..., 'time': ...}
  today = datetime.strptime(now['date'], '%Y-%m-%d')
  since = (today - timedelta(days=5)).strftime('%Y-%m-%d')

  # 5) Send a text message to one person
  token = login('phone')
  hits = fetch_all_pages('phone', 'search_contacts', token, query='Bob')
  call_api('phone', 'send_text_message', token,
           phone_number=hits[0]['phone_number'], message='Hi Bob')
  apis.supervisor.complete_task(answer=None)

═══ CROSS-APP DEPENDENCIES ═══
  • Credentials → phone is the ONE app that does NOT authenticate by email: its
    login username is the supervisor profile's phone_number. The login() helper you
    defined in your first code block already handles that — just call login('phone').

═══ CRITICAL RULES ═══
  • Group lookup: ALWAYS use search_contacts(relationship='<type>'). NEVER guess emails.
  • show_contact_relationships gives TYPES, not PEOPLE — do not iterate it for emails.
  • Sandbox clock ≠ today. Use get_current_date_and_time, never datetime.now().
  • search_contacts is paginated (page_limit defaults to 5, max 20) — use fetch_all_pages
    or you will miss group members beyond the first page.
  • Action tasks (send_text_message, create_alarm, delete_contact...) →
    apis.supervisor.complete_task(answer=None). Value tasks return the computed value.
=== SURFACE: phone_specialist:prompt === END
"""
