"""Geographic-conformance tests for habitat-cell fixtures.

These tests catch the v0.51.0 Danė problem ("river reaches too wide,
not conform the dane river polygons") and the CELL_2357 problem (single
hand-traced lagoon blob) automatically across all fixtures.

Architecture:
- ``app/modules/geographic_conformance.py`` provides classification +
  metrics + rule application as pure functions.
- This file is the CI-level gate. It parametrizes per (fixture, reach)
  and asserts ``check_reach_plausibility`` returns no issues.
- Fixtures known to violate the rules are marked ``xfail`` with a
  concrete reason — the PASS column tells you which fixtures are
  geographically faithful (Mörrumsån + example_a + example_b at v0.51.2),
  the XFAIL column tells you what the next geometry-fix release needs
  to address.

Re-running this test after fixing a fixture should flip an XFAIL into
XPASS, signalling that an xfail entry can be removed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from modules.geographic_conformance import (  # noqa: E402
    DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M,
    DEFAULT_MIN_MARINE_CELLS,
    ReachClass,
    ReachIssue,
    classify_reach,
    check_fixture_geography,
    compute_reach_metrics,
)


# Per-reach xfail registry. Each entry is keyed by ``(fixture, reach)``.
# The value is the human reason. Adding a key here marks the test as
# expected-fail; removing a key after a fix forces XPASS, which is a
# loud signal the registry is now stale.
KNOWN_GEOMETRY_DRIFT: dict[tuple[str, str], str] = {
    # v0.51.0 Danė fixture — buffered-centerline cell generation produced
    # 376-465 m effective widths against a real ~25-50 m river.
    ("example_baltic", "Dane_Lower"):  "v0.51.0 buffered-centerline geometry; effective_width 465 m vs real ~30 m",
    ("example_baltic", "Dane_Middle"): "v0.51.0 buffered-centerline geometry; effective_width 376 m vs real ~25 m",
    ("example_baltic", "Dane_Mouth"):  "v0.51.0 buffered-centerline geometry; effective_width 465 m vs real ~50 m",
    ("example_baltic", "Dane_Upper"): "v0.51.0 buffered-centerline geometry; effective_width 385 m vs real ~25 m",
    # v0.51.0 KlaipedaStrait — single 11.3 km² hand-traced polygon.
    ("example_baltic", "KlaipedaStrait"): "v0.51.0 hand-traced single mega-cell (11.3 km²)",

    # v0.45.x Simojoki + Tornionjoki — buffered-centerline geometry on
    # large rivers. The threshold (350 m) sits above the real-channel
    # widths of Mörrumsån + Byskealven (179-281 m) but below these.
    # The fix is the same path that produced v0.45.2 Mörrumsån: clip
    # cell grid to OSM `natural=water` polygons, not the centerline buffer.
    ("example_simojoki", "Lower"):     "v0.45.x effective_width 554 m vs real Simojoki ~80 m",
    ("example_simojoki", "Middle"):    "v0.45.x effective_width 1112 m",
    ("example_simojoki", "Upper"):     "v0.45.x effective_width 755 m",
    ("example_tornionjoki", "Lower"):  "v0.45.x effective_width 1035 m vs real Tornionjoki ~250 m",
    ("example_tornionjoki", "Middle"): "v0.45.x effective_width 563 m",
    ("example_tornionjoki", "Upper"): "v0.45.x effective_width 1477 m",
}


def _all_fixture_dirs() -> list[Path]:
    """Discover fixture directories that ship a Shapefile cell layer."""
    fixtures_root = ROOT / "tests" / "fixtures"
    if not fixtures_root.exists():
        return []
    return sorted(
        d for d in fixtures_root.iterdir()
        if d.is_dir() and not d.name.startswith("_")
        and (d / "Shapefile").exists()
        and any((d / "Shapefile").glob("*.shp"))
    )


def _fixture_reach_pairs() -> list[tuple[str, str]]:
    """Enumerate (fixture, reach) pairs across every fixture."""
    pairs: list[tuple[str, str]] = []
    for fx_dir in _all_fixture_dirs():
        results = check_fixture_geography(fx_dir)
        for reach in results.keys():
            pairs.append((fx_dir.name, reach))
    return pairs


# --------------------------------------------------------------------------
# Unit tests for the helper module (synthetic geometries, no fixture IO)
# --------------------------------------------------------------------------

def test_classify_reach_marine_keywords():
    """All marine keyword variants should classify as marine."""
    assert classify_reach("BalticCoast") == "marine"
    assert classify_reach("CuronianLagoon") == "marine"
    assert classify_reach("KlaipedaStrait") == "marine"
    assert classify_reach("GulfOfBothnia") == "marine"
    assert classify_reach("NarrowBay") == "marine"
    assert classify_reach("SkagerakSea") == "marine"
    assert classify_reach("PortHarbour") == "marine"


def test_classify_reach_river_default():
    """Plain river names default to river classification."""
    assert classify_reach("Dane_Mouth") == "river"
    assert classify_reach("Mouth") == "river"
    assert classify_reach("Tornionjoki") == "river"
    assert classify_reach("Nemunas") == "river"
    assert classify_reach("ExampleA") == "river"


def test_classify_reach_empty_defaults_river():
    assert classify_reach("") == "river"


def test_compute_reach_metrics_empty_returns_zero():
    import geopandas as gpd
    empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:3857")
    m = compute_reach_metrics(empty)
    assert m.cells == 0
    assert m.area_m2 == 0.0


def test_compute_reach_metrics_simple_rectangle():
    """A 100m × 50m rectangle: width 50, length 100, area 5000,
    effective_width = 5000/100 = 50."""
    import geopandas as gpd
    from shapely.geometry import box
    rect = gpd.GeoDataFrame(geometry=[box(0, 0, 100, 50)], crs="EPSG:3857")
    m = compute_reach_metrics(rect)
    assert m.cells == 1
    assert m.area_m2 == pytest.approx(5000.0)
    assert m.mrr_width_m == pytest.approx(50.0)
    assert m.mrr_length_m == pytest.approx(100.0)
    assert m.effective_width_m == pytest.approx(50.0)


def test_check_river_under_threshold_passes():
    """Narrow river (effective_width 50 m) under default 350 m → no issues."""
    from app.modules.geographic_conformance import check_reach_plausibility, ReachMetrics  # noqa: E402
    metrics = ReachMetrics(cells=20, area_m2=5000, mrr_width_m=50,
                           mrr_length_m=100, effective_width_m=50)
    assert check_reach_plausibility(metrics, "river") == []


def test_check_river_over_threshold_flags():
    """Wide river (effective_width 800 m) → RIVER_TOO_WIDE issue."""
    from app.modules.geographic_conformance import check_reach_plausibility, ReachMetrics  # noqa: E402
    metrics = ReachMetrics(cells=200, area_m2=200000, mrr_width_m=400,
                           mrr_length_m=250, effective_width_m=800)
    issues = check_reach_plausibility(metrics, "river")
    assert len(issues) == 1
    assert issues[0].code == "RIVER_TOO_WIDE"


def test_check_marine_single_mega_cell_flags():
    """Single 11 km² cell → MARINE_SINGLE_MEGA_CELL (CELL_2357 case)."""
    from app.modules.geographic_conformance import check_reach_plausibility, ReachMetrics  # noqa: E402
    metrics = ReachMetrics(cells=1, area_m2=11_000_000, mrr_width_m=2000,
                           mrr_length_m=5500, effective_width_m=2000)
    issues = check_reach_plausibility(metrics, "marine")
    assert len(issues) == 1
    assert issues[0].code == "MARINE_SINGLE_MEGA_CELL"


def test_check_marine_too_few_cells_flags():
    """3 normal-sized cells in a marine reach → MARINE_TOO_FEW_CELLS."""
    from app.modules.geographic_conformance import check_reach_plausibility, ReachMetrics  # noqa: E402
    metrics = ReachMetrics(cells=3, area_m2=45_000, mrr_width_m=150,
                           mrr_length_m=300, effective_width_m=150)
    issues = check_reach_plausibility(metrics, "marine")
    assert len(issues) == 1
    assert issues[0].code == "MARINE_TOO_FEW_CELLS"


def test_check_marine_polygon_fill_passes():
    """v0.45.2-style marine polygon fill (60+ cells, varied sizes) → clean."""
    from app.modules.geographic_conformance import check_reach_plausibility, ReachMetrics  # noqa: E402
    metrics = ReachMetrics(cells=65, area_m2=860_000_000, mrr_width_m=28000,
                           mrr_length_m=37000, effective_width_m=23300)
    # Marine reach effective_width is unbounded by current rules — the
    # only failure modes are too-few-cells and single-mega-cell.
    assert check_reach_plausibility(metrics, "marine") == []


# --------------------------------------------------------------------------
# Fixture-level parametrized test (the actual CI gate)
# --------------------------------------------------------------------------

_PAIRS = _fixture_reach_pairs()


def _xfail_marker_for(fixture: str, reach: str):
    """Return a pytest.mark.xfail marker if (fixture, reach) is in the
    known-drift registry, else None.
    """
    key = (fixture, reach)
    if key in KNOWN_GEOMETRY_DRIFT:
        return pytest.mark.xfail(
            reason=KNOWN_GEOMETRY_DRIFT[key],
            strict=True,  # XPASS = registry stale; surface loudly
        )
    return None


def _parametrize_fixture_reach_pairs():
    """Build the parametrize list, attaching xfail markers per pair."""
    params = []
    for fixture, reach in _PAIRS:
        marker = _xfail_marker_for(fixture, reach)
        if marker is not None:
            params.append(pytest.param(fixture, reach, marks=marker, id=f"{fixture}-{reach}"))
        else:
            params.append(pytest.param(fixture, reach, id=f"{fixture}-{reach}"))
    return params


@pytest.mark.parametrize("fixture,reach", _parametrize_fixture_reach_pairs())
def test_reach_geographic_plausibility(fixture: str, reach: str):
    """Each (fixture, reach) must satisfy the v0.51.2 plausibility rules.

    Currently-broken reaches are xfailed via ``KNOWN_GEOMETRY_DRIFT``;
    each entry there is a concrete TODO for a future geometry-fix
    release. Removing an entry without fixing the underlying fixture
    will surface as XPASS-strict.
    """
    fx_dir = ROOT / "tests" / "fixtures" / fixture
    results = check_fixture_geography(fx_dir)
    assert reach in results, f"reach {reach!r} not found in {fixture}"
    metrics, classification, issues = results[reach]
    if issues:
        pretty = "\n".join(f"  [{i.severity}] {i.code}: {i.message}" for i in issues)
        pytest.fail(
            f"{fixture}/{reach} ({classification}, {metrics.cells} cells, "
            f"effective_width={metrics.effective_width_m:.0f} m) has "
            f"{len(issues)} issue(s):\n{pretty}"
        )


def test_known_drift_registry_consistency():
    """Every entry in ``KNOWN_GEOMETRY_DRIFT`` must reference a real
    (fixture, reach) pair that exists on disk. Stops typos in the
    registry from silently swallowing fix-related XPASS signals.
    """
    real_pairs = set(_PAIRS)
    stale = [k for k in KNOWN_GEOMETRY_DRIFT if k not in real_pairs]
    assert not stale, (
        f"KNOWN_GEOMETRY_DRIFT references {len(stale)} fixture/reach pairs "
        f"that don't exist on disk: {stale}"
    )
