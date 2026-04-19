import re
import time

from appworld import AppWorld, load_task_ids

from agent import PlannerAgent, ExecutorAgent
from config import (
    MAX_REPEATED_CODE,
    MAX_PLAN_STEPS,
    MAX_PLANNING_ROUNDS,
)
import logger

# ---------------------------------------------------------------------------
# TOOLS — loaded once and injected at the start of every session
# ---------------------------------------------------------------------------
with open("tools.py", "r") as f:
    CUSTOM_TOOLS_CODE = f.read()

# ---------------------------------------------------------------------------
# RUN CONFIG
# ---------------------------------------------------------------------------
dataset_name            = "train"
experiment_name         = "lara_main_runner"
max_interactions        = 15
max_mission_retries     = 2
max_consecutive_errors  = 3

# ---------------------------------------------------------------------------
# ERROR MESSAGES
# ---------------------------------------------------------------------------
_SYNTAX_ERROR_FEEDBACK = (
    "SyntaxError: your last response was not valid Python code. "
    "Output ONLY Python code — no English text, no explanations, no analysis. "
    "Write the single next step and stop."
)

_RECOVERY_REMINDER = (
    "REMINDER: You have produced invalid code twice in a row. "
    "Your ENTIRE response must be valid Python code. "
    "No English sentences, no reasoning, no markdown. "
    "Write ONE Python statement or function call and stop immediately."
)


def _sanitize_error(error_str: str) -> str:
    """Returns a short, clear error message without the failing code."""
    low = error_str.lower()
    if "syntax error" in low or "unterminated string" in low or "invalid syntax" in low:
        return _SYNTAX_ERROR_FEEDBACK
    lines = error_str.strip().splitlines()
    return "\n".join(lines[-5:])[:400]


def inject_real_apis(raw_error: str, world) -> str | None:
    """If the error is 'No API named X found in Y app', fetch and return the real API list."""
    m = re.search(r"No API named '(\w+)' found in the (\w+) app", raw_error)
    if not m:
        return None
    api_name, app_name = m.group(1), m.group(2)
    try:
        real_apis = world.execute(
            f"print(apis.api_docs.show_api_descriptions(app_name='{app_name}'))"
        )
        return (
            f"No API named '{api_name}' exists in the {app_name} app. "
            f"Here are the real {app_name} APIs — pick the correct name from this list:\n{real_apis}"
        )
    except Exception:
        return None


def _run_planner(world, task, feedback: str, cycle: int) -> tuple[str, bool]:
    """
    Run the planner and return (plan_text, plan_complete).
    On cycle > 0 the planner receives executor failure feedback and writes a revised plan.
    """
    label_prefix = "Plan" if cycle == 0 else f"Replan{cycle}"
    phase_label  = "📋 Phase 1: Planning" if cycle == 0 else f"🔄 Replanning (cycle {cycle + 1}/{MAX_PLANNING_ROUNDS})"
    logger.phase(phase_label)

    # Reset blackboard so the planner writes a fresh plan
    try:
        world.execute("blackboard = Blackboard()")
    except Exception:
        pass

    planner      = PlannerAgent(task, feedback=feedback)
    output       = None
    plan_complete = False

    for step in range(MAX_PLAN_STEPS):
        code = planner.next_code_block(output)

        if "__AGENT_LLM_FAILURE__" in code:
            logger.error("Planner LLM failed.")
            break
        if planner.is_stuck():
            logger.warning(f"Planner stuck ({MAX_REPEATED_CODE}x same code).")
            break

        label = f"{label_prefix}.{step + 1}"
        logger.code_block(code, label=label)

        try:
            output = world.execute(code)
            logger.output_block(output, label=label)
        except Exception as e:
            output = _sanitize_error(str(e))
            logger.error(output)

        try:
            bb_status = world.execute("print(blackboard.plan_status)").strip()
            if bb_status == "complete":
                plan_complete = True
                logger.success("✅ Plan complete.")
                break
        except Exception:
            pass

    try:
        plan_text = world.execute("print(blackboard.plan_text())").strip()
    except Exception:
        plan_text = ""

    return plan_text, plan_complete


def _run_executor(world, task, plan_text: str, task_id: str) -> tuple[bool, str]:
    """
    Run the executor with the given plan.
    Returns (mission_success, last_error).
    last_error is non-empty when the executor failed so the planner can revise.
    """
    logger.output_block(plan_text or "(none)", label="📌 Plan handed to executor")
    logger.phase("⚙️  Phase 2: Execution")

    executor           = ExecutorAgent(task, plan=plan_text)
    output             = None
    consecutive_errors = 0
    last_error         = ""

    for step in range(max_interactions):
        code = executor.next_code_block(output)

        if "__AGENT_LLM_FAILURE__" in code:
            logger.error("Executor LLM failed after all retries.")
            last_error = "LLM failed to produce valid code after all retries."
            break
        if executor.is_stuck():
            logger.warning(f"Executor stuck ({MAX_REPEATED_CODE}x same code).")
            last_error = "Executor got stuck repeating the same code without making progress."
            break

        label = f"Step {step + 1}"
        logger.code_block(code, label=label)

        try:
            output = world.execute(code)
            logger.output_block(output, label=label)

            # AppWorld returns execution errors as strings in output, not as exceptions.
            # Detect and handle "No API named X" errors here.
            if "No API named" in output:
                last_error = output
                injected = inject_real_apis(output, world)
                if injected:
                    output = injected
                    consecutive_errors = 0
                    logger.info("💉 Injected real API list into executor context.")
                else:
                    consecutive_errors += 1
            elif "Execution failed" in output:
                last_error = output
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        f"{max_consecutive_errors} consecutive errors — aborting execution."
                    )
                    break
                if consecutive_errors >= 2:
                    output = _RECOVERY_REMINDER
                    consecutive_errors = 0
            else:
                consecutive_errors = 0
                last_error = ""

        except Exception as e:
            raw_error = str(e)
            last_error = raw_error
            logger.error(raw_error[:300])
            consecutive_errors += 1

            if consecutive_errors >= max_consecutive_errors:
                logger.error(
                    f"{max_consecutive_errors} consecutive errors — aborting execution."
                )
                break

            if consecutive_errors >= 2:
                output = _RECOVERY_REMINDER
                consecutive_errors = 0
            else:
                output = _sanitize_error(raw_error)

        if world.task_completed():
            agent_failed = 'status="fail"' in code or "status='fail'" in code
            if agent_failed:
                logger.error(f"Task {task_id}: agent gave up (status='fail'). Will retry.")
                return False, "Agent explicitly called complete_task(status='fail')."

            # Verify correctness — task_completed() only means complete_task() was called,
            # not that the answer was right. evaluate() runs the actual test suite.
            eval_result = world.evaluate()
            passed = eval_result.pass_count
            total  = eval_result.total_count
            pct    = eval_result.pass_percentage
            if eval_result.success:
                logger.success(
                    f"Task {task_id} completed correctly! "
                    f"({passed}/{total} tests passed, {pct:.0f}%)"
                )
                return True, ""
            else:
                fail_reqs = [f['requirement'] for f in eval_result.failures[:3]]
                logger.error(
                    f"Task {task_id}: complete_task() called but evaluation FAILED "
                    f"({passed}/{total} tests passed, {pct:.0f}%). "
                    f"Failed: {fail_reqs}"
                )
                return False, (
                    f"complete_task() was called but the answer was wrong. "
                    f"{passed}/{total} tests passed ({pct:.0f}%). "
                    f"Failed requirements: {fail_reqs}"
                )

    return False, last_error


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------
task_ids = load_task_ids(dataset_name)

for index, task_id in enumerate(task_ids[1:5]):
    logger.task_header(task_id, index + 1, len(task_ids))
    mission_success = False

    for attempt in range(1, max_mission_retries + 1):
        logger.attempt(attempt, max_mission_retries)
        
        try:
            with AppWorld(task_id=task_id, experiment_name=experiment_name) as world:

                logger.task_instruction(world.task.instruction)

                try:
                    world.execute(CUSTOM_TOOLS_CODE)
                    logger.info("🔧 Tools injected.")
                except Exception as e:
                    logger.warning(f"Tool injection failed: {e}")

                planner_feedback = ""

                for cycle in range(MAX_PLANNING_ROUNDS):
                    # --- PLANNING ---
                    plan_text, plan_complete = _run_planner(
                        world, world.task, planner_feedback, cycle
                    )

                    if not plan_complete:
                        logger.warning("Planner did not produce a complete plan — skipping execution.")
                        break

                    # --- EXECUTION ---
                    mission_success, last_error = _run_executor(
                        world, world.task, plan_text, task_id
                    )

                    if mission_success:
                        break

                    if cycle < MAX_PLANNING_ROUNDS - 1:
                        # Collect what was done for planner feedback
                        try:
                            done_steps = world.execute("print(blackboard.completed_steps)").strip()
                        except Exception:
                            done_steps = "unknown"

                        # Build specific guidance based on error type
                        api_err = re.search(
                            r"No API named '(\w+)' found in the (\w+) app", last_error
                        )
                        if api_err:
                            wrong_api, app = api_err.group(1), api_err.group(2)
                            error_guidance = (
                                f"The executor called '{wrong_api}' in the {app} app, which does not exist.\n"
                                f"The revised plan MUST add a step at the point of failure that says:\n"
                                f"  \"Call show_api_descriptions('{app}') to get the real API names, "
                                f"then use the correct API to [describe what data is needed].\"\n"
                                f"Do NOT assume any {app} API names — let the executor look them up first."
                            )
                        elif last_error:
                            error_guidance = last_error[:400]
                        else:
                            error_guidance = "The executor got stuck repeating the same code."

                        planner_feedback = (
                            f"Execution cycle {cycle + 1} failed.\n"
                            f"Steps completed before failure: {done_steps}\n"
                            f"Error: {error_guidance}\n\n"
                            f"Write a corrected plan. Continue from where the executor left off — "
                            f"do not repeat already-completed steps."
                        )
                        logger.info(f"📤 Sending failure context to planner:\n{planner_feedback}")

                if mission_success:
                    break

        except Exception as e:
            logger.error(f"Environment error: {e}")

        if not mission_success and attempt < max_mission_retries:
            logger.info("⏳ Retrying with fresh environment...")
            time.sleep(5)

    logger.separator()

logger.done()
