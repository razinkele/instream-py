"""Remove per-function sys.path.insert and sys imports from
generate_analytical_reference.py, adding a single module-top
import-check for salmopy."""
import re
from pathlib import Path

p = Path(__file__).parent / "generate_analytical_reference.py"
text = p.read_text(encoding="utf-8")

# Remove all `    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))`
text = re.sub(
    r'    sys\.path\.insert\(0,\s*str\(Path\(__file__\)\.parent\.parent / "src"\)\)\n',
    '',
    text,
)

# Insert a top-level import check after existing imports if not present.
guard = (
    'try:\n'
    '    import salmopy  # noqa: F401\n'
    'except ImportError as _exc:\n'
    '    raise SystemExit(\n'
    '        f"salmopy not importable: {_exc}\\n"\n'
    '        "This script requires salmopy to be installed in the active "\n'
    '        "environment (e.g. `micromamba run -n shiny python scripts/generate_analytical_reference.py`)."\n'
    '    )\n'
)

if "import salmopy  # noqa: F401" not in text:
    # Insert after the last top-level import line
    idx = text.find("\n\n", text.find("import "))
    if idx > 0:
        text = text[:idx + 1] + "\n" + guard + "\n" + text[idx + 1:]

p.write_text(text, encoding="utf-8", newline="\n")
print("done")
