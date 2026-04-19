import os

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://192.116.98.6")
OLLAMA_API_URL  = f"{OLLAMA_BASE_URL}/api/chat"   # Qwen uses /api/chat
OLLAMA_AUTH     = (
    os.environ.get("OLLAMA_USER", "group1"),
    os.environ.get("OLLAMA_PASS", "MTAgroup1"),
)
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:latest")

MAX_HISTORY_MESSAGES = 30
MAX_REPEATED_CODE    = 3
MAX_PLAN_STEPS       = 7   # steps the planner gets to write a plan (usually 1–2)
MAX_PLANNING_ROUNDS  = 2   # planner→executor cycles: initial plan + up to N-1 revisions on failure
LLM_MAX_TOKENS       = 800   # enough for a full set_plan([...]) call; 400 truncated mid-list

LLM_FALLBACK_CODE = "# __AGENT_LLM_FAILURE__\nraise RuntimeError('LLM retries exhausted')"
