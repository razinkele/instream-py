"""Invariant: deck.gl props in app/ must be camelCase.

Per memory/feedback_deckgl_camelcase.md: deck.gl's JS side silently ignores
unrecognized (snake_case) keys. A regression here produces an invisible
layer with no runtime error. Scans app/ for the known forbidden keys.
"""
import re
from pathlib import Path

FORBIDDEN_KEYS = (
    "get_fill_color",
    "get_line_color",
    "get_line_width",
    "get_position",
    "get_radius",
    "get_elevation",
    "get_text",
    "get_icon",
    "get_source_position",
    "get_target_position",
)


def test_no_snake_case_deckgl_props_in_app():
    app_dir = Path(__file__).parent.parent / "app"
    pattern = re.compile(rf"\b({'|'.join(FORBIDDEN_KEYS)})\s*=")
    offenders = []
    for py in app_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # Ignore lines that are comments about the forbidden keys
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            if pattern.search(line):
                offenders.append(
                    f"{py.relative_to(app_dir.parent)}:{lineno}: {stripped}"
                )
    assert not offenders, (
        "Found snake_case deck.gl props in app/ (must be camelCase — see "
        "memory/feedback_deckgl_camelcase.md):\n" + "\n".join(offenders)
    )
