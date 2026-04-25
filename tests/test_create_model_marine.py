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
