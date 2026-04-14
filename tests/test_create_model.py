"""Unit tests for the 4 core Create Model modules."""

import sys
from pathlib import Path

import geopandas as gpd
import yaml
from shapely.geometry import LineString

# Allow imports from app/modules/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from modules.create_model_utils import DEFAULT_REACH_PARAMS, detect_utm_epsg
from modules.create_model_grid import generate_cells
from modules.create_model_reaches import assign_segment_to_reach, remove_segment_from_reach
from modules.create_model_export import export_yaml


# ---------------------------------------------------------------------------
# TestUtils
# ---------------------------------------------------------------------------

class TestUtils:
    def test_detect_utm_lithuania(self):
        assert detect_utm_epsg(21.1, 55.7) == 32634

    def test_detect_utm_southern(self):
        assert detect_utm_epsg(21.1, -35.0) == 32734

    def test_default_params_nonzero(self):
        for key, val in DEFAULT_REACH_PARAMS.items():
            if key == "light_turbid_const":
                continue
            assert val != 0, f"DEFAULT_REACH_PARAMS[{key!r}] should not be zero"


# ---------------------------------------------------------------------------
# TestGrid
# ---------------------------------------------------------------------------

class TestGrid:
    @staticmethod
    def _one_segment():
        """A short LineString in Lithuania (WGS84)."""
        return {
            "TestReach": {
                "segments": [LineString([(21.1, 55.7), (21.105, 55.705)])],
                "frac_spawn": 0.5,
            }
        }

    def test_hexagonal_produces_cells(self):
        gdf = generate_cells(self._one_segment(), cell_size=50.0, cell_shape="hexagonal")
        assert len(gdf) > 0
        for col in ("cell_id", "reach_name", "area", "dist_escape", "num_hiding",
                     "frac_vel_shelter", "frac_spawn", "geometry"):
            assert col in gdf.columns, f"Missing column: {col}"

    def test_rectangular_produces_cells(self):
        gdf = generate_cells(self._one_segment(), cell_size=50.0, cell_shape="rectangular")
        assert len(gdf) > 0
        for col in ("cell_id", "reach_name", "area", "dist_escape", "num_hiding",
                     "frac_vel_shelter", "frac_spawn", "geometry"):
            assert col in gdf.columns, f"Missing column: {col}"

    def test_empty_segments_empty_result(self):
        gdf = generate_cells({})
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 0


# ---------------------------------------------------------------------------
# TestReaches
# ---------------------------------------------------------------------------

class TestReaches:
    @staticmethod
    def _seg():
        return LineString([(21.1, 55.7), (21.105, 55.705)])

    def test_assign_segment(self):
        reaches: dict = {}
        seg = self._seg()
        assign_segment_to_reach(reaches, "R1", seg, {"name": "s1"})
        assert "R1" in reaches
        assert len(reaches["R1"]["segments"]) == 1

    def test_remove_segment(self):
        reaches: dict = {}
        seg = self._seg()
        assign_segment_to_reach(reaches, "R1", seg, {"name": "s1"})
        remove_segment_from_reach(reaches, seg)
        assert "R1" not in reaches, "Reach should be deleted when its only segment is removed"


# ---------------------------------------------------------------------------
# TestExport
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_yaml_has_reaches(self):
        cells_gdf = gpd.GeoDataFrame(
            {"cell_id": ["C0001"], "reach_name": ["MyReach"]},
        )
        reaches = {"MyReach": {}}
        text = export_yaml(
            reaches=reaches,
            cells_gdf=cells_gdf,
            model_name="test_model",
            species_params={},
            start_date="2020-01-01",
            end_date="2020-12-31",
        )
        parsed = yaml.safe_load(text)
        assert "reaches" in parsed
        assert "MyReach" in parsed["reaches"]
        assert "drift_conc" in parsed["reaches"]["MyReach"]
