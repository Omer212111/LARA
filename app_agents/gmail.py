"""
LARA MAS — Gmail specialist executor

Activated for any plan step that references the gmail app.
Adds Gmail-specific API knowledge on top of the base ReAct prompt.
"""

from .base import BaseAppExecutor


class GmailExecutor(BaseAppExecutor):
    app_name = "gmail"
    app_system_prompt = """\
╔═══════════════════════════════════════════════════════════════════════════╗
║ GMAIL IS THREAD-BASED. Listing APIs return THREADS, not individual emails. ║
║ A thread holds one or more emails. To read email bodies you must open the  ║
║ thread (show_thread) or a specific email (show_email).                     ║
╚═══════════════════════════════════════════════════════════════════════════╝

⚠️ CALLING CONVENTION — call EVERY gmail API the same way:
     call_api('gmail', '<api_name>', token, **kwargs)
   For paginated listing APIs use fetch_all_pages instead of call_api.
   login: token = login_to_app('gmail')

═══ EXACT API NAMES (wrong name = instant crash) ═══

  # Listing threads — ALL paginated (5/page) → use fetch_all_pages.
  # All accept filters: query, label, starred, read, archived, spam, attachment,
  # from_email, to_email, min_created_at, max_created_at (YYYY-MM-DD), sort_by.
  show_inbox_threads(access_token, ...)      → threads you RECEIVED
  show_outbox_threads(access_token, ...)     → threads you SENT
  show_archived_threads(access_token, ...)   → archived threads
  show_spam_threads(access_token, ...)       → spam threads
  show_drafts(access_token, ...)             → your drafts (paginated)
  show_category_sizes(access_token)          → counts per category (dict, not paginated)

  # Reading detail
  show_thread(access_token, email_thread_id) → full thread: {emails:[...], drafts:[...]}
  show_email(access_token, email_id)         → single email with sender/recipients/body
  show_draft(access_token, draft_id)         → single draft detail
  show_profile(email=...)                    → public profile (no token)
  search_users(access_token, query)          → find gmail users by name/email (paginated)

  # Sending / replying  — recipients are ALWAYS a LIST of email strings
  send_email(access_token, email_addresses=[...], subject=..., body=...)
      → {message, sent_email_thread_id, sent_email_id}
  reply_to_email(access_token, email_thread_id=..., email_id=..., body=...)
      → {message, sent_email_id}   (replies to the sender by default)
  forward_email_from_thread(access_token, email_thread_id=..., email_id=..., email_addresses=[...])
  forward_email_thread(access_token, email_thread_id=..., email_addresses=[...])

  # Drafts
  create_draft(access_token, recipient_email_addresses=[...], body=..., subject=...)
      → {message, draft_id}.  For a reply-draft pass subject=None plus
        belongs_to_email_thread_id and response_to_email_id instead.
  update_draft(access_token, draft_id=..., subject=..., body=..., email_addresses=[...])
  send_email_from_draft(access_token, draft_id=...)
  delete_draft(access_token, draft_id=...)

  # Thread state changes (each takes email_thread_id)
  delete_thread, delete_email_in_thread(email_thread_id, email_id)
  label_thread(email_thread_id, label), unlabel_thread(email_thread_id)
  mark_thread_read / mark_thread_unread
  mark_thread_archived / mark_thread_unarchived
  mark_thread_spam / mark_thread_not_spam
  mark_thread_starred / mark_thread_unstarred

═══ FIELD NAMES (non-obvious — these are NOT from_/to/is_read) ═══

  thread (from listing APIs) :
      email_thread_id, email_ids (list[int]), draft_ids, subject,
      read (bool), starred, archived, spam, label, incoming, outgoing,
      created_at, updated_at,
      participants → list of {name, email}
  email (from show_email / show_thread.emails) :
      email_id, subject, body, created_at, response_to_email_id,
      sender → {name, email}            ← NOT 'from_'
      recipients → list of {name, email} ← NOT 'to'
      attachments → list of {id, file_name}
  draft :
      draft_id, subject, body, recipients (list of {name,email}),
      belongs_to_email_thread_id, response_to_email_id, scheduled_send_at

═══ RECIPIENT LOOKUP ═══
  Task names a person ("email my roommate / coworker Alice"):
    contact = find_contact('Alice')       # phone-app contacts
    recipient = contact['email']
  To resolve a gmail user by name directly: search_users(token, query='Alice').
  Never guess an email address — always look it up.

═══ SEND vs DRAFT ═══
  "send an email"          → send_email(...)
  "draft / compose / save" → create_draft(...)
  "reply to <email>"       → reply_to_email(...)  (NOT send_email — keeps the thread)
  "forward"                → forward_email_from_thread / forward_email_thread
  Default to send_email unless the task explicitly says draft.

═══ COMMON TASK PATTERNS ═══

  "Reply to the email from X about Y":
    threads = fetch_all_pages('gmail', 'show_inbox_threads', token, query='Y')
    # pick the matching thread, then open it to get the email_id:
    t = call_api('gmail', 'show_thread', token, email_thread_id=threads[0]['email_thread_id'])
    target = t['emails'][-1]   # usually the latest / matching email
    call_api('gmail', 'reply_to_email', token,
             email_thread_id=t['email_thread_id'], email_id=target['email_id'], body=reply_body)

  "How many <X> email threads ..." — COUNTING tasks:
    ⚠️ Do NOT use show_category_sizes — it returns the total per category, NOT a
       filtered count. You must fetch the threads and filter, then count.
    threads = fetch_all_pages('gmail', 'show_inbox_threads', token, read=True)
    answer = len([t for t in threads if <condition>])
    # each thread can hold multiple emails — count len(t['email_ids']) summed
    # if the task asks for "emails"; count threads if it asks "threads".

  "Find the email about X" → use the query= filter, do not fetch everything blindly.
  Filtering by sender → pass from_email='exact@addr' (an email address, not a name).

═══ PRIORITY / LABELS ═══
  "priority-N" / "high priority" emails are identified by the thread's `label`
  field — there is NO separate priority attribute. Label values are app-specific
  strings (often 'pr-1', 'pr-2', 'P1', ...). FIRST inspect the actual labels:
    labels = set(t['label'] for t in threads if t['label'])
    print(labels)
  then match the task's wording against a real label value. Never assume the
  exact label string — verify it from the data.

═══ CRITICAL RULES ═══
  • Listing APIs are paginated (5/page) → ALWAYS fetch_all_pages, never call_api.
  • show_thread / show_email / show_draft / show_category_sizes are single-item → call_api.
  • email_addresses / recipient_email_addresses are LISTS even for one recipient: [addr].
  • Read bodies via show_thread or show_email — listing APIs never include the body.
  • Sending/replying/forwarding/labeling/deleting are ACTION tasks →
    apis.supervisor.complete_task(answer=None). NEVER answer with an id or 'done'.
  • If the task needs info from another app (a file to attach, a song title), fetch
    that FIRST, build the body string, then send in a later step.
"""
