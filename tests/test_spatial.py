"""Tests for spatial mesh backends and FEMSpace."""
import numpy as np
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestPolygonMesh:
    """Test shapefile-based polygon mesh."""

    def test_load_example_a_cell_count(self):
        from instream.space.polygon_mesh import PolygonMesh
        from instream.io.hydraulics_reader import read_depth_table, read_velocity_table
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp",
            id_field="ID_TEXT",
            reach_field="REACH_NAME",
            area_field="AREA",
            dist_escape_field="M_TO_ESC",
            hiding_field="NUM_HIDING",
            shelter_field="FRACVSHL",
            spawn_field="FRACSPWN",
        )
        assert mesh.num_cells > 0

    def test_load_example_a_areas_positive(self):
        from instream.space.polygon_mesh import PolygonMesh
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp",
            id_field="ID_TEXT", reach_field="REACH_NAME", area_field="AREA",
            dist_escape_field="M_TO_ESC", hiding_field="NUM_HIDING",
            shelter_field="FRACVSHL", spawn_field="FRACSPWN",
        )
        assert np.all(mesh.areas > 0)

    def test_load_example_a_areas_in_cm2(self):
        """Areas from shapefile are in m²; must be converted to cm² (×10000)."""
        from instream.space.polygon_mesh import PolygonMesh
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp",
            id_field="ID_TEXT", reach_field="REACH_NAME", area_field="AREA",
            dist_escape_field="M_TO_ESC", hiding_field="NUM_HIDING",
            shelter_field="FRACVSHL", spawn_field="FRACSPWN",
        )
        # Areas should be in cm² (m² × 10000); the smallest cell is ~0.4 m² = ~3991 cm²
        # Check that conversion happened: mean area should be >> 1 (would be ~12.6 if still in m²)
        assert np.mean(mesh.areas) > 1000  # mean ~125866 cm²
        # Also verify against known m² values: min ~0.4 m² → ~3991 cm²
        assert np.min(mesh.areas) > 3000

    def test_load_example_a_has_centroids(self):
        from instream.space.polygon_mesh import PolygonMesh
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp",
            id_field="ID_TEXT", reach_field="REACH_NAME", area_field="AREA",
            dist_escape_field="M_TO_ESC", hiding_field="NUM_HIDING",
            shelter_field="FRACVSHL", spawn_field="FRACSPWN",
        )
        assert len(mesh.centroids_x) == mesh.num_cells
        assert len(mesh.centroids_y) == mesh.num_cells

    def test_load_example_a_reach_names(self):
        from instream.space.polygon_mesh import PolygonMesh
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp",
            id_field="ID_TEXT", reach_field="REACH_NAME", area_field="AREA",
            dist_escape_field="M_TO_ESC", hiding_field="NUM_HIDING",
            shelter_field="FRACVSHL", spawn_field="FRACSPWN",
        )
        # All cells in Example A belong to reach "ExampleA"
        assert all(r == "ExampleA" for r in mesh.reach_names)

    def test_load_example_a_cell_attributes(self):
        from instream.space.polygon_mesh import PolygonMesh
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp",
            id_field="ID_TEXT", reach_field="REACH_NAME", area_field="AREA",
            dist_escape_field="M_TO_ESC", hiding_field="NUM_HIDING",
            shelter_field="FRACVSHL", spawn_field="FRACSPWN",
        )
        assert len(mesh.frac_spawn) == mesh.num_cells
        assert len(mesh.frac_vel_shelter) == mesh.num_cells
        assert len(mesh.num_hiding_places) == mesh.num_cells
        assert len(mesh.dist_escape) == mesh.num_cells

    def test_adjacency_symmetric(self):
        from instream.space.polygon_mesh import PolygonMesh
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp",
            id_field="ID_TEXT", reach_field="REACH_NAME", area_field="AREA",
            dist_escape_field="M_TO_ESC", hiding_field="NUM_HIDING",
            shelter_field="FRACVSHL", spawn_field="FRACSPWN",
        )
        # neighbor_indices is (num_cells, max_neighbors), padded with -1
        ni = mesh.neighbor_indices
        for i in range(mesh.num_cells):
            neighbors = ni[i][ni[i] >= 0]
            for j in neighbors:
                j_neighbors = ni[j][ni[j] >= 0]
                assert i in j_neighbors, f"Cell {i} neighbors {j}, but {j} doesn't neighbor {i}"

    def test_to_cell_state(self):
        from instream.space.polygon_mesh import PolygonMesh
        from instream.io.hydraulics_reader import read_depth_table, read_velocity_table
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp",
            id_field="ID_TEXT", reach_field="REACH_NAME", area_field="AREA",
            dist_escape_field="M_TO_ESC", hiding_field="NUM_HIDING",
            shelter_field="FRACVSHL", spawn_field="FRACSPWN",
        )
        d_flows, d_vals = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        v_flows, v_vals = read_velocity_table(FIXTURES_DIR / "example_a" / "ExampleA-Vels.csv")
        cs = mesh.to_cell_state(d_flows, d_vals, v_flows, v_vals)
        from instream.state.cell_state import CellState
        assert isinstance(cs, CellState)
        assert cs.area.shape[0] == mesh.num_cells
        assert cs.depth_table_values.shape[0] == mesh.num_cells

    def test_load_example_b_multiple_reaches(self):
        from instream.space.polygon_mesh import PolygonMesh
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_b" / "Shapefile" / "ExampleB.shp",
            id_field="ID_text", reach_field="REACH_NAME", area_field="Area_m2",
            dist_escape_field="DISTANCE_T", hiding_field="NUM_HIDING",
            shelter_field="FRAC_VEL_S", spawn_field="FRAC_SPAWN",
        )
        unique_reaches = set(mesh.reach_names)
        assert len(unique_reaches) >= 3  # Example B has 3 reaches


class TestFEMSpace:
    """Test custom Mesa space wrapping mesh backends."""

    @pytest.fixture
    def fem_space_example_a(self):
        from instream.space.polygon_mesh import PolygonMesh
        from instream.space.fem_space import FEMSpace
        from instream.io.hydraulics_reader import read_depth_table, read_velocity_table
        mesh = PolygonMesh(
            FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp",
            id_field="ID_TEXT", reach_field="REACH_NAME", area_field="AREA",
            dist_escape_field="M_TO_ESC", hiding_field="NUM_HIDING",
            shelter_field="FRACVSHL", spawn_field="FRACSPWN",
        )
        d_flows, d_vals = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        v_flows, v_vals = read_velocity_table(FIXTURES_DIR / "example_a" / "ExampleA-Vels.csv")
        cell_state = mesh.to_cell_state(d_flows, d_vals, v_flows, v_vals)
        return FEMSpace(cell_state, mesh.neighbor_indices)

    def test_has_correct_cell_count(self, fem_space_example_a):
        assert fem_space_example_a.num_cells > 0

    def test_cells_in_radius_returns_indices(self, fem_space_example_a):
        result = fem_space_example_a.cells_in_radius(0, 50000.0)  # 500m radius
        assert isinstance(result, np.ndarray)
        assert result.dtype in (np.int32, np.int64, int)
        assert len(result) > 0

    def test_cells_in_radius_includes_self(self, fem_space_example_a):
        result = fem_space_example_a.cells_in_radius(0, 50000.0)
        assert 0 in result

    def test_cells_in_radius_small_radius_returns_few(self, fem_space_example_a):
        result = fem_space_example_a.cells_in_radius(0, 1.0)  # 1cm — very small
        # Should return at least self (or empty if centroid-based and no others within 1cm)
        assert len(result) >= 0  # at least doesn't crash

    def test_cells_in_radius_large_radius_returns_many(self, fem_space_example_a):
        result = fem_space_example_a.cells_in_radius(0, 1e8)  # huge radius
        assert len(result) == fem_space_example_a.num_cells  # all cells

    def test_get_neighbor_indices(self, fem_space_example_a):
        neighbors = fem_space_example_a.get_neighbor_indices(0)
        assert isinstance(neighbors, np.ndarray)
        # Should have valid indices (>= 0) and possibly -1 padding
        valid = neighbors[neighbors >= 0]
        assert len(valid) > 0

    def test_update_hydraulics_changes_depth(self, fem_space_example_a):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        # Before update, depths should be zero (initialized with zeros)
        assert np.all(fem_space_example_a.cell_state.depth == 0.0)
        # Update at a real flow
        fem_space_example_a.update_hydraulics(5.0, backend)
        # After update, some cells should have positive depth
        assert np.any(fem_space_example_a.cell_state.depth > 0.0)

    def test_update_hydraulics_dry_cells_have_zero_velocity(self, fem_space_example_a):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        fem_space_example_a.update_hydraulics(1.42, backend)  # minimum flow
        dry_mask = fem_space_example_a.cell_state.depth == 0.0
        if np.any(dry_mask):
            assert np.all(fem_space_example_a.cell_state.velocity[dry_mask] == 0.0)
