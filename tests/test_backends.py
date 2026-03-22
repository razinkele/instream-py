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


def test_numba_evaluate_all_cells_matches_python():
    """Numba compiled inner loop must match Python fitness_for."""
    pytest.importorskip("numba")
    import numpy as np
    from instream.modules.behavior import fitness_for
    from instream.backends.numba_backend.fitness import _evaluate_all_cells

    n_cells = 5
    depths = np.array([50.0, 30.0, 0.0, 80.0, 10.0])
    vels = np.array([20.0, 15.0, 0.0, 25.0, 5.0])
    lights = np.array([100.0, 200.0, 0.0, 50.0, 300.0])
    dist_esc = np.array([50.0, 30.0, 10.0, 80.0, 20.0])
    avail_drift = np.array([10.0, 5.0, 0.0, 15.0, 3.0])
    avail_search = np.array([10.0, 5.0, 0.0, 15.0, 3.0])
    avail_shelter = np.array([500.0, 200.0, 0.0, 800.0, 100.0])
    avail_hiding = np.array([5.0, 2.0, 0.0, 8.0, 1.0])
    pisciv = np.zeros(n_cells)
    candidates = np.array([0, 1, 3, 4], dtype=np.int32)
    cmax_tx = np.array([0.0, 10.0, 20.0, 30.0])
    cmax_ty = np.array([0.0, 0.5, 1.0, 0.3])

    best_c, best_a, best_fit, best_g = _evaluate_all_cells(
        10.0,
        5.0,
        0.9,
        0.0,
        1,
        depths,
        vels,
        lights,
        dist_esc,
        avail_drift,
        avail_search,
        avail_shelter,
        avail_hiding,
        pisciv,
        candidates,
        0.0,
        12.0,
        0.001,
        0.001,
        100.0,
        0.3,
        1.0,
        0.628,
        0.3,
        cmax_tx,
        cmax_ty,
        1.0,
        0.1,
        10.0,
        0.1,
        -0.1,
        50.0,
        0.1,
        -0.1,
        1.3,
        0.4,
        1.5,
        0.0,
        1.0,
        0.0253,
        0.75,
        0.03,
        1.2,
        3500.0,
        5500.0,
        28.0,
        24.0,
        0.8,
        0.992,
        0.99,
        10.0,
        3.0,
        50.0,
        10.0,
        0.5,
        0.1,
        200.0,
        50.0,
        25.0,
        15.0,
        0.5,
        0.99,
        15.0,
        5.0,
        50.0,
        10.0,
        50.0,
        10.0,
        200.0,
        50.0,
        50.0,
        10.0,
        0.5,
        0.5,
    )

    # Compare with Python fitness_for
    py_best_fit = -1e308
    py_best_c = -1
    py_best_a = -1
    acts = ["drift", "search", "hide"]
    for c in candidates:
        for ai, act in enumerate(acts):
            f = fitness_for(
                activity=act,
                length=10.0,
                weight=5.0,
                depth=depths[c],
                velocity=vels[c],
                light=lights[c],
                turbidity=0.0,
                temperature=12.0,
                drift_conc=0.001,
                search_prod=0.001,
                search_area=100.0,
                available_drift=avail_drift[c],
                available_search=avail_search[c],
                available_shelter=avail_shelter[c],
                shelter_speed_frac=0.3,
                superind_rep=1,
                prev_consumption=0.0,
                step_length=1.0,
                cmax_A=0.628,
                cmax_B=0.3,
                cmax_temp_table_x=cmax_tx,
                cmax_temp_table_y=cmax_ty,
                react_dist_A=1.0,
                react_dist_B=0.1,
                turbid_threshold=10.0,
                turbid_min=0.1,
                turbid_exp=-0.1,
                light_threshold=50.0,
                light_min=0.1,
                light_exp=-0.1,
                capture_R1=1.3,
                capture_R9=0.4,
                max_speed_A=1.5,
                max_speed_B=0.0,
                max_swim_temp_term=1.0,
                resp_A=0.0253,
                resp_B=0.75,
                resp_D=0.03,
                resp_temp_term=1.2,
                prey_energy_density=3500.0,
                fish_energy_density=5500.0,
                condition=0.9,
                dist_escape=dist_esc[c],
                available_hiding=int(avail_hiding[c]),
                pisciv_density=0.0,
            )
            if f > py_best_fit:
                py_best_fit = f
                py_best_c = int(c)
                py_best_a = ai

    assert best_c == py_best_c, "Cell mismatch: numba={}, python={}".format(
        best_c, py_best_c
    )
    assert best_a == py_best_a, "Activity mismatch: numba={}, python={}".format(
        best_a, py_best_a
    )
    np.testing.assert_allclose(best_fit, py_best_fit, rtol=1e-10)


# ---- JAX backend tests ----


def test_jax_backend_hydraulics():
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend

    backend = JaxBackend()
    flows = np.array([1.0, 5.0, 10.0])
    depths = np.array([[5.0, 10.0, 20.0], [3.0, 8.0, 15.0]])
    vels = np.array([[1.0, 3.0, 5.0], [0.5, 2.0, 4.0]])
    d, v = backend.update_hydraulics(5.0, flows, depths, vels)
    np.testing.assert_allclose(d, [10.0, 8.0], rtol=1e-10)
    np.testing.assert_allclose(v, [3.0, 2.0], rtol=1e-10)


def test_jax_backend_logistic():
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.backends.numpy_backend import NumpyBackend

    jax_b = JaxBackend()
    np_b = NumpyBackend()
    x = np.array([5.0, 10.0, 15.0, 20.0])
    jax_result = jax_b.evaluate_logistic(x, 10.0, 20.0)
    np_result = np_b.evaluate_logistic(x, 10.0, 20.0)
    np.testing.assert_allclose(jax_result, np_result, rtol=1e-10)


def test_jax_backend_cell_light():
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.backends.numpy_backend import NumpyBackend

    jax_b = JaxBackend()
    np_b = NumpyBackend()
    depths = np.array([10.0, 30.0, 50.0, 0.0])
    jax_light = jax_b.compute_cell_light(depths, 800.0, 0.01, 5.0, 0.01)
    np_light = np_b.compute_cell_light(depths, 800.0, 0.01, 5.0, 0.01)
    np.testing.assert_allclose(jax_light, np_light, rtol=1e-10)
