"""
LARA MAS — Gmail specialist executor

Activated for any plan step that references the gmail app.
Adds Gmail-specific API knowledge on top of the base ReAct prompt.
"""

from .base import BaseAppExecutor


class GmailExecutor(BaseAppExecutor):
    app_name = "gmail"
    app_system_prompt = """\
=== SURFACE: gmail_specialist:prompt === BEGIN
╔═══════════════════════════════════════════════════════════════════════════╗
║ GMAIL IS THREAD-BASED. Listing APIs return THREADS, not individual emails. ║
║ A thread holds one or more emails. To read email bodies you must open the  ║
║ thread (show_thread) or a specific email (show_email).                     ║
╚═══════════════════════════════════════════════════════════════════════════╝

⚠️ CALLING CONVENTION — call EVERY gmail API the same way:
     call_api('gmail', '<api_name>', token, **kwargs)
   For paginated listing APIs use fetch_all_pages instead of call_api.
   login: token = login('gmail')

═══ EXACT API NAMES (wrong name = instant crash) ═══

  # Listing threads — ALL paginated (5/page) → use fetch_all_pages.
  # All accept filters: query, label, starred, read, attachment,
  # from_email, to_email, min_created_at, max_created_at (YYYY-MM-DD), sort_by.
  # archived= / spam= default to False, so an inbox/outbox listing EXCLUDES
  # archived and spam threads unless you pass archived=True / spam=True.
  # (show_archived_threads has no archived=; show_spam_threads has no spam=.)
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
  show_profile(email=...)                    → public profile
  search_users(query=...)                    → gmail users (paginated)
      → [{first_name, last_name, email, registered_at}]
  ⚠️ show_profile and search_users declare NO access_token, but the helpers are still
     the right way to reach them: the injected token goes into a header the endpoint
     ignores, it does NOT crash. search_users is paginated at 5/page, so you MUST use
     fetch_all_pages('gmail', 'search_users', token, query='Alice') or you will only
     see the first five matches.

  # Sending / replying  — recipients are ALWAYS a LIST of email strings
  send_email(access_token, email_addresses=[...], subject=..., body=...)
      → {message, sent_email_thread_id, sent_email_id}
  reply_to_email(access_token, email_thread_id=..., email_id=..., body=...)
      → {message, sent_email_id}   (replies to the sender by default)
  forward_email_from_thread(access_token, email_thread_id=..., email_id=..., email_addresses=[...])
  forward_email_thread(access_token, email_thread_id=..., email_addresses=[...])
      both also accept draft_not_send=True → saves a draft instead of sending.

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
      email_id, subject, body, created_at,
      response_to_email_id (present on show_email, not in show_thread.emails),
      sender → {name, email}            ← NOT 'from_'
      recipients → list of {name, email} ← NOT 'to'
      attachments → list of {id, file_name}
  draft :
      draft_id, subject, body, recipients (list of {name,email}),
      belongs_to_email_thread_id, response_to_email_id, scheduled_send_at

═══ RECIPIENT LOOKUP ═══
  Every send/forward/draft API takes email ADDRESSES, never names. When the task
  names a person or a relationship, resolve it to an address first:
    contact = fetch_all_pages('phone', 'search_contacts', login('phone'), query='Alice')[0]       # phone-app contacts
    recipient = contact['email']
  Or resolve a gmail user directly:
    fetch_all_pages('gmail', 'search_users', token, query='Alice')
  → [{first_name, last_name, email, ...}]  — paginated, so never call_api here.
  Never guess or construct an email address — always look it up.

═══ SEND vs DRAFT ═══
  "send an email"          → send_email(...)
  "draft / compose / save" → create_draft(...)
  "reply to <email>"       → reply_to_email(...)  (NOT send_email — keeps the thread)
  "forward"                → forward_email_from_thread / forward_email_thread
  Default to send_email unless the task explicitly says draft.

═══ FINDING AND COUNTING THREADS ═══
  Narrow with the server-side filters instead of fetching everything blindly:
  query= for a topic/subject, from_email='exact@addr' for a sender (an address,
  not a name), min_created_at / max_created_at for a date window.
  Acting on ONE email needs both ids: listings only give you email_ids, so open
  the thread with show_thread and read the individual emails before calling
  reply_to_email / forward_email_from_thread / delete_email_in_thread.
  Counting: show_category_sizes takes only access_token and returns whole-category
  totals ({inbox, outbox, archived, spam, unscheduled_drafts, scheduled_drafts}) —
  it can never answer a FILTERED count. Fetch with fetch_all_pages, filter, len().
  A thread can hold several emails (email_ids is a list): count threads when asked
  for threads, sum len(t['email_ids']) when asked for emails.

═══ LABELS ═══
  `label` is a free-form string on the thread and the only classification field
  in the schema; the docs define no set of allowed values. Never assume a label
  string — print the real ones and match against those:
    print(set(t['label'] for t in threads if t['label']))
  label_thread(email_thread_id, label) sets it, unlabel_thread removes it.

═══ CRITICAL RULES ═══
  • Listing APIs are paginated (5/page) → ALWAYS fetch_all_pages, never call_api.
  • show_thread / show_email / show_draft / show_category_sizes are single-item → call_api.
  • email_addresses / recipient_email_addresses are LISTS even for one recipient: [addr].
  • Read bodies via show_thread or show_email — listing APIs never include the body.
  • Sending/replying/forwarding/labeling/deleting are ACTION tasks →
    apis.supervisor.complete_task(answer=None). NEVER answer with an id or 'done'.
  • If the body needs content from another app (a song title, a total), fetch that
    FIRST, build the body string, then send in a later step.
  • A file attachment is a real parameter, not body text: send_email /
    reply_to_email / create_draft take attachment_file_paths=['/abs/path'] plus
    file_system_access_token=login('file_system').
=== SURFACE: gmail_specialist:prompt === END
"""
