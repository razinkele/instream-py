"""Tests for numpy backend baseline kernels."""
import numpy as np
import pytest


class TestHydraulicsInterp:
    """Test hydraulic depth/velocity interpolation."""

    def test_single_flow_single_cell(self):
        """Interpolate depth at a flow that's exactly in the table."""
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        table_flows = np.array([1.0, 2.0, 3.0])
        depth_values = np.array([[10.0, 20.0, 30.0]])  # 1 cell
        vel_values = np.array([[5.0, 10.0, 15.0]])
        depths, vels = b.update_hydraulics(2.0, table_flows, depth_values, vel_values)
        np.testing.assert_allclose(depths, [20.0])
        np.testing.assert_allclose(vels, [10.0])

    def test_interpolation_between_flows(self):
        """Midpoint between two tabulated flows gives linear interpolation."""
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        table_flows = np.array([1.0, 3.0])
        depth_values = np.array([[10.0, 30.0]])  # 1 cell
        vel_values = np.array([[5.0, 15.0]])
        depths, vels = b.update_hydraulics(2.0, table_flows, depth_values, vel_values)
        np.testing.assert_allclose(depths, [20.0])
        np.testing.assert_allclose(vels, [10.0])

    def test_zero_flow_returns_zero_depth(self):
        """At zero flow, depth and velocity should be zero (clamped)."""
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        table_flows = np.array([1.0, 2.0, 3.0])
        depth_values = np.array([[10.0, 20.0, 30.0]])
        vel_values = np.array([[5.0, 10.0, 15.0]])
        depths, vels = b.update_hydraulics(0.0, table_flows, depth_values, vel_values)
        np.testing.assert_allclose(depths, [0.0])
        np.testing.assert_allclose(vels, [0.0])

    def test_multiple_cells(self):
        """Interpolation works for multiple cells simultaneously."""
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
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
        depths, vels = b.update_hydraulics(1.5, table_flows, depth_values, vel_values)
        np.testing.assert_allclose(depths, [15.0, 45.0, 6.5])
        np.testing.assert_allclose(vels, [1.5, 4.5, 0.65])

    def test_dry_cell_velocity_is_zero(self):
        """If interpolated depth is zero or negative, velocity must be zero."""
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        table_flows = np.array([1.0, 2.0])
        # Cell that goes dry at low flow (negative extrapolation clamped to 0)
        depth_values = np.array([[0.5, 1.0]])
        vel_values = np.array([[5.0, 10.0]])
        depths, vels = b.update_hydraulics(0.0, table_flows, depth_values, vel_values)
        assert depths[0] == 0.0
        assert vels[0] == 0.0


class TestLogistic:
    """Test logistic function evaluation."""

    def test_at_L1_returns_0_1(self):
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        result = b.evaluate_logistic(np.array([3.0]), L1=3.0, L9=6.0)
        np.testing.assert_allclose(result, [0.1], atol=0.01)

    def test_at_L9_returns_0_9(self):
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        result = b.evaluate_logistic(np.array([6.0]), L1=3.0, L9=6.0)
        np.testing.assert_allclose(result, [0.9], atol=0.01)

    def test_at_midpoint_returns_0_5(self):
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        result = b.evaluate_logistic(np.array([4.5]), L1=3.0, L9=6.0)
        np.testing.assert_allclose(result, [0.5], atol=0.01)

    def test_monotonically_increasing(self):
        """When L1 < L9, function should increase."""
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        x = np.linspace(0, 10, 50)
        result = b.evaluate_logistic(x, L1=3.0, L9=6.0)
        assert np.all(np.diff(result) >= 0)

    def test_monotonically_decreasing_when_inverted(self):
        """When L1 > L9, function should decrease."""
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        x = np.linspace(0, 10, 50)
        result = b.evaluate_logistic(x, L1=6.0, L9=3.0)
        assert np.all(np.diff(result) <= 0)

    def test_vectorized(self):
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        x = np.array([3.0, 4.5, 6.0])
        result = b.evaluate_logistic(x, L1=3.0, L9=6.0)
        assert result.shape == (3,)
        np.testing.assert_allclose(result, [0.1, 0.5, 0.9], atol=0.01)

    def test_scalar_input(self):
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        result = b.evaluate_logistic(np.array([4.5]), L1=3.0, L9=6.0)
        assert result.shape == (1,)


class TestInterp1d:
    """Test generic 1D interpolation wrapper."""

    def test_at_table_points_exact(self):
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        table_x = np.array([0.0, 10.0, 20.0, 30.0])
        table_y = np.array([0.05, 0.5, 1.0, 0.0])
        result = b.interp1d(np.array([0.0, 10.0, 20.0, 30.0]), table_x, table_y)
        np.testing.assert_allclose(result, [0.05, 0.5, 1.0, 0.0])

    def test_between_points_linear(self):
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        table_x = np.array([0.0, 10.0])
        table_y = np.array([0.0, 1.0])
        result = b.interp1d(np.array([5.0]), table_x, table_y)
        np.testing.assert_allclose(result, [0.5])

    def test_clamp_below_table(self):
        """Values below table range should clamp to first value."""
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        table_x = np.array([10.0, 20.0])
        table_y = np.array([1.0, 2.0])
        result = b.interp1d(np.array([5.0]), table_x, table_y)
        np.testing.assert_allclose(result, [1.0])  # clamp to first

    def test_clamp_above_table(self):
        """Values above table range should clamp to last value."""
        from instream.backends.numpy_backend import NumpyBackend
        b = NumpyBackend()
        table_x = np.array([10.0, 20.0])
        table_y = np.array([1.0, 2.0])
        result = b.interp1d(np.array([25.0]), table_x, table_y)
        np.testing.assert_allclose(result, [2.0])  # clamp to last
