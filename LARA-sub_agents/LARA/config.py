"""
LARA MAS — Configuration
All runtime constants in one place. Change here, takes effect everywhere.
"""

# ── Graph limits ──────────────────────────────────────────────────────────────
# NOTE: `iterations` increments ONLY on Explorer/Executor node runs (not Supervisor).
# With MAX_ITERATIONS=3 any re-plan (Explorer→Executor→Explorer) hit the ceiling and
# the retry Executor was cut off. Raised to 6 so a full re-plan/retry cycle (incl. the
# Reviewer path) can actually complete. recursion_limit auto-scales as MAX_ITERATIONS*4.
MAX_ITERATIONS    = 6    # hard ceiling on total Explorer+Executor node runs per task
MAX_EXECUTOR_RUNS = 2    # max number of Executor attempts per task
MAX_REACT_STEPS   = 16   # max ReAct steps per Executor attempt

# ── Executor backend — change ONE line to switch models ──────────────────────
#   "openai"  → uses EXECUTOR_MODEL_OPENAI via OpenAI API
#   "ollama"  → uses EXECUTOR_MODEL_OLLAMA via college Ollama server
# Authorized OpenAI models: gpt-5-nano, gpt-4.1-nano, gpt-4.1-mini.
# gpt-4.1-mini is the strongest code-gen model of the three → used for the Executor
# (where wrong answers are minted) and the Explorer (plan-level scope/metric errors).
EXECUTOR_BACKEND       = "openai"
EXECUTOR_MODEL_OPENAI  = "gpt-4.1-mini"
EXECUTOR_MODEL_OLLAMA  = "qwen2.5-coder:latest"

# ── Explorer (always OpenAI) ──────────────────────────────────────────────────
EXPLORER_MODEL = "gpt-4.1-mini"

# ── Reviewer (diagnosis — pure reasoning role) ────────────────────────────────
# gpt-4.1-mini for reliable diagnosis. Try "gpt-5-nano" (reasoning tier) as an A/B
# experiment — but note gpt-5 models may reject the temperature=0.1 override.
REVIEWER_MODEL = "gpt-4.1-mini"

# ── Ollama server (Supervisor + Executor when backend="ollama") ───────────────
OLLAMA_MODEL      = "qwen2.5-coder:latest"
OLLAMA_API_URL    = "https://192.116.98.6/api/generate"   # generate endpoint (Supervisor)
OLLAMA_CHAT_URL   = "https://192.116.98.6/api/chat"       # chat endpoint (Executor ReAct)
OLLAMA_AUTH_USER  = "group1"
OLLAMA_AUTH_PASS  = "MTAgroup1"
OLLAMA_TIMEOUT    = 240   # seconds per request
