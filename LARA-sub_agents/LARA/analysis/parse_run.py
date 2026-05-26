"""
LARA — Benchmark run trace parser

Given a benchmark run output file (the tee'd log from `python benchmark.py ...`),
extract a structured per-task report and tag each task with failure categories
defined in analysis/error_categories.json.

CLI:
    python analysis/parse_run.py <output_file> [--out report.json]

Module:
    from analysis.parse_run import parse_run
    report = parse_run("/tmp/...output")
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# ── Dictionary loading ────────────────────────────────────────────────────────

DICT_PATH = Path(__file__).parent / "error_categories.json"

def _load_dictionary() -> dict:
    with DICT_PATH.open() as f:
        return json.load(f)


# ── Trace markers (orchestrator emits these reliably) ─────────────────────────

RE_TASK_HEADER       = re.compile(r"^Task\s+\d+/\d+:\s*(\S+)\s*$", re.MULTILINE)
RE_INSTRUCTION       = re.compile(r"^📋 Instruction:\s*(.+)$", re.MULTILINE)
RE_PLAN_START        = re.compile(r"^\[OUTPUT — 📋 Explorer Plan\]\s*$", re.MULTILINE)
RE_DISPATCH          = re.compile(
    r"^\[Orchestrator\] Step (\d+): dispatching to (\w+)\s*$|"
    r"^\[Orchestrator\] Step (\d+): generic executor\s*$",
    re.MULTILINE,
)
RE_CODE_BLOCK_HEADER = re.compile(
    r"^\[CODE — ReAct step (\d+) / attempt (\d+)\]\s*$", re.MULTILINE
)
RE_OUTPUT_HEADER     = re.compile(
    r"^\[OUTPUT — ReAct step (\d+) / attempt (\d+)\]\s*$", re.MULTILINE
)
RE_WRONG_SUMMARY     = re.compile(
    r"^❌ complete_task\(\) called but WRONG — (\d+)/(\d+) tests passed \((\d+)%\)\.\s*Failed:\s*(\[.+?\])\s*$",
    re.MULTILINE | re.DOTALL,
)
RE_CORRECT_SUMMARY   = re.compile(
    r"^Task CORRECT at step \d+ — (\d+)/(\d+) tests passed \((\d+)%\)",
    re.MULTILINE,
)
RE_ATTEMPT_DONE      = re.compile(
    r"^\[Orchestrator\] Done — attempt (\d+), (\d+) steps, completed=(True|False), correct=(True|False), had_error=(True|False)\s*$",
    re.MULTILINE,
)
RE_TASK_CLOSE_WRONG  = re.compile(
    r"^❌ Task (\S+) WRONG — (\d+)/(\d+) tests passed \((\d+)%\)\s*\|\s*Failed:\s*(\[.+?\])\s*\|\s*([\d.]+)s\s*$",
    re.MULTILINE | re.DOTALL,
)
RE_TASK_CLOSE_RIGHT  = re.compile(
    r"^✅ Task (\S+) CORRECT — (\d+)/(\d+) tests passed \((\d+)%\)\s*\|\s*([\d.]+)s\s*$",
    re.MULTILINE,
)
RE_BENCH_COMPLETE    = re.compile(r"^BENCHMARK COMPLETE — (\d+)/(\d+) tasks correct\s*$", re.MULTILINE)
RE_SLICE_HEADER      = re.compile(r"^Found \d+ tasks: \[(.+?)\]\s*$", re.MULTILINE)
RE_FLOW_CRASH        = re.compile(r"^❌ Flow crashed:\s*(.+)$", re.MULTILINE)


# ── Pagination allow-list (E-PAGINATION-MISSED detection) ─────────────────────
# Derived from the venmo / gmail / spotify / amazon / phone specialist prompts'
# enumerated paginated APIs. Extend as new specialists are added.

PAGINATED_APIS = {
    "venmo": {
        "show_transactions", "show_received_payment_requests", "show_sent_payment_requests",
        "show_transaction_comments", "show_social_feed", "show_notifications",
        "search_users", "search_friends", "show_bank_transfer_history",
    },
    "phone": {
        "search_contacts", "show_text_message_window", "search_text_messages",
        "show_voice_message_window", "search_voice_messages", "show_alarms",
    },
    "gmail": {
        "show_inbox", "show_sent", "show_drafts", "show_trash", "show_starred",
        "show_thread", "search_emails",
    },
    "spotify": {
        "show_playlist_library", "show_song_library", "show_album_library",
        "show_liked_songs", "show_song_reviews",
    },
    "amazon": {
        "search_products", "show_orders", "show_product_reviews",
    },
}

ACTION_API_TOKENS = (
    "like_transaction", "unlike_transaction",
    "create_transaction_comment", "update_transaction_comment", "delete_transaction_comment",
    "like_transaction_comment", "unlike_transaction_comment",
    "create_transaction", "update_transaction",
    "create_payment_request", "update_payment_request", "delete_payment_request",
    "approve_payment_request", "deny_payment_request", "remind_payment_request",
    "send_text_message", "send_voice_message",
    "create_alarm", "update_alarm", "delete_alarm",
    "place_order", "delete_product_from_cart", "add_product_to_cart",
    "move_product_from_wish_list_to_cart", "initiate_return",
    "send_email", "reply_to_email", "delete_email",
    "like_song", "unlike_song", "review_song", "update_song_review",
    "add_song_to_playlist", "remove_song_from_playlist",
    "add_contact", "update_contact", "delete_contact",
    "add_friend", "remove_friend",
    "subscribe_prime",
    "add_payment_card", "update_payment_card", "delete_payment_card",
    "add_to_venmo_balance", "withdraw_from_venmo_balance",
)

RELATIONSHIP_WORDS = (
    "roommate", "roommates", "coworker", "coworkers", "colleague", "colleagues",
    "sibling", "siblings", "parent", "parents", "brother", "brothers",
    "sister", "sisters", "mother", "father",
    "friend", "friends",
)
ACTION_VERB_STARTS = (
    "send", "add", "like", "comment", "create", "place", "buy", "order",
    "delete", "remove", "approve", "deny", "rate", "review",
    "move", "transfer", "request", "subscribe", "download", "update",
)


# ── Per-task parsing ──────────────────────────────────────────────────────────

def _slice_per_task(text: str) -> list[tuple[str, str]]:
    """Split run text into [(task_id, task_body)] using 'Task N/M: <id>' headers."""
    matches = list(RE_TASK_HEADER.finditer(text))
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1), text[start:end]))
    return out


def _extract_instruction(body: str) -> str:
    m = RE_INSTRUCTION.search(body)
    return m.group(1).strip() if m else ""


def _extract_plan(body: str) -> str:
    """Plan begins after [OUTPUT — 📋 Explorer Plan] and continues until the next
    Supervisor decision or attempt 1 Executor line."""
    m = RE_PLAN_START.search(body)
    if not m:
        return ""
    start = m.end()
    # Stop at the next Supervisor decision marker OR the first Orchestrator step
    end_markers = [
        body.find("🧭 Supervisor", start),
        body.find("[Orchestrator] Step 1: dispatching", start),
        body.find("[Orchestrator] Step 1: generic", start),
        body.find("\n\n[Executor]", start),
    ]
    end_markers = [e for e in end_markers if e > start]
    end = min(end_markers) if end_markers else len(body)
    return body[start:end].strip()


def _extract_dispatch_map(body: str) -> dict[int, str]:
    """Per ReAct step → specialist name (or 'generic')."""
    out = {}
    for m in RE_DISPATCH.finditer(body):
        if m.group(1):       # named specialist
            out[int(m.group(1))] = m.group(2)
        elif m.group(3):     # generic
            out[int(m.group(3))] = "generic"
    return out


def _extract_react_steps(body: str) -> list[dict]:
    """All [CODE — ReAct step N / attempt M] blocks with their outputs."""
    code_matches = list(RE_CODE_BLOCK_HEADER.finditer(body))
    output_matches = list(RE_OUTPUT_HEADER.finditer(body))

    steps = []
    for cm in code_matches:
        step = int(cm.group(1))
        attempt = int(cm.group(2))
        # Code spans from after this header to the next [ACTION] Executing or [OUTPUT
        next_action = body.find("\n[ACTION] Executing Python code", cm.end())
        next_output_after_cm = next((om for om in output_matches if om.start() > cm.end()), None)
        code_end = next_action if next_action > cm.end() else (
            next_output_after_cm.start() if next_output_after_cm else len(body)
        )
        code = body[cm.end():code_end].strip()

        # Output spans from the matching [OUTPUT — ReAct step N / attempt M] to next marker
        om = next_output_after_cm
        if om and int(om.group(1)) == step and int(om.group(2)) == attempt:
            # End at next [CODE — ReAct step or [Orchestrator] Step
            next_code = body.find("[CODE — ReAct step", om.end())
            next_orch = body.find("[Orchestrator] Step", om.end())
            end_candidates = [c for c in (next_code, next_orch) if c > om.end()]
            end = min(end_candidates) if end_candidates else len(body)
            output = body[om.end():end].strip()
        else:
            output = ""

        had_error = (
            output.startswith("Execution failed")
            or output.startswith("Execution Failed")
            or "Traceback" in output
        )

        steps.append({
            "step": step,
            "attempt": attempt,
            "code": code,
            "output": output,
            "had_error": had_error,
        })
    return steps


def _extract_attempts(body: str) -> list[dict]:
    """Per-attempt close lines."""
    out = []
    for m in RE_ATTEMPT_DONE.finditer(body):
        out.append({
            "attempt": int(m.group(1)),
            "steps": int(m.group(2)),
            "completed": m.group(3) == "True",
            "correct": m.group(4) == "True",
            "had_error": m.group(5) == "True",
        })
    return out


def _extract_final_score(body: str) -> dict:
    """Final score for the task. Look for ❌ Task ... WRONG or ✅ Task ... CORRECT."""
    m = RE_TASK_CLOSE_WRONG.search(body)
    if m:
        return {
            "status": "wrong",
            "pass": int(m.group(2)),
            "total": int(m.group(3)),
            "pct": int(m.group(4)),
            "failures": _parse_failure_list(m.group(5)),
            "time_s": float(m.group(6)),
        }
    m = RE_TASK_CLOSE_RIGHT.search(body)
    if m:
        return {
            "status": "correct",
            "pass": int(m.group(2)),
            "total": int(m.group(3)),
            "pct": int(m.group(4)),
            "failures": [],
            "time_s": float(m.group(5)),
        }
    # Partial — check if mid-attempt WRONG summaries exist (the task may have ended without close marker)
    m = RE_WRONG_SUMMARY.search(body)
    if m:
        return {
            "status": "incomplete-wrong",
            "pass": int(m.group(1)),
            "total": int(m.group(2)),
            "pct": int(m.group(3)),
            "failures": _parse_failure_list(m.group(4)),
            "time_s": None,
        }
    return {"status": "no-data", "pass": 0, "total": 0, "pct": 0, "failures": [], "time_s": None}


def _parse_failure_list(raw: str) -> list[str]:
    """Failures come as a Python-style list literal in the log. Parse via eval-safe means."""
    # The list contains strings with embedded newlines and special chars; use ast.literal_eval
    import ast
    try:
        return ast.literal_eval(raw)
    except Exception:
        return [raw.strip("[]")]


# ── Category tagging ──────────────────────────────────────────────────────────

def _tag_signature_categories(task: dict, categories: list[dict]) -> list[str]:
    """For each category with non-empty signatures, substring-match against
    the full task body (plan + all code + all output)."""
    haystack = "\n".join([
        task["plan"],
        "\n".join(s["code"] for s in task["react_steps"]),
        "\n".join(s["output"] for s in task["react_steps"]),
    ])
    tagged = []
    for c in categories:
        sigs = c.get("signatures") or []
        if not sigs:
            continue
        if any(s in haystack for s in sigs):
            tagged.append(c["code"])
    return tagged


def _tag_structural_categories(task: dict) -> list[str]:
    """The 8 structural categories. Best-effort heuristics."""
    tagged = []
    instr = task["instruction"].lower()
    plan = task["plan"]
    steps = task["react_steps"]
    all_code = "\n".join(s["code"] for s in steps)
    all_output = "\n".join(s["output"] for s in steps)

    # E-PLAN-NO-CONTACT-LOOKUP
    has_rel_word = any(w in instr for w in RELATIONSHIP_WORDS)
    # exclude "venmo friends" which is the venmo concept, not phone contacts
    venmo_friends_only = "venmo friends" in instr and not any(
        w in instr for w in RELATIONSHIP_WORDS if w not in ("friend", "friends")
    )
    if has_rel_word and not venmo_friends_only and "search_contacts" not in plan:
        tagged.append("E-PLAN-NO-CONTACT-LOOKUP")

    # E-PLAN-DATE-NOT-WIRED
    if "get_current_date_and_time" in plan:
        # Check whether any later plan line OR any code step mentions a date kwarg
        if not (
            "min_created_at" in plan or "max_created_at" in plan
            or "min_created_at" in all_code or "max_created_at" in all_code
        ):
            tagged.append("E-PLAN-DATE-NOT-WIRED")

    # E-WRONG-DATA-SOURCE — task references both transactions AND involvement,
    # but plan restricts to social_feed only (which is a subset of transactions).
    if (
        "show_social_feed" in plan
        and "transactions" in instr and "involving" in instr
        and "show_transactions" not in plan
    ):
        tagged.append("E-WRONG-DATA-SOURCE")

    # E-EXEC-WRONG-QUERY — search_contacts(query=...) on a relationship-group task
    if has_rel_word and re.search(r"search_contacts\([^)]*query\s*=", all_code):
        tagged.append("E-EXEC-WRONG-QUERY")

    # E-EXEC-OVER-ACT — action API called in a loop over social_feed (NOT over a
    # pre-filtered sub-list) with no email filter inside the loop block itself.
    for s in steps:
        if not any(a in s["code"] for a in ("like_transaction", "create_transaction_comment")):
            continue
        # The same block must iterate social_feed directly (not a filtered alias)
        if not re.search(r"for\s+\w+\s+in\s+social_feed\b", s["code"]):
            continue
        # And the same block has no sender/receiver email filter
        no_email_filter = not re.search(
            r"sender.*\['email'\].*in|receiver.*\['email'\].*in",
            s["code"], re.DOTALL,
        )
        if no_email_filter:
            tagged.append("E-EXEC-OVER-ACT")
            break

    # E-LINEAR-RETRY — two consecutive steps with HTTP-error output and >70% code similarity
    for i in range(len(steps) - 1):
        a, b = steps[i], steps[i + 1]
        if a["had_error"] and b["had_error"]:
            a_code, b_code = a["code"], b["code"]
            if a_code and b_code:
                # Naive char-level similarity (ratio of common chars in same order — quick approximation)
                from difflib import SequenceMatcher
                sim = SequenceMatcher(None, a_code, b_code).ratio()
                if sim > 0.7:
                    tagged.append("E-LINEAR-RETRY")
                    break

    # E-NO-FAIL-CLOSED — ACTION task + complete_task called + zero successful action APIs
    is_action_task = any(instr.strip().lower().startswith(v) for v in ACTION_VERB_STARTS)
    complete_called = "complete_task" in all_code
    successful_action = False
    for s in steps:
        if s["had_error"]:
            continue
        if any(a in s["code"] for a in ACTION_API_TOKENS):
            successful_action = True
            break
    if is_action_task and complete_called and not successful_action:
        tagged.append("E-NO-FAIL-CLOSED")

    # E-PAGINATION-MISSED — call_api on a known paginated API
    for app, apis in PAGINATED_APIS.items():
        for api in apis:
            pattern = rf"call_api\(\s*['\"]{app}['\"]\s*,\s*['\"]{api}['\"]"
            if re.search(pattern, all_code):
                # Exclude cases where fetch_all_pages was also used for that API
                if not re.search(
                    rf"fetch_all_pages\(\s*['\"]{app}['\"]\s*,\s*['\"]{api}['\"]",
                    all_code,
                ):
                    tagged.append("E-PAGINATION-MISSED")
                    break
        if "E-PAGINATION-MISSED" in tagged:
            break

    return tagged


# ── Top-level parser ──────────────────────────────────────────────────────────

def parse_run(path: str | os.PathLike) -> dict:
    """Parse a benchmark run output file into a structured report."""
    text = Path(path).read_text(errors="replace")

    # Slice & metadata
    slice_m = RE_SLICE_HEADER.search(text)
    slice_ids = []
    if slice_m:
        slice_ids = [t.strip().strip("'\"") for t in slice_m.group(1).split(",")]

    bench_m = RE_BENCH_COMPLETE.search(text)
    bench_summary = None
    if bench_m:
        bench_summary = {"correct": int(bench_m.group(1)), "total": int(bench_m.group(2))}

    dictionary = _load_dictionary()
    categories = dictionary["categories"]

    tasks = []
    for task_id, body in _slice_per_task(text):
        instruction = _extract_instruction(body)
        plan = _extract_plan(body)
        dispatch = _extract_dispatch_map(body)
        react_steps = _extract_react_steps(body)
        # Annotate each react step with its dispatched specialist
        for s in react_steps:
            if s["attempt"] == 1:
                s["specialist"] = dispatch.get(s["step"], "unknown")
            else:
                s["specialist"] = "unknown"  # attempt 2+ dispatches aren't reliably re-logged

        attempts = _extract_attempts(body)
        final = _extract_final_score(body)
        flow_crash = RE_FLOW_CRASH.search(body)

        task = {
            "task_id": task_id,
            "instruction": instruction,
            "plan": plan,
            "react_steps": react_steps,
            "attempts": attempts,
            "final_score": final,
            "flow_crash": flow_crash.group(1).strip() if flow_crash else None,
        }

        # Status
        if final["status"] == "correct":
            task["status"] = "correct"
        elif final["status"] == "wrong":
            task["status"] = "wrong"
        elif final["status"] in ("incomplete-wrong", "no-data"):
            task["status"] = "incomplete"
        else:
            task["status"] = "unknown"

        # Tag categories
        sig_tags = _tag_signature_categories(task, categories)
        struct_tags = _tag_structural_categories(task)
        task["tagged_categories"] = sorted(set(sig_tags + struct_tags))

        tasks.append(task)

    # Summary
    cat_counts = Counter()
    for t in tasks:
        for c in t["tagged_categories"]:
            cat_counts[c] += 1
    cat_to_tasks = {c: [t["task_id"] for t in tasks if c in t["tagged_categories"]]
                    for c in cat_counts}

    return {
        "input_path": str(path),
        "slice_task_ids": slice_ids,
        "benchmark_summary": bench_summary,
        "tasks": tasks,
        "category_counts": dict(cat_counts),
        "category_to_tasks": cat_to_tasks,
        "schema_version": 1,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to benchmark run output file")
    parser.add_argument("--out", help="Path to write JSON report (default: stdout)")
    parser.add_argument(
        "--summary", action="store_true",
        help="Print a human summary instead of JSON",
    )
    args = parser.parse_args()

    report = parse_run(args.input)

    if args.summary:
        print(f"Input: {report['input_path']}")
        if report["benchmark_summary"]:
            bs = report["benchmark_summary"]
            print(f"Benchmark: {bs['correct']}/{bs['total']} correct")
        print(f"Tasks parsed: {len(report['tasks'])}")
        print()
        print("Per-task:")
        for t in report["tasks"]:
            fs = t["final_score"]
            cats = ", ".join(t["tagged_categories"]) or "—"
            print(f"  {t['task_id']:<14} {t['status']:<11} "
                  f"{fs.get('pass', 0):>2}/{fs.get('total', 0):<2} "
                  f"({fs.get('pct', 0):>3}%)  steps={sum(a['steps'] for a in t['attempts'])}  "
                  f"cats=[{cats}]")
        print()
        print("Category counts (across all tasks):")
        for c, n in sorted(report["category_counts"].items(), key=lambda x: -x[1]):
            tasks = ", ".join(report["category_to_tasks"][c])
            print(f"  {c:<28} {n}  ({tasks})")
        return

    out = json.dumps(report, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(out)
        print(f"Wrote {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    _cli()
