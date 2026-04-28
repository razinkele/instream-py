"""v0.52.2: reproject TornionjokiExample.shp from EPSG:4326 (degrees)
to EPSG:3035 (LAEA Europe, meters).

The shipped Tornionjoki shapefile uses geographic CRS (lat/lon), but the
model's spawning module (`select_spawn_cell`) treats cell centroid
distances as METERS for the `defense_area_m` check. With centroids in
degrees, defense_area_m=1.0 (1 meter) effectively excludes every cell
within 1 degree (~46 km at 65°N), blocking nearly all redd creation
beyond the first per spawn season.

Fix: reproject to EPSG:3035 (the same projection used by example_baltic).
After reprojection:
- centroids are in meters → defense_area_m=1.0 means 1 meter (excludes
  only the same cell, allowing spawners to spread)
- cell AREA field is recalculated to true m² (was degree² before, then
  multiplied ×10000 in polygon_mesh.py giving meaningless values)
- cell suitability scores become biologically meaningful

Other WGBAST fixtures (Simojoki/Byskealven/Morrumsan) remain in
EPSG:4326. They currently pass test_latitudinal_smolt_age_gradient on
bootstrap-population fish; their tests don't probe natal recruitment
deeply enough to expose the same bug. Defer reprojection of those
fixtures until/unless their tests start failing.
"""
from pathlib import Path
import sys

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
SHP = ROOT / "tests/fixtures/example_tornionjoki/Shapefile/TornionjokiExample.shp"


def main() -> int:
    if not SHP.exists():
        print(f"missing {SHP}")
        return 1
    gdf = gpd.read_file(SHP)
    print(f"Original: CRS={gdf.crs}, n_cells={len(gdf)}")
    print(f"  bbox: {tuple(round(b, 4) for b in gdf.total_bounds)}")
    if "AREA" in gdf.columns:
        print(f"  AREA min/max: {gdf['AREA'].min():.2f} / {gdf['AREA'].max():.2f}")

    if gdf.crs and gdf.crs.to_epsg() == 3035:
        print("Already EPSG:3035 — nothing to do")
        return 0

    # Reproject geometry
    gdf_3035 = gdf.to_crs("EPSG:3035")
    print(f"\nReprojected: CRS={gdf_3035.crs}")
    print(f"  bbox: {tuple(round(b, 2) for b in gdf_3035.total_bounds)}")

    # Recalculate AREA field in m² (the polygon_mesh.py reader will
    # multiply by 10000 to convert to cm² internally — that conversion
    # only makes sense when AREA is in m², so the v0.45.0 stored values
    # in degree² × 10000 were meaningless).
    gdf_3035["AREA"] = gdf_3035.geometry.area
    print(f"  new AREA min/max: {gdf_3035['AREA'].min():.0f} / "
          f"{gdf_3035['AREA'].max():.0f} m²")

    # Save back to same path (overwrites .shp/.dbf/.shx/.prj)
    gdf_3035.to_file(SHP)
    print(f"\nWrote {SHP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
