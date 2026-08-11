"""
AppWorld compliance check — run this before any leaderboard run
===============================================================
Proves, rather than remembers, that the agent contains no hardcoded API call.

    python analysis/compliance_check.py        # exit 0 = clean, 1 = violations

What it checks
--------------
1. **No concrete endpoint named in our executable code.** Walks the AST of every agent
   module and of `BOOTSTRAP_CODE` (a string here, but code that we ship into the sandbox)
   looking for `apis.<app>.<endpoint>(...)`. This is the thing AppWorld's rule names:
   "hardcode any API calls into their agent's logic".

   Prompts are exempt by design — the rules explicitly allow "tell the agent in the prompt
   to do so by itself" — so an `apis.venmo.show_x(...)` inside a prompt string is fine and
   is not reported.

2. **No references to helpers that were removed** for rule reasons. A prompt naming
   `login_to_app` after the helper is gone produces a NameError at inference time, and
   re-adding the helper would re-break the rule.

3. **No matching on the task instruction text.** Deciding behaviour by regex over the
   task wording is how test-split phrasings leak into the agent — that is exactly what
   `amazon_template_plan` and the old ACTION-task regex did.

Deliberate exemptions are listed in ALLOWED below, each with the reason it is allowed.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

LARA = Path(__file__).resolve().parent.parent

# Modules that make up the agent. analysis/ is tooling, not the agent, and is excluded.
AGENT_FILES = sorted(
    [p for p in LARA.glob("*.py") if p.name not in {"main.py", "test_ledger.py"}]
    + list((LARA / "app_agents").glob("*.py"))
)

# (module, endpoint) pairs that may name an API in executable code, and why.
ALLOWED = {
    # The supervisor endpoints are the task protocol itself, not an app feature: every
    # agent must be able to submit an answer, and AppWorld's own examples call them.
    ("tools.py", "apis.supervisor.complete_task"),
    ("tools.py", "apis.supervisor.show_profile"),
    # Documentation discovery. AppWorld actively encourages "read documentation, explore,
    # experiment" — this is the mechanism that replaces baked-in API listings.
    ("tools.py", "apis.api_docs.show_app_descriptions"),
    ("tools.py", "apis.api_docs.show_api_descriptions"),
    ("tools.py", "apis.api_docs.show_api_doc"),
}

REMOVED_HELPERS = ("login_to_app", "find_contact")

# Regex literals that match against the TASK TEXT. Structural parsing of our own plan
# format or of the model's output is fine; these markers indicate task-wording matching.
TASK_TEXT_SMELLS = (
    "place an order",
    "buy me",
    "order all",
    "in my cart",
    "wish list",
    "highest-rated seller",
)


class _ApiCallFinder(ast.NodeVisitor):
    """Collect `apis.<app>.<endpoint>` attribute chains that are actually called."""

    def __init__(self) -> None:
        self.found: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        chain = self._chain(node.func)
        if chain and chain[0] == "apis" and len(chain) >= 3:
            self.found.append((getattr(node, "lineno", 0), ".".join(chain[:3])))
        self.generic_visit(node)

    @staticmethod
    def _chain(node: ast.AST) -> list[str] | None:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            return list(reversed(parts))
        return None


def _without_module_docstring(source: str) -> str:
    """`source` minus its module docstring, so notes ABOUT a removed helper do not
    read as uses OF it. Falls back to the whole file if the module will not parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    doc = ast.get_docstring(tree, clean=False)
    if not doc:
        return source
    return source.replace(doc, "", 1)


def _scan_code(source: str, label: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"{label}: does not parse — {e}"]
    finder = _ApiCallFinder()
    finder.visit(tree)
    out = []
    for lineno, call in finder.found:
        if (label, call) in ALLOWED:
            continue
        out.append(f"{label}:{lineno}: hardcoded API call `{call}(...)` in executable code")
    return out


def main() -> int:
    violations: list[str] = []
    checked = 0

    for path in AGENT_FILES:
        rel = path.relative_to(LARA).as_posix()
        label = path.name if path.parent == LARA else rel
        src = path.read_text(encoding="utf-8")
        checked += 1
        violations += _scan_code(src, label)

        # Search everything EXCEPT the module docstring: that is where the removal is
        # documented, and a file explaining why a helper is gone must not be reported as
        # still using it. What matters is the prompt bodies and the shipped code, both of
        # which live after the docstring.
        for helper in REMOVED_HELPERS:
            if helper in _without_module_docstring(src):
                violations.append(
                    f"{label}: references `{helper}`, which was removed as a rule violation"
                )

        # Task-text matching: only flag inside a regex literal, so a prompt sentence
        # containing the same words is not a false positive.
        low = src.lower()
        for marker in TASK_TEXT_SMELLS:
            for probe in (f'r"({marker}', f"r'({marker}", f'r"{marker}', f"r'{marker}"):
                if probe in low:
                    violations.append(
                        f"{label}: regex literal matches task wording {marker!r}"
                    )

    # BOOTSTRAP_CODE ships into the sandbox, so it is our code even though it is a string.
    sys.path.insert(0, str(LARA))
    from executor_helpers import BOOTSTRAP_CODE  # noqa: E402

    violations += _scan_code(BOOTSTRAP_CODE, "executor_helpers.py::BOOTSTRAP_CODE")

    print(f"AppWorld compliance check — {checked} agent modules + BOOTSTRAP_CODE")
    if violations:
        print(f"\n{len(violations)} VIOLATION(S):\n")
        for v in violations:
            print(f"  {v}")
        return 1
    print("\nclean — no hardcoded API call in executable code,")
    print("        no reference to a removed helper,")
    print("        no regex matching on the task instruction text.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
