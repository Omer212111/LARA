"""
LARA — Run a named benchmark slice

Loads analysis/slices.json, looks up the requested slice by name, and runs
benchmark.py's `run_official_benchmark` with the pinned task IDs.

CLI:
    python analysis/run_slice.py <slice_name> [--list] [--dry-run] [--log-to <path>]
                                              [--auto-parse] [--auto-panel] [--baseline <path>]

Examples:
    # List available slices
    python analysis/run_slice.py --list

    # Show what would run, without executing
    python analysis/run_slice.py venmo-smoke-5 --dry-run

    # Run the slice and tee output to a log
    python analysis/run_slice.py venmo-smoke-5 --log-to /tmp/lara_run.log

    # Run, parse, and produce a panel vs. a baseline report — full Stage 4
    python analysis/run_slice.py venmo-smoke-5 \\
        --log-to /tmp/lara_run.log \\
        --auto-parse --auto-panel --baseline /tmp/baseline_report.json
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
LARA_ROOT = HERE.parent
SLICES_PATH = HERE / "slices.json"


def _load_slices() -> dict:
    with SLICES_PATH.open() as f:
        return json.load(f)


def _list_slices(data: dict) -> None:
    print("Available slices:")
    for name, slice_def in data["slices"].items():
        n = len(slice_def["task_ids"])
        purpose = slice_def.get("purpose", "")
        print(f"  {name}  ({slice_def['dataset']}, {n} tasks)")
        if purpose:
            print(f"      {purpose[:140]}")


class _Tee:
    """Tee stdout/stderr to a file while still writing to the real stream.

    AppWorld's sandbox introspects sys.stdout (e.g. calls .fileno()) to wire up
    its own stream capture, so we must forward unknown attribute access to the
    underlying real stream. Without this, every world.execute() crashes with
    `'_Tee' object has no attribute 'fileno'`.
    """
    def __init__(self, stream, log_file):
        self.stream = stream
        self.log_file = log_file

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        self.log_file.write(data)
        self.log_file.flush()

    def flush(self):
        self.stream.flush()
        self.log_file.flush()

    def __getattr__(self, name):
        # Forward anything we don't override (fileno, isatty, encoding, ...) to
        # the real underlying stream so wrapper-aware libraries (AppWorld) work.
        return getattr(self.stream, name)


@contextlib.contextmanager
def _tee_to(path: str | None):
    if path is None:
        yield
        return
    # UTF-8 + errors="replace": the logger prints emojis (📋, 🚀, ✅); on Windows the
    # default cp1252 encoding raises UnicodeEncodeError and kills the run mid-task.
    log_file = open(path, "w", buffering=1, encoding="utf-8", errors="replace")
    real_stdout, real_stderr = sys.stdout, sys.stderr
    sys.stdout = _Tee(real_stdout, log_file)
    sys.stderr = _Tee(real_stderr, log_file)
    try:
        yield
    finally:
        sys.stdout = real_stdout
        sys.stderr = real_stderr
        log_file.close()


def _ensure_lara_importable():
    """Add LARA root to sys.path so we can import benchmark / main."""
    if str(LARA_ROOT) not in sys.path:
        sys.path.insert(0, str(LARA_ROOT))


def run_slice(slice_name: str, dry_run: bool = False) -> dict:
    """Run a named slice. Returns the slice definition that was executed."""
    data = _load_slices()
    if slice_name not in data["slices"]:
        raise SystemExit(
            f"Slice '{slice_name}' not found. "
            f"Available: {list(data['slices'].keys())}"
        )

    slice_def = data["slices"][slice_name]
    task_ids = slice_def["task_ids"]
    dataset = slice_def["dataset"]

    print(f"=== Slice: {slice_name} ===")
    print(f"Dataset: {dataset}")
    print(f"Task IDs ({len(task_ids)}): {task_ids}")
    if slice_def.get("purpose"):
        print(f"Purpose: {slice_def['purpose']}")
    print()

    if dry_run:
        print("[dry-run] Skipping execution.")
        return slice_def

    _ensure_lara_importable()
    # Import inside the function so dry-run / --list don't pay the import cost.
    from benchmark import run_official_benchmark

    run_official_benchmark(
        num_tasks=len(task_ids),
        dataset=dataset,
        task_ids=task_ids,
    )
    return slice_def


def _auto_post_process(log_path: str, want_parse: bool, want_panel: bool,
                       baseline: str | None) -> None:
    """After a run, optionally parse + produce a panel."""
    if not want_parse and not want_panel:
        return

    report_path = log_path.rsplit(".", 1)[0] + ".report.json"
    if want_parse:
        from analysis.parse_run import parse_run
        report = parse_run(log_path)
        Path(report_path).write_text(json.dumps(report, indent=2, default=str))
        print(f"\n[run_slice] Wrote report: {report_path}")

    if want_panel:
        from analysis.panel import compute_panel, render_panel
        current = json.loads(Path(report_path).read_text())
        baseline_report = json.loads(Path(baseline).read_text()) if baseline else None
        panel = compute_panel(current, baseline_report)
        print()
        print(render_panel(panel))


def _cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slice_name", nargs="?", help="Slice to run")
    parser.add_argument("--list", action="store_true", help="List available slices")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would run; don't execute")
    parser.add_argument("--log-to", help="Tee stdout+stderr to this file")
    parser.add_argument("--auto-parse", action="store_true",
                        help="After the run, parse the log into a report JSON")
    parser.add_argument("--auto-panel", action="store_true",
                        help="After parsing, render the behavioral panel")
    parser.add_argument("--baseline",
                        help="Baseline report JSON for the panel's delta computation")
    args = parser.parse_args()

    data = _load_slices()
    if args.list:
        _list_slices(data)
        return

    if not args.slice_name:
        parser.print_help()
        sys.exit(1)

    if args.auto_panel and not args.auto_parse:
        # Panel needs a report — implicitly enable parse.
        args.auto_parse = True

    if args.auto_parse and not args.log_to:
        parser.error("--auto-parse requires --log-to (we need a log file to parse).")

    with _tee_to(args.log_to):
        run_slice(args.slice_name, dry_run=args.dry_run)

    if not args.dry_run:
        _auto_post_process(
            log_path=args.log_to,
            want_parse=args.auto_parse,
            want_panel=args.auto_panel,
            baseline=args.baseline,
        )


if __name__ == "__main__":
    _cli()
