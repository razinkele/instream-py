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


def test_partition_into_4_equal_groups():
    """10 polygons distributed along a centerline → 4 groups whose sizes
    sum to 10. With n=10, n_reaches=4, q=2.5 the slice math gives
    [(0,2),(2,5),(5,7),(7,10)] → group sizes [2, 3, 2, 3]. The last
    slice always extends to n (absorbs rounding remainder)."""
    from modules.create_model_river import partition_polygons_along_channel

    centerline = [LineString([(0, 0), (10, 0)])]
    # 10 polygons strung along x = 0..10
    polys = [
        Polygon([(i, -0.5), (i + 0.5, -0.5), (i + 0.5, 0.5), (i, 0.5)])
        for i in range(10)
    ]

    groups = partition_polygons_along_channel(
        centerline=centerline,
        polygons=polys,
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=4,
    )
    assert len(groups) == 4
    # All polygons must be in exactly one group; total count preserved.
    total = sum(len(g) for g in groups)
    assert total == 10


def test_partition_with_too_few_polygons():
    """Fewer polygons than n_reaches → some groups empty; no errors."""
    from modules.create_model_river import partition_polygons_along_channel

    centerline = [LineString([(0, 0), (10, 0)])]
    polys = [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])]  # only 1 polygon

    groups = partition_polygons_along_channel(
        centerline=centerline,
        polygons=polys,
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=4,
    )
    assert len(groups) == 4
    # All polygons accounted for
    assert sum(len(g) for g in groups) == 1


def test_partition_orders_by_along_channel_distance():
    """First group contains polygons closest to mouth; last group contains
    polygons furthest from mouth.

    Uses 6 polygons over 3 reaches (2 per group) so the assertion
    actually exercises the partition algorithm, not just len-1 slicing.
    With 3 polys / 3 reaches each group would have exactly 1 polygon
    and the assertion `near_mouth in groups[0]` would pass even with
    a buggy zero-everything `.project()` because Python's stable sort
    preserves insertion order — a false-positive."""
    from modules.create_model_river import partition_polygons_along_channel

    centerline = [LineString([(0, 0), (12, 0)])]
    p_a = Polygon([(0.5, -0.3), (1.5, -0.3), (1.5, 0.3), (0.5, 0.3)])    # near
    p_b = Polygon([(2.5, -0.3), (3.5, -0.3), (3.5, 0.3), (2.5, 0.3)])    # near-mid
    p_c = Polygon([(4.5, -0.3), (5.5, -0.3), (5.5, 0.3), (4.5, 0.3)])    # mid-low
    p_d = Polygon([(6.5, -0.3), (7.5, -0.3), (7.5, 0.3), (6.5, 0.3)])    # mid-high
    p_e = Polygon([(8.5, -0.3), (9.5, -0.3), (9.5, 0.3), (8.5, 0.3)])    # far-low
    p_f = Polygon([(10.5, -0.3), (11.5, -0.3), (11.5, 0.3), (10.5, 0.3)])  # far

    groups = partition_polygons_along_channel(
        centerline=centerline,
        polygons=[p_f, p_d, p_b, p_a, p_e, p_c],   # input shuffled
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=3,
    )
    assert len(groups) == 3
    # First group should contain the two nearest (p_a, p_b)
    assert p_a in groups[0] and p_b in groups[0]
    # Middle group should contain p_c, p_d
    assert p_c in groups[1] and p_d in groups[1]
    # Last group should contain p_e, p_f
    assert p_e in groups[2] and p_f in groups[2]


def test_partition_handles_multilinestring_centerline():
    """Tornionjoki centerline is a MultiLineString; project() on a raw
    MultiLineString returns 0.0 for every point. Verify partition
    still orders polygons mouth → source after linemerge / coordinate
    concatenation."""
    from shapely.geometry import MultiLineString
    from modules.create_model_river import partition_polygons_along_channel

    # Two sub-lines that merge cleanly into a single LineString
    cl = MultiLineString([
        [(0, 0), (5, 0)],
        [(5, 0), (10, 0)],
    ])
    near_mouth = Polygon([(0, -0.5), (1, -0.5), (1, 0.5), (0, 0.5)])
    far = Polygon([(9, -0.5), (10, -0.5), (10, 0.5), (9, 0.5)])

    groups = partition_polygons_along_channel(
        centerline=cl,
        polygons=[far, near_mouth],
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=2,
    )
    assert near_mouth in groups[0], "near-mouth polygon not in first group"
    assert far in groups[1], "far polygon not in last group"


def test_partition_handles_disjoint_multilinestring():
    """Genuinely disjoint MultiLineString (no shared endpoints) — linemerge
    cannot merge, so the helper falls back to coordinate-distance sort.
    Approximate but should still order polygons mouth → source for a
    river-shaped (roughly radial-from-mouth) input."""
    from shapely.geometry import MultiLineString
    from modules.create_model_river import partition_polygons_along_channel

    # Disjoint: no endpoint shared between (0,0)→(4,0) and (6,0)→(10,0)
    cl = MultiLineString([
        [(0, 0), (4, 0)],
        [(6, 0), (10, 0)],
    ])
    near_mouth = Polygon([(0, -0.5), (1, -0.5), (1, 0.5), (0, 0.5)])
    far = Polygon([(9, -0.5), (10, -0.5), (10, 0.5), (9, 0.5)])

    groups = partition_polygons_along_channel(
        centerline=cl,
        polygons=[far, near_mouth],
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=2,
    )
    assert near_mouth in groups[0], "near-mouth polygon not in first group (disjoint MLS)"
    assert far in groups[1], "far polygon not in last group (disjoint MLS)"


def test_partition_handles_y_shaped_multilinestring():
    """Y-junction case (real Tornionjoki+Muonio shape): mouth at one end,
    centerline branches in two directions. The fallback's
    Euclidean-distance sort produces a self-crossing synthetic
    LineString — verify partition still places near-mouth polygons in
    the first reach group regardless of which branch they're on.

    This is the case the prior tests (1-D colinear segments) cannot
    surface: real branching geometry where Euclidean distance from
    mouth ≠ along-channel distance."""
    from shapely.geometry import MultiLineString
    from modules.create_model_river import partition_polygons_along_channel

    # Trunk going north, then branches NE (Torne main) and NW (Muonio)
    # Mouth at (0, 0). Trunk: (0,0)→(0,3). NE branch: (0,3)→(2,5). NW: (0,3)→(-2,5).
    cl = MultiLineString([
        [(0, 0), (0, 3)],     # trunk (mouth → confluence)
        [(0, 3), (2, 5)],     # NE branch (Torne main)
        [(0, 3), (-2, 5)],    # NW branch (Muonio)
    ])
    # 6 polygons: 2 near mouth, 2 mid-trunk, 1 each on NE and NW branches
    p_mouth_a = Polygon([(0.1, 0.0), (0.4, 0.0), (0.4, 0.3), (0.1, 0.3)])
    p_mouth_b = Polygon([(-0.4, 0.0), (-0.1, 0.0), (-0.1, 0.3), (-0.4, 0.3)])
    p_mid_a = Polygon([(0.1, 1.5), (0.4, 1.5), (0.4, 1.8), (0.1, 1.8)])
    p_mid_b = Polygon([(-0.4, 1.5), (-0.1, 1.5), (-0.1, 1.8), (-0.4, 1.8)])
    p_ne = Polygon([(1.7, 4.5), (2.0, 4.5), (2.0, 4.8), (1.7, 4.8)])
    p_nw = Polygon([(-2.0, 4.5), (-1.7, 4.5), (-1.7, 4.8), (-2.0, 4.8)])

    groups = partition_polygons_along_channel(
        centerline=cl,
        polygons=[p_ne, p_nw, p_mid_a, p_mid_b, p_mouth_a, p_mouth_b],
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=3,
    )
    # First group must contain BOTH near-mouth polygons (they're closer
    # to mouth than mid-trunk, regardless of which branch they sit on).
    assert p_mouth_a in groups[0] and p_mouth_b in groups[0], (
        "near-mouth polygons not in first group (Y-shaped MLS): "
        f"groups[0]={groups[0]}"
    )
    # Last group must contain BOTH branch-end polygons.
    assert p_ne in groups[2] and p_nw in groups[2], (
        "branch-end polygons not in last group (Y-shaped MLS): "
        f"groups[2]={groups[2]}"
    )


def test_default_reach_names_n4():
    from modules.create_model_river import default_reach_names
    assert default_reach_names(4) == ["Mouth", "Lower", "Middle", "Upper"]


def test_default_reach_names_other_n():
    from modules.create_model_river import default_reach_names
    assert default_reach_names(2) == ["Reach1", "Reach2"]
    assert default_reach_names(3) == ["Reach1", "Reach2", "Reach3"]
    assert default_reach_names(8) == [f"Reach{i}" for i in range(1, 9)]


# ---------------------------------------------------------------------------
# filter_centerlines_by_name — v0.51.1 single-river selection helper
# ---------------------------------------------------------------------------

def test_filter_centerlines_substring_match_case_insensitive():
    """Common case: user types 'dane' (ASCII), OSM has 'Danė' (Lithuanian
    diacritic). The casefold-based comparison must match Latin-with-marks
    variants AND be substring-based so 'dan' alone also matches."""
    from modules.create_model_river import filter_centerlines_by_name

    a = LineString([(0, 0), (1, 0)])
    b = LineString([(0, 1), (1, 1)])
    c = LineString([(0, 2), (1, 2)])

    kept = filter_centerlines_by_name(
        centerlines=[a, b, c],
        names=["Danė", "Minija", "Nemunas"],
        name_query="dan",
    )
    assert kept == [a]


def test_filter_centerlines_empty_query_returns_all():
    """Empty / whitespace query short-circuits to passthrough — that's
    how the panel signals 'no filter'. Critical: must NOT drop ways
    with name=None when filter is off."""
    from modules.create_model_river import filter_centerlines_by_name

    a = LineString([(0, 0), (1, 0)])
    b = LineString([(0, 1), (1, 1)])

    assert filter_centerlines_by_name([a, b], ["Danė", None], "") == [a, b]
    assert filter_centerlines_by_name([a, b], ["Danė", None], "   ") == [a, b]


def test_filter_centerlines_no_match_returns_empty():
    from modules.create_model_river import filter_centerlines_by_name

    a = LineString([(0, 0), (1, 0)])
    kept = filter_centerlines_by_name([a], ["Minija"], name_query="dane")
    assert kept == []


def test_filter_centerlines_skips_none_and_empty_names_when_filtering():
    """OSM frequently has name=None on unnamed tributaries. With a
    non-empty filter those must be dropped — keeping them would defeat
    'show me only the Danė' (the v0.51.0 motivating case)."""
    from modules.create_model_river import filter_centerlines_by_name

    a = LineString([(0, 0), (1, 0)])
    b = LineString([(0, 1), (1, 1)])
    c = LineString([(0, 2), (1, 2)])

    kept = filter_centerlines_by_name(
        centerlines=[a, b, c],
        names=["Danė", None, ""],
        name_query="dan",
    )
    assert kept == [a]


def test_filter_centerlines_mismatched_lengths_raises():
    """Parallel-list contract: callers must pass len(names) == len(centerlines)."""
    from modules.create_model_river import filter_centerlines_by_name

    a = LineString([(0, 0), (1, 0)])
    with pytest.raises(ValueError, match="length"):
        filter_centerlines_by_name([a], ["Danė", "Minija"], "dan")
