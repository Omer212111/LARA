"""
LARA MAS — Code Reviewer agent

Triggered ONLY when complete_task() was called but the answer was WRONG
(eval_info["completed"] == True AND eval_info["correct"] == False).

Goal: understand WHY the answer was wrong and produce a diagnosis that the
Executor can act on in its next attempt.

Uses GPT-4.1-nano (same as Explorer) — stronger reasoning than Qwen.
"""

import os

from openai import OpenAI

import logger
from config import EXPLORER_MODEL
from state import AgentState


def reviewer_node(state: AgentState) -> dict:
    logger.phase("🔎 Code Reviewer — diagnosing wrong answer")

    task         = state["messages"][0].content
    plan         = state.get("plan", "")
    findings     = state.get("findings", {})
    eval_failure = state.get("last_eval_failure", "")   # set by executor on wrong answer
    last_code    = state.get("last_code", "")           # set by executor on every run

    # Summarise all attempt outputs (latest first, capped to keep prompt short)
    attempts_summary = ""
    for key in reversed(list(findings.keys())):
        attempts_summary += f"\n--- {key} ---\n{findings[key][:800]}\n"
        if len(attempts_summary) > 2400:
            break

    prompt = f"""You are a code reviewer for an AI agent called LARA that solves tasks in AppWorld
(a simulated environment of apps like Spotify, Gmail, Venmo accessed via `apis.<app>.<method>()`).

The agent submitted an answer that was marked WRONG by the test suite, OR the code crashed entirely.
Your job: find the root cause from the evidence below. Every claim must be grounded in the output.

=== TASK ===
{task}

=== PLAN THAT WAS FOLLOWED ===
{plan[:1200]}

=== CODE THAT RAN (last attempt) ===
{last_code[:2000]}

=== EXECUTION OUTPUT (all attempts, latest first) ===
{attempts_summary}

=== FAILED TEST REQUIREMENTS ===
{eval_failure if eval_failure else "Not available — check the output above."}

=== DIAGNOSTIC PROCESS — work through these steps in order ===

STEP 0 — Check for ENVIRONMENT / SYSTEM ERRORS first (highest priority):
  If the output contains ANY of these strings:
    'Execution failed', 'SIGALRM', 'Alarm clock', 'signal.alarm',
    'TimeoutExpired', 'Killed', 'timed out', 'resource unavailable',
    'Execution Failed'
  → ROOT_CAUSE is ENVIRONMENT_ERROR. Stop here — do NOT continue to Steps 1-5.

  Look at the code that crashed. Identify the SPECIFIC heavy operation that caused the timeout:
    - A `for` loop calling call_api() or show_song() for every item in a large list?
    - A nested loop (for playlist → for song)?
    - A single code block that does login + fetch + iterate + complete_task all at once?

  FIX_INSTRUCTION MUST include ALL of these:
    1. "The code hit a sandbox timeout (SIGALRM)."
    2. Name the exact loop or operation that was too heavy (e.g. "the for-loop calling show_song() 200+ times").
    3. Prescribe a CONCRETE smaller approach. Pick the best strategy from:
       a) SKIP DETAIL FETCHES: if the list items already contain the needed field (e.g. songs from
          show_playlist often include 'title', 'like_count'), do NOT call show_song() per item.
          "Instead of calling show_song() for each song, use the fields already present in the
           playlist response. Print one item's keys first to verify."
       b) PAGINATION / BATCHING: "Process at most 20 items per ReAct step. In step 1, login and
          fetch the list. In step 2, process items [0:20]. In step 3, process [20:40]. Track the
          running best across steps."
       c) EARLY TERMINATION: "If looking for a max/min, keep a running best and skip items that
          can't beat it (e.g. if you already found like_count=500, skip songs with like_count < 500
          without fetching details)."
    4. "Use at most 5-8 lines of code per ReAct step. Each step must print its result."

STEP 1 — What was actually submitted?
  Find the submitted answer in the output (look for lines like "Most liked song: X" or "FINAL_ANSWER: X").
  Write it down before diagnosing.

STEP 2 — Check SCOPE first (most common logic error):
  If the task says "in my playlists / orders / albums" (PLURAL), the code MUST iterate ALL of them.
  WRONG SCOPE: the code picked only the best-ranked container (e.g. most-liked playlist)
               and searched only inside it — missing all items in the other containers.
  Check the output: does it print only ONE playlist/album/order ID, when there are several?
  If yes → ROOT_CAUSE is WRONG SCOPE.

STEP 3 — Check METRIC (second most common error):
  "most/least played"   → must sort by 'play_count'   — NOT 'added_at', NOT 'like_count'
  "most/least liked"    → must sort by 'like_count'    — NOT 'rating', NOT 'play_count'
  "highest/lowest rated"→ must sort by 'rating'
  "most/least recent"   → must sort by 'created_at' or 'added_at'
  If the code sorted/filtered by a proxy field (e.g. 'added_at' for "least-played"), → WRONG METRIC.

STEP 4 — Check FIELD NAME (only if Steps 2 & 3 are clear):
  ONLY diagnose WRONG FIELD if you can see in the printed output that:
    (a) the field was read, AND (b) an empty or wrong value came out.
  Example of valid WRONG FIELD evidence: output shows "Song title: None" or "Song title: Unknown".
  DO NOT claim WRONG FIELD if the submitted value is non-empty and plausible — the issue is
  almost certainly scope or metric, not the field name.
  DO NOT flip between 'title' and 'name' without seeing evidence in the output.

STEP 5 — Other causes:
  WRONG DATA SOURCE  — used the wrong API endpoint entirely (e.g. show_liked_songs vs show_playlist)
  WRONG FILTER       — included wrong items or excluded correct ones
  WRONG ENTITY       — acted on the wrong person, playlist, or item
  OFF-BY-ONE         — picked index [0] when [1] was correct, or vice versa
  WRONG FORMAT       — submitted a list when a string was expected, or vice versa

=== YOUR RESPONSE — use this exact format ===
SUBMITTED_ANSWER: <what the code actually submitted, or 'None — code crashed' if execution failed>
ROOT_CAUSE: <ENVIRONMENT_ERROR | WRONG SCOPE | WRONG METRIC | WRONG FIELD | WRONG DATA SOURCE | WRONG FILTER | WRONG ENTITY | OFF-BY-ONE | WRONG FORMAT>
EVIDENCE: <quote the specific output line that proves this diagnosis>
EXPLANATION: <1-2 sentences: exactly what went wrong>
FIX_INSTRUCTION: <concrete instruction for the Executor — name the exact loop, field, or API to change>
"""

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=EXPLORER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=600,
    )
    diagnosis = response.choices[0].message.content or ""
    logger.output_block(diagnosis, label="🔎 Reviewer Diagnosis")

    return {
        "reviewer_diagnosis": diagnosis,
        "reviewer_ran": True,
    }