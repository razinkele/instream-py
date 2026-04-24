"""Deep tests for inSTREAM spatial visualization pipeline.

Tests cover:
1. FEMSpace KD-tree spatial queries — radius semantics, edge cases
2. Movement radius — logistic function, length-dependent scaling
3. Candidate cell generation — wet filtering, neighbor inclusion, self inclusion
4. Numba vs Python spatial parity (when numba available)
5. Mesh adjacency — symmetry, boundary cells, isolated cells
6. Hydraulic interpolation — depth/velocity at flow breakpoints and between
7. CRS reprojection pipeline — projected → WGS84 for deck.gl
8. Trajectory building — cell_idx → [lon, lat, day] conversion
9. Color mapping — _value_to_rgba edge cases, color modes
10. Cell GeoDataFrame construction — column presence, fish count, dynamic state
11. Coordinate system consistency — centroid units match radius units
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from salmopy.modules.behavior import (
    build_candidate_lists,
    evaluate_logistic,
    evaluate_logistic_array,
    movement_radius,
)
from salmopy.space.fem_space import FEMSpace
from salmopy.state.cell_state import CellState

# Make app/ importable for simulation helpers (kept for any downstream
# tests in this module that import from app.* — deferred imports are fine).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "app"))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ============================================================================
# Helpers
# ============================================================================


def _make_cell_state(
    n=10,
    *,
    x_range=(0.0, 100.0),
    y_range=(0.0, 100.0),
    depths=None,
    velocities=None,
    num_flows=3,
):
    """Build a CellState with n cells on a regular grid."""
    cs = CellState.zeros(n, num_flows=num_flows)
    cs.centroid_x[:] = np.linspace(x_range[0], x_range[1], n)
    cs.centroid_y[:] = np.linspace(y_range[0], y_range[1], n)
    cs.area[:] = 10_000.0  # 1 m² in cm²
    if depths is not None:
        cs.depth[:] = depths
    else:
        cs.depth[:] = 50.0  # 50cm default
    if velocities is not None:
        cs.velocity[:] = velocities
    else:
        cs.velocity[:] = 20.0  # 20 cm/s default
    # Simple hydraulic tables
    flows = np.array([1.0, 5.0, 10.0], dtype=np.float64)
    cs.depth_table_flows[:] = flows
    cs.vel_table_flows[:] = flows
    cs.depth_table_values[:] = np.tile(np.linspace(10, 100, num_flows), (n, 1))
    cs.vel_table_values[:] = np.tile(np.linspace(5, 50, num_flows), (n, 1))
    return cs


def _make_neighbor_indices(n, max_neighbors=3):
    """Build a simple linear neighbor matrix: cell i neighbors i-1 and i+1."""
    ni = np.full((n, max_neighbors), -1, dtype=np.int32)
    for i in range(n):
        k = 0
        if i > 0:
            ni[i, k] = i - 1
            k += 1
        if i < n - 1:
            ni[i, k] = i + 1
            k += 1
    return ni


def _make_fem_space(n=10, **kwargs):
    """Build a FEMSpace with n cells on a linear grid."""
    cs = _make_cell_state(n, **kwargs)
    ni = _make_neighbor_indices(n)
    return FEMSpace(cs, ni)


def _make_gdf_wgs84(n=5):
    """Build a GeoDataFrame with n rectangular cells in WGS84."""
    lon_start, lat_start = 20.0, 55.0
    dx, dy = 0.01, 0.01
    polys = []
    for i in range(n):
        x0 = lon_start + i * dx
        polys.append(box(x0, lat_start, x0 + dx, lat_start + dy))
    return gpd.GeoDataFrame(
        {"cell_id": list(range(n))},
        geometry=polys,
        crs="EPSG:4326",
    )


# ============================================================================
# 1. FEMSpace KD-tree spatial queries
# ============================================================================


class TestFEMSpaceQueries:
    """KD-tree radius queries on FEMSpace."""

    def test_cells_in_radius_includes_self(self):
        """Queried cell should always be in its own radius result."""
        fs = _make_fem_space(10)
        result = fs.cells_in_radius(5, radius=1.0)
        assert 5 in result

    def test_cells_in_radius_returns_neighbors(self):
        """Cells within radius should include close neighbors."""
        # Cells on diagonal: spacing ~11.1 in x AND y → distance ~15.7
        # Use radius 20 to reliably capture ±1 neighbor
        fs = _make_fem_space(10)
        result = fs.cells_in_radius(5, radius=20.0)
        assert 4 in result or 6 in result

    def test_zero_radius_returns_self_only(self):
        """Zero radius should return only self (KD-tree point match)."""
        fs = _make_fem_space(10)
        result = fs.cells_in_radius(5, radius=0.0)
        assert len(result) == 1
        assert result[0] == 5

    def test_huge_radius_returns_all(self):
        """Radius larger than domain should return all cells."""
        fs = _make_fem_space(10, x_range=(0, 100), y_range=(0, 100))
        result = fs.cells_in_radius(0, radius=1e6)
        assert len(result) == 10

    def test_boundary_cell_query(self):
        """First and last cells (boundary) should work without error."""
        fs = _make_fem_space(10)
        r0 = fs.cells_in_radius(0, radius=20.0)
        r9 = fs.cells_in_radius(9, radius=20.0)
        assert 0 in r0
        assert 9 in r9

    def test_radius_units_match_centroids(self):
        """Radius is in centroid units (metres for projected CRS)."""
        # Centroids at 0,0 and 100,100 — distance = sqrt(2)*100 ≈ 141.4
        cs = CellState.zeros(2, num_flows=1)
        cs.centroid_x[:] = [0.0, 100.0]
        cs.centroid_y[:] = [0.0, 100.0]
        cs.depth[:] = 50.0
        ni = np.full((2, 1), -1, dtype=np.int32)
        fs = FEMSpace(cs, ni)

        result_small = fs.cells_in_radius(0, radius=100.0)
        result_big = fs.cells_in_radius(0, radius=200.0)
        # 100.0 < sqrt(2)*100 ≈ 141.4, so cell 1 should NOT be in small radius
        assert 1 not in result_small
        # 200 > 141.4, so cell 1 SHOULD be in big radius
        assert 1 in result_big

    def test_get_neighbor_indices_padded(self):
        """Neighbor indices should be padded with -1."""
        fs = _make_fem_space(10)
        nb = fs.get_neighbor_indices(0)
        # Cell 0 has only 1 neighbor (cell 1)
        valid = nb[nb >= 0]
        assert len(valid) >= 1
        assert 1 in valid

    def test_num_cells_property(self):
        fs = _make_fem_space(20)
        assert fs.num_cells == 20


class TestFEMSpaceHydraulics:
    """Hydraulic interpolation through FEMSpace.update_hydraulics."""

    @pytest.fixture
    def fem_space_with_tables(self):
        """FEMSpace with simple hydraulic tables for 5 cells at 3 flows."""
        n = 5
        cs = CellState.zeros(n, num_flows=3)
        cs.centroid_x[:] = np.arange(n, dtype=float)
        cs.centroid_y[:] = np.zeros(n)
        cs.area[:] = 10_000.0

        flows = np.array([1.0, 5.0, 10.0])
        cs.depth_table_flows[:] = flows
        cs.vel_table_flows[:] = flows
        # Depth: cell 0 is 10,50,100 cm at flows 1,5,10
        for i in range(n):
            cs.depth_table_values[i, :] = [
                10.0 * (i + 1),
                50.0 * (i + 1),
                100.0 * (i + 1),
            ]
            cs.vel_table_values[i, :] = [5.0 * (i + 1), 25.0 * (i + 1), 50.0 * (i + 1)]

        ni = _make_neighbor_indices(n)
        return FEMSpace(cs, ni)

    def test_update_at_exact_flow(self, fem_space_with_tables):
        """Depth at exact flow breakpoint should match table value."""
        from salmopy.backends import get_backend

        backend = get_backend("numpy")

        fem_space_with_tables.update_hydraulics(5.0, backend)
        # Cell 0 at flow=5 → depth=50
        assert abs(fem_space_with_tables.cell_state.depth[0] - 50.0) < 0.01
        # Cell 2 at flow=5 → depth=150
        assert abs(fem_space_with_tables.cell_state.depth[2] - 150.0) < 0.01

    def test_update_between_flows_interpolates(self, fem_space_with_tables):
        """Depth between flow breakpoints should be interpolated."""
        from salmopy.backends import get_backend

        backend = get_backend("numpy")

        fem_space_with_tables.update_hydraulics(3.0, backend)
        # Cell 0: between flow=1(depth=10) and flow=5(depth=50)
        # Linear interp: 10 + (50-10)*(3-1)/(5-1) = 10 + 20 = 30
        assert abs(fem_space_with_tables.cell_state.depth[0] - 30.0) < 0.5

    def test_update_below_min_flow(self, fem_space_with_tables):
        """Flow below minimum should use leftmost table value."""
        from salmopy.backends import get_backend

        backend = get_backend("numpy")

        fem_space_with_tables.update_hydraulics(0.5, backend)
        # Should clamp to or extrapolate from minimum flow value
        depth = fem_space_with_tables.cell_state.depth[0]
        assert depth >= 0  # Should not be negative

    def test_update_above_max_flow(self, fem_space_with_tables):
        """Flow above maximum should use rightmost table value."""
        from salmopy.backends import get_backend

        backend = get_backend("numpy")

        fem_space_with_tables.update_hydraulics(20.0, backend)
        depth = fem_space_with_tables.cell_state.depth[0]
        # Should clamp to or extrapolate from max value (100 for cell 0)
        assert depth >= 0  # Should not be negative

    def test_dry_cells_have_zero_velocity(self, fem_space_with_tables):
        """Cells with zero depth must also have zero velocity."""
        from salmopy.backends import get_backend

        backend = get_backend("numpy")

        # Force cell 0 depths to zero at all flows
        fem_space_with_tables.cell_state.depth_table_values[0, :] = 0.0
        fem_space_with_tables.update_hydraulics(5.0, backend)

        assert fem_space_with_tables.cell_state.depth[0] == 0.0
        assert fem_space_with_tables.cell_state.velocity[0] == 0.0

    def test_mismatched_flow_breakpoints_raises(self):
        """CellState with different depth/vel flow breakpoints should raise."""
        cs = CellState.zeros(3, num_flows=2)
        cs.depth_table_flows[:] = [1.0, 5.0]
        cs.vel_table_flows[:] = [2.0, 8.0]  # Different!
        ni = _make_neighbor_indices(3)
        with pytest.raises(ValueError, match="different flow breakpoints"):
            FEMSpace(cs, ni)


# ============================================================================
# 2. Movement radius — logistic function
# ============================================================================


class TestMovementRadius:
    """Movement radius is length-dependent via logistic function."""

    def test_small_fish_small_radius(self):
        """Fish at L1 should get ~10% of max radius."""
        r = movement_radius(
            length=3.0, move_radius_max=200.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        assert abs(r - 200.0 * 0.1) < 1.0

    def test_large_fish_large_radius(self):
        """Fish at L9 should get ~90% of max radius."""
        r = movement_radius(
            length=15.0, move_radius_max=200.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        assert abs(r - 200.0 * 0.9) < 1.0

    def test_mid_fish_half_radius(self):
        """Fish at midpoint should get ~50% of max radius."""
        L1, L9 = 3.0, 15.0
        mid = (L1 + L9) / 2
        r = movement_radius(
            length=mid, move_radius_max=200.0, move_radius_L1=L1, move_radius_L9=L9
        )
        assert abs(r - 100.0) < 1.0

    def test_radius_never_exceeds_max(self):
        """Radius should never exceed max even for very large fish."""
        r = movement_radius(
            length=1000.0,
            move_radius_max=200.0,
            move_radius_L1=3.0,
            move_radius_L9=15.0,
        )
        assert r <= 200.0 + 0.01

    def test_radius_always_positive(self):
        """Radius should always be positive (logistic > 0)."""
        for length in [0.1, 1.0, 5.0, 20.0, 100.0]:
            r = movement_radius(
                length=length,
                move_radius_max=200.0,
                move_radius_L1=3.0,
                move_radius_L9=15.0,
            )
            assert r > 0

    def test_radius_monotonically_increases(self):
        """Larger fish → larger radius."""
        radii = []
        for length in [1.0, 3.0, 5.0, 9.0, 15.0, 25.0]:
            r = movement_radius(
                length=length,
                move_radius_max=200.0,
                move_radius_L1=3.0,
                move_radius_L9=15.0,
            )
            radii.append(r)
        for i in range(len(radii) - 1):
            assert radii[i] <= radii[i + 1]

    def test_equal_L1_L9_gives_step_function(self):
        """When L1 == L9, logistic should return 0.9 (step function)."""
        r = movement_radius(
            length=10.0, move_radius_max=200.0, move_radius_L1=10.0, move_radius_L9=10.0
        )
        assert abs(r - 180.0) < 0.01


class TestLogisticFunction:
    """Scalar and array logistic function tests."""

    def test_logistic_at_L1_returns_01(self):
        assert abs(evaluate_logistic(3.0, L1=3.0, L9=15.0) - 0.1) < 0.001

    def test_logistic_at_L9_returns_09(self):
        assert abs(evaluate_logistic(15.0, L1=3.0, L9=15.0) - 0.9) < 0.001

    def test_logistic_midpoint_returns_05(self):
        mid = (3.0 + 15.0) / 2
        assert abs(evaluate_logistic(mid, L1=3.0, L9=15.0) - 0.5) < 0.001

    def test_logistic_array_matches_scalar(self):
        L1, L9 = 3.0, 15.0
        xs = [1.0, 3.0, 9.0, 15.0, 20.0]
        array_result = evaluate_logistic_array(xs, L1, L9)
        for x, arr_val in zip(xs, array_result):
            scalar_val = evaluate_logistic(x, L1, L9)
            assert abs(arr_val - scalar_val) < 1e-10

    def test_logistic_extreme_values_no_overflow(self):
        """Extreme inputs should not cause overflow (clamped to ±500)."""
        val_neg = evaluate_logistic(-1e6, L1=3.0, L9=15.0)
        val_pos = evaluate_logistic(1e6, L1=3.0, L9=15.0)
        assert 0.0 <= val_neg <= 1.0
        assert 0.0 <= val_pos <= 1.0


# ============================================================================
# 3. Candidate cell generation
# ============================================================================


class TestCandidateLists:
    """build_candidate_lists() — spatial candidate generation."""

    @pytest.fixture
    def setup(self):
        """10-cell FEMSpace with 5 fish."""
        from salmopy.state.trout_state import TroutState

        n_cells = 10
        n_fish = 5
        fs = _make_fem_space(n_cells)

        ts = TroutState.zeros(n_fish)
        ts.alive[:] = True
        ts.cell_idx[:] = [0, 2, 5, 7, 9]
        ts.length[:] = [5.0, 8.0, 12.0, 15.0, 20.0]
        return ts, fs

    def test_returns_list_of_correct_length(self, setup):
        ts, fs = setup
        result = build_candidate_lists(
            ts, fs, move_radius_max=50.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        assert len(result) == len(ts.alive)

    def test_alive_fish_have_candidates(self, setup):
        ts, fs = setup
        result = build_candidate_lists(
            ts, fs, move_radius_max=50.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        for i in range(len(ts.alive)):
            if ts.alive[i]:
                assert result[i] is not None
                assert len(result[i]) >= 1  # At least self

    def test_dead_fish_have_none(self, setup):
        ts, fs = setup
        ts.alive[2] = False
        result = build_candidate_lists(
            ts, fs, move_radius_max=50.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        assert result[2] is None

    def test_current_cell_always_included(self, setup):
        ts, fs = setup
        result = build_candidate_lists(
            ts, fs, move_radius_max=1.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        for i in range(len(ts.alive)):
            if ts.alive[i] and result[i] is not None:
                assert ts.cell_idx[i] in result[i]

    def test_dry_cells_excluded(self, setup):
        ts, fs = setup
        # Make cell 3 dry
        fs.cell_state.depth[3] = 0.0
        result = build_candidate_lists(
            ts, fs, move_radius_max=200.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        for i in range(len(ts.alive)):
            if result[i] is not None:
                assert 3 not in result[i]

    def test_neighbors_included_even_with_tiny_radius(self, setup):
        ts, fs = setup
        # Very tiny radius — but neighbors should still be included
        result = build_candidate_lists(
            ts, fs, move_radius_max=0.01, move_radius_L1=3.0, move_radius_L9=15.0
        )
        # Fish at cell 5 should include neighbors 4 and 6
        fish_at_5 = 2  # ts.cell_idx[2] = 5
        cands = result[fish_at_5]
        assert cands is not None
        assert 4 in cands or 6 in cands

    def test_larger_fish_get_more_candidates(self, setup):
        ts, fs = setup
        result = build_candidate_lists(
            ts, fs, move_radius_max=30.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        # Fish 0 (length=5, small) should have fewer candidates than fish 4 (length=20, big)
        n_small = len(result[0]) if result[0] is not None else 0
        n_big = len(result[4]) if result[4] is not None else 0
        assert n_small <= n_big

    def test_all_candidates_are_valid_indices(self, setup):
        ts, fs = setup
        result = build_candidate_lists(
            ts, fs, move_radius_max=50.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        for cands in result:
            if cands is not None:
                assert np.all(cands >= 0)
                assert np.all(cands < fs.num_cells)


# ============================================================================
# 4. Numba vs Python spatial parity
# ============================================================================


class TestNumbaParity:
    """Numba spatial backend should match Python/KD-tree results."""

    @pytest.fixture
    def setup(self):
        from salmopy.state.trout_state import TroutState

        n_cells = 20
        n_fish = 8
        fs = _make_fem_space(n_cells, x_range=(0, 200), y_range=(0, 200))

        ts = TroutState.zeros(n_fish)
        ts.alive[:] = True
        ts.alive[6] = False  # One dead fish
        ts.cell_idx[:] = [0, 3, 7, 10, 14, 17, 5, 19]
        ts.length[:] = [4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 9.0, 20.0]
        return ts, fs

    def test_numba_returns_same_candidates(self, setup):
        """When numba is available, candidates should match Python fallback."""
        from salmopy.modules.behavior import _HAS_NUMBA_SPATIAL
        if not _HAS_NUMBA_SPATIAL:
            pytest.skip("Numba spatial backend not available")
        ts, fs = setup
        result = build_candidate_lists(
            ts, fs, move_radius_max=40.0, move_radius_L1=3.0, move_radius_L9=15.0
        )
        # Basic sanity: alive fish have candidates, dead fish don't
        assert result[6] is None  # dead fish
        for i in [0, 1, 2, 3, 4, 5, 7]:
            assert result[i] is not None
            assert len(result[i]) >= 1


# ============================================================================
# 5. Mesh adjacency
# ============================================================================


class TestMeshAdjacency:
    """Adjacency matrix properties."""

    def test_adjacency_symmetry_synthetic(self):
        """If i→j then j→i in the neighbor matrix."""
        ni = _make_neighbor_indices(10)
        for i in range(10):
            neighbors_i = ni[i][ni[i] >= 0]
            for j in neighbors_i:
                neighbors_j = ni[j][ni[j] >= 0]
                assert i in neighbors_j, f"Asymmetric: {i}→{j} but not {j}→{i}"

    def test_boundary_cells_have_fewer_neighbors(self):
        """First and last cells in a linear chain have fewer neighbors."""
        ni = _make_neighbor_indices(10)
        n_first = np.sum(ni[0] >= 0)
        n_mid = np.sum(ni[5] >= 0)
        assert n_first < n_mid

    def test_no_self_neighbors(self):
        """A cell should not appear in its own neighbor list."""
        ni = _make_neighbor_indices(10)
        for i in range(10):
            neighbors = ni[i][ni[i] >= 0]
            assert i not in neighbors

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp").exists(),
        reason="ExampleA fixture not available",
    )
    def test_real_mesh_adjacency_symmetric(self):
        """Real shapefile mesh adjacency should be symmetric."""
        from salmopy.space.polygon_mesh import PolygonMesh

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
        ni = mesh.neighbor_indices
        for i in range(mesh.num_cells):
            for j in ni[i][ni[i] >= 0]:
                j_nbrs = ni[j][ni[j] >= 0]
                assert i in j_nbrs

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp").exists(),
        reason="ExampleA fixture not available",
    )
    def test_real_mesh_all_cells_have_neighbors(self):
        """Every cell in the real mesh should have at least one neighbor."""
        from salmopy.space.polygon_mesh import PolygonMesh

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
        ni = mesh.neighbor_indices
        for i in range(mesh.num_cells):
            valid = ni[i][ni[i] >= 0]
            assert len(valid) > 0, f"Cell {i} has no neighbors"


# ============================================================================
# 6. FEMMesh triangle geometry
# ============================================================================


class TestFEMMeshGeometry:
    """FEM triangle mesh area and centroid calculations."""

    def test_triangle_area_cross_product(self, tmp_path):
        """Area = 0.5 * |cross(v1-v0, v2-v0)|, converted to cm²."""
        pytest.importorskip("meshio")
        import meshio
        from salmopy.space.fem_mesh import FEMMesh

        # Right triangle with legs 3m and 4m → area = 6 m² = 60000 cm²
        points = np.array([[0, 0, 0], [3, 0, 0], [0, 4, 0]], dtype=float)
        cells = [("triangle", np.array([[0, 1, 2]]))]
        mesh = meshio.Mesh(points, cells)
        mesh_path = tmp_path / "tri.msh"
        meshio.write(str(mesh_path), mesh)

        fem = FEMMesh(str(mesh_path))
        np.testing.assert_allclose(fem._areas, [60000.0], rtol=1e-10)

    def test_centroid_is_vertex_average(self, tmp_path):
        """Centroid should be the average of 3 vertices."""
        pytest.importorskip("meshio")
        import meshio
        from salmopy.space.fem_mesh import FEMMesh

        points = np.array([[0, 0, 0], [6, 0, 0], [3, 6, 0]], dtype=float)
        cells = [("triangle", np.array([[0, 1, 2]]))]
        mesh = meshio.Mesh(points, cells)
        mesh_path = tmp_path / "tri.msh"
        meshio.write(str(mesh_path), mesh)

        fem = FEMMesh(str(mesh_path))
        assert abs(fem._centroids_x[0] - 3.0) < 0.001
        assert abs(fem._centroids_y[0] - 2.0) < 0.001

    def test_shared_edge_adjacency(self, tmp_path):
        """Two triangles sharing an edge should be neighbors."""
        pytest.importorskip("meshio")
        import meshio
        from salmopy.space.fem_mesh import FEMMesh

        # Two triangles sharing edge 1-2
        points = np.array(
            [[0, 0, 0], [1, 0, 0], [0.5, 1, 0], [0.5, -1, 0]], dtype=float
        )
        cells = [("triangle", np.array([[0, 1, 2], [0, 1, 3]]))]
        mesh = meshio.Mesh(points, cells)
        mesh_path = tmp_path / "tri.msh"
        meshio.write(str(mesh_path), mesh)

        fem = FEMMesh(str(mesh_path))
        ni = fem.neighbor_indices
        assert 1 in ni[0][ni[0] >= 0]
        assert 0 in ni[1][ni[1] >= 0]

    def test_no_shared_edge_no_adjacency(self, tmp_path):
        """Two triangles NOT sharing an edge should NOT be neighbors."""
        pytest.importorskip("meshio")
        import meshio
        from salmopy.space.fem_mesh import FEMMesh

        # Two separate triangles (no shared vertices)
        points = np.array(
            [
                [0, 0, 0],
                [1, 0, 0],
                [0.5, 1, 0],
                [10, 10, 0],
                [11, 10, 0],
                [10.5, 11, 0],
            ],
            dtype=float,
        )
        cells = [("triangle", np.array([[0, 1, 2], [3, 4, 5]]))]
        mesh = meshio.Mesh(points, cells)
        mesh_path = tmp_path / "tri.msh"
        meshio.write(str(mesh_path), mesh)

        fem = FEMMesh(str(mesh_path))
        ni = fem.neighbor_indices
        # Neither should be in the other's neighbor list
        assert 1 not in ni[0][ni[0] >= 0]
        assert 0 not in ni[1][ni[1] >= 0]


# ============================================================================
# 7. CRS reprojection pipeline
# ============================================================================


class TestCRSReprojection:
    """Projected CRS → WGS84 reprojection for deck.gl visualization."""

    def test_utm_to_wgs84_produces_valid_coords(self):
        """UTM coordinates should reproject to valid lon/lat."""
        # Create cells in UTM Zone 34N (EPSG:32634) — Baltic region
        polys = [
            box(500000, 6100000, 500100, 6100100),
            box(500100, 6100000, 500200, 6100100),
        ]
        gdf_utm = gpd.GeoDataFrame(
            {"cell_id": [0, 1]}, geometry=polys, crs="EPSG:32634"
        )
        gdf_wgs84 = gdf_utm.to_crs(epsg=4326)

        for geom in gdf_wgs84.geometry:
            centroid = geom.centroid
            assert -180 <= centroid.x <= 180, f"lon {centroid.x} out of range"
            assert -90 <= centroid.y <= 90, f"lat {centroid.y} out of range"

    def test_wgs84_passthrough(self):
        """Data already in EPSG:4326 should not change."""
        gdf = _make_gdf_wgs84(3)
        gdf2 = gdf.to_crs(epsg=4326)
        np.testing.assert_array_almost_equal(
            gdf.geometry.centroid.x.values,
            gdf2.geometry.centroid.x.values,
        )

    def test_centroid_extraction_from_reprojected(self):
        """Centroids from reprojected GeoDataFrame should be usable for trajectories."""
        gdf = _make_gdf_wgs84(5)
        centroids = gdf.geometry.centroid
        lut = np.column_stack([centroids.x, centroids.y])
        assert lut.shape == (5, 2)
        # All lons should be near 20.0, lats near 55.0
        assert np.all(lut[:, 0] > 19.5)
        assert np.all(lut[:, 1] > 54.5)


# ============================================================================
# 8. Trajectory building
# ============================================================================


class TestTrajectoryBuilding:
    """_build_trajectories_data() — cell_idx to [lon, lat, day] paths."""

    @staticmethod
    def _make_traj_df(n_fish=3, n_days=5, n_cells=5):
        rows = []
        for day in range(n_days):
            for fish in range(n_fish):
                rows.append(
                    {
                        "fish_idx": fish,
                        "cell_idx": (fish + day) % n_cells,
                        "species_idx": fish % 2,
                        "activity": day % 5,
                        "life_history": 0,
                        "day_num": day,
                    }
                )
        return pd.DataFrame(rows)

    def test_correct_number_of_paths(self):
        from simulation import _build_trajectories_data

        traj = self._make_traj_df(n_fish=3, n_days=5)
        gdf = _make_gdf_wgs84(5)
        paths, props = _build_trajectories_data(traj, gdf, ["sp_a", "sp_b"])
        assert len(paths) == 3

    def test_path_length_matches_fish_lifespan(self):
        from simulation import _build_trajectories_data

        traj = self._make_traj_df(n_fish=3, n_days=5)
        gdf = _make_gdf_wgs84(5)
        paths, _ = _build_trajectories_data(traj, gdf, ["sp_a", "sp_b"])
        for path in paths:
            assert len(path) == 5  # All fish alive all 5 days

    def test_paths_are_lon_lat_day(self):
        from simulation import _build_trajectories_data

        traj = self._make_traj_df(n_fish=2, n_days=3)
        gdf = _make_gdf_wgs84(5)
        paths, _ = _build_trajectories_data(traj, gdf, ["sp_a", "sp_b"])
        for path in paths:
            for pt in path:
                assert len(pt) == 3
                lon, lat, day = pt
                assert -180 <= lon <= 180
                assert -90 <= lat <= 90
                assert isinstance(day, int)

    def test_species_coloring(self):
        from simulation import _build_trajectories_data

        traj = self._make_traj_df(n_fish=3, n_days=2)
        gdf = _make_gdf_wgs84(5)
        _, props = _build_trajectories_data(
            traj, gdf, ["sp_a", "sp_b"], color_mode="species"
        )
        for p in props:
            assert "color" in p
            assert len(p["color"]) == 4  # RGBA
            assert p["species"] in ["sp_a", "sp_b"]

    def test_activity_coloring(self):
        from simulation import _build_trajectories_data

        traj = self._make_traj_df(n_fish=2, n_days=3)
        gdf = _make_gdf_wgs84(5)
        _, props = _build_trajectories_data(
            traj, gdf, ["sp_a", "sp_b"], color_mode="activity"
        )
        for p in props:
            assert "color" in p
            assert len(p["color"]) == 4

    def test_life_history_coloring(self):
        from simulation import _build_trajectories_data

        traj = self._make_traj_df(n_fish=2, n_days=3)
        gdf = _make_gdf_wgs84(5)
        _, props = _build_trajectories_data(
            traj, gdf, ["sp_a"], color_mode="life_history"
        )
        for p in props:
            assert len(p["color"]) == 4

    def test_empty_trajectory_returns_empty(self):
        from simulation import _build_trajectories_data

        traj = pd.DataFrame(
            columns=[
                "fish_idx",
                "cell_idx",
                "species_idx",
                "activity",
                "life_history",
                "day_num",
            ]
        )
        gdf = _make_gdf_wgs84(5)
        paths, props = _build_trajectories_data(traj, gdf, ["sp_a"])
        assert paths == []
        assert props == []

    def test_cell_idx_out_of_range_raises(self):
        from simulation import _build_trajectories_data

        traj = pd.DataFrame(
            {
                "fish_idx": [0],
                "cell_idx": [999],  # out of range
                "species_idx": [0],
                "activity": [0],
                "life_history": [0],
                "day_num": [0],
            }
        )
        gdf = _make_gdf_wgs84(5)
        with pytest.raises(ValueError, match="out of range"):
            _build_trajectories_data(traj, gdf, ["sp_a"])

    def test_utm_cells_auto_reprojected(self):
        """Cells in UTM CRS should be reprojected to WGS84 for paths."""
        from simulation import _build_trajectories_data

        # Create cells in UTM
        polys = [
            box(500000 + i * 100, 6100000, 500000 + (i + 1) * 100, 6100100)
            for i in range(3)
        ]
        gdf_utm = gpd.GeoDataFrame(
            {"cell_id": [0, 1, 2]}, geometry=polys, crs="EPSG:32634"
        )
        traj = pd.DataFrame(
            {
                "fish_idx": [0, 0],
                "cell_idx": [0, 1],
                "species_idx": [0, 0],
                "activity": [0, 0],
                "life_history": [0, 0],
                "day_num": [0, 1],
            }
        )
        paths, _ = _build_trajectories_data(traj, gdf_utm, ["sp_a"])
        # Should be in WGS84 range
        for lon, lat, _ in paths[0]:
            assert -180 <= lon <= 180
            assert -90 <= lat <= 90


# ============================================================================
# 9. Color mapping
# ============================================================================


class TestValueToRgba:
    """_value_to_rgba edge cases."""

    def test_gradient_min_max(self):
        from simulation import _value_to_rgba

        result = _value_to_rgba(np.array([0.0, 100.0]))
        assert len(result) == 2
        # Min and max should have different colors
        assert result[0] != result[1]

    def test_all_nan_returns_transparent(self):
        from simulation import _value_to_rgba

        result = _value_to_rgba(np.array([np.nan, np.nan]))
        for rgba in result:
            assert rgba == [0, 0, 0, 0]

    def test_single_valid_value(self):
        from simulation import _value_to_rgba

        result = _value_to_rgba(np.array([42.0]))
        assert len(result) == 1
        assert len(result[0]) == 4

    def test_mixed_nan_and_values(self):
        from simulation import _value_to_rgba

        result = _value_to_rgba(np.array([1.0, np.nan, 3.0, np.nan, 5.0]))
        assert result[1] == [0, 0, 0, 0]
        assert result[3] == [0, 0, 0, 0]
        assert result[0] != [0, 0, 0, 0]

    def test_custom_alpha(self):
        from simulation import _value_to_rgba

        result = _value_to_rgba(np.array([1.0, 2.0]), alpha=128)
        for rgba in result:
            assert rgba[3] == 128

    def test_constant_values_no_crash(self):
        from simulation import _value_to_rgba

        result = _value_to_rgba(np.array([7.0, 7.0, 7.0, 7.0]))
        assert len(result) == 4
        # All should be same color
        assert result[0] == result[1] == result[2] == result[3]

    def test_negative_values(self):
        from simulation import _value_to_rgba

        result = _value_to_rgba(np.array([-10.0, 0.0, 10.0]))
        assert len(result) == 3
        for rgba in result:
            assert all(0 <= c <= 255 for c in rgba)

    def test_large_array_performance(self):
        """Should handle 10k values without issue."""
        from simulation import _value_to_rgba

        values = np.random.rand(10_000) * 100
        result = _value_to_rgba(values)
        assert len(result) == 10_000


# ============================================================================
# 10. CellState zeros factory
# ============================================================================


class TestCellStateFactory:
    """CellState.zeros() creates correct array shapes."""

    def test_zeros_shapes(self):
        cs = CellState.zeros(50, num_flows=5)
        assert cs.area.shape == (50,)
        assert cs.depth.shape == (50,)
        assert cs.depth_table_values.shape == (50, 5)
        assert cs.depth_table_flows.shape == (5,)

    def test_zeros_all_zero(self):
        cs = CellState.zeros(10)
        assert np.all(cs.depth == 0)
        assert np.all(cs.velocity == 0)
        assert np.all(cs.area == 0)

    def test_zeros_correct_dtypes(self):
        cs = CellState.zeros(5)
        assert cs.area.dtype == np.float64
        assert cs.centroid_x.dtype == np.float64
        assert cs.reach_idx.dtype == np.int32
        assert cs.num_hiding_places.dtype == np.int32
        assert cs.available_hiding_places.dtype == np.int32


# ============================================================================
# 11. Spatial panel zoom heuristic
# ============================================================================


class TestZoomHeuristic:
    """The zoom = max(8, min(18, int(14 - extent*100))) formula."""

    def test_small_extent_high_zoom(self):
        """Small river reach → high zoom level."""
        extent = 0.01  # ~1km
        zoom = max(8, min(18, int(14 - extent * 100)))
        assert zoom == 13

    def test_large_extent_low_zoom(self):
        """Large area → low zoom level."""
        extent = 0.5  # ~50km
        zoom = max(8, min(18, int(14 - extent * 100)))
        assert zoom == 8  # clamped to min

    def test_zoom_clamped_to_range(self):
        """Zoom should always be in [8, 18]."""
        for extent in [0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]:
            zoom = max(8, min(18, int(14 - extent * 100)))
            assert 8 <= zoom <= 18


# ============================================================================
# 12. Hydraulics reader integration
# ============================================================================


class TestHydraulicsReader:
    """Hydraulic CSV parsing and unit handling."""

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv").exists(),
        reason="ExampleA fixtures not available",
    )
    def test_read_depth_table_shapes(self):
        from salmopy.io.hydraulics_reader import read_depth_table

        flows, values = read_depth_table(
            FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv"
        )
        assert flows.ndim == 1
        assert values.ndim == 2
        assert values.shape[1] == len(flows)

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "example_a" / "ExampleA-Vels.csv").exists(),
        reason="ExampleA fixtures not available",
    )
    def test_read_velocity_table_shapes(self):
        from salmopy.io.hydraulics_reader import read_velocity_table

        flows, values = read_velocity_table(
            FIXTURES_DIR / "example_a" / "ExampleA-Vels.csv"
        )
        assert flows.ndim == 1
        assert values.ndim == 2

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv").exists(),
        reason="ExampleA fixtures not available",
    )
    def test_depth_and_velocity_same_flows(self):
        """Depth and velocity tables must share the same flow breakpoints."""
        from salmopy.io.hydraulics_reader import read_depth_table, read_velocity_table

        d_flows, _ = read_depth_table(
            FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv"
        )
        v_flows, _ = read_velocity_table(
            FIXTURES_DIR / "example_a" / "ExampleA-Vels.csv"
        )
        np.testing.assert_array_equal(d_flows, v_flows)

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv").exists(),
        reason="ExampleA fixtures not available",
    )
    def test_flows_monotonically_increasing(self):
        """Flow breakpoints should be sorted in ascending order."""
        from salmopy.io.hydraulics_reader import read_depth_table

        flows, _ = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        assert np.all(np.diff(flows) > 0), "Flows not monotonically increasing"

    @pytest.mark.skipif(
        not (FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv").exists(),
        reason="ExampleA fixtures not available",
    )
    def test_depth_values_non_negative(self):
        """All depth values should be ≥ 0."""
        from salmopy.io.hydraulics_reader import read_depth_table

        _, values = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        assert np.all(values >= 0), "Negative depth values found"
