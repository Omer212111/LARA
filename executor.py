"""
LARA MAS — ReAct Executor agent

Works one step at a time:
  1. LLM writes a small focused code block (Thought + Action)
  2. Code runs in the AppWorld sandbox
  3. Output is fed back as Observation
  4. Loop until complete_task() is called or MAX_REACT_STEPS reached

Backend is selected by EXECUTOR_BACKEND in config.py:
  "openai"  → OpenAI chat completions (GPT-4.1-nano)
  "ollama"  → Ollama /api/chat endpoint (Qwen2.5-coder)
"""

import os
import re
import time

import requests
from langchain_core.messages import AIMessage
from openai import OpenAI

import logger
from config import (
    EXECUTOR_BACKEND,
    EXECUTOR_MODEL_OLLAMA,
    EXECUTOR_MODEL_OPENAI,
    MAX_REACT_STEPS,
    OLLAMA_AUTH_PASS,
    OLLAMA_AUTH_USER,
    OLLAMA_CHAT_URL,
    OLLAMA_TIMEOUT,
)
from executor_helpers import BOOTSTRAP_CODE
from prompts import REACT_EXECUTOR_SYSTEM, build_react_initial_message
from state import AgentState
from tools import evaluate_task, execute_python_code


def _extract_code_block(text: str) -> str:
    """Pull the first ```python ... ``` block. Falls back to bare ``` block."""
    m = re.search(r"```python\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def _summarize_findings(findings: dict, max_chars: int = 1500) -> str:
    if not findings:
        return "None yet."
    parts = [f"[{key}]: {str(value)[:400]}" for key, value in findings.items()]
    return "\n".join(parts)[:max_chars]


def _llm_call(messages: list[dict]) -> str:
    """Call the configured LLM backend with a messages list. Returns assistant text."""
    if EXECUTOR_BACKEND == "openai":
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        response = client.chat.completions.create(
            model=EXECUTOR_MODEL_OPENAI,
            messages=messages,
            temperature=0.1,
            max_tokens=1500,
        )
        return response.choices[0].message.content or ""

    elif EXECUTOR_BACKEND == "ollama":
        payload = {
            "model": EXECUTOR_MODEL_OLLAMA,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 1500,
            },
        }
        last_err = None
        for attempt in range(2):
            try:
                resp = requests.post(
                    OLLAMA_CHAT_URL,
                    json=payload,
                    auth=(OLLAMA_AUTH_USER, OLLAMA_AUTH_PASS),
                    verify=False,
                    timeout=OLLAMA_TIMEOUT,
                )
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "")
            except Exception as e:
                last_err = e
                if attempt == 0:
                    logger.warning(f"Ollama chat failed (attempt 1), retrying in 10s... ({e})")
                    time.sleep(10)
        raise RuntimeError(f"Ollama chat error after 2 attempts: {last_err}")

    else:
        raise ValueError(f"Unknown EXECUTOR_BACKEND: {EXECUTOR_BACKEND!r}")


# ── LangGraph node ────────────────────────────────────────────────────────────

def executor_node(state: AgentState) -> dict:
    attempt_num = state.get("executor_runs", 0) + 1
    backend_label = f"{EXECUTOR_BACKEND}:{EXECUTOR_MODEL_OLLAMA if EXECUTOR_BACKEND == 'ollama' else EXECUTOR_MODEL_OPENAI}"
    logger.phase(f"⚙️  Executor (attempt {attempt_num}, {backend_label})")

    task               = state["messages"][0].content
    plan               = state.get("plan", "[no plan available]")
    findings           = state.get("findings", {})
    last_error         = state.get("last_error", "")
    reviewer_diagnosis = state.get("reviewer_diagnosis", "")

    messages = [
        {"role": "system", "content": REACT_EXECUTOR_SYSTEM},
        {"role": "user",   "content": build_react_initial_message(
            task, plan,
            _summarize_findings(findings),
            last_error         if last_error         else "None",
            reviewer_diagnosis if reviewer_diagnosis else "None",
        )},
    ]

    all_code_steps: list[str] = []
    all_outputs:    list[str] = []
    eval_info = {
        "correct": False, "completed": False,
        "pass_count": 0, "total_count": 0,
        "pass_percentage": 0.0, "failures": [],
    }
    last_output_had_error = False

    for step in range(1, MAX_REACT_STEPS + 1):
        # ── Ask LLM for next step ─────────────────────────────────────────────
        try:
            assistant_text = _llm_call(messages)
        except Exception as e:
            logger.error(f"LLM call failed on step {step}: {e}")
            break

        messages.append({"role": "assistant", "content": assistant_text})

        code = _extract_code_block(assistant_text)
        if not code:
            logger.info(f"[ReAct step {step}] No code block — stopping")
            break

        logger.code_block(code, label=f"ReAct step {step} / attempt {attempt_num}")
        all_code_steps.append(code)

        # ── Execute ───────────────────────────────────────────────────────────
        full_code = BOOTSTRAP_CODE + "\n" + code
        output    = execute_python_code.invoke({"code": full_code})
        logger.output_block(output, label=f"ReAct step {step} / attempt {attempt_num}")
        all_outputs.append(output)

        last_output_had_error = (
            output.startswith("Execution failed") or "Traceback" in output
        )

        # ── Feed observation back ─────────────────────────────────────────────
        messages.append({
            "role":    "user",
            "content": (
                f"Observation:\n{output}\n\n"
                "Continue with the next step, or call "
                "apis.supervisor.complete_task() if you have the answer."
            ),
        })

        # ── Check completion ──────────────────────────────────────────────────
        eval_info = evaluate_task()
        if eval_info["completed"]:
            if eval_info["correct"]:
                logger.success(
                    f"Task CORRECT at step {step} — "
                    f"{eval_info['pass_count']}/{eval_info['total_count']} tests passed "
                    f"({eval_info['pass_percentage']:.0f}%)"
                )
            else:
                logger.error(
                    f"complete_task() called but WRONG — "
                    f"{eval_info['pass_count']}/{eval_info['total_count']} tests passed "
                    f"({eval_info['pass_percentage']:.0f}%). "
                    f"Failed: {eval_info['failures']}"
                )
            break

    # ── Build return values ───────────────────────────────────────────────────
    combined_output = "\n".join(all_outputs)
    last_code       = "\n---\n".join(all_code_steps)

    eval_failure_str = ""
    if eval_info["completed"] and not eval_info["correct"]:
        eval_failure_str = "\n".join(eval_info.get("failures", []))

    answer = ""
    m = re.search(r"FINAL_ANSWER:\s*(.+)", combined_output)
    if m:
        answer = m.group(1).strip().splitlines()[0]

    new_findings = dict(findings)
    new_findings[f"attempt_{attempt_num}"] = combined_output[:1500]

    report = (
        f"EXECUTOR_REPORT (attempt {attempt_num}, {len(all_code_steps)} ReAct steps):\n"
        f"--- Last step code ---\n"
        f"{all_code_steps[-1][:600] if all_code_steps else 'none'}\n"
        f"--- Combined output ---\n{combined_output[:1200]}"
    )

    had_error = last_output_had_error and not eval_info["completed"]

    return {
        "messages":            [AIMessage(content=report)],
        "findings":            new_findings,
        "last_error":          combined_output if had_error else "",
        "reviewer_diagnosis":  "",
        "task_signal_complete": eval_info["correct"],
        "final_answer":        answer,
        "executor_runs":       attempt_num,
        "iterations":          state.get("iterations", 0) + 1,
        "last_code":           last_code,
        "last_eval_failure":   eval_failure_str,
        "reviewer_ran":        False,
    }
