"""Tests for compute backend interface and factory."""
import pytest


class TestBackendFactory:
    def test_get_backend_numpy_returns_object(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert backend is not None

    def test_get_backend_invalid_raises(self):
        from instream.backends import get_backend
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend("fake")

    def test_backend_has_update_hydraulics(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "update_hydraulics")

    def test_backend_has_growth_rate(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "growth_rate")

    def test_backend_has_survival(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "survival")

    def test_backend_has_fitness_all(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "fitness_all")

    def test_backend_has_deplete_resources(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "deplete_resources")

    def test_backend_has_spawn_suitability(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "spawn_suitability")

    def test_backend_has_compute_light(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "compute_light")

    def test_backend_has_compute_cell_light(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "compute_cell_light")

    def test_backend_has_evaluate_logistic(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "evaluate_logistic")

    def test_backend_has_interp1d(self):
        from instream.backends import get_backend
        backend = get_backend("numpy")
        assert hasattr(backend, "interp1d")


def test_numpy_evaluate_logistic_equal_L1_L9():
    import numpy as np
    from instream.backends.numpy_backend import NumpyBackend
    backend = NumpyBackend()
    result = backend.evaluate_logistic(np.array([5.0]), L1=5.0, L9=5.0)
    assert np.allclose(result, 0.5)
