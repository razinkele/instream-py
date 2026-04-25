"""Diagnose why Tornionjoki only keeps 860 cells out of 9072 OSM polygons.

Reports:
  - Total raw polygon count and per-polygon area distribution
  - Whether the BFS terminates early due to MAX_CONNECTED_POLYS cap
  - How many polygons sit in the bbox but are NOT centerline-connected
  - Bounding box of the kept connected component vs the bbox of all polys
  - Suggested actions (raise cap? lower tolerance? rethink BFS seed?)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _generate_wgbast_physical_domains import (
    OSM_CACHE,
    POLY_CONNECT_TOL_DEG,
    MAX_CONNECTED_POLYS,
    RIVERS,
    _load_osm_ways,
)


def diag(river_short_name: str):
    river = next(r for r in RIVERS if r.short_name == river_short_name)
    print(f"\n=== {river.river_name} ({river.short_name}) ===")
    print(f"Mouth waypoint: {river.waypoints[0]}")
    print(f"Source waypoint: {river.waypoints[-1]}")
    print(f"POLY_CONNECT_TOL_DEG = {POLY_CONNECT_TOL_DEG}  "
          f"(~{POLY_CONNECT_TOL_DEG*111000:.0f} m)")
    print(f"MAX_CONNECTED_POLYS = {MAX_CONNECTED_POLYS}")

    poly_cache = OSM_CACHE / f"{river.short_name}_polygons.json"
    data = json.loads(poly_cache.read_text(encoding="utf-8"))
    raw_polys = []
    for item in data:
        try:
            poly = shape(item["geometry"])
        except Exception:
            continue
        if poly.is_valid and not poly.is_empty and poly.geom_type in ("Polygon", "MultiPolygon"):
            raw_polys.append(poly)
    print(f"\nTotal raw polygons: {len(raw_polys)}")

    # Polygon area histogram (in deg² since CRS is WGS84; rough but enough)
    areas = sorted(p.area for p in raw_polys)
    print(f"  area percentiles (deg²): "
          f"p10={areas[len(areas)//10]:.2e} "
          f"p50={areas[len(areas)//2]:.2e} "
          f"p90={areas[int(len(areas)*0.9)]:.2e} "
          f"max={areas[-1]:.2e}")

    # Centerline
    ways = _load_osm_ways(river)
    if ways is None:
        print("  no OSM line ways")
        return
    centerline_union = unary_union(ways)
    print(f"  centerline ways: {len(ways)}, "
          f"total length {centerline_union.length:.4f} deg "
          f"(~{centerline_union.length*111:.0f} km)")
    print(f"  centerline geom_type: {centerline_union.geom_type}")
    print(f"  centerline bbox: {centerline_union.bounds}")

    # Replicate BFS but instrument it
    buffered = [p.buffer(POLY_CONNECT_TOL_DEG) for p in raw_polys]
    from shapely.strtree import STRtree
    tree = STRtree(buffered)
    n = len(raw_polys)
    visited = [False] * n
    queue = []
    seed_buffered_line = centerline_union.buffer(POLY_CONNECT_TOL_DEG)
    n_seed = 0
    for i in tree.query(seed_buffered_line):
        if seed_buffered_line.intersects(buffered[i]):
            if not visited[i]:
                visited[i] = True
                queue.append(i)
                n_seed += 1
    print(f"  seed polygons (touch centerline): {n_seed}")

    # BFS, tracking when we'd hit the cap
    hit_cap = False
    bfs_iters = 0
    while queue and sum(visited) < MAX_CONNECTED_POLYS:
        i = queue.pop()
        bfs_iters += 1
        for j in tree.query(buffered[i]):
            if visited[j]:
                continue
            if buffered[i].intersects(buffered[j]):
                visited[j] = True
                queue.append(j)
    if queue:
        hit_cap = True
    kept = sum(visited)
    print(f"  BFS iterations: {bfs_iters}; kept {kept}/{n} polygons; "
          f"hit cap: {hit_cap}; queue still had {len(queue)} unprocessed")

    # Geographic spread
    if kept > 0:
        kept_polys = [raw_polys[i] for i, v in enumerate(visited) if v]
        union = unary_union(kept_polys)
        print(f"  kept-component bbox: {union.bounds}")
    all_union = unary_union(raw_polys)
    print(f"  all-polys bbox:      {all_union.bounds}")

    # Diagnose: what fraction of unkept polygons are within X of centerline?
    unkept = [raw_polys[i] for i, v in enumerate(visited) if not v]
    print(f"  unkept polygons: {len(unkept)}")
    if unkept and kept > 0:
        # Distances from centerline (sample first 200 if many)
        sample = unkept[:200]
        dists_deg = [centerline_union.distance(p) for p in sample]
        sample_len = len(sample)
        within_50m = sum(1 for d in dists_deg if d < 0.0005)
        within_500m = sum(1 for d in dists_deg if d < 0.005)
        within_5km = sum(1 for d in dists_deg if d < 0.05)
        print(f"  unkept-from-centerline distance (sample of {sample_len}):")
        print(f"    <50 m:  {within_50m}")
        print(f"    <500 m: {within_500m}")
        print(f"    <5 km:  {within_5km}")


if __name__ == "__main__":
    for river in ["example_tornionjoki", "example_simojoki",
                  "example_byskealven", "example_morrumsan"]:
        diag(river)
