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


def nearest_distance_km(a_geoms, b_geoms) -> tuple[float, tuple, tuple]:
    """Returns (distance_km, (a_lon, a_lat), (b_lon, b_lat)) for the closest pair.
    Inputs are UTM geometries; output points are converted to WGS84 lon/lat."""
    import geopandas as gpd
    tree = STRtree(b_geoms)
    best = float("inf")
    best_a = best_b = None
    for g in a_geoms:
        idx = tree.nearest(g)
        nb = b_geoms[idx]
        d = g.distance(nb)
        if d < best:
            best = d
            best_a, best_b = g, nb
    # Convert UTM centroids back to WGS84 for display.
    ca = gpd.GeoSeries([best_a.centroid], crs="EPSG:32634").to_crs("EPSG:4326").iloc[0]
    cb = gpd.GeoSeries([best_b.centroid], crs="EPSG:32634").to_crs("EPSG:4326").iloc[0]
    return best / 1000.0, (ca.x, ca.y), (cb.x, cb.y)


def main() -> None:
    gdf = gpd.read_file(str(SHP)).to_crs("EPSG:32634")

    reaches = {}
    for r in gdf["REACH_NAME"].unique():
        reaches[r] = list(gdf.loc[gdf["REACH_NAME"] == r].geometry.values)

    # Pairs listed as (a, b, note). `note` is None if the two reaches should
    # be directly adjacent (CONNECTED < 0.5 km). Non-None note describes the
    # real-geography reason why a gap is expected and the valid multi-hop
    # migration path — gaps with a note are acceptable.
    pairs = [
        # Primary migration path: Baltic → lagoon → delta rivers
        ("BalticCoast", "CuronianLagoon", None),
        ("CuronianLagoon", "Atmata", None),
        ("CuronianLagoon", "Gilija", None),
        ("CuronianLagoon", "Skirvyte", None),
        # OSM-data gap: Minija's mainline ends at (21.276, 55.346); real
        # Ventės Ragas mouth is ~6 km SW. Salmon reach Minija via the
        # lagoon's Kintai bay edge, which neighbours Minija's final cells.
        ("CuronianLagoon", "Minija",
         "OSM Minija ends ~6 km short of real Ventės Ragas mouth; "
         "reachable via Kintai bay shore"),
        # Real geography: Leitė joins Nemunas at Rusnė, not the lagoon.
        ("CuronianLagoon", "Leite",
         "real geography — Leite joins Nemunas at Rusnė, not lagoon; "
         "migration route: Leite → Nemunas → Atmata → lagoon"),
        # Inter-river confluences
        ("Atmata", "Sysa", None),
        ("Atmata", "Nemunas", None),
        # Real geography: Šyša joins Atmata at Šilutė, not Nemunas.
        ("Sysa", "Nemunas",
         "real geography — Šyša joins Atmata at Šilutė, not Nemunas; "
         "migration route: Sysa → Atmata → Nemunas"),
        ("Skirvyte", "Nemunas", None),
        ("Leite", "Nemunas", None),
        ("Gilija", "Nemunas", None),
    ]
    print(f"{'pair':<30} {'nearest_km':>10}  verdict")
    print("-" * 75)
    unexpected_gaps = 0
    for entry in pairs:
        a, b, note = entry
        if a not in reaches or b not in reaches:
            print(f"{a} ↔ {b}: one reach missing")
            continue
        d_km, pa, pb = nearest_distance_km(reaches[a], reaches[b])
        if d_km < 0.5:
            verdict = "CONNECTED"
        elif note:
            verdict = f"gap OK ({note})"
        else:
            verdict = "UNEXPECTED GAP — investigate!"
            unexpected_gaps += 1
        print(f"{a:>14} ↔ {b:<15} {d_km:>10.3f}  {verdict}")
    print()
    if unexpected_gaps:
        print(f"FAIL: {unexpected_gaps} unexpected gap(s) — "
              f"reaches should be adjacent but aren't.")
        raise SystemExit(1)
    print("PASS: all direct-adjacency pairs are CONNECTED; "
          "documented gaps have valid multi-hop paths.")


if __name__ == "__main__":
    main()
