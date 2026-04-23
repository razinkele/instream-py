"""Tests for the test infrastructure itself — fixtures, helpers, data availability."""

import numpy as np
import pytest

from tests.conftest import assert_close, netlogo_reference


class TestFixturesExist:
    """Verify test fixture data files are present."""

    def test_example_a_directory_exists(self, example_a_data_path):
        assert example_a_data_path.exists()

    def test_example_a_has_depths_csv(self, example_a_data_path):
        assert (example_a_data_path / "ExampleA-Depths.csv").exists()

    def test_example_a_has_velocities_csv(self, example_a_data_path):
        assert (example_a_data_path / "ExampleA-Vels.csv").exists()

    def test_example_a_has_timeseries_csv(self, example_a_data_path):
        assert (example_a_data_path / "ExampleA-TimeSeriesInputs.csv").exists()

    def test_example_a_has_initial_populations(self, example_a_data_path):
        assert (example_a_data_path / "ExampleA-InitialPopulations.csv").exists()

    def test_example_a_has_shapefile(self, example_a_data_path):
        assert (example_a_data_path / "Shapefile" / "ExampleA.shp").exists()

    def test_example_a_has_parameters(self, example_a_data_path):
        assert (example_a_data_path / "parameters-ExampleA.nls").exists()

    def test_example_b_directory_exists(self, example_b_data_path):
        assert example_b_data_path.exists()

    def test_example_b_has_shapefile(self, example_b_data_path):
        assert (example_b_data_path / "Shapefile" / "ExampleB.shp").exists()

    def test_reference_directory_exists(self, reference_dir):
        assert reference_dir.exists()


class TestBackendParametrize:
    """Verify the backend parametric fixture works."""

    def test_backend_name_is_string(self, backend_name):
        assert isinstance(backend_name, str)

    def test_numpy_always_available(self):
        from tests.conftest import _available_backends
        assert "numpy" in _available_backends()


class TestAssertClose:
    """Verify the assert_close helper works correctly."""

    def test_passes_on_identical_arrays(self):
        a = np.array([1.0, 2.0, 3.0])
        assert_close(a, a)

    def test_passes_on_close_arrays(self):
        a = np.array([1.0, 2.0, 3.0])
        b = a + 1e-8
        assert_close(a, b, rtol=1e-6)

    def test_fails_on_different_arrays(self):
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([1.0, 2.0, 4.0])
        with pytest.raises(AssertionError):
            assert_close(a, b, rtol=1e-6)

    def test_passes_on_scalars(self):
        assert_close(1.0, 1.0 + 1e-10)

    def test_fails_on_nan_vs_number(self):
        with pytest.raises(AssertionError):
            assert_close(np.nan, 1.0)


class TestNetLogoReference:
    """Verify the NetLogo reference data helper."""

    def test_returns_path_object(self):
        ref = netlogo_reference("cell-depth-test-out")
        assert hasattr(ref, "exists")

    def test_reference_data_not_yet_generated(self):
        """Reference data is not yet generated — this is expected.
        Tests that need it should pytest.skip() when missing."""
        ref = netlogo_reference("cell-depth-test-out")
        # This will be True once NetLogo outputs are generated
        # For now, just verify the path is reasonable
        assert ref.suffix == ".csv"
