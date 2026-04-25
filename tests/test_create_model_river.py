"""Unit tests for app/modules/create_model_river.py.

Pure-Python tests on synthetic geometries.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from shapely.geometry import LineString, Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_filter_keeps_polygons_touching_centerline():
    """Three polygons; one is on the centerline, one touches it, one is
    far away. The far one is dropped; the touching one is kept."""
    from modules.create_model_river import filter_polygons_by_centerline_connectivity

    centerline = [LineString([(0, 0), (10, 0)])]
    on_centerline = Polygon([(0, -0.5), (10, -0.5), (10, 0.5), (0, 0.5)])
    near_centerline = Polygon([(2, 0.5), (4, 0.5), (4, 1.5), (2, 1.5)])  # touches via buffer
    far_away = Polygon([(50, 50), (52, 50), (52, 52), (50, 52)])

    kept = filter_polygons_by_centerline_connectivity(
        centerline=centerline,
        polygons=[on_centerline, near_centerline, far_away],
        tolerance_deg=0.001,  # ~110m
        max_polys=100,
    )
    kept_set = {id(p) for p in kept}
    assert id(on_centerline) in kept_set, "on-centerline polygon dropped"
    assert id(far_away) not in kept_set, "far polygon was kept"


def test_filter_caps_at_max_polys():
    """If the connected component is huge, return at most max_polys.
    Test design: only ONE polygon touches the centerline directly; the
    rest chain via mutual buffer overlap, forcing the cap to fire
    during BFS traversal (not just during seeding). Without this
    distinction, a centerline that touched many polygons at once
    would seed past the cap before the BFS while-loop ran."""
    from modules.create_model_river import filter_polygons_by_centerline_connectivity

    # Centerline is a tiny segment touching only polys[0]
    centerline = [LineString([(0.4, 0.0), (0.6, 0.0)])]
    # 20 unit squares chained edge-to-edge from x=0..20
    polys = [
        Polygon([(i, -0.5), (i + 1, -0.5), (i + 1, 0.5), (i, 0.5)])
        for i in range(20)
    ]
    kept = filter_polygons_by_centerline_connectivity(
        centerline=centerline,
        polygons=polys,
        tolerance_deg=0.001,  # ~110m — enough to bridge edge-touching squares
        max_polys=5,
    )
    assert len(kept) <= 5
    assert len(kept) >= 1, "should have kept at least the seed polygon"


def test_filter_empty_polygons_returns_empty():
    """Empty input → empty output, no errors."""
    from modules.create_model_river import filter_polygons_by_centerline_connectivity

    kept = filter_polygons_by_centerline_connectivity(
        centerline=[LineString([(0, 0), (1, 0)])],
        polygons=[],
        tolerance_deg=0.001,
        max_polys=100,
    )
    assert kept == []
