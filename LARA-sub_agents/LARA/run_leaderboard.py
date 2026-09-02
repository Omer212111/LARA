"""
Leaderboard runner for the held-out test_normal / test_challenge splits.

benchmark.py hardcodes experiment_name = "lara_langchain_agent" on purpose
(see CLAUDE.md) so dev/train runs never accidentally collide with each other.
A leaderboard run needs its own experiment_name instead of overwriting that
dev output directory. Rather than edit benchmark.py's hardcoded value, this
subclasses AppWorld to force the experiment_name it's constructed with,
then reuses benchmark.py's existing run_official_benchmark() loop unchanged.

Usage:
    python run_leaderboard.py test_normal lara_test_normal
    python run_leaderboard.py test_challenge lara_test_challenge
"""
import sys

import benchmark
from appworld import AppWorld as _RealAppWorld, load_task_ids


def _appworld_with_fixed_name(fixed_name):
    class _NamedAppWorld(_RealAppWorld):
        def __init__(self, *args, **kwargs):
            kwargs["experiment_name"] = fixed_name
            super().__init__(*args, **kwargs)
    return _NamedAppWorld


def main():
    if len(sys.argv) != 3:
        print("Usage: python run_leaderboard.py <test_normal|test_challenge> <experiment_name>")
        sys.exit(1)
    dataset, experiment_name = sys.argv[1], sys.argv[2]

    # benchmark.py's run_official_benchmark() calls the module-level `AppWorld`
    # name at run time, so patching it here is picked up without touching benchmark.py.
    benchmark.AppWorld = _appworld_with_fixed_name(experiment_name)

    task_ids = load_task_ids(dataset)
    print(f"Running {len(task_ids)} tasks from '{dataset}' under experiment_name='{experiment_name}'")
    benchmark.run_official_benchmark(num_tasks=len(task_ids), dataset=dataset, task_ids=task_ids)


if __name__ == "__main__":
    main()
