"""Verify Sysa-Atmata and BalticCoast-strait connectivity on the cell grid.

A "connected" pair means their cells have at least one pair within one cell
diameter (~200-500 m). If the nearest inter-reach cell distance exceeds the
cell size, the reaches are visually disconnected on the map.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.strtree import STRtree

SHP = (
    Path(__file__).resolve().parent.parent
    / "tests" / "fixtures" / "example_baltic" / "Shapefile" / "BalticExample.shp"
)


def nearest_distance_km(a_geoms, b_geoms) -> float:
    """Minimum distance in kilometres between any geom in a_geoms and b_geoms."""
    tree = STRtree(b_geoms)
    best = float("inf")
    for g in a_geoms:
        idx = tree.nearest(g)
        nb = b_geoms[idx]
        d = g.distance(nb)
        if d < best:
            best = d
    # UTM coords → metres; convert to km.
    return best / 1000.0


def main() -> None:
    gdf = gpd.read_file(str(SHP)).to_crs("EPSG:32634")

    reaches = {}
    for r in gdf["REACH_NAME"].unique():
        reaches[r] = list(gdf.loc[gdf["REACH_NAME"] == r].geometry.values)

    pairs = [
        ("Atmata", "Sysa"),
        ("Atmata", "Nemunas"),
        ("Atmata", "CuronianLagoon"),
        ("Sysa", "Nemunas"),
        ("CuronianLagoon", "BalticCoast"),
        ("BalticCoast", "Atmata"),
    ]
    print(f"{'pair':<30} {'nearest_km':>12}  verdict")
    print("-" * 60)
    for a, b in pairs:
        if a not in reaches or b not in reaches:
            print(f"{a} ↔ {b}: one reach missing")
            continue
        d_km = nearest_distance_km(reaches[a], reaches[b])
        verdict = "CONNECTED" if d_km < 0.5 else "gap"
        print(f"{a:>14} ↔ {b:<13} {d_km:>12.3f}  {verdict}")


if __name__ == "__main__":
    main()
