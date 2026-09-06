"""Reviewer-ablation event log.

One JSONL line per RETRY event — i.e. every time an Executor second attempt runs,
whether the Reviewer drove it (arm B) or it was a blind re-roll (arm C). Arm A
(no retry) emits nothing, which is itself the check that the Reviewer never fired.

Each row answers the study's headline within-arm 2x2 (attempt-1 correct/wrong x
final correct/wrong) plus the mechanism checks:

    {"task_id": "...", "arm": "rev_reviewer_ext", "reviewer_fired": true,
     "executor_runs": 2, "diagnosis": "ROOT_CAUSE: WRONG SCOPE ...",
     "attempt1_completed": true, "attempt1_correct": false,
     "final_completed": true, "final_correct": true,
     "submission_differed": true,
     "reviewer_tokens": 812, "executor_run2_tokens": 19344, "t": 175...}

Emission is gated on LARA_REVIEWER_LOG: unset -> no-op, so a normal run is
untouched. Same env-var pattern as token_meter.py. Best-effort: any failure in
here is swallowed so it can never break a run.
"""
from __future__ import annotations

import json
import os
import threading
import time

_LOCK = threading.Lock()
_PATH = os.environ.get("LARA_REVIEWER_LOG")   # read once at import; unset -> disabled


def log_event(**row) -> None:
    """Append one retry-event row. No-op unless LARA_REVIEWER_LOG is set. Never raises."""
    if not _PATH:
        return
    try:
        row.setdefault("t", round(time.time(), 3))
        with _LOCK, open(_PATH, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:
        pass
