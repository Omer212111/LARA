"""
logger.py — writes agent run output to run_log.html (auto-refreshes every 2s).
Open run_log.html in a browser while running main.py to watch in real time.
Console output is flushed immediately so Windows buffers don't swallow it when
the HTML file is blocked by the AppWorld sandbox.
"""
import html as _html
import sys
from datetime import datetime

# Windows consoles default to cp1252 which can't encode emojis.
# Reconfigure to UTF-8 once at import time so all print() calls work.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_LOG_FILE = "run_log.html"

_HTML_HEADER = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="5">
<title>LARA Agent Log</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: 'Consolas', 'Fira Code', 'Courier New', monospace;
    background: #1e1e1e;
    color: #d4d4d4;
    margin: 0;
    padding: 16px 24px;
    font-size: 13px;
    line-height: 1.5;
  }
  h1 { color: #569cd6; font-size: 1.2em; margin: 0 0 16px 0; letter-spacing: 1px; }
  .ts { color: #555; font-size: 0.8em; float: right; padding-left: 12px; }

  /* ── base card ── */
  .card {
    margin: 4px 0;
    padding: 7px 12px;
    border-radius: 4px;
    border-left: 4px solid #555;
    overflow: hidden;
  }

  /* ── card variants ── */
  .task    { background:#1a3554; border-color:#4a9eff; font-size:1.05em; font-weight:bold; margin-top:18px; }
  .instruction { background:#1e2218; border-color:#b5cea8; color:#c8e6b0; margin-top:4px; }
  .attempt { background:#252540; border-color:#9d7fff; }
  .phase   { background:#1e2a3a; border-color:#56b6c2; font-weight:bold; margin-top:10px; }
  .round   { background:#222;    border-color:#444; }
  .info    { background:#1e1e1e; border-color:#555; }
  .success { background:#1a3a1a; border-color:#4ec94e; color:#6ddf6d; font-weight:bold; }
  .warning { background:#2e2212; border-color:#d7ba7d; color:#d7ba7d; }
  .error   { background:#3a1616; border-color:#f44747; color:#f88; }
  .done    { background:#0d1f0d; border-color:#4ec94e; color:#6ddf6d; font-size:1.1em; font-weight:bold; margin-top:18px; text-align:center; }
  .eval-pass { background:#0d2010; border-color:#4ec94e; color:#6ddf6d; font-weight:bold; }
  .eval-fail { background:#2a1010; border-color:#f44747; color:#f88; font-weight:bold; }

  /* ── code / output blocks ── */
  .code-block, .output-block {
    margin: 3px 0;
    border-radius: 4px;
    border-left: 4px solid;
    overflow: hidden;
  }
  .code-block   { border-color: #569cd6; background: #252526; }
  .output-block { border-color: #4ec94e; background: #1a241a; }

  .block-label {
    font-size: 0.78em;
    padding: 3px 10px 2px;
    color: #888;
    border-bottom: 1px solid #333;
  }
  .code-block   .block-label { background: #2d2d2d; }
  .output-block .block-label { background: #1e2b1e; }

  pre {
    margin: 0;
    padding: 8px 12px;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 400px;
    overflow-y: auto;
  }
  .code-block   pre { color: #9cdcfe; }
  .output-block pre { color: #b5cea8; }

  /* ── separator ── */
  hr { border: none; border-top: 1px solid #333; margin: 14px 0; }
</style>
</head>
<body>
<h1>LARA Agent Run Log</h1>
<div id="log">
"""

_initialized = False


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _esc(text: str) -> str:
    return _html.escape(str(text))


def _append(snippet: str) -> None:
    global _initialized
    try:
        if not _initialized:
            # ניסיון יצירת הקובץ עם הכותרת
            with open(_LOG_FILE, "w", encoding="utf-8") as f:
                f.write(_HTML_HEADER)
            _initialized = True
        
        # ניסיון הוספת הלוג החדש
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(snippet + "\n")
            
    except PermissionError:
        # אם AppWorld חוסם כתיבה, אנחנו מדפיסים למסך כדי שלא נאבד מידע
        # אבל לא נותנים לשגיאה להקריס את ה-Benchmark
        print(f"\n[AppWorld Safety Block] Logger couldn't write to file. Output: {snippet[:100]}...", flush=True)
    except Exception as e:
        print(f"\n[Logger Error] {e}", flush=True)
    sys.stdout.flush()


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def task_header(task_id: str, index: int, total: int) -> None:
    print(f"\n{'*'*40}\nTask {index}/{total}: {task_id}\n{'*'*40}")
    _append(
        f'<div class="card task">'
        f'<span class="ts">{_ts()}</span>'
        f'Task {index}/{total} — {_esc(task_id)}'
        f'</div>'
    )


def task_instruction(instruction: str) -> None:
    print(f"📋 Instruction: {instruction}")
    _append(
        f'<div class="card instruction">'
        f'<span class="ts">{_ts()}</span>'
        f'<strong>📋 Task:</strong> {_esc(instruction)}'
        f'</div>'
    )


def attempt(num: int, total: int) -> None:
    print(f"\n🚀 Attempt {num}/{total}...")
    _append(
        f'<div class="card attempt">'
        f'<span class="ts">{_ts()}</span>'
        f'🚀 Attempt {num}/{total}'
        f'</div>'
    )


def phase(msg: str) -> None:
    print(f"\n{msg}")
    _append(
        f'<div class="card phase">'
        f'<span class="ts">{_ts()}</span>'
        f'{_esc(msg)}'
        f'</div>'
    )


def round_header(msg: str) -> None:
    print(f"\n{msg}")
    _append(
        f'<div class="card round">'
        f'<span class="ts">{_ts()}</span>'
        f'{_esc(msg)}'
        f'</div>'
    )


def info(msg: str) -> None:
    print(msg)
    _append(
        f'<div class="card info">'
        f'<span class="ts">{_ts()}</span>'
        f'{_esc(msg)}'
        f'</div>'
    )


def code_block(code_str: str, label: str = "") -> None:
    print(f"\n[CODE{' — ' + label if label else ''}]\n{code_str}")
    label_html = f'<div class="block-label">{_esc(label)}</div>' if label else ""
    _append(
        f'<div class="code-block">'
        f'{label_html}'
        f'<pre>{_esc(code_str)}</pre>'
        f'</div>'
    )


def output_block(out_str: str, label: str = "") -> None:
    print(f"\n[OUTPUT{' — ' + label if label else ''}]\n{out_str}")
    label_html = f'<div class="block-label">{_esc(label)}</div>' if label else ""
    _append(
        f'<div class="output-block">'
        f'{label_html}'
        f'<pre>{_esc(str(out_str))}</pre>'
        f'</div>'
    )


def success(msg: str) -> None:
    print(f"✅ {msg}")
    _append(
        f'<div class="card success">'
        f'<span class="ts">{_ts()}</span>'
        f'✅ {_esc(msg)}'
        f'</div>'
    )


def warning(msg: str) -> None:
    print(f"⚠️  {msg}")
    _append(
        f'<div class="card warning">'
        f'<span class="ts">{_ts()}</span>'
        f'⚠️ {_esc(msg)}'
        f'</div>'
    )


def error(msg: str) -> None:
    print(f"❌ {msg}")
    _append(
        f'<div class="card error">'
        f'<span class="ts">{_ts()}</span>'
        f'❌ {_esc(msg)}'
        f'</div>'
    )


def separator() -> None:
    print()
    _append('<hr>')


def done() -> None:
    print("\n--- Done ---")
    _append(
        f'<div class="done">'
        f'<span class="ts">{_ts()}</span>'
        f'─── Run complete ───'
        f'</div>'
    )
    _append('</div></body></html>')
