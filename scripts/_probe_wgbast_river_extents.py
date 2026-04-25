"""Throwaway probe: inspect the 4 WGBAST river fixtures to understand what's there."""
import sys

# UTF-8 stdout/stderr — non-ASCII reach names (Mörrumsån, älv, etc.)
# must not crash on Windows cp1252 default. Setting via os.environ from
# inside Python is too late; reconfigure() is the supported API.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]

RIVERS = ["example_tornionjoki", "example_simojoki", "example_byskealven", "example_morrumsan"]

print(f"{'river':<25} {'reaches':<70} {'cells':>6} {'lon range':<25} {'lat range':<25}")
print("-" * 130)
for r in RIVERS:
    shp_dir = ROOT / "tests" / "fixtures" / r / "Shapefile"
    shps = list(shp_dir.glob("*.shp"))
    if not shps:
        print(f"{r:<25} <no shapefile>")
        continue
    gdf = gpd.read_file(shps[0])
    reach_col = "REACH_NAME" if "REACH_NAME" in gdf.columns else "reach_name"
    reaches = gdf.groupby(reach_col).size().to_dict()
    reaches_str = ", ".join(f"{k}={v}" for k, v in sorted(reaches.items()))
    bx = gdf.total_bounds
    lon_r = f"{bx[0]:.3f}..{bx[2]:.3f}"
    lat_r = f"{bx[1]:.3f}..{bx[3]:.3f}"
    print(f"{r:<25} {reaches_str:<70} {len(gdf):>6} {lon_r:<25} {lat_r:<25}")
print()

# Also report OSM cache file sizes / lengths (line + polygon)
print("OSM caches:")
print(f"{'river':<25} {'lines.json':<15} {'polygons.json':<15}")
print("-" * 60)
cache_dir = ROOT / "tests" / "fixtures" / "_osm_cache"
for r in RIVERS:
    line_file = cache_dir / f"{r}.json"
    poly_file = cache_dir / f"{r}_polygons.json"
    line_info = "missing"
    poly_info = "missing"
    if line_file.exists():
        d = json.loads(line_file.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            line_info = f"{len(d.get('elements', []))} elem"
        else:
            line_info = f"{len(d)} top"
    if poly_file.exists():
        d = json.loads(poly_file.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            poly_info = f"{len(d.get('elements', []))} elem"
        else:
            poly_info = f"{len(d)} top"
    print(f"{r:<25} {line_info:<15} {poly_info:<15}")
