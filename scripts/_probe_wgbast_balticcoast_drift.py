"""Probe: where ARE the BalticCoast cells in WGBAST fixtures?

The v0.56.0 connectivity check flagged Simojoki/Tornionjoki BalticCoast
182-257 km from configured neighbors. Real river mouths are at 65.62°N
(Simo) and 65.88°N (Tornio). If BalticCoast cells are at the head of the
Bothnian Bay near those mouths, the gap should be <10 km. 257 km is
suspicious — could be a generation bug or a Marine Regions polygon
choice issue.
"""
import geopandas as gpd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

for fx in ("example_simojoki", "example_tornionjoki"):
    shp = ROOT / "tests/fixtures" / fx / "Shapefile"
    shp_files = list(shp.glob("*.shp"))
    if not shp_files:
        print(f"{fx}: no shapefile")
        continue
    g = gpd.read_file(shp_files[0])
    print(f"\n=== {fx} ===")
    print(f"CRS: {g.crs}")
    g_wgs = g.to_crs("EPSG:4326")
    for r in sorted(g["REACH_NAME"].unique()):
        sub = g_wgs[g_wgs["REACH_NAME"] == r]
        b = sub.total_bounds
        cen_lon = (b[0] + b[2]) / 2
        cen_lat = (b[1] + b[3]) / 2
        print(f"  {r:>15}: {len(sub):>4} cells, "
              f"WGS84 bbox [{b[0]:.3f}, {b[1]:.3f}] -> [{b[2]:.3f}, {b[3]:.3f}], "
              f"centroid (lon={cen_lon:.3f}, lat={cen_lat:.3f})")
