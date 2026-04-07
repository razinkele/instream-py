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
    # Degenerate case: L1 == L9 => step function: 0.9 if x >= L1, else 0.1
    result = backend.evaluate_logistic(np.array([5.0]), L1=5.0, L9=5.0)
    assert np.allclose(result, 0.9)
    result_below = backend.evaluate_logistic(np.array([4.0]), L1=5.0, L9=5.0)
    assert np.allclose(result_below, 0.1)


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


class TestSpawnSuitabilityBackend:
    def test_numpy_spawn_suitability_vectorized(self):
        from instream.backends.numpy_backend import NumpyBackend

        b = NumpyBackend()
        depths = np.array([10.0, 50.0, 0.0])
        vels = np.array([20.0, 40.0, 0.0])
        frac = np.array([0.5, 0.8, 0.0])
        area = np.array([100.0, 200.0, 50.0])
        dtx = np.array([0.0, 30.0, 60.0])
        dty = np.array([0.0, 1.0, 0.0])
        vtx = np.array([0.0, 30.0, 60.0])
        vty = np.array([0.0, 1.0, 0.0])
        scores = b.spawn_suitability(
            depths,
            vels,
            frac,
            area=area,
            depth_table_x=dtx,
            depth_table_y=dty,
            vel_table_x=vtx,
            vel_table_y=vty,
        )
        assert scores.shape == (3,)
        assert scores[2] == 0.0  # dry cell with no spawn fraction
        assert scores[0] > 0.0
        assert scores[1] > 0.0


class TestNumpySurvivalVectorized:
    def test_survival_matches_scalar_loop(self):
        """Vectorized survival must match the per-fish scalar computation."""
        from instream.backends.numpy_backend import NumpyBackend
        from instream.modules.survival import (
            survival_high_temperature,
            survival_stranding,
            survival_condition,
            survival_fish_predation,
            survival_terrestrial_predation,
        )

        b = NumpyBackend()
        n = 5
        lengths = np.array([5.0, 8.0, 12.0, 3.0, 15.0])
        weights = np.array([2.0, 6.0, 20.0, 0.5, 40.0])
        conditions = np.array([0.9, 0.7, 1.0, 0.3, 0.85])
        temperatures = np.array([15.0, 20.0, 25.0, 10.0, 28.0])
        depths = np.array([30.0, 0.0, 50.0, 10.0, 100.0])
        velocities = np.array([10.0, 0.0, 30.0, 5.0, 50.0])
        lights = np.array([100.0, 0.0, 200.0, 50.0, 300.0])
        activities = np.array([0, 1, 2, 0, 2])
        pisciv_densities = np.array([0.0, 0.0, 0.001, 0.0, 0.002])
        dist_escapes = np.array([50.0, 100.0, 20.0, 80.0, 10.0])
        available_hidings = np.array([5.0, 0.0, 3.0, 1.0, 10.0])
        superind_reps = np.array([1, 1, 1, 1, 1])

        # Species params (same for all fish in this test)
        T1, T9 = 28.0, 24.0
        swd = 0.5
        K5, K8 = 0.8, 0.992
        fp_min = 0.99
        tp_min = 0.99

        vec_result = b.survival(
            lengths,
            weights,
            conditions,
            temperatures,
            depths,
            velocities=velocities,
            lights=lights,
            activities=activities,
            pisciv_densities=pisciv_densities,
            dist_escapes=dist_escapes,
            available_hidings=available_hidings,
            superind_reps=superind_reps,
            sp_mort_high_temp_T1=np.full(n, T1),
            sp_mort_high_temp_T9=np.full(n, T9),
            sp_mort_strand_survival_when_dry=np.full(n, swd),
            sp_mort_condition_S_at_K5=np.full(n, K5),
            sp_mort_condition_S_at_K8=np.full(n, K8),
            rp_fish_pred_min=np.full(n, fp_min),
            sp_mort_fish_pred_L1=np.full(n, 10.0),
            sp_mort_fish_pred_L9=np.full(n, 5.0),
            sp_mort_fish_pred_D1=np.full(n, 50.0),
            sp_mort_fish_pred_D9=np.full(n, 20.0),
            sp_mort_fish_pred_P1=np.full(n, 0.01),
            sp_mort_fish_pred_P9=np.full(n, 0.001),
            sp_mort_fish_pred_I1=np.full(n, 200.0),
            sp_mort_fish_pred_I9=np.full(n, 100.0),
            sp_mort_fish_pred_T1=np.full(n, 25.0),
            sp_mort_fish_pred_T9=np.full(n, 15.0),
            sp_mort_fish_pred_hiding_factor=np.full(n, 0.5),
            rp_terr_pred_min=np.full(n, tp_min),
            sp_mort_terr_pred_L1=np.full(n, 10.0),
            sp_mort_terr_pred_L9=np.full(n, 5.0),
            sp_mort_terr_pred_D1=np.full(n, 50.0),
            sp_mort_terr_pred_D9=np.full(n, 20.0),
            sp_mort_terr_pred_V1=np.full(n, 30.0),
            sp_mort_terr_pred_V9=np.full(n, 10.0),
            sp_mort_terr_pred_I1=np.full(n, 200.0),
            sp_mort_terr_pred_I9=np.full(n, 100.0),
            sp_mort_terr_pred_H1=np.full(n, 80.0),
            sp_mort_terr_pred_H9=np.full(n, 30.0),
            sp_mort_terr_pred_hiding_factor=np.full(n, 0.5),
        )

        # Compute scalar reference
        scalar_result = np.empty(n)
        for i in range(n):
            s_ht = survival_high_temperature(temperatures[i], T1, T9)
            s_str = survival_stranding(depths[i], swd)
            s_cond = survival_condition(conditions[i], K5, K8)
            s_fp = survival_fish_predation(
                lengths[i],
                depths[i],
                lights[i],
                pisciv_densities[i],
                temperatures[i],
                activities[i],
                fp_min,
                10.0,
                5.0,
                50.0,
                20.0,
                0.01,
                0.001,
                200.0,
                100.0,
                25.0,
                15.0,
                0.5,
            )
            s_tp = survival_terrestrial_predation(
                lengths[i],
                depths[i],
                velocities[i],
                lights[i],
                dist_escapes[i],
                activities[i],
                int(available_hidings[i]),
                int(superind_reps[i]),
                tp_min,
                10.0,
                5.0,
                50.0,
                20.0,
                30.0,
                10.0,
                200.0,
                100.0,
                80.0,
                30.0,
                0.5,
            )
            scalar_result[i] = s_ht * s_str * s_cond * s_fp * s_tp

        np.testing.assert_allclose(vec_result, scalar_result, rtol=1e-12)


class TestNumpyGrowthRateVectorized:
    def test_growth_rate_returns_correct_shape(self):
        from instream.backends.numpy_backend import NumpyBackend

        b = NumpyBackend()
        n = 3
        result = b.growth_rate(
            np.array([5.0, 8.0, 12.0]),
            np.array([2.0, 6.0, 20.0]),
            np.array([15.0, 15.0, 15.0]),
            np.array([10.0, 20.0, 30.0]),
            np.array([30.0, 50.0, 100.0]),
            activities=np.array([0, 1, 2]),
            lights=np.array([100.0, 100.0, 100.0]),
            turbidities=np.array([5.0, 5.0, 5.0]),
            drift_concs=np.array([1e-6, 1e-6, 1e-6]),
            search_prods=np.array([1e-6, 1e-6, 1e-6]),
            search_areas=np.array([100.0, 100.0, 100.0]),
            available_drifts=np.array([1.0, 1.0, 1.0]),
            available_searches=np.array([1.0, 1.0, 1.0]),
            available_shelters=np.array([100.0, 100.0, 100.0]),
            shelter_speed_fracs=np.array([0.5, 0.5, 0.5]),
            superind_reps=np.array([1, 1, 1]),
            prev_consumptions=np.array([0.0, 0.0, 0.0]),
            step_length=1.0,
            cmax_As=np.array([0.628, 0.628, 0.628]),
            cmax_Bs=np.array([-0.3, -0.3, -0.3]),
            cmax_temp_table_xs=[np.array([0.0, 10.0, 20.0, 25.0, 30.0])],
            cmax_temp_table_ys=[np.array([0.0, 0.5, 1.0, 0.8, 0.0])],
            species_idxs=np.array([0, 0, 0]),
            react_dist_As=np.array([3.0, 3.0, 3.0]),
            react_dist_Bs=np.array([0.5, 0.5, 0.5]),
            turbid_thresholds=np.array([10.0, 10.0, 10.0]),
            turbid_mins=np.array([0.1, 0.1, 0.1]),
            turbid_exps=np.array([1.0, 1.0, 1.0]),
            light_thresholds=np.array([200.0, 200.0, 200.0]),
            light_mins=np.array([0.1, 0.1, 0.1]),
            light_exps=np.array([1.0, 1.0, 1.0]),
            capture_R1s=np.array([5.0, 5.0, 5.0]),
            capture_R9s=np.array([15.0, 15.0, 15.0]),
            max_speed_As=np.array([1.5, 1.5, 1.5]),
            max_speed_Bs=np.array([0.0, 0.0, 0.0]),
            max_swim_temp_terms=np.array([1.0, 1.0, 1.0]),
            resp_As=np.array([0.0253, 0.0253, 0.0253]),
            resp_Bs=np.array([-0.217, -0.217, -0.217]),
            resp_Ds=np.array([0.03, 0.03, 0.03]),
            resp_temp_terms=np.array([1.0, 1.0, 1.0]),
            prey_energy_densities=np.array([5900.0, 5900.0, 5900.0]),
            fish_energy_densities=np.array([5900.0, 5900.0, 5900.0]),
        )
        assert result.shape == (3,)
        assert np.isfinite(result).all()
        # Hide activity (idx 2) should have negative growth (only respiration)
        assert result[2] < 0.0


class TestNumbaEvaluateLogistic:
    def test_numba_logistic_matches_numpy(self):
        pytest.importorskip("numba")
        from instream.backends.numpy_backend import NumpyBackend
        from instream.backends.numba_backend import NumbaBackend

        np_b = NumpyBackend()
        nb_b = NumbaBackend()
        x = np.array([1.0, 5.0, 10.0, 15.0, 20.0])
        np_r = np_b.evaluate_logistic(x, 5.0, 15.0)
        nb_r = nb_b.evaluate_logistic(x, 5.0, 15.0)
        np.testing.assert_allclose(np_r, nb_r, rtol=1e-12)


class TestNumpyDepleteResources:
    def test_drift_depletes_food_and_shelter(self):
        from instream.backends.numpy_backend import NumpyBackend

        b = NumpyBackend()
        drift = np.array([10.0, 5.0])  # 2 cells
        search = np.array([10.0, 5.0])
        shelter = np.array([1000.0, 500.0])
        hiding = np.array([5.0, 3.0])
        b.deplete_resources(
            fish_order=np.array([0]),
            chosen_cells=np.array([0, -1]),  # fish 0 in cell 0
            available_drift=drift,
            available_search=search,
            chosen_activities=np.array([0, -1]),  # drift
            intake_amounts=np.array([3.0, 0.0]),
            fish_lengths=np.array([10.0, 0.0]),
            superind_reps=np.array([1, 1]),
            available_shelter=shelter,
            available_hiding=hiding,
        )
        assert drift[0] == 7.0  # 10 - 3
        assert shelter[0] == 900.0  # 1000 - 10^2

    def test_hide_depletes_hiding_places(self):
        from instream.backends.numpy_backend import NumpyBackend

        b = NumpyBackend()
        drift = np.array([10.0])
        search = np.array([10.0])
        shelter = np.array([100.0])
        hiding = np.array([5.0])
        b.deplete_resources(
            fish_order=np.array([0]),
            chosen_cells=np.array([0]),
            available_drift=drift,
            available_search=search,
            chosen_activities=np.array([2]),  # hide
            intake_amounts=np.array([0.0]),
            fish_lengths=np.array([5.0]),
            superind_reps=np.array([1]),
            available_shelter=shelter,
            available_hiding=hiding,
        )
        assert hiding[0] == 4.0  # 5 - 1


class TestCrossBackendParity:
    """Verify all backends produce identical results for the same inputs."""

    def _get_backends(self):
        """Return list of (name, backend) tuples for available backends."""
        from instream.backends.numpy_backend import NumpyBackend

        backends = [("numpy", NumpyBackend())]
        try:
            from instream.backends.numba_backend import NumbaBackend

            backends.append(("numba", NumbaBackend()))
        except ImportError:
            pass
        try:
            from instream.backends.jax_backend import JaxBackend

            backends.append(("jax", JaxBackend()))
        except ImportError:
            pass
        return backends

    def test_spawn_suitability_parity(self):
        backends = self._get_backends()
        assert len(backends) >= 2, "Need at least 2 backends"
        depths = np.array([10.0, 50.0, 0.0, 30.0])
        vels = np.array([20.0, 40.0, 0.0, 25.0])
        frac = np.array([0.5, 0.8, 0.0, 1.0])
        area = np.array([100.0, 200.0, 50.0, 150.0])
        dtx = np.array([0.0, 30.0, 60.0])
        dty = np.array([0.0, 1.0, 0.0])
        vtx = np.array([0.0, 30.0, 60.0])
        vty = np.array([0.0, 1.0, 0.0])
        ref = None
        for name, b in backends:
            result = b.spawn_suitability(
                depths,
                vels,
                frac,
                area=area,
                depth_table_x=dtx,
                depth_table_y=dty,
                vel_table_x=vtx,
                vel_table_y=vty,
            )
            if ref is None:
                ref = result
                ref_name = name
            else:
                np.testing.assert_allclose(
                    result,
                    ref,
                    rtol=1e-10,
                    err_msg=f"{name} vs {ref_name} spawn_suitability mismatch",
                )

    def _call_survival(
        self,
        name,
        backend,
        lengths,
        weights,
        conditions,
        temperatures,
        depths,
        velocities,
        lights,
        activities,
        pisciv_densities,
        dist_escapes,
        available_hidings,
        superind_reps,
        scalar_params,
    ):
        """Call survival with the appropriate signature for each backend."""
        from instream.backends.jax_backend import JaxBackend

        if isinstance(backend, JaxBackend):
            return backend.survival(
                lengths,
                depths,
                velocities,
                lights,
                temperatures,
                conditions,
                activities,
                dist_escapes,
                available_hidings,
                superind_reps,
                pisciv_densities,
                survival_when_dry=scalar_params["survival_when_dry"],
                high_temp_T1=scalar_params["high_temp_T1"],
                high_temp_T9=scalar_params["high_temp_T9"],
                cond_S_at_K5=scalar_params["cond_S_at_K5"],
                cond_S_at_K8=scalar_params["cond_S_at_K8"],
                fish_pred_min_surv=scalar_params["fish_pred_min_surv"],
                fish_pred_L1=scalar_params["fish_pred_L1"],
                fish_pred_L9=scalar_params["fish_pred_L9"],
                fish_pred_D1=scalar_params["fish_pred_D1"],
                fish_pred_D9=scalar_params["fish_pred_D9"],
                fish_pred_P1=scalar_params["fish_pred_P1"],
                fish_pred_P9=scalar_params["fish_pred_P9"],
                fish_pred_I1=scalar_params["fish_pred_I1"],
                fish_pred_I9=scalar_params["fish_pred_I9"],
                fish_pred_T1=scalar_params["fish_pred_T1"],
                fish_pred_T9=scalar_params["fish_pred_T9"],
                fish_pred_hiding_factor=scalar_params["fish_pred_hiding_factor"],
                terr_pred_min_surv=scalar_params["terr_pred_min_surv"],
                terr_pred_L1=scalar_params["terr_pred_L1"],
                terr_pred_L9=scalar_params["terr_pred_L9"],
                terr_pred_D1=scalar_params["terr_pred_D1"],
                terr_pred_D9=scalar_params["terr_pred_D9"],
                terr_pred_V1=scalar_params["terr_pred_V1"],
                terr_pred_V9=scalar_params["terr_pred_V9"],
                terr_pred_I1=scalar_params["terr_pred_I1"],
                terr_pred_I9=scalar_params["terr_pred_I9"],
                terr_pred_H1=scalar_params["terr_pred_H1"],
                terr_pred_H9=scalar_params["terr_pred_H9"],
                terr_pred_hiding_factor=scalar_params["terr_pred_hiding_factor"],
            )
        else:
            n = len(lengths)
            return backend.survival(
                lengths,
                weights,
                conditions,
                temperatures,
                depths,
                velocities=velocities,
                lights=lights,
                activities=activities,
                pisciv_densities=pisciv_densities,
                dist_escapes=dist_escapes,
                available_hidings=available_hidings,
                superind_reps=superind_reps,
                sp_mort_high_temp_T1=np.full(n, scalar_params["high_temp_T1"]),
                sp_mort_high_temp_T9=np.full(n, scalar_params["high_temp_T9"]),
                sp_mort_strand_survival_when_dry=np.full(
                    n, scalar_params["survival_when_dry"]
                ),
                sp_mort_condition_S_at_K5=np.full(n, scalar_params["cond_S_at_K5"]),
                sp_mort_condition_S_at_K8=np.full(n, scalar_params["cond_S_at_K8"]),
                rp_fish_pred_min=np.full(n, scalar_params["fish_pred_min_surv"]),
                sp_mort_fish_pred_L1=np.full(n, scalar_params["fish_pred_L1"]),
                sp_mort_fish_pred_L9=np.full(n, scalar_params["fish_pred_L9"]),
                sp_mort_fish_pred_D1=np.full(n, scalar_params["fish_pred_D1"]),
                sp_mort_fish_pred_D9=np.full(n, scalar_params["fish_pred_D9"]),
                sp_mort_fish_pred_P1=np.full(n, scalar_params["fish_pred_P1"]),
                sp_mort_fish_pred_P9=np.full(n, scalar_params["fish_pred_P9"]),
                sp_mort_fish_pred_I1=np.full(n, scalar_params["fish_pred_I1"]),
                sp_mort_fish_pred_I9=np.full(n, scalar_params["fish_pred_I9"]),
                sp_mort_fish_pred_T1=np.full(n, scalar_params["fish_pred_T1"]),
                sp_mort_fish_pred_T9=np.full(n, scalar_params["fish_pred_T9"]),
                sp_mort_fish_pred_hiding_factor=np.full(
                    n, scalar_params["fish_pred_hiding_factor"]
                ),
                rp_terr_pred_min=np.full(n, scalar_params["terr_pred_min_surv"]),
                sp_mort_terr_pred_L1=np.full(n, scalar_params["terr_pred_L1"]),
                sp_mort_terr_pred_L9=np.full(n, scalar_params["terr_pred_L9"]),
                sp_mort_terr_pred_D1=np.full(n, scalar_params["terr_pred_D1"]),
                sp_mort_terr_pred_D9=np.full(n, scalar_params["terr_pred_D9"]),
                sp_mort_terr_pred_V1=np.full(n, scalar_params["terr_pred_V1"]),
                sp_mort_terr_pred_V9=np.full(n, scalar_params["terr_pred_V9"]),
                sp_mort_terr_pred_I1=np.full(n, scalar_params["terr_pred_I1"]),
                sp_mort_terr_pred_I9=np.full(n, scalar_params["terr_pred_I9"]),
                sp_mort_terr_pred_H1=np.full(n, scalar_params["terr_pred_H1"]),
                sp_mort_terr_pred_H9=np.full(n, scalar_params["terr_pred_H9"]),
                sp_mort_terr_pred_hiding_factor=np.full(
                    n, scalar_params["terr_pred_hiding_factor"]
                ),
            )

    def test_survival_parity(self):
        backends = self._get_backends()
        assert len(backends) >= 2
        lengths = np.array([5.0, 8.0, 12.0, 15.0])
        weights = np.array([2.0, 6.0, 20.0, 40.0])
        # Use 1.0 so condition survival == 1.0 in NumPy/Numba, matching
        # the JAX backend which omits condition survival entirely.
        conditions = np.array([1.0, 1.0, 1.0, 1.0])
        temperatures = np.array([15.0, 20.0, 25.0, 28.0])
        depths = np.array([30.0, 0.0, 50.0, 100.0])
        velocities = np.array([10.0, 0.0, 30.0, 50.0])
        lights = np.array([100.0, 0.0, 200.0, 300.0])
        activities = np.array([0, 1, 2, 0])
        pisciv_densities = np.array([0.0, 0.0, 0.001, 0.002])
        dist_escapes = np.array([50.0, 100.0, 20.0, 10.0])
        available_hidings = np.array([5.0, 0.0, 3.0, 10.0])
        superind_reps = np.array([1, 1, 1, 1])
        scalar_params = dict(
            high_temp_T1=28.0,
            high_temp_T9=24.0,
            survival_when_dry=0.5,
            cond_S_at_K5=0.8,
            cond_S_at_K8=0.992,
            fish_pred_min_surv=0.99,
            fish_pred_L1=10.0,
            fish_pred_L9=5.0,
            fish_pred_D1=50.0,
            fish_pred_D9=20.0,
            fish_pred_P1=0.01,
            fish_pred_P9=0.001,
            fish_pred_I1=200.0,
            fish_pred_I9=100.0,
            fish_pred_T1=25.0,
            fish_pred_T9=15.0,
            fish_pred_hiding_factor=0.5,
            terr_pred_min_surv=0.99,
            terr_pred_L1=10.0,
            terr_pred_L9=5.0,
            terr_pred_D1=50.0,
            terr_pred_D9=20.0,
            terr_pred_V1=30.0,
            terr_pred_V9=10.0,
            terr_pred_I1=200.0,
            terr_pred_I9=100.0,
            terr_pred_H1=80.0,
            terr_pred_H9=30.0,
            terr_pred_hiding_factor=0.5,
        )
        ref = None
        for name, b in backends:
            result = self._call_survival(
                name,
                b,
                lengths,
                weights,
                conditions,
                temperatures,
                depths,
                velocities,
                lights,
                activities,
                pisciv_densities,
                dist_escapes,
                available_hidings,
                superind_reps,
                scalar_params,
            )
            if ref is None:
                ref = result
                ref_name = name
            else:
                rtol = 1e-10 if "jax" in name else 1e-12
                np.testing.assert_allclose(
                    result,
                    ref,
                    rtol=rtol,
                    err_msg=f"{name} vs {ref_name} survival mismatch",
                )

    def test_evaluate_logistic_parity(self):
        backends = self._get_backends()
        assert len(backends) >= 2
        x = np.array([1.0, 5.0, 10.0, 15.0, 20.0])
        ref = None
        for name, b in backends:
            result = b.evaluate_logistic(x, 5.0, 15.0)
            if ref is None:
                ref = result
                ref_name = name
            else:
                np.testing.assert_allclose(
                    result,
                    ref,
                    rtol=1e-10,
                    err_msg=f"{name} vs {ref_name} logistic mismatch",
                )

    def test_update_hydraulics_parity(self):
        """All backends must produce identical hydraulic interpolation."""
        backends = self._get_backends()
        assert len(backends) >= 2
        rng = np.random.default_rng(42)
        n_cells, n_flows = 50, 8
        table_flows = np.sort(rng.uniform(0.5, 100.0, n_flows))
        depth_values = rng.uniform(0, 200, (n_cells, n_flows))
        vel_values = rng.uniform(0, 100, (n_cells, n_flows))
        test_flows = [0.0, 1.0, 5.5, 50.0, 200.0]
        for flow in test_flows:
            ref_d, ref_v = None, None
            ref_name = None
            for name, b in backends:
                d, v = b.update_hydraulics(flow, table_flows, depth_values, vel_values)
                if ref_d is None:
                    ref_d, ref_v = d, v
                    ref_name = name
                else:
                    rtol = 1e-10 if "jax" in name else 1e-12
                    np.testing.assert_allclose(
                        d,
                        ref_d,
                        rtol=rtol,
                        err_msg=f"{name} vs {ref_name} depth at flow={flow}",
                    )
                    np.testing.assert_allclose(
                        v,
                        ref_v,
                        rtol=rtol,
                        err_msg=f"{name} vs {ref_name} vel at flow={flow}",
                    )

    def test_compute_light_parity(self):
        """All backends must produce identical solar irradiance."""
        backends = self._get_backends()
        assert len(backends) >= 2
        for jd in [1, 80, 172, 266, 355]:
            for lat in [0.0, 30.0, 45.0, 60.0, 80.0]:
                ref = None
                ref_name = None
                for name, b in backends:
                    dl, tl, irr = b.compute_light(jd, lat, 1.0, 0.9, 0.001, 6.0)
                    result = np.array([dl, tl, irr])
                    if ref is None:
                        ref = result
                        ref_name = name
                    else:
                        rtol = 1e-10 if "jax" in name else 1e-12
                        np.testing.assert_allclose(
                            result,
                            ref,
                            rtol=rtol,
                            err_msg=f"{name} vs {ref_name} light jd={jd} lat={lat}",
                        )

    def test_compute_cell_light_parity(self):
        """All backends must produce identical Beer-Lambert attenuation."""
        backends = self._get_backends()
        assert len(backends) >= 2
        depths = np.array([0.0, 10.0, 50.0, 100.0, 200.0])
        for turbid_const in [0.0, 0.005]:
            ref = None
            ref_name = None
            for name, b in backends:
                light = b.compute_cell_light(
                    depths, 500.0, 0.01, 5.0, 0.001, turbid_const
                )
                if ref is None:
                    ref = np.asarray(light)
                    ref_name = name
                else:
                    rtol = 1e-10 if "jax" in name else 1e-12
                    np.testing.assert_allclose(
                        np.asarray(light),
                        ref,
                        rtol=rtol,
                        err_msg=f"{name} vs {ref_name} cell_light turbid_const={turbid_const}",
                    )

    def test_interp1d_parity(self):
        """All backends must produce identical 1D interpolation."""
        backends = self._get_backends()
        assert len(backends) >= 2
        table_x = np.array([0.0, 5.0, 10.0, 20.0, 30.0])
        table_y = np.array([0.0, 0.5, 1.0, 0.8, 0.0])
        x = np.array([-1.0, 0.0, 2.5, 7.5, 15.0, 25.0, 35.0])
        ref = None
        ref_name = None
        for name, b in backends:
            result = b.interp1d(x, table_x, table_y)
            if ref is None:
                ref = np.asarray(result)
                ref_name = name
            else:
                np.testing.assert_allclose(
                    np.asarray(result),
                    ref,
                    rtol=1e-12,
                    err_msg=f"{name} vs {ref_name} interp1d",
                )

    def test_evaluate_logistic_array_params_parity(self):
        """Logistic with per-element L1/L9 arrays must match across backends."""
        backends = self._get_backends()
        assert len(backends) >= 2
        x = np.array([1.0, 5.0, 10.0, 15.0, 20.0])
        L1 = np.array([3.0, 4.0, 5.0, 6.0, 7.0])
        L9 = np.array([10.0, 12.0, 15.0, 18.0, 20.0])
        ref = None
        ref_name = None
        for name, b in backends:
            result = b.evaluate_logistic(x, L1, L9)
            if ref is None:
                ref = np.asarray(result)
                ref_name = name
            else:
                rtol = 1e-10 if "jax" in name else 1e-12
                np.testing.assert_allclose(
                    np.asarray(result),
                    ref,
                    rtol=rtol,
                    err_msg=f"{name} vs {ref_name} logistic array params",
                )

    def test_deplete_resources_parity(self):
        """deplete_resources must produce identical results across backends."""
        backends = self._get_backends()
        # Skip JAX if its signature differs
        compatible = [(n, b) for n, b in backends if n != "jax"]
        if len(compatible) < 2:
            pytest.skip("Need numpy + numba for deplete_resources parity")
        ref_drift = None
        ref_search = None
        ref_name = None
        for name, b in compatible:
            drift = np.array([10.0, 5.0, 8.0])
            search = np.array([10.0, 5.0, 8.0])
            shelter = np.array([1000.0, 500.0, 800.0])
            hiding = np.array([5.0, 3.0, 4.0])
            b.deplete_resources(
                fish_order=np.array([0, 1, 2]),
                chosen_cells=np.array([0, 1, 0]),
                available_drift=drift,
                available_search=search,
                chosen_activities=np.array([0, 1, 2]),
                intake_amounts=np.array([3.0, 2.0, 0.0]),
                fish_lengths=np.array([10.0, 8.0, 5.0]),
                superind_reps=np.array([1, 1, 1]),
                available_shelter=shelter,
                available_hiding=hiding,
            )
            if ref_drift is None:
                ref_drift = drift.copy()
                ref_search = search.copy()
                ref_name = name
            else:
                np.testing.assert_allclose(
                    drift,
                    ref_drift,
                    rtol=1e-12,
                    err_msg=f"{name} vs {ref_name} drift after depletion",
                )
                np.testing.assert_allclose(
                    search,
                    ref_search,
                    rtol=1e-12,
                    err_msg=f"{name} vs {ref_name} search after depletion",
                )

    def test_growth_rate_parity(self):
        """growth_rate must produce identical results for numpy and numba."""
        backends = self._get_backends()
        compatible = [(n, b) for n, b in backends if n != "jax"]
        if len(compatible) < 2:
            pytest.skip("Need numpy + numba for growth_rate parity")
        params = dict(
            activities=np.array([0, 1, 2]),
            lights=np.array([100.0, 100.0, 100.0]),
            turbidities=np.array([5.0, 5.0, 5.0]),
            drift_concs=np.array([1e-6, 1e-6, 1e-6]),
            search_prods=np.array([1e-6, 1e-6, 1e-6]),
            search_areas=np.array([100.0, 100.0, 100.0]),
            available_drifts=np.array([1.0, 1.0, 1.0]),
            available_searches=np.array([1.0, 1.0, 1.0]),
            available_shelters=np.array([100.0, 100.0, 100.0]),
            shelter_speed_fracs=np.array([0.5, 0.5, 0.5]),
            superind_reps=np.array([1, 1, 1]),
            prev_consumptions=np.array([0.0, 0.0, 0.0]),
            step_length=1.0,
            cmax_As=np.array([0.628, 0.628, 0.628]),
            cmax_Bs=np.array([-0.3, -0.3, -0.3]),
            cmax_temp_table_xs=[np.array([0.0, 10.0, 20.0, 25.0, 30.0])],
            cmax_temp_table_ys=[np.array([0.0, 0.5, 1.0, 0.8, 0.0])],
            species_idxs=np.array([0, 0, 0]),
            react_dist_As=np.array([3.0, 3.0, 3.0]),
            react_dist_Bs=np.array([0.5, 0.5, 0.5]),
            turbid_thresholds=np.array([10.0, 10.0, 10.0]),
            turbid_mins=np.array([0.1, 0.1, 0.1]),
            turbid_exps=np.array([1.0, 1.0, 1.0]),
            light_thresholds=np.array([200.0, 200.0, 200.0]),
            light_mins=np.array([0.1, 0.1, 0.1]),
            light_exps=np.array([1.0, 1.0, 1.0]),
            capture_R1s=np.array([5.0, 5.0, 5.0]),
            capture_R9s=np.array([15.0, 15.0, 15.0]),
            max_speed_As=np.array([1.5, 1.5, 1.5]),
            max_speed_Bs=np.array([0.0, 0.0, 0.0]),
            max_swim_temp_terms=np.array([1.0, 1.0, 1.0]),
            resp_As=np.array([0.0253, 0.0253, 0.0253]),
            resp_Bs=np.array([-0.217, -0.217, -0.217]),
            resp_Ds=np.array([0.03, 0.03, 0.03]),
            resp_temp_terms=np.array([1.0, 1.0, 1.0]),
            prey_energy_densities=np.array([5900.0, 5900.0, 5900.0]),
            fish_energy_densities=np.array([5900.0, 5900.0, 5900.0]),
        )
        ref = None
        ref_name = None
        for name, b in compatible:
            result = b.growth_rate(
                np.array([5.0, 8.0, 12.0]),
                np.array([2.0, 6.0, 20.0]),
                np.array([15.0, 15.0, 15.0]),
                np.array([10.0, 20.0, 30.0]),
                np.array([30.0, 50.0, 100.0]),
                **params,
            )
            if ref is None:
                ref = result.copy()
                ref_name = name
            else:
                np.testing.assert_allclose(
                    result,
                    ref,
                    rtol=1e-12,
                    err_msg=f"{name} vs {ref_name} growth_rate",
                )

    @pytest.mark.slow
    def test_full_model_parity_numpy_numba(self):
        """Running the same simulation on numpy and numba backends must produce identical population counts."""
        from pathlib import Path

        from instream.model import InSTREAMModel

        pytest.importorskip("numba")

        config_path = str(Path(__file__).parent.parent / "configs" / "example_a.yaml")
        data_dir = str(Path(__file__).parent / "fixtures" / "example_a")

        results = {}
        for backend_name in ["numpy", "numba"]:
            # Create a fresh config for each backend
            from instream.io.config import load_config

            config = load_config(config_path)
            config.performance.backend = backend_name
            config.simulation.seed = 12345

            model = InSTREAMModel(config, data_dir=data_dir)
            for _ in range(10):
                if model.time_manager.is_done():
                    break
                model.step()

            alive = model.trout_state.alive_indices()
            results[backend_name] = {
                "num_alive": len(alive),
                "mean_length": float(np.mean(model.trout_state.length[alive]))
                if len(alive) > 0
                else 0.0,
                "mean_weight": float(np.mean(model.trout_state.weight[alive]))
                if len(alive) > 0
                else 0.0,
            }

        assert results["numpy"]["num_alive"] == results["numba"]["num_alive"], (
            f"Population mismatch: numpy={results['numpy']['num_alive']} vs numba={results['numba']['num_alive']}"
        )
        np.testing.assert_allclose(
            results["numpy"]["mean_length"],
            results["numba"]["mean_length"],
            rtol=1e-6,
            err_msg="Mean length mismatch",
        )
