"""Probe OSM for the southern Nemunas-Delta branch (Gilija / Matrosovka)."""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from modules.create_model_osm import query_waterways  # noqa: E402

ww = query_waterways(("lithuania", "kaliningrad"), (20.50, 54.40, 22.20, 55.95))
print(f"total waterways in merged bbox: {len(ww)}")
for n in ("Gilija", "Матросовка", "Matrosovka"):
    hits = (ww["nameText"] == n).sum()
    print(f"  {n!r}: {hits} features")

# Top 15 named waterways containing 'Gilij' or 'Matros' or 'Mатрос' (case-insensitive)
match = ww[
    ww["nameText"].str.contains("Gilij|Matros|Матрос|Kurš", case=False, na=False, regex=True)
]
print(f"\nContain-match on Gilij/Matros/Kurš ({len(match)} features):")
for _, row in match.head(20).iterrows():
    print(f"  {row['nameText']!r}  waterway={row.get('waterway', '?')!r}")
