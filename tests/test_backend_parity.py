"""Cross-backend parity tests: JAX vs Numba vs NumPy.

Every Protocol method is tested with identical inputs across all three backends.
Results must match within documented tolerance tiers:
  - numpy ↔ numba: rtol=1e-12 (same math, different dispatch)
  - numpy ↔ jax:   rtol=1e-10 (different exp/log implementations)
"""

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _get_backends():
    """Return dict of available backend instances."""
    from salmopy.backends.numpy_backend import NumpyBackend

    backends = {"numpy": NumpyBackend()}

    try:
        from salmopy.backends.numba_backend import NumbaBackend

        backends["numba"] = NumbaBackend()
    except ImportError:
        pass

    try:
        from salmopy.backends.jax_backend import JaxBackend

        backends["jax"] = JaxBackend()
    except ImportError:
        pass

    return backends


@pytest.fixture(scope="module")
def all_backends():
    return _get_backends()


@pytest.fixture
def rng():
    """Fresh RNG per test so RNG-state consumed by one test doesn't leak
    into the next. Previously scope='module' which meant test order
    affected numerical results — a latent flakiness source."""
    return np.random.default_rng(12345)


def _rtol_for(name):
    """Return tolerance for backend vs numpy."""
    return 1e-10 if name == "jax" else 1e-12


def _skip_if_missing(backends, name):
    if name not in backends:
        pytest.skip(f"{name} backend not available")


def _non_numpy_backends(backends):
    """Yield (name, backend) for numba and jax if available."""
    for name in ("numba", "jax"):
        if name in backends:
            yield name, backends[name]


# ---------------------------------------------------------------------------
# 1. update_hydraulics
# ---------------------------------------------------------------------------


class TestUpdateHydraulicsParity:
    """All backends must produce identical depth/velocity interpolation."""

    @pytest.fixture
    def hydraulic_data(self):
        table_flows = np.array([1.0, 3.0, 5.0, 10.0])
        n_cells = 8
        rng = np.random.default_rng(42)
        depth_values = rng.uniform(0, 100, (n_cells, 4))
        vel_values = rng.uniform(-5, 50, (n_cells, 4))
        return table_flows, depth_values, vel_values

    @pytest.mark.parametrize("flow", [0.0, 0.5, 2.0, 5.0, 7.5, 10.0, 15.0])
    def test_hydraulics_at_flow(self, all_backends, hydraulic_data, flow):
        table_flows, depth_values, vel_values = hydraulic_data
        np_be = all_backends["numpy"]
        np_d, np_v = np_be.update_hydraulics(
            flow, table_flows, depth_values, vel_values
        )
        for name, be in _non_numpy_backends(all_backends):
            d, v = be.update_hydraulics(flow, table_flows, depth_values, vel_values)
            np.testing.assert_allclose(
                d,
                np_d,
                rtol=_rtol_for(name),
                err_msg=f"{name} depths differ at flow={flow}",
            )
            np.testing.assert_allclose(
                v,
                np_v,
                rtol=_rtol_for(name),
                err_msg=f"{name} velocities differ at flow={flow}",
            )
            assert np.all(d >= 0), f"{name}: negative depth at flow={flow}"
            assert np.all(v >= 0), f"{name}: negative velocity at flow={flow}"


# ---------------------------------------------------------------------------
# 2. compute_light
# ---------------------------------------------------------------------------


class TestComputeLightParity:
    """Solar irradiance computation must match across backends."""

    @pytest.mark.parametrize("jd", [1, 80, 172, 265, 355])
    @pytest.mark.parametrize("lat", [30.0, 45.0, 60.0])
    def test_light_at_julian_date(self, all_backends, jd, lat):
        np_be = all_backends["numpy"]
        np_dl, np_tw, np_irr = np_be.compute_light(jd, lat, 1.0, 0.8, 0.01, 6.0)
        for name, be in _non_numpy_backends(all_backends):
            dl, tw, irr = be.compute_light(jd, lat, 1.0, 0.8, 0.01, 6.0)
            assert abs(dl - np_dl) < 1e-10, (
                f"{name}: day_length differs at jd={jd}, lat={lat}"
            )
            assert abs(tw - np_tw) < 1e-10, (
                f"{name}: twilight differs at jd={jd}, lat={lat}"
            )
            assert abs(irr - np_irr) < 1e-8, (
                f"{name}: irradiance differs at jd={jd}, lat={lat}"
            )


# ---------------------------------------------------------------------------
# 3. compute_cell_light
# ---------------------------------------------------------------------------


class TestComputeCellLightParity:
    """Beer-Lambert cell light must match across backends."""

    def test_cell_light(self, all_backends, rng):
        depths = rng.uniform(0, 200, 20)
        depths[0] = 0.0  # ensure a dry cell
        np_be = all_backends["numpy"]
        np_light = np_be.compute_cell_light(depths, 500.0, 0.02, 8.0, 0.01, 0.001)
        for name, be in _non_numpy_backends(all_backends):
            light = be.compute_cell_light(depths, 500.0, 0.02, 8.0, 0.01, 0.001)
            np.testing.assert_allclose(
                light,
                np_light,
                rtol=_rtol_for(name),
                err_msg=f"{name}: cell light differs",
            )


# ---------------------------------------------------------------------------
# 4. evaluate_logistic
# ---------------------------------------------------------------------------


class TestEvaluateLogisticParity:
    """Logistic function must match across backends, including degenerate cases."""

    @pytest.mark.parametrize(
        "L1,L9",
        [(10.0, 20.0), (20.0, 10.0), (5.0, 5.0), (0.0, 100.0), (50.0, 50.0)],
    )
    def test_logistic(self, all_backends, L1, L9):
        x = np.linspace(-10, 60, 50)
        np_be = all_backends["numpy"]
        np_result = np_be.evaluate_logistic(x, L1, L9)
        for name, be in _non_numpy_backends(all_backends):
            result = be.evaluate_logistic(x, L1, L9)
            np.testing.assert_allclose(
                result,
                np_result,
                rtol=_rtol_for(name),
                err_msg=f"{name}: logistic differs for L1={L1}, L9={L9}",
            )


# ---------------------------------------------------------------------------
# 5. interp1d
# ---------------------------------------------------------------------------


class TestInterp1dParity:
    """Piecewise-linear interpolation must match across backends."""

    def test_interp1d(self, all_backends):
        table_x = np.array([0.0, 5.0, 10.0, 20.0, 30.0])
        table_y = np.array([0.0, 0.5, 1.0, 0.7, 0.0])
        x = np.array([-1.0, 0.0, 2.5, 7.5, 15.0, 25.0, 30.0, 35.0])
        np_be = all_backends["numpy"]
        np_result = np_be.interp1d(x, table_x, table_y)
        for name, be in _non_numpy_backends(all_backends):
            result = be.interp1d(x, table_x, table_y)
            np.testing.assert_allclose(
                result,
                np_result,
                rtol=_rtol_for(name),
                err_msg=f"{name}: interp1d differs",
            )


# ---------------------------------------------------------------------------
# 6. growth_rate
# ---------------------------------------------------------------------------


def _growth_params(rng, n):
    """Build a full growth_rate **params dict for n fish."""
    return dict(
        activities=rng.choice([0, 1, 2], n).astype(np.int32),
        lights=rng.uniform(50, 500, n),
        turbidities=rng.uniform(1, 15, n),
        drift_concs=rng.uniform(1e-11, 1e-9, n),
        search_prods=rng.uniform(1e-8, 1e-6, n),
        search_areas=rng.uniform(2000, 8000, n),
        available_drifts=np.full(n, 1e6),
        available_searches=np.full(n, 1e6),
        available_shelters=np.full(n, 1e6),
        shelter_speed_fracs=np.full(n, 0.3),
        superind_reps=np.ones(n, dtype=np.int32),
        prev_consumptions=rng.uniform(0, 0.5, n),
        step_length=1.0,
        cmax_As=np.full(n, 0.628),
        cmax_Bs=np.full(n, -0.3),
        cmax_temp_table_xs=[np.array([0, 5, 10, 15, 20, 25, 30], dtype=np.float64)] * n,
        cmax_temp_table_ys=[
            np.array([0.0, 0.15, 0.5, 0.98, 1.0, 0.8, 0.0], dtype=np.float64)
        ]
        * n,
        species_idxs=np.zeros(n, dtype=np.int32),
        react_dist_As=np.full(n, 0.5),
        react_dist_Bs=np.full(n, 0.1),
        turbid_thresholds=np.full(n, 10.0),
        turbid_mins=np.full(n, 0.1),
        turbid_exps=np.full(n, -0.1),
        light_thresholds=np.full(n, 100.0),
        light_mins=np.full(n, 0.1),
        light_exps=np.full(n, -0.01),
        capture_R1s=np.full(n, 0.5),
        capture_R9s=np.full(n, 0.9),
        max_speed_As=np.full(n, 2.5),
        max_speed_Bs=np.full(n, 0.5),
        max_swim_temp_terms=np.full(n, 1.0),
        resp_As=np.full(n, 0.0196),
        resp_Bs=np.full(n, -0.218),
        resp_Ds=np.full(n, 0.03),
        resp_temp_terms=np.full(n, 1.2),
        prey_energy_densities=np.full(n, 3500.0),
        fish_energy_densities=np.full(n, 5900.0),
    )


class TestGrowthRateParity:
    """Growth rate computation must match across all backends."""

    @pytest.mark.parametrize("n", [1, 5, 20])
    def test_growth_rate_batch(self, all_backends, rng, n):
        lengths = rng.uniform(3, 25, n)
        weights = rng.uniform(1, 100, n)
        temperatures = rng.uniform(5, 22, n)
        velocities = rng.uniform(1, 60, n)
        depths = rng.uniform(5, 200, n)
        kwargs = _growth_params(rng, n)

        np_be = all_backends["numpy"]
        np_result = np_be.growth_rate(
            lengths, weights, temperatures, velocities, depths, **kwargs
        )

        for name, be in _non_numpy_backends(all_backends):
            result = be.growth_rate(
                lengths, weights, temperatures, velocities, depths, **kwargs
            )
            np.testing.assert_allclose(
                result,
                np_result,
                rtol=_rtol_for(name),
                err_msg=f"{name}: growth_rate differs for n={n}",
            )

    def test_growth_rate_dry_cells(self, all_backends, rng):
        """Fish on dry cells should get negative growth (respiration only)."""
        n = 3
        lengths = rng.uniform(5, 15, n)
        weights = rng.uniform(5, 50, n)
        temperatures = np.full(n, 12.0)
        velocities = np.zeros(n)
        depths = np.zeros(n)
        kwargs = _growth_params(rng, n)
        kwargs["activities"] = np.full(n, 2, dtype=np.int32)  # hide

        np_be = all_backends["numpy"]
        np_result = np_be.growth_rate(
            lengths, weights, temperatures, velocities, depths, **kwargs
        )

        for name, be in _non_numpy_backends(all_backends):
            result = be.growth_rate(
                lengths, weights, temperatures, velocities, depths, **kwargs
            )
            np.testing.assert_allclose(
                result,
                np_result,
                rtol=_rtol_for(name),
                err_msg=f"{name}: growth_rate dry cells differ",
            )
        # All should be negative (pure respiration loss)
        assert np.all(np_result < 0), "Dry cell growth should be negative"

    def test_growth_rate_per_activity(self, all_backends):
        """Each activity type tested individually."""
        n = 1
        rng_local = np.random.default_rng(99)
        lengths = np.array([10.0])
        weights = np.array([8.0])
        temperatures = np.array([14.0])
        velocities = np.array([20.0])
        depths = np.array([50.0])

        np_be = all_backends["numpy"]
        for act in [0, 1, 2]:
            kwargs = _growth_params(rng_local, n)
            kwargs["activities"] = np.array([act], dtype=np.int32)
            np_result = np_be.growth_rate(
                lengths, weights, temperatures, velocities, depths, **kwargs
            )
            for name, be in _non_numpy_backends(all_backends):
                result = be.growth_rate(
                    lengths, weights, temperatures, velocities, depths, **kwargs
                )
                np.testing.assert_allclose(
                    result,
                    np_result,
                    rtol=_rtol_for(name),
                    err_msg=f"{name}: growth differs for activity={act}",
                )


# ---------------------------------------------------------------------------
# 7. survival
# ---------------------------------------------------------------------------


def _survival_params(rng, n):
    """Build a full survival **params dict for n fish."""
    return dict(
        velocities=rng.uniform(5, 60, n),
        lights=rng.uniform(10, 500, n),
        activities=rng.choice([0, 1, 2], n).astype(np.int32),
        pisciv_densities=rng.uniform(0, 0.01, n),
        dist_escapes=rng.uniform(5, 150, n),
        available_hidings=rng.uniform(0, 10, n),
        superind_reps=np.ones(n, dtype=np.int32),
        sp_mort_high_temp_T1=np.full(n, 28.0),
        sp_mort_high_temp_T9=np.full(n, 24.0),
        sp_mort_strand_survival_when_dry=np.full(n, 0.5),
        sp_mort_condition_S_at_K5=np.full(n, 0.8),
        sp_mort_condition_S_at_K8=np.full(n, 0.992),
        rp_fish_pred_min=np.full(n, 0.99),
        sp_mort_fish_pred_L1=np.full(n, 10.0),
        sp_mort_fish_pred_L9=np.full(n, 3.0),
        sp_mort_fish_pred_D1=np.full(n, 50.0),
        sp_mort_fish_pred_D9=np.full(n, 10.0),
        sp_mort_fish_pred_P1=np.full(n, 0.5),
        sp_mort_fish_pred_P9=np.full(n, 0.1),
        sp_mort_fish_pred_I1=np.full(n, 200.0),
        sp_mort_fish_pred_I9=np.full(n, 50.0),
        sp_mort_fish_pred_T1=np.full(n, 25.0),
        sp_mort_fish_pred_T9=np.full(n, 15.0),
        sp_mort_fish_pred_hiding_factor=np.full(n, 0.5),
        rp_terr_pred_min=np.full(n, 0.99),
        sp_mort_terr_pred_L1=np.full(n, 15.0),
        sp_mort_terr_pred_L9=np.full(n, 5.0),
        sp_mort_terr_pred_D1=np.full(n, 50.0),
        sp_mort_terr_pred_D9=np.full(n, 10.0),
        sp_mort_terr_pred_V1=np.full(n, 50.0),
        sp_mort_terr_pred_V9=np.full(n, 10.0),
        sp_mort_terr_pred_I1=np.full(n, 200.0),
        sp_mort_terr_pred_I9=np.full(n, 50.0),
        sp_mort_terr_pred_H1=np.full(n, 50.0),
        sp_mort_terr_pred_H9=np.full(n, 10.0),
        sp_mort_terr_pred_hiding_factor=np.full(n, 0.5),
    )


class TestSurvivalParity:
    """Survival computation must match across all backends."""

    @pytest.mark.parametrize("n", [1, 5, 20])
    def test_survival_batch(self, all_backends, rng, n):
        lengths = rng.uniform(3, 25, n)
        weights = rng.uniform(1, 100, n)
        conditions = rng.uniform(0.3, 1.0, n)
        temperatures = rng.uniform(8, 28, n)
        depths = rng.uniform(5, 200, n)
        kwargs = _survival_params(rng, n)

        np_be = all_backends["numpy"]
        np_result = np_be.survival(
            lengths, weights, conditions, temperatures, depths, **kwargs
        )
        assert np.all((np_result >= 0) & (np_result <= 1)), "Survival out of [0,1]"

        for name, be in _non_numpy_backends(all_backends):
            result = be.survival(
                lengths, weights, conditions, temperatures, depths, **kwargs
            )
            np.testing.assert_allclose(
                result,
                np_result,
                rtol=_rtol_for(name),
                err_msg=f"{name}: survival differs for n={n}",
            )

    def test_survival_stranding(self, all_backends):
        """Fish on dry cells get stranding penalty."""
        n = 3
        lengths = np.array([5.0, 10.0, 15.0])
        weights = np.array([2.0, 10.0, 30.0])
        conditions = np.array([0.9, 0.9, 0.9])
        temperatures = np.full(n, 12.0)
        depths = np.array([0.0, 50.0, 0.0])  # fish 0 and 2 stranded
        kwargs = _survival_params(np.random.default_rng(77), n)

        np_be = all_backends["numpy"]
        np_result = np_be.survival(
            lengths, weights, conditions, temperatures, depths, **kwargs
        )
        # Stranded fish should have lower survival
        assert np_result[0] < np_result[1], "Stranded fish should have lower survival"
        assert np_result[2] < np_result[1], "Stranded fish should have lower survival"

        for name, be in _non_numpy_backends(all_backends):
            result = be.survival(
                lengths, weights, conditions, temperatures, depths, **kwargs
            )
            np.testing.assert_allclose(
                result,
                np_result,
                rtol=_rtol_for(name),
                err_msg=f"{name}: stranding survival differs",
            )

    def test_survival_different_activities_parity(self, all_backends):
        """Backends must agree on survival regardless of activity mix."""
        n = 2
        lengths = np.array([5.0, 5.0])
        weights = np.array([2.0, 2.0])
        conditions = np.array([0.9, 0.9])
        temperatures = np.full(n, 15.0)
        depths = np.full(n, 50.0)

        kwargs = _survival_params(np.random.default_rng(88), n)
        kwargs["activities"] = np.array([0, 2], dtype=np.int32)  # drift vs hide
        kwargs["available_hidings"] = np.array([0.0, 5.0])

        np_be = all_backends["numpy"]
        np_result = np_be.survival(
            lengths, weights, conditions, temperatures, depths, **kwargs
        )

        for name, be in _non_numpy_backends(all_backends):
            result = be.survival(
                lengths, weights, conditions, temperatures, depths, **kwargs
            )
            np.testing.assert_allclose(
                result,
                np_result,
                rtol=_rtol_for(name),
                err_msg=f"{name}: activity-mix survival differs",
            )

    def test_survival_extreme_conditions(self, all_backends):
        """Edge cases: condition at 0, 0.5, 0.8, 1.0 boundaries."""
        n = 5
        lengths = np.full(n, 10.0)
        weights = np.full(n, 8.0)
        conditions = np.array([0.0, 0.3, 0.5, 0.8, 1.0])
        temperatures = np.full(n, 12.0)
        depths = np.full(n, 50.0)
        kwargs = _survival_params(np.random.default_rng(99), n)

        np_be = all_backends["numpy"]
        np_result = np_be.survival(
            lengths, weights, conditions, temperatures, depths, **kwargs
        )
        # condition=0 should give very low survival, condition=1 highest
        assert np_result[0] < np_result[4], (
            "condition=0 should have lower survival than condition=1"
        )

        for name, be in _non_numpy_backends(all_backends):
            result = be.survival(
                lengths, weights, conditions, temperatures, depths, **kwargs
            )
            np.testing.assert_allclose(
                result,
                np_result,
                rtol=_rtol_for(name),
                err_msg=f"{name}: extreme condition survival differs",
            )


# ---------------------------------------------------------------------------
# 8. spawn_suitability
# ---------------------------------------------------------------------------


class TestSpawnSuitabilityParity:
    """Spawn suitability scores must match across backends."""

    def test_spawn_suitability(self, all_backends):
        depths = np.array([10.0, 30.0, 50.0, 0.0, 80.0])
        velocities = np.array([15.0, 25.0, 40.0, 0.0, 60.0])
        frac_spawn = np.array([0.5, 0.8, 0.3, 0.0, 1.0])
        kwargs = dict(
            area=np.array([100.0, 200.0, 150.0, 50.0, 300.0]),
            depth_table_x=np.array([0.0, 20.0, 40.0, 60.0, 100.0]),
            depth_table_y=np.array([0.0, 0.5, 1.0, 0.8, 0.0]),
            vel_table_x=np.array([0.0, 20.0, 40.0, 60.0, 100.0]),
            vel_table_y=np.array([0.0, 0.7, 1.0, 0.5, 0.0]),
        )

        np_be = all_backends["numpy"]
        np_result = np_be.spawn_suitability(depths, velocities, frac_spawn, **kwargs)
        assert np_result[3] == 0.0, "Dry cell should have zero suitability"

        for name, be in _non_numpy_backends(all_backends):
            result = be.spawn_suitability(depths, velocities, frac_spawn, **kwargs)
            np.testing.assert_allclose(
                result,
                np_result,
                rtol=_rtol_for(name),
                err_msg=f"{name}: spawn suitability differs",
            )


# ---------------------------------------------------------------------------
# 9. deplete_resources
# ---------------------------------------------------------------------------


class TestDepleteResourcesParity:
    """Sequential resource depletion must match across backends."""

    def test_deplete_resources(self, all_backends):
        fish_order = np.array([0, 1, 2, 3])
        chosen_cells = np.array([0, 1, 0, 2])

        for name, be in all_backends.items():
            drift = np.array([10.0, 20.0, 15.0])
            search = np.array([8.0, 12.0, 10.0])
            shelter = np.array([500.0, 300.0, 400.0])
            hiding = np.array([5.0, 3.0, 4.0])

            be.deplete_resources(
                fish_order,
                chosen_cells,
                drift,
                search,
                chosen_activities=np.array([0, 1, 0, 2]),
                intake_amounts=np.array([2.0, 3.0, 1.5, 0.0]),
                fish_lengths=np.array([8.0, 10.0, 6.0, 12.0]),
                superind_reps=np.array([1, 1, 1, 1]),
                available_shelter=shelter,
                available_hiding=hiding,
            )

        # Compare final state: all backends should deplete identically
        # (depletion is inherently serial, all backends use Python loops)
        np_drift = np.array([10.0, 20.0, 15.0])
        np_search = np.array([8.0, 12.0, 10.0])
        np_shelter = np.array([500.0, 300.0, 400.0])
        np_hiding = np.array([5.0, 3.0, 4.0])
        all_backends["numpy"].deplete_resources(
            fish_order,
            chosen_cells,
            np_drift,
            np_search,
            chosen_activities=np.array([0, 1, 0, 2]),
            intake_amounts=np.array([2.0, 3.0, 1.5, 0.0]),
            fish_lengths=np.array([8.0, 10.0, 6.0, 12.0]),
            superind_reps=np.array([1, 1, 1, 1]),
            available_shelter=np_shelter,
            available_hiding=np_hiding,
        )

        for name, be in _non_numpy_backends(all_backends):
            be_drift = np.array([10.0, 20.0, 15.0])
            be_search = np.array([8.0, 12.0, 10.0])
            be_shelter = np.array([500.0, 300.0, 400.0])
            be_hiding = np.array([5.0, 3.0, 4.0])
            be.deplete_resources(
                fish_order,
                chosen_cells,
                be_drift,
                be_search,
                chosen_activities=np.array([0, 1, 0, 2]),
                intake_amounts=np.array([2.0, 3.0, 1.5, 0.0]),
                fish_lengths=np.array([8.0, 10.0, 6.0, 12.0]),
                superind_reps=np.array([1, 1, 1, 1]),
                available_shelter=be_shelter,
                available_hiding=be_hiding,
            )
            np.testing.assert_allclose(
                be_drift,
                np_drift,
                rtol=1e-15,
                err_msg=f"{name}: drift depletion differs",
            )
            np.testing.assert_allclose(
                be_search,
                np_search,
                rtol=1e-15,
                err_msg=f"{name}: search depletion differs",
            )
            np.testing.assert_allclose(
                be_shelter,
                np_shelter,
                rtol=1e-15,
                err_msg=f"{name}: shelter depletion differs",
            )
            np.testing.assert_allclose(
                be_hiding,
                np_hiding,
                rtol=1e-15,
                err_msg=f"{name}: hiding depletion differs",
            )
