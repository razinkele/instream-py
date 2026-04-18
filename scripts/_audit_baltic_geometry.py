"""Audit the Baltic shapefile against real-world Curonian Lagoon + Nemunas geometry.

Prints bbox, area (UTM 34N), and centroid for each reach. Flags likely issues:
  - lagoon polygon that extends west of the Curonian Spit (into Baltic Sea)
  - river reaches clipped to bbox that cut off real segments
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd

SHP = (
    Path(__file__).resolve().parent.parent
    / "tests" / "fixtures" / "example_baltic" / "Shapefile" / "BalticExample.shp"
)

# Real-world Curonian Lagoon reference (from published sources):
# - Area: 1,584 km²
# - Bbox: approximately (20.73, 54.70, 21.40, 55.72) — N-S 90 km, E-W 8-46 km
# - Western boundary is the EAST shore of the Curonian Spit, not open sea.
# Key sentinel points that must be INSIDE the lagoon:
LAGOON_INSIDE = [
    (21.10, 55.30),  # centre
    (21.25, 55.50),  # NE
    (21.05, 55.00),  # S mid
]
# Points that must be OUTSIDE the lagoon (Baltic Sea side of the spit):
LAGOON_OUTSIDE = [
    (20.70, 55.30),  # Baltic Sea west of spit (spit is ~20.95-21.05°E)
    (20.80, 54.80),  # Baltic Sea west of Kaliningrad spit root
]

# The Curonian Spit runs N-S along longitudes ~20.95-21.05 at most latitudes.
# Any lagoon polygon whose western extent is at longitude < 20.85 likely
# includes open Baltic Sea + the spit itself.


def main() -> None:
    if not SHP.exists():
        print(f"ERROR: shapefile not found at {SHP}")
        sys.exit(1)

    gdf = gpd.read_file(str(SHP))
    print(f"Shapefile: {len(gdf)} cells, CRS = {gdf.crs}")
    print(f"Columns: {list(gdf.columns)}")
    print()

    gdf_wgs = gdf.to_crs("EPSG:4326")
    gdf_utm = gdf.to_crs("EPSG:32634")

    print(f"{'Reach':<18} {'cells':>5}  {'area (km²)':>10}  bbox (WGS84 lon/lat)")
    print("-" * 90)
    for reach in gdf["REACH_NAME"].unique():
        mask = gdf["REACH_NAME"] == reach
        area_km2 = gdf_utm.loc[mask].geometry.area.sum() / 1e6
        bounds = gdf_wgs.loc[mask].total_bounds  # (minx, miny, maxx, maxy)
        print(
            f"{reach:<18} {mask.sum():>5}  {area_km2:>10.1f}  "
            f"lon [{bounds[0]:.3f}, {bounds[2]:.3f}] "
            f"lat [{bounds[1]:.3f}, {bounds[3]:.3f}]"
        )

    print()
    print("=== Curonian Lagoon polygon audit ===")
    from shapely.geometry import Point
    from shapely.ops import unary_union

    lagoon_cells = gdf_wgs[gdf_wgs["REACH_NAME"] == "CuronianLagoon"]
    if len(lagoon_cells) == 0:
        print("  no CuronianLagoon reach found")
        return

    lagoon_poly = unary_union(lagoon_cells.geometry.values)
    minx, miny, maxx, maxy = lagoon_poly.bounds
    print(f"  bbox: lon [{minx:.3f}, {maxx:.3f}]  lat [{miny:.3f}, {maxy:.3f}]")
    print(f"  E-W span at centre lat: approx {(maxx-minx)*111*0.57:.1f} km")
    print(f"  N-S span: approx {(maxy-miny)*111:.1f} km")

    print()
    print("  Sentinel checks:")
    for lon, lat in LAGOON_INSIDE:
        contained = lagoon_poly.contains(Point(lon, lat))
        status = "OK (inside)" if contained else "FAIL (should be inside)"
        print(f"    ({lon}, {lat}) inside lagoon? -> {status}")
    for lon, lat in LAGOON_OUTSIDE:
        contained = lagoon_poly.contains(Point(lon, lat))
        status = "FAIL (should be OUTSIDE — this is Baltic Sea!)" if contained else "OK (outside)"
        print(f"    ({lon}, {lat}) inside lagoon? -> {status}")

    print()
    print("  West-extent check:")
    if minx < 20.85:
        print(f"    FAIL: lagoon west edge at lon={minx:.3f} extends west of the Curonian Spit (~20.95).")
        print("          Polygon likely includes open Baltic Sea and the spit itself.")
    else:
        print(f"    OK: lagoon west edge at lon={minx:.3f} — stays east of the spit.")


if __name__ == "__main__":
    main()
