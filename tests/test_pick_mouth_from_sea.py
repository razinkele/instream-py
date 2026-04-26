"""Unit tests for _pick_mouth_from_sea (create_model_panel module-level helper)."""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiLineString, Polygon

# Ensure app/modules importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))


def _sea_gdf(polygon):
    return gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")


def test_pick_mouth_returns_endpoint_near_sea_offshore_gap():
    """Endpoint sits ~1 km outside the sea polygon, simulating the
    Simojoki regression where the v0.47.0 batch generator's centerline
    endpoint was 945 m offshore. Polygon offset to (2.005-2.05) so
    (2.0, 2.0) is OUTSIDE the polygon's nearest edge."""
    from modules.create_model_panel import _pick_mouth_from_sea
    line = LineString([(1.0, 1.0), (2.0, 2.0)])
    sea = Polygon([
        (2.005, 2.005), (2.05, 2.005), (2.05, 2.05), (2.005, 2.05), (2.005, 2.005)
    ])
    result = _pick_mouth_from_sea([line], _sea_gdf(sea))
    assert result is not None
    lon, lat = result
    assert lon == pytest.approx(2.0, abs=0.001)
    assert lat == pytest.approx(2.0, abs=0.001)


def test_pick_mouth_returns_none_if_far_from_sea():
    from modules.create_model_panel import _pick_mouth_from_sea
    line = LineString([(1.0, 1.0), (2.0, 2.0)])
    # Sea polygon ~50 km away (>>5 km threshold)
    sea = Polygon([
        (5.0, 5.0), (5.5, 5.0), (5.5, 5.5), (5.0, 5.5), (5.0, 5.0)
    ])
    result = _pick_mouth_from_sea([line], _sea_gdf(sea))
    assert result is None


def test_pick_mouth_handles_connected_multilinestring():
    """Two end-to-end sub-LineStrings: linemerge collapses them into one,
    so the LineString branch handles endpoint enumeration."""
    from modules.create_model_panel import _pick_mouth_from_sea
    line1 = LineString([(0.0, 0.0), (1.0, 1.0)])
    line2 = LineString([(1.0, 1.0), (2.0, 2.0)])
    mls = MultiLineString([line1, line2])
    sea = Polygon([
        (2.005, 2.005), (2.05, 2.005), (2.05, 2.05), (2.005, 2.05), (2.005, 2.005)
    ])
    result = _pick_mouth_from_sea([mls], _sea_gdf(sea))
    assert result is not None
    lon, lat = result
    # After linemerge → LineString (0,0)→(2,2). Endpoints are (0,0) and (2,2);
    # (2,2) is closer to sea.
    assert lon == pytest.approx(2.0, abs=0.001)
    assert lat == pytest.approx(2.0, abs=0.001)


def test_pick_mouth_handles_disjoint_multilinestring():
    """Two DISJOINT sub-LineStrings: linemerge cannot collapse → result
    stays a MultiLineString, so the MultiLineString endpoint-enumeration
    branch is exercised. Without the linemerge step, this would have
    enumerated 4 endpoints from a connected MultiLineString and risked
    selecting an interior junction."""
    from modules.create_model_panel import _pick_mouth_from_sea
    line1 = LineString([(0.0, 0.0), (0.5, 0.5)])
    line2 = LineString([(1.5, 1.5), (2.0, 2.0)])  # gap at (0.5,0.5)→(1.5,1.5)
    mls = MultiLineString([line1, line2])
    sea = Polygon([
        (2.005, 2.005), (2.05, 2.005), (2.05, 2.05), (2.005, 2.05), (2.005, 2.005)
    ])
    result = _pick_mouth_from_sea([mls], _sea_gdf(sea))
    assert result is not None
    lon, lat = result
    # 4 endpoints: (0,0), (0.5,0.5), (1.5,1.5), (2,2). Closest to sea = (2,2).
    assert lon == pytest.approx(2.0, abs=0.001)
    assert lat == pytest.approx(2.0, abs=0.001)


def test_pick_mouth_handles_unavailable_detect_utm_epsg(monkeypatch):
    from modules import create_model_panel as panel_mod
    monkeypatch.setattr(panel_mod, "detect_utm_epsg", None)
    line = LineString([(1.0, 1.0), (2.0, 2.0)])
    sea = Polygon([
        (2.005, 2.005), (2.05, 2.005), (2.05, 2.05), (2.005, 2.05), (2.005, 2.005)
    ])
    result = panel_mod._pick_mouth_from_sea([line], _sea_gdf(sea))
    assert result is None
