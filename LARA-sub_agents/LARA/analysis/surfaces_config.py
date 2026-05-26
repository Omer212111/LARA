"""
LARA — Surface registry

Maps fix-mappings surface keys to (file_path, marker_label). The apply-and-measure
wrapper uses this to extract the editable region of a target file by name.

Each entry:
  - surface_key   : matches fix_mappings.json's "surface" field
  - file_path     : project-relative path to the file to edit
  - marker_label  : the label appearing in '=== SURFACE: <label> === BEGIN/END' sentinels
  - description   : short human note about what's in this region

When a fix's surface points to a surface_key not in this table, the wrapper
refuses to apply (and prints a helpful "you need to mark this region first").
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LARA_ROOT = Path(__file__).parent.parent


@dataclass(frozen=True)
class Surface:
    surface_key: str
    file_path: Path
    marker_label: str
    description: str


# Only entries with markers actually in place are listed here. Add more as we
# mark more files (the wrapper will refuse to apply to unmarked surfaces).

SURFACES: dict[str, Surface] = {
    "explorer_prompt": Surface(
        surface_key="explorer_prompt",
        file_path=LARA_ROOT / "prompts.py",
        marker_label="explorer_prompt:semantic_api_selection",
        description=(
            "The SEMANTIC API SELECTION block of the Explorer system prompt. "
            "Most plan-time fixes (group-lookup, time-window, venmo patterns) land here."
        ),
    ),
    "venmo_specialist": Surface(
        surface_key="venmo_specialist",
        file_path=LARA_ROOT / "app_agents" / "venmo.py",
        marker_label="venmo_specialist:prompt",
        description=(
            "Venmo specialist system prompt. Transaction vs payment-request disambiguation, "
            "API names, field names, pagination rules, task patterns."
        ),
    ),
    "phone_specialist": Surface(
        surface_key="phone_specialist",
        file_path=LARA_ROOT / "app_agents" / "phone.py",
        marker_label="phone_specialist:prompt",
        description=(
            "Phone specialist system prompt. Contact/relationship resolution, "
            "sandbox clock, text/voice messages, alarms."
        ),
    ),
}


def get_surface(key: str) -> Surface | None:
    return SURFACES.get(key)


def list_surfaces() -> list[Surface]:
    return list(SURFACES.values())
