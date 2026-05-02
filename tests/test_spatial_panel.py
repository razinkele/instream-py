"""Tests for spatial panel helper functions."""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "app"))

from simulation import _build_trajectories_data, _value_to_rgba  # noqa: E402 (sys.path.insert above is load-bearing)


class TestBuildTrajectoriesData:
    """Unit tests for _build_trajectories_data()."""

    @staticmethod
    def _make_gdf():
        """3 cells in EPSG:4326 (already lon/lat)."""
        polys = [
            Polygon([(20.0, 55.0), (20.01, 55.0), (20.01, 55.01), (20.0, 55.01)]),
            Polygon([(20.01, 55.0), (20.02, 55.0), (20.02, 55.01), (20.01, 55.01)]),
            Polygon([(20.02, 55.0), (20.03, 55.0), (20.03, 55.01), (20.02, 55.01)]),
        ]
        return gpd.GeoDataFrame(
            {"cell_id": [0, 1, 2]},
            geometry=polys,
            crs="EPSG:4326",
        )

    @staticmethod
    def _make_traj():
        """5 fish, 3 days. Fish 4 dies on day 1 (absent day 2)."""
        rows = []
        for day in range(3):
            for fish in range(5):
                if fish == 4 and day == 2:
                    continue  # fish 4 dies
                rows.append(
                    {
                        "fish_idx": fish,
                        "cell_idx": fish % 3,
                        "species_idx": fish % 2,
                        "activity": 0,
                        "life_history": 0,
                        "day_num": day,
                    }
                )
        return pd.DataFrame(rows)

    def test_returns_two_lists(self):
        paths, props = _build_trajectories_data(
            self._make_traj(),
            self._make_gdf(),
            ["sp_a", "sp_b"],
        )
        assert isinstance(paths, list)
        assert isinstance(props, list)
        assert len(paths) == len(props)

    def test_paths_are_3d(self):
        paths, _ = _build_trajectories_data(
            self._make_traj(),
            self._make_gdf(),
            ["sp_a", "sp_b"],
        )
        for path in paths:
            for pt in path:
                assert len(pt) == 3, f"Expected [lon, lat, day_num], got {pt}"

    def test_correct_fish_count(self):
        """5 unique fish → 5 trips."""
        paths, props = _build_trajectories_data(
            self._make_traj(),
            self._make_gdf(),
            ["sp_a", "sp_b"],
        )
        assert len(paths) == 5

    def test_variable_length_paths(self):
        """Fish 4 has 2 days, others have 3."""
        paths, props = _build_trajectories_data(
            self._make_traj(),
            self._make_gdf(),
            ["sp_a", "sp_b"],
        )
        lengths = {p["fish_idx"]: len(path) for path, p in zip(paths, props)}
        assert lengths[4] == 2
        assert lengths[0] == 3

    def test_timestamps_are_actual_day_nums(self):
        """Third coordinate should be the actual day_num, not auto-generated."""
        paths, _ = _build_trajectories_data(
            self._make_traj(),
            self._make_gdf(),
            ["sp_a", "sp_b"],
        )
        # Fish 0 is present days 0, 1, 2
        fish0_path = paths[0]
        assert fish0_path[0][2] == 0
        assert fish0_path[1][2] == 1
        assert fish0_path[2][2] == 2

    def test_properties_contain_species(self):
        _, props = _build_trajectories_data(
            self._make_traj(),
            self._make_gdf(),
            ["sp_a", "sp_b"],
        )
        for p in props:
            assert "species" in p
            assert "color" in p
            assert "fish_idx" in p

    def test_coords_are_lon_lat(self):
        """Coordinates should be in WGS84 range."""
        paths, _ = _build_trajectories_data(
            self._make_traj(),
            self._make_gdf(),
            ["sp_a", "sp_b"],
        )
        for path in paths:
            for lon, lat, _ in path:
                assert -180 <= lon <= 180, f"lon out of range: {lon}"
                assert -90 <= lat <= 90, f"lat out of range: {lat}"


class TestValueToRgba:
    """Unit tests for _value_to_rgba()."""

    def test_returns_list_of_rgba(self):
        values = np.array([0.0, 0.5, 1.0])
        result = _value_to_rgba(values)
        assert len(result) == 3
        for rgba in result:
            assert len(rgba) == 4
            assert all(0 <= c <= 255 for c in rgba)

    def test_nan_is_transparent(self):
        values = np.array([1.0, np.nan, 2.0])
        result = _value_to_rgba(values)
        assert result[1] == [0, 0, 0, 0]

    def test_constant_values(self):
        """All same values should not crash (zero range)."""
        values = np.array([5.0, 5.0, 5.0])
        result = _value_to_rgba(values)
        assert len(result) == 3

    def test_custom_alpha(self):
        values = np.array([0.0, 1.0])
        result = _value_to_rgba(values, alpha=200)
        for rgba in result:
            assert rgba[3] == 200


class TestBuildOsmOverlayLayers:
    """v0.56.17: per-reach overlay layers + in-map legend widget."""

    def test_returns_empty_when_no_sidecars(self):
        from modules.spatial_panel import build_osm_overlay_layers
        assert build_osm_overlay_layers({}) == []
        assert build_osm_overlay_layers(None) == []

    def test_one_layer_per_reach_per_kind(self):
        """Two reaches × two kinds (poly + line) → 4 layers with stable ids."""
        from shapely.geometry import LineString, Polygon as ShPoly
        from modules.spatial_panel import build_osm_overlay_layers

        polys = gpd.GeoDataFrame(
            {"REACH_NAME": ["Minija", "Babrungas"]},
            geometry=[
                ShPoly([(0, 0), (1, 0), (1, 1), (0, 1)]),
                ShPoly([(2, 0), (3, 0), (3, 1), (2, 1)]),
            ],
            crs="EPSG:4326",
        )
        lines = gpd.GeoDataFrame(
            {"REACH_NAME": ["Minija", "Babrungas"]},
            geometry=[LineString([(0, 0), (1, 1)]), LineString([(2, 0), (3, 1)])],
            crs="EPSG:4326",
        )
        layers = build_osm_overlay_layers({
            "Fix-tribs-osm-polygons": polys,
            "Fix-tribs-osm-centerlines": lines,
        })
        ids = sorted(l["id"] for l in layers)
        assert ids == [
            "osm-Babrungas-centerlines",
            "osm-Babrungas-polygons",
            "osm-Minija-centerlines",
            "osm-Minija-polygons",
        ]
        # Polygon layers have filled=True, centerlines filled=False
        styles = {l["id"]: l for l in layers}
        assert styles["osm-Minija-polygons"].get("filled") is True
        assert styles["osm-Minija-centerlines"].get("filled") is False

    def test_legend_widget_entries_match_layer_ids(self):
        from shapely.geometry import LineString, Polygon as ShPoly
        from modules.spatial_panel import (
            build_osm_overlay_layers, build_osm_overlay_legend_widget,
        )

        polys = gpd.GeoDataFrame(
            {"REACH_NAME": ["Minija"]},
            geometry=[ShPoly([(0, 0), (1, 0), (1, 1), (0, 1)])],
            crs="EPSG:4326",
        )
        lines = gpd.GeoDataFrame(
            {"REACH_NAME": ["Minija"]},
            geometry=[LineString([(0, 0), (1, 1)])],
            crs="EPSG:4326",
        )
        sidecars = {
            "Fix-tribs-osm-polygons": polys,
            "Fix-tribs-osm-centerlines": lines,
        }
        layers = build_osm_overlay_layers(sidecars)
        widget = build_osm_overlay_legend_widget(sidecars)
        assert widget is not None
        layer_ids = {l["id"] for l in layers}
        widget_ids = {e["layer_id"] for e in widget["entries"]}
        # Every legend entry refers to a real layer
        assert widget_ids == layer_ids
        # Polygon entries get a "rect" swatch, centerlines get "line"
        shapes = {e["layer_id"]: e["shape"] for e in widget["entries"]}
        assert shapes["osm-Minija-polygons"] == "rect"
        assert shapes["osm-Minija-centerlines"] == "line"

    def test_legend_widget_returns_none_when_no_sidecars(self):
        from modules.spatial_panel import build_osm_overlay_legend_widget
        assert build_osm_overlay_legend_widget({}) is None
        assert build_osm_overlay_legend_widget(None) is None
