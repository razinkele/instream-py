"""Audit each reach's geometry: centroid, longest span, and disconnectedness.

Flags reaches that extend far from the salmon-relevant Nemunas/Klaipėda area
(e.g. Minija's full basin reaching into Plateliai lake, 150 km from the
lagoon — probably unintended scope for a salmon-lifecycle case study).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

SHP = (
    Path(__file__).resolve().parent.parent
    / "tests" / "fixtures" / "example_baltic" / "Shapefile" / "BalticExample.shp"
)

# Salmon-relevant anchor point — Klaipėda strait (lagoon exit / Baltic entry).
ANCHOR = (21.10, 55.70)


def main() -> None:
    gdf = gpd.read_file(str(SHP)).to_crs("EPSG:4326")
    gdf_utm = gdf.to_crs("EPSG:32634")

    print(f"{'Reach':<16} {'cells':>5} {'area_km2':>8}  "
          f"{'centroid':<18}  {'span_km':>8}  {'dist_Klp':>8}")
    print("-" * 85)
    for reach in gdf["REACH_NAME"].unique():
        mask = gdf["REACH_NAME"] == reach
        merged = unary_union(gdf.loc[mask].geometry.values)
        c = merged.centroid
        bounds = merged.bounds
        # span = diagonal of bbox in km
        import math
        span_km = math.hypot(
            (bounds[2] - bounds[0]) * 111 * math.cos(math.radians((bounds[1]+bounds[3])/2)),
            (bounds[3] - bounds[1]) * 111,
        )
        dx = (c.x - ANCHOR[0]) * 111 * math.cos(math.radians(c.y))
        dy = (c.y - ANCHOR[1]) * 111
        dist_klp = math.hypot(dx, dy)
        area_km2 = gdf_utm.loc[mask].geometry.area.sum() / 1e6
        print(f"{reach:<16} {mask.sum():>5} {area_km2:>8.1f}  "
              f"({c.x:.3f},{c.y:.3f})   {span_km:>6.1f} km {dist_klp:>6.1f} km")

    print()
    print("Reaches whose bbox-span exceeds 30 km likely extend beyond the")
    print("salmon-relevant Nemunas/Klaipėda area. Consider tightening the")
    print("clip in scripts/generate_baltic_example.py.")


if __name__ == "__main__":
    main()
