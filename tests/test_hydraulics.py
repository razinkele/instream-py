"""Tests for hydraulic interpolation — parametrized across backends."""
import numpy as np
import pytest


def _get_backend(name):
    from instream.backends import get_backend
    return get_backend(name)


class TestHydraulicsAllBackends:
    """Hydraulic interpolation tests parametrized across all available backends."""

    @pytest.fixture(params=["numpy", "numba"])
    def backend(self, request):
        try:
            return _get_backend(request.param)
        except (NotImplementedError, ImportError):
            pytest.skip(f"{request.param} backend not available")

    def test_exact_table_flow(self, backend):
        table_flows = np.array([1.0, 2.0, 3.0])
        depth_values = np.array([[10.0, 20.0, 30.0]])
        vel_values = np.array([[5.0, 10.0, 15.0]])
        depths, vels = backend.update_hydraulics(2.0, table_flows, depth_values, vel_values)
        np.testing.assert_allclose(depths, [20.0])
        np.testing.assert_allclose(vels, [10.0])

    def test_interpolation_between_flows(self, backend):
        table_flows = np.array([1.0, 3.0])
        depth_values = np.array([[10.0, 30.0]])
        vel_values = np.array([[5.0, 15.0]])
        depths, vels = backend.update_hydraulics(2.0, table_flows, depth_values, vel_values)
        np.testing.assert_allclose(depths, [20.0])
        np.testing.assert_allclose(vels, [10.0])

    def test_zero_flow_returns_zero(self, backend):
        table_flows = np.array([1.0, 2.0, 3.0])
        depth_values = np.array([[10.0, 20.0, 30.0]])
        vel_values = np.array([[5.0, 10.0, 15.0]])
        depths, vels = backend.update_hydraulics(0.0, table_flows, depth_values, vel_values)
        np.testing.assert_allclose(depths, [0.0])
        np.testing.assert_allclose(vels, [0.0])

    def test_multiple_cells(self, backend):
        table_flows = np.array([1.0, 2.0])
        depth_values = np.array([
            [10.0, 20.0],
            [30.0, 60.0],
            [5.0, 8.0],
        ])
        vel_values = np.array([
            [1.0, 2.0],
            [3.0, 6.0],
            [0.5, 0.8],
        ])
        depths, vels = backend.update_hydraulics(1.5, table_flows, depth_values, vel_values)
        np.testing.assert_allclose(depths, [15.0, 45.0, 6.5])
        np.testing.assert_allclose(vels, [1.5, 4.5, 0.65])

    def test_dry_cell_velocity_is_zero(self, backend):
        table_flows = np.array([1.0, 2.0])
        depth_values = np.array([[0.5, 1.0]])
        vel_values = np.array([[5.0, 10.0]])
        depths, vels = backend.update_hydraulics(0.0, table_flows, depth_values, vel_values)
        assert depths[0] == 0.0
        assert vels[0] == 0.0

    def test_large_cell_array(self, backend):
        """Test with realistic number of cells."""
        n_cells = 1000
        n_flows = 26
        table_flows = np.linspace(1.0, 100.0, n_flows)
        depth_values = np.random.rand(n_cells, n_flows) * 200
        vel_values = np.random.rand(n_cells, n_flows) * 100
        depths, vels = backend.update_hydraulics(50.0, table_flows, depth_values, vel_values)
        assert depths.shape == (n_cells,)
        assert vels.shape == (n_cells,)
        assert np.all(depths >= 0)


class TestBackendParity:
    """Verify numpy and numba produce identical results."""

    def test_hydraulics_numpy_numba_parity(self):
        try:
            np_backend = _get_backend("numpy")
            nb_backend = _get_backend("numba")
        except (NotImplementedError, ImportError):
            pytest.skip("Numba not available")

        table_flows = np.array([1.42, 2.12, 2.83, 3.54, 4.25, 5.66, 7.08, 14.16, 56.63, 1416.0])
        n_cells = 50
        rng = np.random.RandomState(42)
        depth_values = rng.rand(n_cells, len(table_flows)) * 200
        vel_values = rng.rand(n_cells, len(table_flows)) * 100

        for flow in [0.0, 1.42, 3.0, 10.0, 100.0, 2000.0]:
            d_np, v_np = np_backend.update_hydraulics(flow, table_flows, depth_values, vel_values)
            d_nb, v_nb = nb_backend.update_hydraulics(flow, table_flows, depth_values, vel_values)
            np.testing.assert_allclose(d_np, d_nb, rtol=1e-12,
                                       err_msg=f"Depth parity failed at flow={flow}")
            np.testing.assert_allclose(v_np, v_nb, rtol=1e-12,
                                       err_msg=f"Velocity parity failed at flow={flow}")
