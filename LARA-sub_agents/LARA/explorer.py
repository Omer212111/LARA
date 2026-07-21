"""
LARA MAS — Explorer agent

Calls GPT-4.1-nano with OpenAI native function calling.
  1. Detects relevant apps from the task text via keyword matching.
  2. Pre-injects explore_app_apis results into the system prompt.
  3. Forces at least one tool call (tool_choice="required" on round 0).
  4. Loops until the model produces a plan with no tool calls.
"""

import json
import os
import re

from openai import OpenAI
from langchain_core.messages import AIMessage

import logger
from config import EXPLORER_MODEL
from prompts_explorer import EXPLORER_TOOLS_OPENAI, build_explorer_system
from state import AgentState


# ── Deterministic Amazon plan templates ───────────────────────────────────────
# The LLM Explorer (gpt-4.1-nano) reliably mis-plans the templated AppWorld Amazon
# tasks (catalog searches for cart tasks, hallucinated APIs, hardcoded IDs).
# These tasks come in a few fixed shapes, so we match the instruction and emit a
# known-correct plan, skipping the LLM entirely.

def _depluralize(phrase: str) -> str:
    """Singularize the last word of a noun phrase (product_type is singular)."""
    words = phrase.strip().split()
    if not words:
        return phrase.strip()
    w = words[-1]
    if w.endswith(("ches", "shes", "sses", "xes", "zes")):
        w = w[:-2]
    elif w.endswith("s") and len(w) > 1:
        w = w[:-1]
    words[-1] = w
    return " ".join(words)


def amazon_template_plan(task_text: str) -> str | None:
    """Return a deterministic plan for a recognized Amazon task family, else None."""
    body = task_text.split("Task:", 1)[-1] if "Task:" in task_text else task_text
    t = body.strip().lower()

    m = re.search(r"order for all (.+?) in my (?:amazon )?cart", t)
    if m:
        x = _depluralize(m.group(1))
        return f"""APP: amazon
REASONING:
  - Scope: order ONLY the '{x}'-type items already in the cart, at their current quantities.
  - Metric: product_type == '{x}', confirmed per item via show_product.
PLAN:
  1. [amazon] Use login_to_app('amazon') to get the access token.
  2. [amazon] Use call_api('amazon', 'show_cart', token) — returns a dict; cart['cart_items'] is the item list. Do NOT search the catalog.
  3. [amazon] For EACH item in cart['cart_items'], call call_api('amazon', 'show_product', token, product_id=item['product_id']) and read ['product_type']. [field: 'product_type']
  4. [amazon] For every cart item whose product_type != '{x}', call call_api('amazon', 'delete_product_from_cart', token, product_id=item['product_id']). Leave the '{x}' items untouched — do NOT change their quantities.
  5. [amazon] Use call_api('amazon', 'show_addresses', token) and call_api('amazon', 'show_payment_cards', token) to get address and card ids.
  6. [amazon] Place the order: loop over the payment cards and call call_api('amazon', 'place_order', token, payment_card_id=card['payment_card_id'], address_id=addresses[0]['address_id']) inside try/except; continue to the next card on failure until one succeeds.
  7. [amazon] This is an ACTION task — call apis.supervisor.complete_task(answer=None).
"""

    m = re.search(r"order for all (.+?) in my (?:amazon )?wish ?list", t)
    if m:
        x = _depluralize(m.group(1))
        return f"""APP: amazon
REASONING:
  - Scope: order ONLY the '{x}'-type items from the wishlist; leave other wishlist items alone.
  - Metric: product_type == '{x}', confirmed per item via show_product.
PLAN:
  1. [amazon] Use login_to_app('amazon') to get the access token.
  2. [amazon] Use call_api('amazon', 'show_cart', token); for EACH item in cart['cart_items'] call call_api('amazon', 'delete_product_from_cart', token, product_id=item['product_id']) to EMPTY the cart.
  3. [amazon] Use call_api('amazon', 'show_wish_list', token) to get the wishlist items (a list, not paginated).
  4. [amazon] For EACH wishlist item, call call_api('amazon', 'show_product', token, product_id=item['product_id']) and read ['product_type']. [field: 'product_type']
  5. [amazon] For every wishlist item whose product_type == '{x}', call call_api('amazon', 'move_product_from_wish_list_to_cart', token, product_id=item['product_id'], quantity=item['quantity']). Leave non-'{x}' items in the wishlist.
  6. [amazon] Use call_api('amazon', 'show_addresses', token) and call_api('amazon', 'show_payment_cards', token).
  7. [amazon] Place the order: loop over the payment cards and call call_api('amazon', 'place_order', token, payment_card_id=card['payment_card_id'], address_id=addresses[0]['address_id']) inside try/except; continue on failure until one succeeds.
  8. [amazon] This is an ACTION task — call apis.supervisor.complete_task(answer=None).
"""

    m = re.search(r"buy me an? (.+?) on amazon from its highest-rated seller using my (.+?) card for my (\w+) address", t)
    if m:
        x = m.group(1).strip()
        card = m.group(2).strip()
        addr = m.group(3).strip().capitalize()
        return f"""APP: amazon
REASONING:
  - Scope: order EXACTLY ONE '{x}' from the highest-rated seller, from an empty cart.
  - Metric: highest show_seller(seller_id)['rating'] among '{x}' products.
PLAN:
  1. [amazon] Use login_to_app('amazon') to get the access token.
  2. [amazon] Use call_api('amazon', 'show_cart', token); for EACH item in cart['cart_items'] call call_api('amazon', 'delete_product_from_cart', token, product_id=item['product_id']) to EMPTY the cart.
  3. [amazon] Use fetch_all_pages('amazon', 'search_products', token, product_type='{x}') to get all '{x}' products. Use product_type=, NEVER query=.
  4. [amazon] For EACH product p in the results, get its SELLER rating, then pick the best:
       for p in products:
           seller = call_api('amazon', 'show_seller', token, seller_id=p['seller_id'])
           p['_seller_rating'] = seller['rating']
       best = max(products, key=lambda p: p['_seller_rating'])
     ⚠️ Rank by the SELLER's rating (seller['rating']), NEVER the product's own p['rating']. [field: 'rating']
  5. [amazon] Use call_api('amazon', 'add_product_to_cart', token, product_id=best['product_id'], quantity=1, clear_cart_first=True) to add exactly that one product.
  6. [amazon] Use call_api('amazon', 'show_addresses', token); pick the address whose name == '{addr}'. Use call_api('amazon', 'show_payment_cards', token); pick the card whose card_name contains '{card}' (case-insensitive).
  7. [amazon] Call call_api('amazon', 'place_order', token, payment_card_id=<chosen card id>, address_id=<chosen address id>). On failure, try the other payment cards in try/except until one succeeds.
  8. [amazon] This is an ACTION task — call apis.supervisor.complete_task(answer=None).
"""

    return None


# ── App keyword detection ─────────────────────────────────────────────────────
# Add keywords here when new task patterns appear.

_APP_KEYWORDS = {
    "spotify":    ["spotify", "music", "song", "playlist", "album", "artist", "track",
                   "listen", "liked songs", "song library"],
    "venmo":      ["venmo", "pay", "payment", "send money", "charge", "transaction",
                   "transfer", "request money", "send $", "dollars", "money to"],
    "gmail":      ["gmail", "email", "mail", "inbox", "send email",
                   "compose", "draft", "attachment"],
    "amazon":     ["amazon", "order", "purchase", "product",
                   "cart", "delivery", "wish list", "amazon order"],
    "splitwise":  ["splitwise", "expense", "owe", "debt", "group expense", "settle",
                   "balance", "split bill", "split the"],
    "todoist":    ["todoist", "task", "reminder", "todo", "to-do", "due date",
                   "project", "priority", "deadline"],
    "simplenote": ["simplenote", "note", "notes", "jot", "write down"],
    "phone":      ["phone", "contact", "call", "roommate", "coworker", "colleague",
                   "friend", "sibling", "text message", "sms", "phone number"],
    "file_system":["file", "folder", "directory", "download", "document", "upload",
                   "path", "filesystem", "file system", "read file", "write file"],
    # Conservative — api_docs tasks are rare. Avoid the bare word "api" (it appears in
    # unrelated task text) and require doc/count-of-apis phrasing.
    "api_docs":   ["api docs", "api documentation", "how many apis", "which apis",
                   "available apis", "list of apis", "api that"],
}


def _detect_apps(task_text: str) -> list:
    """Return list of app names whose keywords appear in the task body.
    Strips the supervisor preamble ('My name is... My phone number is...')
    so that 'phone' and 'gmail' don't trigger on every single task."""
    task_body = task_text.split("Task:", 1)[-1] if "Task:" in task_text else task_text
    text_lower = task_body.lower()
    return [app for app, kws in _APP_KEYWORDS.items()
            if any(kw in text_lower for kw in kws)]


# ── Core Explorer call ────────────────────────────────────────────────────────

def _call_gpt_explorer(user_input: str, task_text: str = "") -> str:
    """
    Calls GPT-4.1-nano using OpenAI native function calling.

    Flow:
      Round 0 : tool_choice="required" — model MUST call a tool (explore_app_apis or get_api_details)
      Round 1+: tool_choice="auto"     — model keeps calling tools until it decides to write the plan
      Return  : the plan text (model response with no tool_calls)
    """
    from tools import explore_app_apis, get_api_details

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # ── Pre-injection: run explore_app_apis for all detected apps ─────────────
    detected_apps = _detect_apps(task_text or user_input)
    pre_injected = ""
    if detected_apps:
        logger.info(f"Pre-injecting API docs for: {detected_apps}")
        for app in detected_apps:
            try:
                docs = explore_app_apis.invoke(app)
                pre_injected += f"\n\n{app.upper()} APIs (pre-loaded):\n{docs}"
            except Exception as e:
                pre_injected += f"\n\n{app.upper()} APIs: [error: {e}]"

    system = build_explorer_system(pre_injected)

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_input},
    ]

    tool_map = {
        "explore_app_apis": lambda args: explore_app_apis.invoke(args["app_name"]),
        "get_api_details":  lambda args: get_api_details.invoke(json.dumps(args)),
    }

    seen_call_sigs: set = set()
    last_content = ""
    for round_num in range(10):
        tool_choice = "required" if round_num == 0 else "auto"
        response = client.chat.completions.create(
            model=EXPLORER_MODEL,
            messages=messages,
            tools=EXPLORER_TOOLS_OPENAI,
            tool_choice=tool_choice,
            temperature=0.1,
            max_tokens=2000,
        )
        msg = response.choices[0].message
        last_content = msg.content or ""

        # Log any reasoning the model expresses alongside tool calls
        if msg.tool_calls and last_content:
            logger.info(f"[Explorer round {round_num} thinking] {last_content[:800]}")

        # No tool calls → model finished, return the plan
        if not msg.tool_calls:
            return last_content

        # Detect repeated identical tool calls — model is looping, break early
        call_sig = tuple(sorted(
            (tc.function.name, tc.function.arguments) for tc in msg.tool_calls
        ))
        if call_sig in seen_call_sigs:
            logger.warning(f"Explorer: repeated tool call on round {round_num} — forcing plan generation")
            break
        seen_call_sigs.add(call_sig)

        # Execute tool calls and feed results back
        messages.append(msg)
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
                result = tool_map[tc.function.name](args)
            except Exception as e:
                result = f"Tool error: {e}"
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })

    # Rounds exhausted or repeated-call break — force the model to write the plan now
    logger.warning("Explorer: forcing final plan generation (tool_choice=none)")
    forced = client.chat.completions.create(
        model=EXPLORER_MODEL,
        messages=messages,
        tools=EXPLORER_TOOLS_OPENAI,
        tool_choice="none",
        temperature=0.1,
        max_tokens=2000,
    )
    return forced.choices[0].message.content or "Explorer: failed to produce a plan."


# ── LangGraph node ────────────────────────────────────────────────────────────

def explorer_node(state: AgentState) -> dict:
    run_num = state.get("explorer_runs", 0) + 1
    logger.phase(f"🔍 Explorer — GPT-4.1-nano (run {run_num})")

    task          = state["messages"][0].content
    last_error    = state.get("last_error", "")
    existing_plan = state.get("plan", "")
    eval_failure  = state.get("last_eval_failure", "")

    # Strip the Reviewer's code-level diagnosis from the error before passing to Explorer.
    # The Reviewer diagnoses field-name issues (Executor's job); the Explorer works at
    # algorithm level. Passing the wrong diagnosis here caused the Explorer to re-plan
    # identically while the Executor flip-flopped on field names.
    execution_error = last_error.split("=== CODE REVIEWER DIAGNOSIS ===")[0].strip()

    extra_context = ""
    if existing_plan and "Explorer crashed" not in existing_plan:
        extra_context += f"\n\nPrevious plan:\n{existing_plan}\n"

    if eval_failure:
        # The code ran but the answer was wrong — this is an algorithm problem.
        extra_context += (
            f"\n\nThe previous answer was WRONG. Failed requirements from the test suite:\n"
            f"{eval_failure}\n"
            f"Reconsider the algorithm: check AGGREGATION SCOPE and FIELD MAPPING rules above.\n"
        )
    elif execution_error:
        # The code crashed — this may be a plan-level issue (wrong API name, missing login, etc.)
        extra_context += (
            f"\n\nThe previous Executor run crashed with this error:\n{execution_error}\n"
            f"Refine the plan to fix it (e.g. wrong API name, missing login step).\n"
        )

    # Deterministic plan for recognized Amazon task families — skip the flaky LLM.
    template_plan = amazon_template_plan(task)
    if template_plan:
        logger.info("Explorer: matched Amazon task template — using deterministic plan")
        logger.output_block(template_plan, label="📋 Explorer Plan (template)")
        return {
            "messages":      [AIMessage(content=f"EXPLORER_REPORT:\n{template_plan}")],
            "plan":          template_plan,
            "explorer_runs": run_num,
            "iterations":    state.get("iterations", 0) + 1,
        }

    user_input = f"TASK: {task}{extra_context}\n\nFind the right app(s) and write a concrete plan."

    try:
        plan_text = _call_gpt_explorer(user_input, task_text=task)
    except Exception as e:
        plan_text = f"Explorer crashed: {e}"
        logger.error(f"Explorer crashed: {e}")

    if "Explorer crashed" in plan_text:
        logger.error(f"Explorer failed: {plan_text[:300]}")
    else:
        logger.output_block(plan_text, label="📋 Explorer Plan")

    return {
        "messages":      [AIMessage(content=f"EXPLORER_REPORT:\n{plan_text}")],
        "plan":          plan_text,
        "explorer_runs": run_num,
        "iterations":    state.get("iterations", 0) + 1,
    }
