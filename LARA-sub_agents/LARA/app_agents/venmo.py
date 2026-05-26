"""
LARA MAS — Venmo specialist executor

Activated for any plan step that references the venmo app.
Adds Venmo-specific API knowledge on top of the base ReAct prompt.
"""

from .base import BaseAppExecutor


class VenmoExecutor(BaseAppExecutor):
    app_name = "venmo"
    app_system_prompt = """\
=== SURFACE: venmo_specialist:prompt === BEGIN
╔═══════════════════════════════════════════════════════════════════════════╗
║ VENMO — money moves between users via transactions or payment requests.   ║
║ "Send money" = create_transaction (push). "Request money" = create_       ║
║ payment_request (pull — the other person must approve).                   ║
╚═══════════════════════════════════════════════════════════════════════════╝

⚠️ CALLING CONVENTION — call EVERY venmo API the same way:
     call_api('venmo', '<api_name>', token, **kwargs)
   login: token = login_to_app('venmo')
   Paginated APIs → use fetch_all_pages. Non-paginated → call_api.

═══ EXACT API NAMES (wrong name = instant crash) ═══

  # Account / profile
  show_account(access_token)                        → private account info incl. venmo_balance
  show_profile(access_token, email=None)            → public profile + friends_since
  show_venmo_balance(access_token)                  → {'venmo_balance': float}
  search_users(access_token, query='')              → paginated list of user dicts
  search_friends(access_token, query='', user_email=None) → paginated list of friend dicts

  # Transactions (money sent/received between users)
  show_transactions(access_token, query='', user_email=None,
                    min_created_at=None, max_created_at=None,
                    min_amount=None, max_amount=None,
                    min_like_count=None, max_like_count=None,
                    private=None, direction=None,           ← 'sent' or 'received'
                    sort_by=None, page_index=0)             → paginated list
  show_transaction(access_token, transaction_id)            → single transaction dict
  create_transaction(access_token, receiver_email, amount,
                     description='', payment_card_id=None, private=False)
      → {message, transaction_id}
  update_transaction(access_token, transaction_id, description, private=None)
  download_transaction_receipt(access_token, transaction_id,
                                download_to_file_path=None, overwrite=False,
                                file_system_access_token=None)
      → {message, file_path}

  # Likes / comments on transactions
  like_transaction(access_token, transaction_id)
  unlike_transaction(access_token, transaction_id)
  show_transaction_comments(access_token, transaction_id)   → paginated list
  show_transaction_comment(access_token, comment_id)        → single comment dict
  create_transaction_comment(access_token, transaction_id, comment) → {message, comment_id}
  update_transaction_comment(access_token, comment_id, comment)
  delete_transaction_comment(access_token, comment_id)
  like_transaction_comment(access_token, comment_id)
  unlike_transaction_comment(access_token, comment_id)

  # Payment requests (one user asks another to pay them)
  show_received_payment_requests(access_token, status=None)  → paginated; status: 'pending'/'approved'/'denied'
  show_sent_payment_requests(access_token, status=None)       → paginated
  create_payment_request(access_token, user_email, amount,
                         description='', private=False)       → {message, payment_request_id}
  approve_payment_request(access_token, payment_request_id, payment_card_id=None)
  deny_payment_request(access_token, payment_request_id)
  delete_payment_request(access_token, payment_request_id)
  update_payment_request(access_token, payment_request_id,
                         amount=None, description=None, private=None)
  remind_payment_request(access_token, payment_request_id)   → sends reminder notification

  # Payment cards (linked to the Venmo account)
  show_payment_cards(access_token)                            → list (NOT paginated)
  show_payment_card(access_token, payment_card_id)            → single card dict
  add_payment_card(access_token, card_name, owner_name, card_number,
                   expiry_year, expiry_month, cvv_number)     → {message, payment_card_id}
  update_payment_card(access_token, payment_card_id, card_name)
  delete_payment_card(access_token, payment_card_id)

  # Balance top-up / withdrawal
  add_to_venmo_balance(access_token, amount, payment_card_id)
      → {message, bank_transfer_id}   (card → venmo balance)
  withdraw_from_venmo_balance(access_token, amount, payment_card_id)
      → {message, bank_transfer_id}   (venmo balance → card)
  show_bank_transfer_history(access_token, transfer_type=None)
      → paginated; transfer_type: 'card_to_venmo' or 'venmo_to_card'
  download_bank_transfer_receipt(access_token, bank_transfer_id,
                                  download_to_file_path=None, overwrite=False,
                                  file_system_access_token=None)

  # Social feed & notifications
  show_social_feed(access_token)                              → paginated (friends' transactions)
  show_notifications(access_token, read=None)                 → paginated
  show_notifications_count(access_token, read=None)           → {'notifications_count': float}
  mark_notification(access_token, notification_id, read)
  mark_notifications(access_token, read)                      → marks ALL
  delete_notification(access_token, notification_id)
  delete_notifications(access_token)                          → deletes ALL

  # Friends
  add_friend(access_token, user_email)
  remove_friend(access_token, user_email)

═══ FIELD NAMES (non-obvious) ═══

  transaction dict:
      transaction_id, amount, description, created_at, updated_at,
      private (bool), like_count, comment_count,
      payment_card_digits (last 4 digits of card used, or None if Venmo balance),
      sender   → {name, email}
      receiver → {name, email}

  payment_request dict:
      payment_request_id, amount, description, created_at, updated_at,
      approved_at, denied_at, private,
      sender   → {name, email}    ← the person who SENT the request (wants money)
      receiver → {name, email}    ← the person who must PAY

  comment dict:
      comment_id, transaction_id, comment, created_at, like_count,
      user → {name, email}

  payment card dict:
      payment_card_id, card_name, owner_name, card_number,
      expiry_year, expiry_month, cvv_number

  profile / user dict:
      first_name, last_name, email, registered_at, friends_since

  notification dict:
      notification_id, type, title, message, read (bool), created_at, data (dict)

═══ SEND vs REQUEST ═══
  "send / pay / transfer money TO someone"   → create_transaction(receiver_email=..., amount=...)
  "request / charge money FROM someone"      → create_payment_request(user_email=..., amount=...)
  "approve / pay a payment request"          → approve_payment_request(payment_request_id=...)
  "deny / reject a payment request"          → deny_payment_request(payment_request_id=...)

═══ RECIPIENT LOOKUP ═══
  Task names a person ("send money to my roommate Alice"):
    contact = find_contact('Alice')     # phone-app contacts → returns email
    receiver_email = contact['email']
  Never guess an email — always look it up first.

═══ PAYMENT SOURCE ═══
  By default, create_transaction draws from the Venmo balance.
  Pass payment_card_id to charge a card instead.
  show_payment_cards → list (NOT paginated) → pick by card_name if task specifies one.
  The sandbox clock is NOT today's date — NEVER filter cards by expiry_year/expiry_month
  using datetime.now(). Just use the card(s) as-is.

═══ PAGINATION ═══
  Paginated (5/page) — ALWAYS use fetch_all_pages:
    show_transactions, show_received_payment_requests, show_sent_payment_requests,
    show_transaction_comments, show_social_feed, show_notifications,
    search_users, search_friends, show_bank_transfer_history
  NOT paginated — use call_api:
    show_payment_cards, show_account, show_venmo_balance, show_transaction,
    show_transaction_comment, show_notifications_count

═══ COMMON TASK PATTERNS ═══

  "Send $X to Alice for <reason>":
    token = login_to_app('venmo')
    contact = find_contact('Alice')
    call_api('venmo', 'create_transaction', token,
             receiver_email=contact['email'], amount=X, description='<reason>')
    apis.supervisor.complete_task(answer=None)

  "How much money did I send to Alice total?":
    token = login_to_app('venmo')
    contact = find_contact('Alice')
    txns = fetch_all_pages('venmo', 'show_transactions', token,
                           user_email=contact['email'], direction='sent')
    total = sum(t['amount'] for t in txns)
    apis.supervisor.complete_task(answer=str(total))

  "Approve the payment request from Bob":
    token = login_to_app('venmo')
    reqs = fetch_all_pages('venmo', 'show_received_payment_requests', token, status='pending')
    contact = find_contact('Bob')
    req = next(r for r in reqs if r['sender']['email'] == contact['email'])
    call_api('venmo', 'approve_payment_request', token,
             payment_request_id=req['payment_request_id'])
    apis.supervisor.complete_task(answer=None)

  "What is my Venmo balance?":
    token = login_to_app('venmo')
    bal = call_api('venmo', 'show_venmo_balance', token)
    apis.supervisor.complete_task(answer=str(bal['venmo_balance']))

  "Download the receipt for my transaction with Alice":
    token = login_to_app('venmo')
    contact = find_contact('Alice')
    txns = fetch_all_pages('venmo', 'show_transactions', token,
                           user_email=contact['email'])
    tid = txns[0]['transaction_id']   # pick the relevant one
    call_api('venmo', 'download_transaction_receipt', token,
             transaction_id=tid)      # saves to ~/downloads by default
    apis.supervisor.complete_task(answer=None)

═══ CRITICAL RULES ═══
  • Sending / requesting / approving / denying / liking / commenting are ACTION tasks
    → apis.supervisor.complete_task(answer=None). NEVER pass a transaction_id or 'done'.
  • Querying amounts, counts, balances are VALUE tasks → pass the computed value.
  • show_transactions direction= is either 'sent' or 'received' — no other values.
  • payment_request sender = the person who WANTS money (created the request).
    payment_request receiver = the person who MUST PAY (you, if it's in received_payment_requests).
  • NEVER filter payment cards by expiry date — sandbox clock ≠ today.
=== SURFACE: venmo_specialist:prompt === END
"""
