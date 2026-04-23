"""One-shot refactor: replace `open(path, "w", ...)` with _atomic_write_csv
inside writer functions of src/salmopy/io/output.py.

Handles both csv.writer pattern and df.to_csv(path) pattern.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "src" / "salmopy" / "io" / "output.py"

text = OUTPUT.read_text(encoding="utf-8")

# Replace all `with open(path, "w", newline="") as f:` with atomic variant
text = text.replace(
    'with open(path, "w", newline="") as f:',
    'with _atomic_write_csv(path) as f:',
)

# df.to_csv(path) — wrap in atomic context
text = text.replace(
    "    df.to_csv(path)\n",
    "    with _atomic_write_csv(path) as f:\n"
    "        df.to_csv(f, index=False)\n",
)

OUTPUT.write_text(text, encoding="utf-8", newline="\n")
print("refactored")
