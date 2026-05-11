"""
LARA MAS — Configuration
All runtime constants in one place. Change here, takes effect everywhere.
"""

# ── Graph limits ──────────────────────────────────────────────────────────────
MAX_ITERATIONS    = 12   # hard ceiling on total state-graph iterations per task
MAX_EXECUTOR_RUNS = 2    # max number of Executor attempts per task
MAX_REACT_STEPS   = 10  # max ReAct steps per Executor attempt

# ── Executor backend — change ONE line to switch models ──────────────────────
#   "openai"  → uses EXECUTOR_MODEL_OPENAI via OpenAI API
#   "ollama"  → uses EXECUTOR_MODEL_OLLAMA via college Ollama server
EXECUTOR_BACKEND       = "openai"
EXECUTOR_MODEL_OPENAI  = "gpt-4.1-nano"
EXECUTOR_MODEL_OLLAMA  = "qwen2.5-coder:latest"

# ── Explorer (always OpenAI) ──────────────────────────────────────────────────
EXPLORER_MODEL = "gpt-4.1-nano"

# ── Ollama server (Supervisor + Executor when backend="ollama") ───────────────
OLLAMA_MODEL      = "qwen2.5-coder:latest"
OLLAMA_API_URL    = "https://192.116.98.6/api/generate"   # generate endpoint (Supervisor)
OLLAMA_CHAT_URL   = "https://192.116.98.6/api/chat"       # chat endpoint (Executor ReAct)
OLLAMA_AUTH_USER  = "group1"
OLLAMA_AUTH_PASS  = "MTAgroup1"
OLLAMA_TIMEOUT    = 240   # seconds per request
