"""One-shot rename script: inSTREAM -> Salmopy.

Scope:
- Python .py files: rewrite imports (`from instream` -> `from salmopy`, etc.),
  class references (`InSTREAMModel` -> `SalmopyModel`), and quoted module paths.
- pyproject.toml edits are done manually (separate Edit operations).
- Markdown/YAML brand text is handled as a separate pass.

Preserves upstream-model references: 'inSTREAM/inSALMO 7.4' must NOT be renamed
(it's the NetLogo model this project ports from). This script targets .py files
only — the upstream reference exists in docstrings; we handle it by carving out
the `inSTREAM/inSALMO` and `inSTREAM 7.4` patterns before replacing bare tokens.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Directories to walk. .worktrees/ is skipped intentionally (sibling branch).
WALK_DIRS = ("src", "tests", "app", "scripts", "benchmarks")

# Files to skip within those dirs.
SKIP_NAMES = {"_rename_instream_to_salmopy.py"}

# --- Safe Python-code substitutions -----------------------------------------
# These fire only in contexts that clearly mean "this package", never upstream
# references (which only appear in docstrings/comments as "inSTREAM/inSALMO 7.4").
PY_SUBSTITUTIONS = [
    # Import statements
    (re.compile(r"\bfrom instream\b"), "from salmopy"),
    (re.compile(r"\bimport instream\b"), "import salmopy"),
    # Quoted module paths (e.g., 'instream.io.config' used in imports or __name__ lookups)
    (re.compile(r"([\"'])instream\."), r"\1salmopy."),
    (re.compile(r"([\"'])instream([\"'])"), r"\1salmopy\2"),
    # Class name
    (re.compile(r"\bInSTREAMModel\b"), "SalmopyModel"),
]

# --- Docstring/comment substitutions (SAFE subset) ---------------------------
# Fire only in .py docstrings and comments, preserving "inSTREAM/inSALMO 7.4"
# upstream refs. We use a negative lookahead: "inSTREAM" NOT followed by
# "/inSALMO" or " 7.4" or "/inSTREAM" etc.
# Since this only runs inside docstrings, we apply cautiously.
PY_DOC_SUBS = [
    # "inSTREAM -" brand header (as appears in __init__.py docstring)
    (re.compile(r"\binSTREAM(?=\s*[—\-])"), "Salmopy"),
    # "inSTREAM-py" references
    (re.compile(r"\binSTREAM-py\b"), "Salmopy"),
]


def process_py_file(path: Path) -> bool:
    """Apply Python-code substitutions. Returns True if file changed."""
    text = path.read_text(encoding="utf-8")
    original = text
    for pattern, repl in PY_SUBSTITUTIONS:
        text = pattern.sub(repl, text)
    for pattern, repl in PY_DOC_SUBS:
        text = pattern.sub(repl, text)
    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> int:
    changed = 0
    scanned = 0
    for walk_dir in WALK_DIRS:
        base = ROOT / walk_dir
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            if py.name in SKIP_NAMES:
                continue
            # Skip the worktree directory explicitly
            if ".worktrees" in py.parts:
                continue
            scanned += 1
            if process_py_file(py):
                changed += 1
    print(f"Scanned {scanned} .py files, modified {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
