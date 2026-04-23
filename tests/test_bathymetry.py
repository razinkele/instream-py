"""Tests for app/modules/bathymetry.py — EMODnet DTM fetch + sample."""
from pathlib import Path
import sys

import pytest

pytest.importorskip("shiny")

import geopandas as gpd
import numpy as np
from shapely.geometry import Point, Polygon

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from modules.bathymetry import sample_depth, _cache_path_for_bbox  # noqa: E402


def test_cache_path_deterministic():
    bbox = (20.0, 54.5, 22.5, 56.0)
    p1 = _cache_path_for_bbox(bbox)
    p2 = _cache_path_for_bbox(bbox)
    assert p1 == p2
    assert p1.suffix == ".tif"


def test_sample_depth_on_synthetic_raster(tmp_path):
    """Synthetic GeoTIFF over Baltic coords with EMODnet-style negative
    elevations. Verifies sign-flip + correct pixel→centroid mapping."""
    import rasterio
    from rasterio.transform import from_bounds

    tif = tmp_path / "synth.tif"
    # 3x3 raster over Baltic bbox. Values -1..-9 → depths 1..9m after sign-flip.
    # rasterio writes row 0 at the north (max lat).
    data = -np.arange(1, 10, dtype=np.float32).reshape(3, 3)
    transform = from_bounds(20.0, 54.0, 23.0, 57.0, 3, 3)
    with rasterio.open(
        tif, "w", driver="GTiff", height=3, width=3, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)

    # Centroid (20.5, 56.5) -> row 0 col 0 -> elev -1 -> depth 1m.
    # Centroid (22.5, 54.5) -> row 2 col 2 -> elev -9 -> depth 9m.
    gdf = gpd.GeoDataFrame(
        geometry=[
            Polygon([(20.0, 56.0), (21.0, 56.0), (21.0, 57.0), (20.0, 57.0)]),
            Polygon([(22.0, 54.0), (23.0, 54.0), (23.0, 55.0), (22.0, 55.0)]),
        ],
        crs="EPSG:4326",
    )
    depths = sample_depth(gdf, tif)
    assert len(depths) == 2
    assert depths[0] == pytest.approx(1.0, abs=0.01)
    assert depths[1] == pytest.approx(9.0, abs=0.01)


def test_sample_depth_clamps_land_to_minimum(tmp_path):
    """Positive elevation (land) becomes negative depth; code must clamp to 0.1 m."""
    import rasterio
    from rasterio.transform import from_bounds

    tif = tmp_path / "land.tif"
    data = np.full((3, 3), 5.0, dtype=np.float32)
    transform = from_bounds(20.0, 54.0, 23.0, 57.0, 3, 3)
    with rasterio.open(
        tif, "w", driver="GTiff", height=3, width=3, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)

    gdf = gpd.GeoDataFrame(
        geometry=[Polygon([(20.0, 54.0), (21.0, 54.0), (21.0, 55.0), (20.0, 55.0)])],
        crs="EPSG:4326",
    )
    depths = sample_depth(gdf, tif)
    assert len(depths) == 1
    assert depths[0] == pytest.approx(0.1)


def test_sample_depth_missing_raster_raises(tmp_path):
    # Baltic-area point so any downstream estimate_utm_crs stays within a valid zone.
    gdf = gpd.GeoDataFrame(geometry=[Point(21.0, 55.0)], crs="EPSG:4326")
    with pytest.raises(FileNotFoundError):
        sample_depth(gdf, tmp_path / "does_not_exist.tif")
