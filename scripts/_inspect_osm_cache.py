"""Quick inspection of the _osm_cache contents."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tests" / "fixtures" / "_osm_cache"

for p in sorted(CACHE.glob("*.json")):
    data = json.loads(p.read_text(encoding="utf-8"))
    names = sorted({w.get("name", "") for w in data})
    total_pts = sum(len(w["geometry"]["coordinates"]) for w in data)
    print(f"{p.stem}: {len(data)} ways, {total_pts} coords, names={names}")
