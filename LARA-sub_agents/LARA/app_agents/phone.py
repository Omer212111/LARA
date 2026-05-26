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
   token = login_to_app('phone')        ← bootstrap auto-uses phone_number for login
   Paginated → fetch_all_pages.   Non-paginated → call_api.

═══ EXACT API NAMES ═══

  # Contacts (this is the high-value surface — group resolution lives here)
  show_contact_relationships(token)                → list[str]: AVAILABLE relationship types
  search_contacts(token, query='', relationship=None, page_index=0, page_limit=5)
                                                   → paginated list of contact dicts
  add_contact(token, first_name, last_name, phone_number, email,
              relationships, birthday=None, home_address=None, work_address=None)
  update_contact(token, contact_id, **fields)
  delete_contact(token, contact_id)

  # Date / time — the sandbox clock (NOT today's real date)
  get_current_date_and_time(token)                 → {'date': 'YYYY-MM-DD', 'time': 'HH:MM:SS'}

  # Text & voice messages
  show_text_message_window(token, phone_number, min_datetime=None, max_datetime=None,
                           pagination_order=None, page_index=0, page_limit=5) → paginated
  search_text_messages(token, query='', ...)       → paginated
  show_text_message(token, text_message_id)
  send_text_message(token, phone_number, message)  → {message, text_message_id}
  delete_text_message(token, text_message_id)
  show_voice_message_window(...)                   → mirror of text_message_window
  search_voice_messages(token, query='', ...)
  send_voice_message(token, phone_number, message) → {message, voice_message_id}

  # Alarms
  show_alarms(token, page_index=0, page_limit=5)   → paginated
  show_alarm(token, alarm_id)
  create_alarm(token, time, repeat_days=None, label='', enabled=True,
               snooze_minutes=None, vibration=None) → {message, alarm_id}
  update_alarm(token, alarm_id, **fields)
  delete_alarm(token, alarm_id)

═══ FIELD NAMES (non-obvious) ═══

  contact:
      contact_id, first_name, last_name, email, phone_number,
      relationships (list[str], e.g. ['roommate'], ['manager','coworker']),
      birthday, home_address, work_address, created_at

  text/voice message:
      text_message_id (or voice_message_id), sender, receiver, message, sent_at

  alarm:
      alarm_id, time, repeat_days, label, enabled, snooze_minutes, vibration

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
  token = login_to_app('phone')
  group = fetch_all_pages('phone', 'search_contacts', token, relationship='roommate')
  emails       = [c['email']        for c in group]
  phone_numbers = [c['phone_number'] for c in group]

  # 2) Resolve ONE person by name → email/phone (single-person tasks)
  token = login_to_app('phone')
  hits = fetch_all_pages('phone', 'search_contacts', token, query='Alice')
  alice = hits[0]                        # take the first match — already filtered
  email, phone = alice['email'], alice['phone_number']

  # 3) Confirm a relationship type exists before searching
  token = login_to_app('phone')
  types = call_api('phone', 'show_contact_relationships', token)
  # types looks like ['brother','coworker','father','friend','manager','mother',
  #                   'parent','roommate','sibling'] — use exactly one of these.

  # 4) Sandbox clock — "yesterday" / "last 5 days" / "today"
  # NEVER use datetime.now() — the sandbox clock is not the wall clock.
  from datetime import datetime, timedelta
  token = login_to_app('phone')
  now   = call_api('phone', 'get_current_date_and_time', token)   # {'date': ..., 'time': ...}
  today = datetime.strptime(now['date'], '%Y-%m-%d')
  since = (today - timedelta(days=5)).strftime('%Y-%m-%d')

  # 5) Send a text message to one person
  token = login_to_app('phone')
  hits = fetch_all_pages('phone', 'search_contacts', token, query='Bob')
  call_api('phone', 'send_text_message', token,
           phone_number=hits[0]['phone_number'], message='Hi Bob')
  apis.supervisor.complete_task(answer=None)

═══ CROSS-APP DEPENDENCIES ═══
  • Credentials → login_to_app('phone') already handles supervisor lookup AND uses
    the supervisor profile's phone_number as the username (phone is the ONE app
    that does not authenticate by email). Do not roll your own login.

═══ CRITICAL RULES ═══
  • Group lookup: ALWAYS use search_contacts(relationship='<type>'). NEVER guess emails.
  • show_contact_relationships gives TYPES, not PEOPLE — do not iterate it for emails.
  • Sandbox clock ≠ today. Use get_current_date_and_time, never datetime.now().
  • search_contacts is paginated — use fetch_all_pages or you will miss group members
    beyond the first 5 results.
  • Action tasks (send_text_message, create_alarm, delete_contact...) →
    apis.supervisor.complete_task(answer=None). Value tasks return the computed value.
=== SURFACE: phone_specialist:prompt === END
"""
