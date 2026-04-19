import json
import logging
import os
import re
import time

import requests
import urllib3

from config import (
    OLLAMA_API_URL,
    OLLAMA_AUTH,
    MODEL_NAME,
    LLM_FALLBACK_CODE,
    LLM_MAX_TOKENS,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
OLLAMA_RESPONSE_LOG = os.environ.get("GILADS_AGENT_OLLAMA_LOG", "ollama_responses.log")
_log = logging.getLogger("gilads_agent.ollama")
if not _log.handlers:
    _log.setLevel(logging.DEBUG)
    _fh = logging.FileHandler(OLLAMA_RESPONSE_LOG, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _log.addHandler(_fh)
    _log.propagate = False

# stop sequences — עוצרים את המודל לפני שהוא מייצר תורות שיחה נוספות
_STOP_SEQUENCES = ["\nUSER:", "\n\nUSER:", "\nASSISTANT:", "\n\nASSISTANT:"]


# ---------------------------------------------------------------------------
# TEXT PROCESSING
# ---------------------------------------------------------------------------
def strip_thinking(text: str) -> str:
    """מסיר <think>...</think> של מודלים עם Thinking Mode."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _looks_like_python(text: str) -> bool:
    """מחזיר True אם הטקסט נראה כקוד Python ולא כפרוזה."""
    if not text.strip():
        return False
    python_markers = (
        "apis.", "print(", "import ", "from ", "paginate_all(",
        "filter_results(", "find_one(", "get_by_id(", "sort_results(",
    )
    if any(m in text for m in python_markers):
        return True
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # השמה או קריאת פונקציה — בדאי קוד
        if re.match(r"^[a-z_]\w*\s*[=(]", line):
            return True
        # משפט באנגלית — כנראה פרוזה
        if re.match(r"^[A-Z][a-z]+\s", line):
            return False
        break
    return False


# ---------------------------------------------------------------------------
# OLLAMA CLIENT  (/api/chat — Ollama מטפל בפורמט ChatML של Qwen)
# ---------------------------------------------------------------------------
def call_ollama_api(messages: list[dict]) -> tuple[bool, str]:
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": LLM_MAX_TOKENS,   # מגביל אורך תשובה
            "temperature": 0.1,              # פלט דטרמיניסטי יותר
            "stop": _STOP_SEQUENCES,         # עצור לפני תורות שיחה
        },
    }
    try:
        response = requests.post(
            OLLAMA_API_URL,
            json=payload,
            auth=OLLAMA_AUTH,
            verify=False,
            timeout=180,
        )
        response.raise_for_status()
        result_json = response.json()

        # /api/chat מחזיר message.content (לא response)
        text = result_json.get("message", {}).get("content", "")

        _log.debug("raw_response_repr: %.1000r", text)
        _log.info("response_len=%s", len(text))

        if not text.strip():
            _log.warning("Empty response: %s", json.dumps(result_json)[:2000])
            return False, "empty response"

        return True, text

    except requests.RequestException as e:
        body = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.text[:500]
            except Exception:
                pass
        print(f"❌ Connection Error: {e} | Server body: {body}")
        return False, str(e)
    except (ValueError, TypeError) as e:
        print(f"❌ Parse Error: {e}")
        return False, str(e)


# ---------------------------------------------------------------------------
# LLM CALL WITH RETRY
# ---------------------------------------------------------------------------
_NUDGE_MSG = {
    "role": "user",
    "content": "Output ONLY valid Python code for the next step. No text, no explanations.",
}


def call_llm(messages: list[dict], max_retries: int = 5) -> str:
    for attempt in range(1, max_retries + 1):
        # מניסיון שני ואילך: מוסיף nudge ללחוץ על המודל לכתוב קוד
        current_messages = messages if attempt == 1 else messages + [_NUDGE_MSG]
        ok, response_text = call_ollama_api(current_messages)

        if not ok:
            print(f"⚠️ Attempt {attempt} failed (transport), retrying...")
            time.sleep(2)
            continue

        # הסר thinking tags ו-markdown fences
        response_text = strip_thinking(response_text)
        clean_code = re.sub(r"```(?:python)?\s*|```", "", response_text).strip()

        # חתוך אם המודל מייצר תורות USER/ASSISTANT בפנים
        for marker in ("\nUSER:", "\nASSISTANT:", "\nuser:", "\nassistant:"):
            if marker in clean_code:
                clean_code = clean_code.split(marker)[0].strip()

        if clean_code:
            if not _looks_like_python(clean_code):
                _log.warning("attempt=%s prose detected: %.100r", attempt, clean_code)
                print(f"⚠️ Attempt {attempt}: prose, not code — retrying...")
                time.sleep(2)
                continue
            _log.info("attempt=%s OK, code_len=%s", attempt, len(clean_code))
            return clean_code

        print(f"⚠️ Attempt {attempt}: empty after strip, retrying...")
        time.sleep(2)

    _log.error("All %s attempts failed", max_retries)
    return LLM_FALLBACK_CODE
