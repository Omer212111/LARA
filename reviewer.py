"""
LARA — Code Reviewer

Triggered only when complete_task() was called but the answer was WRONG.
Diagnoses the root cause so the planner can write a better corrected plan.

Returns a diagnosis string that is appended to planner_feedback.
"""

import os

from config import MODEL_NAME


def run_reviewer(task: str, last_code: str, last_output: str, eval_failures: list[str]) -> str:
    """
    Call GPT to diagnose a wrong answer.

    Args:
        task:          The task instruction string.
        last_code:     The Python code that was executed last.
        last_output:   The REPL output from that code.
        eval_failures: List of failed requirement strings from world.evaluate().

    Returns:
        A diagnosis string (ROOT_CAUSE + EXPLANATION + FIX_INSTRUCTION).
        Returns empty string if the API call fails.
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    except Exception:
        return ""

    failures_text = "\n".join(f"- {r}" for r in eval_failures) if eval_failures else "Not available."

    prompt = f"""You are a code reviewer for an AI agent called LARA that solves tasks in AppWorld
(a simulated environment of apps like Spotify, Gmail, Venmo, etc., accessed via apis.<app>.<method>()).

The agent called complete_task() and submitted an answer — but the AppWorld test suite marked it WRONG.
Your job: diagnose exactly WHY and give a concrete fix instruction.

=== TASK ===
{task}

=== CODE THAT RAN (last attempt) ===
{last_code[:2000]}

=== EXECUTION OUTPUT ===
{last_output[:1500]}

=== FAILED TEST REQUIREMENTS ===
{failures_text}

=== YOUR JOB ===
Identify the root cause. Consider these categories:
  1. WRONG DATA SOURCE   — used wrong API (e.g. show_liked_songs instead of show_playlist → songs)
  2. WRONG FIELD         — extracted wrong field (e.g. song['name'] instead of song['title'])
  3. WRONG FILTER        — filter too broad/narrow, missing items or including extras
  4. WRONG AGGREGATION   — max/min/sum/count computed incorrectly
  5. WRONG ENTITY        — acted on wrong person, playlist, or item
  6. MISSING ACTION      — needed create_review AND update_review but only did one
  7. WRONG FORMAT        — right value, wrong format (list vs string, int vs str, etc.)

Respond in this exact format (3 lines, no extra text):
ROOT_CAUSE: <category label>
EXPLANATION: <1-2 sentences describing exactly what went wrong>
FIX_INSTRUCTION: <concrete instruction — specify which API to call, which field to read, what logic to change>
"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=400,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"Reviewer error: {e}"
