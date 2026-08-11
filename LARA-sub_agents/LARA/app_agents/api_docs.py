"""
LARA MAS — API Docs specialist executor

Activated for any plan step that references the api_docs app.
api_docs is a META app: it returns documentation ABOUT the other apps' APIs.

All API/field names verified against data/api_docs/standard/api_docs.json.
"""

from .base import BaseAppExecutor


class ApiDocsExecutor(BaseAppExecutor):
    app_name = "api_docs"
    app_system_prompt = """\
=== SURFACE: api_docs_specialist:prompt === BEGIN
╔═══════════════════════════════════════════════════════════════════════════╗
║ API_DOCS — a META app describing every OTHER app's APIs. Read-only. Use it ║
║ ONLY when the task is about the documentation itself — the app list, an     ║
║ app's API list, or one API's doc (path/method/parameters/response).        ║
╚═══════════════════════════════════════════════════════════════════════════╝

🔑 THIS APP IS DIFFERENT FROM EVERY OTHER APP:
   • NO login and NO access_token. Do NOT call login('api_docs') — there is no
     credential for it, so it raises. That also means you have no token to hand to
     call_api()/fetch_all_pages(), whose third argument is required.
   • Call the functions DIRECTLY on the apis object:  apis.api_docs.<name>(...)

═══ EXACT API NAMES (all read-only, no token) ═══

  apis.api_docs.show_app_descriptions()
      → [{'name', 'description'}]           one entry per available app
  apis.api_docs.show_api_descriptions(app_name='spotify')
      → [{'name', 'description'}]           one entry per API in that app
  apis.api_docs.show_api_doc(app_name='spotify', api_name='show_liked_songs')
      → {'app_name','api_name','path','method','description',
         'parameters':[{'name','type','required','description','default','constraints'}],
         'response_schemas':{'success','failure'}}
  apis.api_docs.search_api_docs(query='...', page_index=0, page_limit=5)
      → PAGINATED list of full api-doc dicts (same shape as show_api_doc)

═══ COMPLETE LISTS vs PAGINATION ═══
  show_app_descriptions and show_api_descriptions take no page parameters: each
  returns the FULL list in one call, so len(result) is the exact number of apps,
  or of APIs in that app. Only search_api_docs is paginated
  (page_index ≥ 0; page_limit 1-20, default 5).

═══ MANUAL PAGINATION (only for search_api_docs) ═══
  fetch_all_pages does NOT work here (it injects access_token). Paginate by hand:
      results, i = [], 0
      while True:
          page = apis.api_docs.search_api_docs(query='...', page_index=i, page_limit=20)
          if not page:
              break
          results.extend(page); i += 1

═══ CRITICAL RULES ═══
  • All four APIs are GET / read-only: api_docs has NO state to change, so an
    api_docs step produces a VALUE to pass — never an ACTION.
  • Take the answer straight out of the response fields listed above (e.g.
    doc['method'], the 'name' key of each list entry). Never paraphrase or guess
    a field; print the response first if unsure of its shape.
  • Never login and never pass access_token to any api_docs API.
  • Call directly (apis.api_docs.<name>), never via call_api / fetch_all_pages / login.
=== SURFACE: api_docs_specialist:prompt === END
"""
