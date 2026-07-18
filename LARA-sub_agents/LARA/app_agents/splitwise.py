"""
LARA MAS — Splitwise specialist executor

Activated for any plan step that references the splitwise app.
Adds Splitwise-specific API knowledge on top of the base ReAct prompt.

All API/field names verified against data/api_docs/standard/splitwise.json.
"""

from .base import BaseAppExecutor


class SplitwiseExecutor(BaseAppExecutor):
    app_name = "splitwise"
    app_system_prompt = """\
=== SURFACE: splitwise_specialist:prompt === BEGIN
╔═══════════════════════════════════════════════════════════════════════════╗
║ SPLITWISE — tracks who owes whom. It is a LEDGER: recording a payment or   ║
║ settling up does NOT move real money (unlike Venmo). Expenses are split    ║
║ among debtors; balances net out what each person owes.                     ║
╚═══════════════════════════════════════════════════════════════════════════╝

⚠️ CALLING CONVENTION — call EVERY splitwise API the same way:
     call_api('splitwise', '<api_name>', token, **kwargs)
   login: token = login_to_app('splitwise')
   Paginated APIs → use fetch_all_pages. Balance/single-item APIs → call_api.

═══ BALANCES — the RIGHT way to answer "who owes whom" (do NOT sum expenses by hand) ═══

  show_people_balance(access_token)
      → {'you_owe_others': float, 'others_owe_you': float,
         'breakdown': [{'email', 'name', 'direction', 'amount'}]}
      direction ∈ {'you_owe_them', 'they_owe_you'}.  USE FOR:
        "who do I owe / who owes me", "net balance with each person",
        "person I owe the most" (filter direction=='you_owe_them', max by amount).
  show_person_balance(access_token, email)
      → {'direction', 'total', 'breakdown': [{'group_id','group_name','direction','amount'}]}
      USE FOR: "how much do I owe Alice" / "does Alice owe me".
  show_groups_balance(access_token)
      → {'you_owe_others','others_owe_you','breakdown':[{'group_id','group_name','you_owe_others','others_owe_you'}]}
      USE FOR: per-group aggregate balances.
  show_group_balance(access_token, group_id=None, email=None)
      → [{'source':{'name','email'}, 'source_owes_to_targets':{'total','breakdown':[{'email','name','amount'}]},
          'targets_owe_to_source':{'total','breakdown':[...]}}]
      USE FOR: detailed member-to-member balances inside a group.

═══ SETTLING UP (ACTION — ledger only, no real money) ═══
  settle_up(access_token, email, group_id=None, description='Settle up balance.')
      → {'message'}   USE FOR: "settle up with Alice" / "clear my balance with Bob".
      If the person is in a group and the task is about that group, pass group_id.

═══ RECORDING EXPENSES & PAYMENTS (ACTIONS) ═══
  record_expense(access_token, description, paid_amount, payer_email,
                 debtor_emails=[...], debt_amounts=[...] , group_id=None)
      → {'message','expense_id'}
      • payer_email = who PAID (usually YOUR own email: apis.supervisor.show_profile()['email']).
      • debtor_emails = everyone who owes a share (may include the payer for an even split).
      • debt_amounts OPTIONAL → if omitted, the amount is split EQUALLY among debtors.
        If passed, it MUST be the same length as debtor_emails.
      • group_id OPTIONAL → omit (None) for a non-group expense.
  record_payment(access_token, payer_email, receiver_email, amount, group_id=None, description=None)
      → {'message','payment_id'}   Ledger entry only — does NOT move real money.

═══ EXPENSES & ACTIVITY (reads) ═══
  show_expense(access_token, expense_id)
      → {'expense_id','group_id','description','paid_amount','deleted','receipt_file_name','created_at',
         'payer':{'name','email'}, 'creator':{'name','email'},
         'shares':[{'debtor':{'name','email'}, 'debt_amount'}]}
      ⚠️ per-person owed amount = share['debt_amount']  (inside the 'shares' list, NOT top-level).
  show_group_expenses(access_token, group_id, participant_email=None, min_amount=..., max_amount=...,
                      min_created_at=..., max_created_at=..., sort_by=None)  → paginated
  show_no_group_expenses(access_token, ...same filters...)                    → paginated (non-group expenses)
  show_activity(access_token, show_expenses=True, show_payments=True, sort_by='-created_at')  → paginated
      each record → {'record_type','amount','paid_by':{'name','email'},
                     'owed_by':[{'name','email','amount'}],'description','group_id','group_name','created_at'}

═══ GROUPS ═══
  show_groups(access_token)                → paginated [{'group_id','name','description','members',
                                                        'creator':{'name','email'},'invitation_code'}]
  show_group(access_token, group_id)       → single group dict
  create_group(access_token, name, member_emails=[...], description=None) → {'message','group_id'}  (ACTION)
  add_member_to_group / remove_member_from_group / delete_group / update_group → ACTIONS

═══ FINDING A PERSON'S EMAIL ═══
  Task names a person ("settle up with my roommate Alice"):
      contact = find_contact('Alice')      # phone-app contacts → returns email
      email   = contact['email']
  Never guess an email. (search_users(access_token, query=...) also finds splitwise users if needed.)

═══ PAGINATION ═══
  Paginated (5/page) — ALWAYS use fetch_all_pages:
    show_groups, show_activity, show_group_expenses, show_no_group_expenses,
    show_group_payments, show_no_group_payments, show_expense_comments,
    show_payment_comments, search_users, show_notifications
  NOT paginated — use call_api:
    show_expense, show_group, show_payment, show_person_balance, show_people_balance,
    show_group_balance, show_groups_balance

═══ COMMON TASK PATTERNS ═══

  "How much do I owe Alice in total?":
    token = login_to_app('splitwise')
    email = find_contact('Alice')['email']
    bal   = call_api('splitwise', 'show_person_balance', token, email=email)
    # bal['direction'] tells you the sign; bal['total'] is the magnitude
    apis.supervisor.complete_task(answer=str(bal['total']))

  "Who owes me the most money?":
    token = login_to_app('splitwise')
    people = call_api('splitwise', 'show_people_balance', token)['breakdown']
    owe_me = [p for p in people if p['direction'] == 'they_owe_you']
    top    = max(owe_me, key=lambda p: p['amount'])
    apis.supervisor.complete_task(answer=top['name'])

  "Settle up with Bob":
    token = login_to_app('splitwise')
    email = find_contact('Bob')['email']
    call_api('splitwise', 'settle_up', token, email=email)
    apis.supervisor.complete_task(answer=None)

  "I paid $60 for dinner, split evenly between me, Alice and Bob":
    token = login_to_app('splitwise')
    me    = apis.supervisor.show_profile()['email']
    alice = find_contact('Alice')['email']; bob = find_contact('Bob')['email']
    call_api('splitwise', 'record_expense', token, description='dinner',
             paid_amount=60, payer_email=me, debtor_emails=[me, alice, bob])   # equal split
    apis.supervisor.complete_task(answer=None)

═══ CRITICAL RULES ═══
  • record_expense / record_payment / settle_up / create_group / delete_* / update_* / add_member /
    remove_member = ACTION tasks → apis.supervisor.complete_task(answer=None). NEVER pass an id or 'done'.
  • Balance / total / count / "who owes ..." queries = VALUE tasks → pass the computed value.
  • settle_up and record_payment are LEDGER ONLY — they do NOT move real money. A task like
    "pay Alice back in Venmo and settle it in Splitwise" needs BOTH the venmo and splitwise apps.
  • Per-person owed amount lives in show_expense()['shares'][i]['debt_amount'] — not a top-level field.
  • debt_amounts (if given) must match debtor_emails length; omit it for an equal split.
  • expense_id, group_id, and payment_id are DISTINCT — never pass one where another is expected.
  • Date-filtered expenses: the sandbox clock ≠ today. Get the date via the phone app
    (get_current_date_and_time), then pass min_created_at / max_created_at as 'YYYY-MM-DD'.
=== SURFACE: splitwise_specialist:prompt === END
"""
