"""
LARA MAS — Configuration
All runtime constants in one place. Change here, takes effect everywhere.
"""

import os

# ── Graph limits ──────────────────────────────────────────────────────────────
# NOTE: `iterations` increments ONLY on Explorer/Executor node runs (not Supervisor).
# With MAX_ITERATIONS=3 any re-plan (Explorer→Executor→Explorer) hit the ceiling and
# the retry Executor was cut off. Raised to 6 so a full re-plan/retry cycle (incl. the
# Reviewer path) can actually complete. recursion_limit auto-scales as MAX_ITERATIONS*4.
MAX_ITERATIONS    = 6    # hard ceiling on total Explorer+Executor node runs per task
MAX_REACT_STEPS   = 16   # max ReAct steps per Executor attempt

# MAX_EXECUTOR_RUNS: max Executor attempts per task (1 = no retry). The reviewer
# ablation overrides this per arm via LARA_MAX_EXECUTOR_RUNS (see run_reviewer_
# ablation.py); the default stays 1 so a normal run is unchanged when the env var
# is absent.
MAX_EXECUTOR_RUNS = int(os.environ.get("LARA_MAX_EXECUTOR_RUNS", "1"))

# ── Reviewer / retry ──────────────────────────────────────────────────────────
# False → one Executor attempt per task: the Reviewer never fires and the
# Supervisor cannot send a second attempt either. Both paths must be closed;
# closing only the Reviewer still allows a retry via the Supervisor.
#
# Measured basis for turning this off: over 165 saved tasks the Reviewer fired
# 75 times and rescued 1 (1.3%). A retry-context change (grader assertions passed
# through verbatim) reached 11/11 retries and converted none. Each retry costs a
# Reviewer call plus a full second Executor attempt, so on a large run it is a
# significant token cost for no measured gain.
#
# Set back to True when a retry mechanism is shown to convert on train/dev.
# Overridable via LARA_ENABLE_RETRY ("1"/"true") for the reviewer ablation; the
# literal False remains the default for a normal run with the env var unset.
def _env_flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

ENABLE_REVIEWER_RETRY = _env_flag("LARA_ENABLE_RETRY", False)

# Reviewer ablation, arm C ("blind retry"): when True AND ENABLE_REVIEWER_RETRY is
# True, a wrong answer routes straight back to the Executor for a SECOND fresh
# attempt WITHOUT the Reviewer running — no diagnosis, no retry context. Isolates
# whether the Reviewer's diagnosis buys anything over a bare re-roll. Default
# False → the normal Reviewer path. See planning_loop._after_executor.
REVIEWER_BYPASS = _env_flag("LARA_REVIEWER_BYPASS", False)

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
# Credentials come from the environment (.env), never from this file — a leaderboard
# submission publishes the repo URL, and these were sitting here in plaintext.
# Only needed when EXECUTOR_BACKEND == "ollama"; the OpenAI path never reads them.
OLLAMA_AUTH_USER  = os.environ.get("OLLAMA_AUTH_USER", "")
OLLAMA_AUTH_PASS  = os.environ.get("OLLAMA_AUTH_PASS", "")
OLLAMA_TIMEOUT    = 240   # seconds per request
