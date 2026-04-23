"""Rename inSTREAM references in plan markdown files."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
plans = [
    "docs/superpowers/plans/2026-04-23-post-review-fixes-roadmap.md",
    "docs/superpowers/plans/2026-04-23-phase1-critical-correctness.md",
    "docs/superpowers/plans/2026-04-23-phase2-scientific-hardening.md",
]
changes = 0
for p in plans:
    path = ROOT / p
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace("src/instream/", "src/salmopy/")
    text = re.sub(r"\bfrom instream\b", "from salmopy", text)
    text = re.sub(r"\bimport instream\b", "import salmopy", text)
    text = re.sub(r"\binstream\.(?=[a-z_])", "salmopy.", text)
    text = re.sub(r"\bInSTREAMModel\b", "SalmopyModel", text)
    text = text.replace("instream[calibration]", "salmopy[calibration]")
    text = text.replace("instream[numba]", "salmopy[numba]")
    text = text.replace("instream[jax]", "salmopy[jax]")
    text = text.replace("instream[dev]", "salmopy[dev]")
    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        changes += 1
        print(f"updated {p}")
print(f"Total plan files updated: {changes}")
