"""v0.46 Task A2: Edit Model panel split-by-line feature.

Tests the side-classification math directly (no Shiny session): given a
GeoDataFrame of cells and a LineString, partition cells into north/south
of the line and verify both partitions are non-empty for a meaningful
split.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def _classify_side(centroid: Point, line: LineString) -> str:
    """Classify a centroid as 'north' or 'south' of a line.

    Iteration-3 fix: when nearest_dist == line.length, `min(nearest_dist + 1e-6, line.length)`
    pins `ahead` to the same point as `nearest_pt`, making dx=dy=0 and the
    cross product identically 0 (everything classifies as 'north' by the
    >= tiebreak). Use a 'behind' fallback at the line endpoint so we always
    have a non-zero tangent vector.
    """
    L = line.length
    nearest_dist = line.project(centroid)
    nearest_pt = line.interpolate(nearest_dist)
    eps = max(L * 1e-6, 1e-9)
    if nearest_dist + eps <= L:
        tangent_pt = line.interpolate(nearest_dist + eps)
        base = nearest_pt
    else:
        prev_pt = line.interpolate(max(nearest_dist - eps, 0.0))
        base = prev_pt
        tangent_pt = nearest_pt
    dx = tangent_pt.x - base.x
    dy = tangent_pt.y - base.y
    cross = (centroid.x - base.x) * dy - (centroid.y - base.y) * dx
    return "north" if cross >= 0 else "south"


def test_horizontal_line_splits_grid_into_two_halves():
    cells = []
    for x in range(4):
        for y in range(4):
            cells.append(Polygon([
                (x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)
            ]))
    gdf = gpd.GeoDataFrame(geometry=cells, crs="EPSG:4326")
    line = LineString([(0, 2), (4, 2)])
    sides = [_classify_side(g.centroid, line) for g in gdf.geometry]
    n_north = sum(1 for s in sides if s == "north")
    n_south = len(sides) - n_north
    assert {n_north, n_south} == {8, 8}


def test_vertical_line_splits_grid_into_two_halves():
    cells = []
    for x in range(4):
        for y in range(4):
            cells.append(Polygon([
                (x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)
            ]))
    gdf = gpd.GeoDataFrame(geometry=cells, crs="EPSG:4326")
    line = LineString([(2, 0), (2, 4)])
    sides = [_classify_side(g.centroid, line) for g in gdf.geometry]
    n_north = sum(1 for s in sides if s == "north")
    n_south = len(sides) - n_north
    assert {n_north, n_south} == {8, 8}


def test_diagonal_line_classifies_off_axis_centroids():
    # Centroids must be OFF the diagonal y=x or the cross product is 0
    # and both fall on the >= tiebreak side. Plan's original polygons had
    # centroids (0.5,0.5) and (2.5,2.5) — both on the line.
    cells = [
        Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),  # centroid (1.5,0.5) — below y=x
        Polygon([(0, 1), (1, 1), (1, 2), (0, 2)]),  # centroid (0.5,1.5) — above y=x
    ]
    gdf = gpd.GeoDataFrame(geometry=cells, crs="EPSG:4326")
    line = LineString([(0, 0), (4, 4)])
    sides = [_classify_side(g.centroid, line) for g in gdf.geometry]
    assert sides[0] != sides[1]
