"""Unit tests for app/modules/create_model_marine.py.

Pure-Python tests on synthetic + mocked inputs. No network access.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import geopandas as gpd
from shapely.geometry import Point, Polygon, box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_clip_sea_polygon_to_disk_basic_intersection():
    """Sea polygon covers a disk at the mouth → result is non-empty
    and inside both the sea polygon and the disk's circular bound."""
    from modules.create_model_marine import clip_sea_polygon_to_disk

    # Sea polygon: a 2°×2° box around (0,0). At equator, ~222 km × 222 km.
    sea = box(-1.0, -1.0, 1.0, 1.0)
    mouth = (0.5, 0.5)
    radius_m = 50_000  # 50 km
    utm_epsg = 32631   # lon 0.5° lies in UTM zone 31 (0°E–6°E central meridian 3°E)

    result = clip_sea_polygon_to_disk(
        sea_polygon=sea,
        mouth_lon_lat=mouth,
        radius_m=radius_m,
        utm_epsg=utm_epsg,
    )

    assert not result.is_empty
    # Result should be inside the sea polygon (with sub-meter tolerance for round-trip)
    assert sea.buffer(1e-6).contains(result), "result not inside sea polygon"


def test_clip_sea_polygon_to_disk_mouth_outside_sea_raises():
    """Mouth far from any sea → intersection empty → ValueError."""
    from modules.create_model_marine import clip_sea_polygon_to_disk

    sea = box(0.0, 0.0, 1.0, 1.0)
    mouth_far_inland = (10.0, 10.0)
    with pytest.raises(ValueError, match="does not intersect"):
        clip_sea_polygon_to_disk(
            sea_polygon=sea,
            mouth_lon_lat=mouth_far_inland,
            radius_m=10_000,
            utm_epsg=32633,
        )


def test_clip_sea_polygon_to_disk_empty_sea_raises():
    """Empty sea polygon → ValueError."""
    from modules.create_model_marine import clip_sea_polygon_to_disk

    sea = Polygon()  # empty
    with pytest.raises(ValueError, match="empty"):
        clip_sea_polygon_to_disk(
            sea_polygon=sea,
            mouth_lon_lat=(0.5, 0.5),
            radius_m=10_000,
            utm_epsg=32633,
        )


def test_query_named_sea_polygon_post_filters_centroid_match(monkeypatch):
    """Among multiple polygons returned by WFS, only the one containing
    the bbox centroid should be returned."""
    from modules import create_model_marine as m

    # Two polygons — one covers the bbox centre, one only touches the bbox edge.
    fake_geoj = {
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "True Match"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {"name": "Edge Toucher"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [1, 1], [3, 1], [3, 3], [1, 3], [1, 1]
                    ]],
                },
            },
        ],
    }

    class _FakeResp:
        # __enter__/__exit__ required: query_named_sea_polygon uses
        # `with requests.get(...) as resp:` (loop-35 fix for socket
        # leak). Without context-manager protocol, the `with` raises
        # TypeError before any of the helper's logic runs.
        # `headers` empty dict satisfies the Content-Length lookup
        # (loop-34 size cap).
        headers: dict[str, str] = {}
        def raise_for_status(self): pass
        def json(self): return fake_geoj
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    monkeypatch.setattr(m.requests, "get", lambda *a, **kw: _FakeResp())

    result = m.query_named_sea_polygon((-1.0, -1.0, 1.0, 1.0))
    assert result is not None
    assert len(result) == 1
    assert result.iloc[0]["name"] == "True Match"


def test_query_named_sea_polygon_returns_none_on_http_error(monkeypatch):
    """HTTP error → None (no exception)."""
    from modules import create_model_marine as m

    class _FailResp:
        headers: dict[str, str] = {}
        def raise_for_status(self):
            raise RuntimeError("HTTP 500")
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    monkeypatch.setattr(m.requests, "get", lambda *a, **kw: _FailResp())
    result = m.query_named_sea_polygon((0, 0, 1, 1))
    assert result is None


def test_query_named_sea_polygon_returns_none_on_empty_features(monkeypatch):
    """Empty WFS response → None."""
    from modules import create_model_marine as m

    class _EmptyResp:
        headers: dict[str, str] = {}
        def raise_for_status(self): pass
        def json(self): return {"features": []}
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    monkeypatch.setattr(m.requests, "get", lambda *a, **kw: _EmptyResp())
    result = m.query_named_sea_polygon((0, 0, 1, 1))
    assert result is None
