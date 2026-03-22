"""Tests for compute backend interface and factory."""

import numpy as np
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


# ---- JAX growth_rate tests ----


def _growth_params():
    """Shared bioenergetics parameters for growth_rate cross-validation."""
    return dict(
        drift_conc=0.001,
        search_prod=0.001,
        search_area=100.0,
        shelter_speed_frac=0.3,
        step_length=1.0,
        cmax_A=0.628,
        cmax_B=0.3,
        cmax_temp_table_x=np.array([0.0, 10.0, 15.0, 20.0, 22.0, 25.0, 30.0]),
        cmax_temp_table_y=np.array([0.0, 0.5, 0.8, 1.0, 0.9, 0.5, 0.0]),
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
    )


def test_jax_growth_rate_drift_matches_python():
    """JAX growth_rate for drift activity matches scalar Python growth_rate_for."""
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.modules.growth import growth_rate_for

    jax_b = JaxBackend()
    p = _growth_params()

    # Single fish: drift feeding in a wet cell
    length, weight, depth, velocity, light_val = 10.0, 5.0, 50.0, 20.0, 100.0
    turbidity, temperature = 0.0, 12.0

    py_result = growth_rate_for(
        activity=0,
        length=length,
        weight=weight,
        depth=depth,
        velocity=velocity,
        light=light_val,
        turbidity=turbidity,
        temperature=temperature,
        available_drift=10.0,
        available_search=10.0,
        available_shelter=500.0,
        superind_rep=1,
        prev_consumption=0.0,
        **p,
    )

    jax_result = jax_b.growth_rate(
        activity=np.array([0]),
        lengths=np.array([length]),
        weights=np.array([weight]),
        depth=np.array([depth]),
        velocity=np.array([velocity]),
        light=np.array([light_val]),
        turbidity=turbidity,
        temperature=temperature,
        available_drift=np.array([10.0]),
        available_search=np.array([10.0]),
        available_shelter=np.array([500.0]),
        superind_rep=np.array([1]),
        prev_consumption=np.array([0.0]),
        **p,
    )

    np.testing.assert_allclose(jax_result[0], py_result, rtol=1e-6)


def test_jax_growth_rate_search_matches_python():
    """JAX growth_rate for search activity matches scalar Python growth_rate_for."""
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.modules.growth import growth_rate_for

    jax_b = JaxBackend()
    p = _growth_params()

    length, weight, depth, velocity, light_val = 8.0, 3.5, 40.0, 10.0, 200.0
    turbidity, temperature = 5.0, 15.0

    py_result = growth_rate_for(
        activity=1,
        length=length,
        weight=weight,
        depth=depth,
        velocity=velocity,
        light=light_val,
        turbidity=turbidity,
        temperature=temperature,
        available_drift=10.0,
        available_search=10.0,
        available_shelter=200.0,
        superind_rep=1,
        prev_consumption=0.0,
        **p,
    )

    jax_result = jax_b.growth_rate(
        activity=np.array([1]),
        lengths=np.array([length]),
        weights=np.array([weight]),
        depth=np.array([depth]),
        velocity=np.array([velocity]),
        light=np.array([light_val]),
        turbidity=turbidity,
        temperature=temperature,
        available_drift=np.array([10.0]),
        available_search=np.array([10.0]),
        available_shelter=np.array([200.0]),
        superind_rep=np.array([1]),
        prev_consumption=np.array([0.0]),
        **p,
    )

    np.testing.assert_allclose(jax_result[0], py_result, rtol=1e-6)


def test_jax_growth_rate_hide_matches_python():
    """JAX growth_rate for hide activity matches scalar Python growth_rate_for."""
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.modules.growth import growth_rate_for

    jax_b = JaxBackend()
    p = _growth_params()

    length, weight, depth, velocity, light_val = 12.0, 8.0, 60.0, 30.0, 50.0
    turbidity, temperature = 2.0, 18.0

    py_result = growth_rate_for(
        activity=2,
        length=length,
        weight=weight,
        depth=depth,
        velocity=velocity,
        light=light_val,
        turbidity=turbidity,
        temperature=temperature,
        available_drift=10.0,
        available_search=10.0,
        available_shelter=500.0,
        superind_rep=1,
        prev_consumption=0.0,
        **p,
    )

    jax_result = jax_b.growth_rate(
        activity=np.array([2]),
        lengths=np.array([length]),
        weights=np.array([weight]),
        depth=np.array([depth]),
        velocity=np.array([velocity]),
        light=np.array([light_val]),
        turbidity=turbidity,
        temperature=temperature,
        available_drift=np.array([10.0]),
        available_search=np.array([10.0]),
        available_shelter=np.array([500.0]),
        superind_rep=np.array([1]),
        prev_consumption=np.array([0.0]),
        **p,
    )

    np.testing.assert_allclose(jax_result[0], py_result, rtol=1e-6)


def test_jax_growth_rate_batch():
    """JAX growth_rate handles multiple fish with different activities."""
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.modules.growth import growth_rate_for

    jax_b = JaxBackend()
    p = _growth_params()

    n = 3
    activities = np.array([0, 1, 2])
    lengths = np.array([10.0, 8.0, 12.0])
    weights = np.array([5.0, 3.5, 8.0])
    depths = np.array([50.0, 40.0, 60.0])
    velocities = np.array([20.0, 10.0, 30.0])
    lights = np.array([100.0, 200.0, 50.0])
    avail_drift = np.array([10.0, 10.0, 10.0])
    avail_search = np.array([10.0, 10.0, 10.0])
    avail_shelter = np.array([500.0, 200.0, 500.0])
    superind_rep = np.array([1, 1, 1])
    prev_consumption = np.array([0.0, 0.0, 0.0])
    turbidity, temperature = 0.0, 15.0

    jax_result = jax_b.growth_rate(
        activity=activities,
        lengths=lengths,
        weights=weights,
        depth=depths,
        velocity=velocities,
        light=lights,
        turbidity=turbidity,
        temperature=temperature,
        available_drift=avail_drift,
        available_search=avail_search,
        available_shelter=avail_shelter,
        superind_rep=superind_rep,
        prev_consumption=prev_consumption,
        **p,
    )

    # Cross-validate each fish individually
    for i in range(n):
        py_result = growth_rate_for(
            activity=int(activities[i]),
            length=lengths[i],
            weight=weights[i],
            depth=depths[i],
            velocity=velocities[i],
            light=lights[i],
            turbidity=turbidity,
            temperature=temperature,
            available_drift=avail_drift[i],
            available_search=avail_search[i],
            available_shelter=avail_shelter[i],
            superind_rep=int(superind_rep[i]),
            prev_consumption=prev_consumption[i],
            **p,
        )
        np.testing.assert_allclose(
            jax_result[i],
            py_result,
            rtol=1e-6,
            err_msg=f"Fish {i} (activity={activities[i]}) mismatch",
        )


def test_jax_growth_rate_dry_cell():
    """JAX growth_rate returns zero drift intake for dry cells (depth=0)."""
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.modules.growth import growth_rate_for

    jax_b = JaxBackend()
    p = _growth_params()

    py_result = growth_rate_for(
        activity=0,
        length=10.0,
        weight=5.0,
        depth=0.0,
        velocity=0.0,
        light=100.0,
        turbidity=0.0,
        temperature=12.0,
        available_drift=10.0,
        available_search=10.0,
        available_shelter=500.0,
        superind_rep=1,
        prev_consumption=0.0,
        **p,
    )
    jax_result = jax_b.growth_rate(
        activity=np.array([0]),
        lengths=np.array([10.0]),
        weights=np.array([5.0]),
        depth=np.array([0.0]),
        velocity=np.array([0.0]),
        light=np.array([100.0]),
        turbidity=0.0,
        temperature=12.0,
        available_drift=np.array([10.0]),
        available_search=np.array([10.0]),
        available_shelter=np.array([500.0]),
        superind_rep=np.array([1]),
        prev_consumption=np.array([0.0]),
        **p,
    )
    np.testing.assert_allclose(jax_result[0], py_result, rtol=1e-6)


# ---- JAX survival tests ----


def test_jax_survival_matches_python():
    """JAX survival matches Python scalar survival functions for a single fish."""
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.modules.survival import (
        survival_high_temperature,
        survival_stranding,
        survival_fish_predation,
        survival_terrestrial_predation,
    )

    jax_b = JaxBackend()

    # Test parameters matching the default keyword args
    length, depth, velocity, light_val = 10.0, 50.0, 20.0, 100.0
    temperature = 12.0
    condition = 0.9
    activity = 0  # drift
    dist_esc = 30.0
    avail_hiding = 5
    superind_rep = 1
    pisciv_dens = 0.2

    # Python scalar
    s_ht = survival_high_temperature(temperature, T1=28.0, T9=24.0)
    s_str = survival_stranding(depth, survival_when_dry=0.5)
    s_fp = survival_fish_predation(
        length,
        depth,
        light_val,
        pisciv_dens,
        temperature,
        activity="drift",
        min_surv=0.99,
        L1=10.0,
        L9=3.0,
        D1=50.0,
        D9=10.0,
        P1=0.5,
        P9=0.1,
        I1=200.0,
        I9=50.0,
        T1=25.0,
        T9=15.0,
        hiding_factor=0.5,
    )
    s_tp = survival_terrestrial_predation(
        length,
        depth,
        velocity,
        light_val,
        dist_esc,
        activity="drift",
        available_hiding=avail_hiding,
        superind_rep=superind_rep,
        min_surv=0.99,
        L1=15.0,
        L9=5.0,
        D1=50.0,
        D9=10.0,
        V1=50.0,
        V9=10.0,
        I1=200.0,
        I9=50.0,
        H1=50.0,
        H9=10.0,
        hiding_factor=0.5,
    )
    py_combined = s_ht * s_str * s_fp * s_tp

    jax_result = jax_b.survival(
        lengths=np.array([length]),
        depths=np.array([depth]),
        velocities=np.array([velocity]),
        light=np.array([light_val]),
        temperatures=temperature,
        conditions=np.array([condition]),
        activities=np.array([activity]),
        dist_escape=np.array([dist_esc]),
        available_hiding=np.array([avail_hiding]),
        superind_rep=np.array([superind_rep]),
        pisciv_density=np.array([pisciv_dens]),
    )

    np.testing.assert_allclose(jax_result[0], py_combined, rtol=1e-6)


def test_jax_survival_hiding_fish():
    """JAX survival applies hiding factor correctly for activity=2."""
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.modules.survival import (
        survival_high_temperature,
        survival_stranding,
        survival_fish_predation,
        survival_terrestrial_predation,
    )

    jax_b = JaxBackend()

    length, depth, velocity, light_val = 8.0, 40.0, 15.0, 150.0
    temperature = 20.0
    dist_esc = 20.0
    avail_hiding = 5
    superind_rep = 1
    pisciv_dens = 0.3

    s_ht = survival_high_temperature(temperature, T1=28.0, T9=24.0)
    s_str = survival_stranding(depth, survival_when_dry=0.5)
    s_fp = survival_fish_predation(
        length,
        depth,
        light_val,
        pisciv_dens,
        temperature,
        activity="hide",
        min_surv=0.99,
        L1=10.0,
        L9=3.0,
        D1=50.0,
        D9=10.0,
        P1=0.5,
        P9=0.1,
        I1=200.0,
        I9=50.0,
        T1=25.0,
        T9=15.0,
        hiding_factor=0.5,
    )
    s_tp = survival_terrestrial_predation(
        length,
        depth,
        velocity,
        light_val,
        dist_esc,
        activity="hide",
        available_hiding=avail_hiding,
        superind_rep=superind_rep,
        min_surv=0.99,
        L1=15.0,
        L9=5.0,
        D1=50.0,
        D9=10.0,
        V1=50.0,
        V9=10.0,
        I1=200.0,
        I9=50.0,
        H1=50.0,
        H9=10.0,
        hiding_factor=0.5,
    )
    py_combined = s_ht * s_str * s_fp * s_tp

    jax_result = jax_b.survival(
        lengths=np.array([length]),
        depths=np.array([depth]),
        velocities=np.array([velocity]),
        light=np.array([light_val]),
        temperatures=temperature,
        conditions=np.array([0.9]),
        activities=np.array([2]),  # hide
        dist_escape=np.array([dist_esc]),
        available_hiding=np.array([avail_hiding]),
        superind_rep=np.array([superind_rep]),
        pisciv_density=np.array([pisciv_dens]),
    )

    np.testing.assert_allclose(jax_result[0], py_combined, rtol=1e-6)


def test_jax_survival_stranding():
    """JAX survival correctly applies stranding penalty for dry cells."""
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend

    jax_b = JaxBackend()

    # Two fish: one in water, one stranded
    result = jax_b.survival(
        lengths=np.array([10.0, 10.0]),
        depths=np.array([50.0, 0.0]),
        velocities=np.array([20.0, 0.0]),
        light=np.array([100.0, 100.0]),
        temperatures=12.0,
        conditions=np.array([0.9, 0.9]),
        activities=np.array([0, 0]),
        dist_escape=np.array([30.0, 30.0]),
        available_hiding=np.array([5, 5]),
        superind_rep=np.array([1, 1]),
        pisciv_density=np.array([0.0, 0.0]),
    )

    # Stranded fish should have lower survival (includes 0.5 stranding factor)
    assert result[1] < result[0], "Stranded fish should have lower survival"
    # Stranding factor is 0.5, so stranded survival <= 0.5
    assert result[1] <= 0.5


def test_jax_survival_batch():
    """JAX survival handles multiple fish with different activities."""
    pytest.importorskip("jax")
    import numpy as np
    from instream.backends.jax_backend import JaxBackend
    from instream.modules.survival import (
        survival_high_temperature,
        survival_stranding,
        survival_fish_predation,
        survival_terrestrial_predation,
    )

    jax_b = JaxBackend()

    n = 3
    lengths = np.array([10.0, 8.0, 12.0])
    depths = np.array([50.0, 40.0, 60.0])
    velocities = np.array([20.0, 10.0, 30.0])
    lights = np.array([100.0, 200.0, 50.0])
    temperature = 15.0
    activities = np.array([0, 1, 2])
    dist_esc = np.array([30.0, 20.0, 50.0])
    avail_hiding = np.array([5, 3, 8])
    superind_reps = np.array([1, 1, 1])
    pisciv_dens = np.array([0.1, 0.2, 0.0])

    jax_result = jax_b.survival(
        lengths=lengths,
        depths=depths,
        velocities=velocities,
        light=lights,
        temperatures=temperature,
        conditions=np.array([0.9, 0.85, 0.95]),
        activities=activities,
        dist_escape=dist_esc,
        available_hiding=avail_hiding,
        superind_rep=superind_reps,
        pisciv_density=pisciv_dens,
    )

    act_names = ["drift", "search", "hide"]
    for i in range(n):
        s_ht = survival_high_temperature(temperature, T1=28.0, T9=24.0)
        s_str = survival_stranding(depths[i], survival_when_dry=0.5)
        s_fp = survival_fish_predation(
            lengths[i],
            depths[i],
            lights[i],
            pisciv_dens[i],
            temperature,
            activity=act_names[int(activities[i])],
            min_surv=0.99,
            L1=10.0,
            L9=3.0,
            D1=50.0,
            D9=10.0,
            P1=0.5,
            P9=0.1,
            I1=200.0,
            I9=50.0,
            T1=25.0,
            T9=15.0,
            hiding_factor=0.5,
        )
        s_tp = survival_terrestrial_predation(
            lengths[i],
            depths[i],
            velocities[i],
            lights[i],
            dist_esc[i],
            activity=act_names[int(activities[i])],
            available_hiding=int(avail_hiding[i]),
            superind_rep=int(superind_reps[i]),
            min_surv=0.99,
            L1=15.0,
            L9=5.0,
            D1=50.0,
            D9=10.0,
            V1=50.0,
            V9=10.0,
            I1=200.0,
            I9=50.0,
            H1=50.0,
            H9=10.0,
            hiding_factor=0.5,
        )
        py_combined = s_ht * s_str * s_fp * s_tp
        np.testing.assert_allclose(
            jax_result[i],
            py_combined,
            rtol=1e-6,
            err_msg=f"Fish {i} (activity={act_names[int(activities[i])]}) mismatch",
        )
