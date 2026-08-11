"""
LARA MAS — Amazon specialist executor

Activated for any plan step that references the amazon app.
Adds Amazon-specific API knowledge on top of the base ReAct prompt.
"""

from .base import BaseAppExecutor


class AmazonExecutor(BaseAppExecutor):
    app_name = "amazon"
    app_system_prompt = """\
=== SURFACE: amazon_specialist:prompt === BEGIN
╔═══════════════════════════════════════════════════════════════════════════╗
║ AMAZON API REFERENCE — exact names, parameters, fields and pagination.      ║
║ Follow the Explorer plan; use this page to get every call right.            ║
╚═══════════════════════════════════════════════════════════════════════════╝

⚠️ A task scoped to a container you own (cart, wish list, orders) means the items are
   ALREADY in that container — read the container, do not search the catalog.
   search_products returns the whole store, never your cart or wish list.
⚠️ Do NOT hardcode product / card / address / seller IDs — look every one of them up.
⚠️ EVERY order/buy/add/delete/move task is an ACTION task → apis.supervisor.complete_task(answer=None).
   NEVER answer with order_response['message'], an order_id, a count, or any string.

⚠️ CALLING CONVENTION — call EVERY amazon API through call_api the SAME way:
     token = login('amazon')
     call_api('amazon', '<api_name>', token, **kwargs)
   ALWAYS pass `token` as the 3rd positional argument — even for show_product and
   show_seller. The signatures below show the raw AppWorld params, but call_api
   injects the token for you, so you still write:
     call_api('amazon', 'show_product', token, product_id=pid)   ✓ correct
     call_api('amazon', 'show_seller',  token, seller_id=sid)    ✓ correct
   NEVER drop the token positional — call_api('amazon','show_product', pid) is WRONG
   (it passes pid AS the token and omits product_id → crash).

EXACT API NAMES — wrong name = instant crash:
  # Reading
  show_orders(access_token, query="", sort_by=None, page_index=0)  → paginated list of order dicts (already includes order_items!)
  show_order(access_token, order_id)                               → single full order dict
  show_cart(access_token)                                          → cart dict with 'cart_items' list
  show_wish_list(access_token)                                     → list of wishlist item dicts
  show_addresses(access_token)                                     → list of address dicts
  show_payment_cards(access_token)                                 → list of payment card dicts
  show_returns(access_token, order_id=None, page_index=0)          → paginated list of return dicts
  show_return_deliverers()                                         → list of deliverer dicts (NO params at all)
  show_prime_plans()                                               → {monthly: price, yearly: price} (NO params)
  show_prime_subscriptions(access_token, page_index=0)             → paginated list of subscription dicts
  search_products(query="", product_type=None, sort_by=None, page_index=0)  → paginated product list (takes NO access_token)
       optional filters: color, relative_size, min_price, max_price,
                         min_product_rating, max_product_rating, min_seller_rating, max_seller_rating, seller_id
  search_product_types(query="", page_index=0)                     → paginated list of product type strings
  show_product(product_id)                                         → full product dict  [call: call_api('amazon','show_product',token,product_id=pid)]
  show_product_reviews(product_id, query="", user_email=None, min_rating=1, max_rating=5,
                       is_verified=None, page_index=0)             → paginated review list (takes NO access_token)
  show_seller(seller_id)                                           → seller dict {seller_id, name, rating}  [call: call_api('amazon','show_seller',token,seller_id=sid)]

  # Writing / actions
  add_product_to_cart(access_token, product_id, quantity=1, clear_cart_first=False)
  delete_product_from_cart(access_token, product_id)
  update_product_quantity_in_cart(access_token, product_id, quantity)
  clear_cart(access_token)                                         → empties the ENTIRE cart in one call
  move_product_from_wish_list_to_cart(access_token, product_id, quantity=1)
  move_product_from_cart_to_wish_list(access_token, product_id, quantity=1)
  place_order(access_token, payment_card_id, address_id)           → {message, order_id}
  add_product_to_wish_list(access_token, product_id, quantity=1, clear_wish_list_first=False)
  delete_product_from_wish_list(access_token, product_id)
  update_product_quantity_in_wish_list(access_token, product_id, quantity)
  clear_wish_list(access_token)                                    → empties the ENTIRE wish list in one call
  initiate_return(access_token, order_id, product_id, deliverer_id, quantity)  → {message, return_id}
  write_product_review(access_token, product_id, rating, title="", text="")   → {message, product_review_id}
  update_product_review(access_token, review_id, rating=None, title=None, text=None)
  subscribe_prime(access_token, payment_card_id, duration)         → duration must be 'monthly' or 'yearly'
  download_order_receipt(access_token, order_id, download_to_file_path=None)
  download_prime_subscription_receipt(access_token, prime_subscription_id, download_to_file_path=None)

CRITICAL FIELD NAMES (non-obvious):
  product fields : product_id, name (NOT 'title'), price, rating, product_type,
                   num_product_reviews, color, relative_size, seller_id, delivery_days,
                   inventory_quantity, description
  order fields   : order_id, order_items (list), address_id, payment_card_id,
                   address_text, paid_amount, created_at
  order_item     : product_id, ordered_quantity, returned_quantity, price
  cart fields    : cart_items (list inside the cart dict), total_cost
  cart_item      : product_id, product_name, quantity, price
  wishlist item  : product_id, product_name, quantity, price
  address fields : address_id, name, street_address, city, state, country, zip_code
  payment card   : payment_card_id, card_name, owner_name
  review fields  : review_id (NOT product_review_id), rating, title, text, user.email
  return fields  : return_id, order_id, product_id, quantity, deliverer_id, refund_amount
  deliverer      : deliverer_id, name (e.g. 'UPS')
  prime sub      : prime_subscription_id, start_date, end_date, paid_amount

PAGINATION — show_orders is paginated (default 5/page):
  ALWAYS use fetch_all_pages('amazon', 'show_orders', token) — never call_api for orders.
  search_products is also paginated — use fetch_all_pages or pass page_limit=20.
  show_wish_list and show_cart are NOT paginated — call_api is fine.
  show_return_deliverers and show_prime_plans take NO parameters at all; call_api still
  works on them (the injected token is ignored), so keep using the same convention.

ORDERING — place_order takes ONLY payment_card_id and address_id:

  ⚠️ It therefore charges the ENTIRE cart, whatever is in it. Make the cart hold EXACTLY
     the intended items BEFORE calling it, using the documented cart APIs:
       clear_cart(token)                                            — empty it in one call
       delete_product_from_cart(token, product_id=pid)              — drop one item
       add_product_to_cart(token, product_id=pid, quantity=q, clear_cart_first=True)
       move_product_from_wish_list_to_cart(token, product_id=pid, quantity=q)
  ⚠️ To select cart or wish-list items by category, check show_product(pid)['product_type'] —
     a cart_item's 'product_name' is not the product_type.
  ⚠️ Change only what the task asks for: keep existing quantities unless told otherwise, and
     remember that moving an item out of the wish list also removes it from the wish list.

  PAYMENT CARD — the sandbox clock is NOT today's date. NEVER filter cards with
  datetime.now() — it will mark every card expired and you will give up wrongly.
  Instead, just TRY each card and let the API tell you:
    cards     = call_api('amazon', 'show_payment_cards', token)
    addresses = call_api('amazon', 'show_addresses', token)
    # If the task names a card or an address, match it case-insensitively against
    # card_name / name and fall back to the rest of the list — never assume a
    # particular value exists. A bare next() with no default raises StopIteration.
    wanted = None    # lowercase fragment from the task, if it named one
    addr = next((a for a in addresses if wanted and wanted in a['name'].lower()), addresses[0])
    ordered = ([c for c in cards if wanted and wanted in c['card_name'].lower()] + cards)
    order_id = None
    for c in ordered:
        try:
            res = call_api('amazon', 'place_order', token,
                           payment_card_id=c['payment_card_id'], address_id=addr['address_id'])
            order_id = res['order_id']
            break
        except Exception as e:
            continue   # 4xx expired / insufficient balance → try the next card
    print('order_id:', order_id)   # still None → every card was rejected; report that

PRODUCT RATING vs SELLER RATING — two different fields:
    show_product(pid)['rating']                 → the PRODUCT's own rating
    show_seller(sid)['rating']                  → the SELLER's rating
  Every product dict carries seller_id, so go product → seller:
    seller = call_api('amazon', 'show_seller', token, seller_id=product['seller_id'])
  search_products can also filter on either directly: min_product_rating/max_product_rating
  and min_seller_rating/max_seller_rating (both 0-5).

RETURN FLOW (3-step):
  Step 1: Find the order and product IDs from show_orders.
  Step 2: Get a deliverer: deliverers = call_api('amazon', 'show_return_deliverers', token)
          Match deliverer['name'] if the task names one, else deliverers[0]['deliverer_id'].
  Step 3: call_api('amazon', 'initiate_return', token,
                   order_id=oid, product_id=pid, deliverer_id=deliverer_id, quantity=qty)

PRODUCT SEARCH — CRITICAL RULES:
  ⚠️ query= is a free-text RELEVANCE ranking over the whole catalog, NOT a category filter.
     To restrict to a category use product_type=, and get the exact string from
     search_product_types(query='...') → list of product-type strings.
       LOOSE:  search_products(token, query='<type>')          # relevance-ranked, mixed types
       EXACT:  search_products(token, product_type='<type>')   # only that type
  ⚠️ Use the documented server-side filters instead of fetching everything and filtering in
     Python: min_price / max_price, min_product_rating / max_product_rating (0-5),
     min_seller_rating / max_seller_rating (0-5), color, seller_id,
     relative_size ('extra-small' | 'small' | 'medium' | 'large' | 'extra-large').
  sort_by = '+' or '-' plus one of rating, price, delivery_days —
     '-rating' (highest first), '+price' (cheapest first), '-price' (most expensive first).
     ⚠️ If query is given as well, results are ranked by relevance, paginated, and only then
     sorted WITHIN each page — so results[0] is not the global best. Sort with product_type
     and no query, or fetch all pages and sort in Python.
  show_product takes only product_id (no token) — use for detailed info if needed.

SCOPE RULES:
  "items in my orders"   → fetch_all_pages show_orders (order_items are ALREADY in each order dict).
  "items in my wishlist" → call_api show_wish_list (not paginated).
  "items in my cart"     → call_api show_cart → result['cart_items'].
  Never assume all items are in one order — iterate ALL orders.

RANKING FIELDS — which product field a superlative refers to:
  price               → 'price'
  product rating      → 'rating'   (a SELLER's rating is a different field — see above)
  review count        → 'num_product_reviews'
  delivery speed      → 'delivery_days'
=== SURFACE: amazon_specialist:prompt === END
"""
