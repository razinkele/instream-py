"""Verify pyosmium can handle multiple PBFs in sequence, and Kaliningrad PBF exists."""
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from modules.create_model_osm import ensure_pbf, GEOFABRIK_REGIONS  # noqa: E402

assert "kaliningrad" in GEOFABRIK_REGIONS, "kaliningrad region must be registered"
print("Geofabrik path:", GEOFABRIK_REGIONS["kaliningrad"])

for country in ("lithuania", "kaliningrad"):
    pbf = ensure_pbf(country)
    print(f"{country}: {pbf} ({pbf.stat().st_size / 1_000_000:.1f} MB)")

import osmium


class CountingHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.n = 0

    def way(self, w):
        self.n += 1


h = CountingHandler()
h.apply_file(str(ensure_pbf("lithuania")))
lt = h.n
h.apply_file(str(ensure_pbf("kaliningrad")))
total = h.n
print(f"Lithuania ways: {lt}, +Kaliningrad ways: {total - lt}, total: {total}")

print()
print("--- Task 3.3: does the merged-PBF fetch assemble the Curonian Lagoon? ---")
from modules.create_model_osm import query_water_bodies  # noqa: E402
from shapely.geometry import Point  # noqa: E402

bbox = (20.50, 54.40, 22.20, 55.95)  # wide enough to enclose the lagoon
wb = query_water_bodies(("lithuania", "kaliningrad"), bbox)
print(f"Total water polygons in merged bbox: {len(wb)}")
lagoon_seed = Point(21.05, 55.20)
hits = wb[wb.geometry.contains(lagoon_seed)]
print(f"Polygons containing lagoon seed (21.05, 55.20): {len(hits)}")
if len(hits) > 0:
    biggest_km2 = hits.to_crs("EPSG:32634").geometry.area.max() / 1e6
    print(f"  Largest containing polygon: {biggest_km2:.0f} km² (real ~1,584)")
else:
    print("  Lagoon relation still does NOT assemble — fall back stays primary")
