"""
LARA MAS — LLM wrappers

  CustomOllamaLLM  : Qwen 2.5-coder via the college Ollama server (Supervisor + Executor)
  OpenAILLM        : GPT-4.1-nano via OpenAI API (Explorer)
  get_llm()        : returns Supervisor LLM (Qwen/Ollama)
  get_executor_llm(): returns Executor LLM (Qwen/Ollama, num_predict capped for code)
  get_explorer_llm(): returns Explorer LLM (GPT-4.1-nano)
"""

import logging
import os
import time
import warnings
from pathlib import Path
from typing import Any, List, Optional

import requests
from langchain.llms.base import LLM

from config import (
    EXECUTOR_MODEL_OPENAI,
    EXPLORER_MODEL,
    OLLAMA_API_URL,
    OLLAMA_AUTH_PASS,
    OLLAMA_AUTH_USER,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
)

# ── Load .env (OPENAI_API_KEY) ────────────────────────────────────────────────
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

logging.getLogger("langchain").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")


# ── Ollama (Qwen) ─────────────────────────────────────────────────────────────

class CustomOllamaLLM(LLM):
    """Wrapper around the college Ollama server over HTTPS + basic auth."""
    model:           str = OLLAMA_MODEL
    api_url:         str = OLLAMA_API_URL
    auth_user:       str = OLLAMA_AUTH_USER
    auth_pass:       str = OLLAMA_AUTH_PASS
    request_timeout: int = OLLAMA_TIMEOUT
    num_predict:     int = -1   # -1 = no limit; set > 0 to cap output tokens

    @property
    def _llm_type(self) -> str:
        return "custom_ollama"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        stop_tokens = ["Observation:", "\nObservation:"]
        if stop:
            stop_tokens.extend(stop)

        options: dict = {"stop": stop_tokens}
        if self.num_predict > 0:
            options["num_predict"] = self.num_predict

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        last_err = None
        for attempt in range(2):  # 1 retry on transient connection failure
            try:
                response = requests.post(
                    self.api_url,
                    json=payload,
                    auth=(self.auth_user, self.auth_pass),
                    verify=False,
                    timeout=self.request_timeout,
                )
                response.raise_for_status()
                return response.json().get("response", "")
            except Exception as e:
                last_err = e
                if attempt == 0:
                    print(f"\n[WARN] Ollama request failed (attempt 1), retrying in 10s... ({e})")
                    time.sleep(10)
        return f"Error: API Connection Error: {last_err}"


# ── OpenAI (GPT-4.1-nano) ─────────────────────────────────────────────────────

class OpenAILLM(LLM):
    """Thin wrapper around OpenAI chat completions — kept for LangChain compatibility.

    base_url defaults to "" (official OpenAI endpoint). Set OPENAI_BASE_URL to point
    this at any OpenAI-compatible proxy (e.g. a LiteLLM gateway) instead.
    """
    model:       str   = EXPLORER_MODEL
    api_key:     str   = ""
    base_url:    str   = ""
    temperature: float = 0.1
    max_tokens:  int   = 2000

    @property
    def _llm_type(self) -> str:
        return "openai"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        from openai import OpenAI
        client = OpenAI(
            api_key=self.api_key or os.environ.get("OPENAI_API_KEY", ""),
            base_url=self.base_url or os.environ.get("OPENAI_BASE_URL") or None,
        )
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stop=stop,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"Error: OpenAI API error: {e}"


# ── Factory functions ─────────────────────────────────────────────────────────

def get_llm() -> CustomOllamaLLM:
    """Returns the Supervisor LLM (Qwen via Ollama)."""
    return CustomOllamaLLM(
        model=os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL),
        api_url=os.environ.get("OLLAMA_API_URL", OLLAMA_API_URL),
    )


def get_executor_llm() -> OpenAILLM:
    """Returns the Executor LLM (GPT-4.1-nano, or OPENAI_BASE_URL/EXECUTOR_MODEL override). Higher max_tokens for code generation."""
    return OpenAILLM(
        model=os.environ.get("EXECUTOR_MODEL", EXECUTOR_MODEL_OPENAI),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        max_tokens=4000,
    )


def get_explorer_llm() -> OpenAILLM:
    """Returns the Explorer LLM (GPT-4.1-nano via OpenAI, or OPENAI_BASE_URL/EXPLORER_MODEL override)."""
    return OpenAILLM(
        model=os.environ.get("EXPLORER_MODEL", EXPLORER_MODEL),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
    )
