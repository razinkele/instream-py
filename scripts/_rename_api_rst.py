"""One-shot: rename instream.* -> salmopy.* in docs/source/api.rst."""
from pathlib import Path

p = Path(__file__).parent.parent / "docs" / "source" / "api.rst"
text = p.read_text(encoding="utf-8")
text = text.replace("instream.", "salmopy.")
p.write_text(text, encoding="utf-8", newline="\n")
print("api.rst updated")
