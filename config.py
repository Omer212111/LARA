import os

# ── OpenAI ────────────────────────────────────────────────────────────────────
MODEL_NAME     = os.environ.get("OPENAI_MODEL", "gpt-4.1-nano")
LLM_MAX_TOKENS = 2000   # enough for planner set_plan + executor steps with room to spare

# ── Ollama (kept for reference — no longer active) ────────────────────────────
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://192.116.98.6")
OLLAMA_API_URL  = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_AUTH     = (
    os.environ.get("OLLAMA_USER", "group1"),
    os.environ.get("OLLAMA_PASS", "MTAgroup1"),
)

# ── Agent limits ──────────────────────────────────────────────────────────────
MAX_HISTORY_MESSAGES = 30
MAX_REPEATED_CODE    = 3
MAX_PLAN_STEPS       = 7   # steps the planner gets to write a plan (usually 1–2)
MAX_PLANNING_ROUNDS  = 3   # planner→executor cycles: initial plan + up to N-1 revisions on failure

LLM_FALLBACK_CODE = "# __AGENT_LLM_FAILURE__\nraise RuntimeError('LLM retries exhausted')"
