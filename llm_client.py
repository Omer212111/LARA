import logging
import os
import re
import time
from pathlib import Path

from config import MODEL_NAME, LLM_FALLBACK_CODE, LLM_MAX_TOKENS

# ── Load .env (tries root project dir first, then LARA-MAS as fallback) ──────
for _env_path in [
    Path(__file__).parent / ".env",
    Path(__file__).parent / "LARA-MAS" / "LARA" / ".env",
]:
    if _env_path.exists():
        for _line in _env_path.read_text().splitlines():
            if "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
        break

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
_log = logging.getLogger("lara.llm")
if not _log.handlers:
    _log.setLevel(logging.DEBUG)
    _fh = logging.FileHandler("ollama_responses.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _log.addHandler(_fh)
    _log.propagate = False


# ---------------------------------------------------------------------------
# TEXT PROCESSING (unchanged — GPT can still wrap code in fences occasionally)
# ---------------------------------------------------------------------------
def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _looks_like_python(text: str) -> bool:
    if not text.strip():
        return False
    python_markers = (
        "apis.", "print(", "import ", "from ", "paginate_all(",
        "filter_results(", "find_one(", "get_by_id(", "sort_results(",
        "blackboard.", "access_token",
    )
    if any(m in text for m in python_markers):
        return True
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^[a-z_]\w*\s*[=(]", line):
            return True
        if re.match(r"^[A-Z][a-z]+\s", line):
            return False
        break
    return False


# ---------------------------------------------------------------------------
# OPENAI CLIENT
# ---------------------------------------------------------------------------
def call_openai_api(messages: list[dict]) -> tuple[bool, str]:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.1,
            max_tokens=LLM_MAX_TOKENS,
        )
        text = response.choices[0].message.content or ""
        _log.debug("raw_response_repr: %.1000r", text)
        _log.info("response_len=%s", len(text))
        if not text.strip():
            _log.warning("Empty response from OpenAI")
            return False, "empty response"
        return True, text
    except Exception as e:
        print(f"❌ OpenAI Error: {e}")
        return False, str(e)


# ---------------------------------------------------------------------------
# LLM CALL WITH RETRY (same interface as before)
# ---------------------------------------------------------------------------
_NUDGE_MSG = {
    "role": "user",
    "content": "Output ONLY valid Python code for the next step. No text, no explanations.",
}


def call_llm(messages: list[dict], max_retries: int = 3) -> str:
    for attempt in range(1, max_retries + 1):
        current_messages = messages if attempt == 1 else messages + [_NUDGE_MSG]
        ok, response_text = call_openai_api(current_messages)

        if not ok:
            print(f"⚠️ Attempt {attempt} failed (API error), retrying...")
            time.sleep(2)
            continue

        # Remove thinking tags and markdown fences
        response_text = strip_thinking(response_text)
        clean_code = re.sub(r"```(?:python)?\s*|```", "", response_text).strip()

        # Truncate if model generates extra conversation turns
        for marker in ("\nUSER:", "\nASSISTANT:", "\nuser:", "\nassistant:"):
            if marker in clean_code:
                clean_code = clean_code.split(marker)[0].strip()

        if clean_code:
            if not _looks_like_python(clean_code):
                _log.warning("attempt=%s prose detected: %.100r", attempt, clean_code)
                print(f"⚠️ Attempt {attempt}: prose detected — retrying...")
                time.sleep(1)
                continue
            _log.info("attempt=%s OK, code_len=%s", attempt, len(clean_code))
            return clean_code

        print(f"⚠️ Attempt {attempt}: empty after strip, retrying...")
        time.sleep(1)

    _log.error("All %s attempts failed", max_retries)
    return LLM_FALLBACK_CODE
