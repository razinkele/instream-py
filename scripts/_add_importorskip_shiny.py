"""One-shot: add pytest.importorskip('shiny') to shiny-dependent tests
so a clean CI install without [frontend] can collect + skip them."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

FILES = [
    "tests/test_create_model_export.py",
    "tests/test_spatial_redds_layer.py",
    "tests/test_create_model_osm.py",
    "tests/test_create_model_grid.py",
    "tests/test_bathymetry.py",
    "tests/test_create_model.py",
    "tests/test_dashboard.py",
    "tests/test_app_smoke.py",
]

GUARD = 'pytest.importorskip("shiny")\n'

for p in FILES:
    path = ROOT / p
    if not path.exists():
        print(f"SKIP {p} (not found)")
        continue
    text = path.read_text(encoding="utf-8")
    if "pytest.importorskip(\"shiny\")" in text:
        print(f"SKIP {p} (already has guard)")
        continue
    # Ensure pytest is imported
    if "import pytest" not in text:
        # Insert import pytest near the top, after the docstring or first
        # import block.
        m = re.search(r'((?:^from .+\n|^import .+\n)+)', text, re.MULTILINE)
        if m:
            insert_at = m.end()
            text = text[:insert_at] + "import pytest\n" + text[insert_at:]
        else:
            text = "import pytest\n" + text
    # Add the guard right after the import block
    m = re.search(r'((?:^from .+\n|^import .+\n)+)\n', text, re.MULTILINE)
    if m:
        insert_at = m.end()
        text = text[:insert_at] + GUARD + "\n" + text[insert_at:]
    else:
        text = text + "\n" + GUARD
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"updated {p}")
