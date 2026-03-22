"""Tests for survival and mortality."""

import numpy as np


class TestHighTemperatureSurvival:
    def test_low_temp_high_survival(self):
        from instream.modules.survival import survival_high_temperature

        s = survival_high_temperature(temperature=10.0, T1=28.0, T9=24.0)
        assert s > 0.99

    def test_high_temp_low_survival(self):
        from instream.modules.survival import survival_high_temperature

        s = survival_high_temperature(temperature=29.0, T1=28.0, T9=24.0)
        assert s < 0.15

    def test_at_midpoint(self):
        from instream.modules.survival import survival_high_temperature

        s = survival_high_temperature(temperature=26.0, T1=28.0, T9=24.0)
        np.testing.assert_allclose(s, 0.5, atol=0.05)

    def test_bounded_zero_one(self):
        from instream.modules.survival import survival_high_temperature

        for t in [0, 10, 20, 25, 28, 30, 35]:
            s = survival_high_temperature(t, T1=28.0, T9=24.0)
            assert 0 <= s <= 1


class TestStrandingSurvival:
    def test_wet_cell_survives(self):
        from instream.modules.survival import survival_stranding

        s = survival_stranding(depth=50.0, survival_when_dry=0.5)
        assert s == 1.0

    def test_dry_cell_partial(self):
        from instream.modules.survival import survival_stranding

        s = survival_stranding(depth=0.0, survival_when_dry=0.5)
        assert s == 0.5


class TestConditionSurvival:
    def test_condition_one_is_one(self):
        from instream.modules.survival import survival_condition

        s = survival_condition(condition=1.0, S_at_K5=0.8, S_at_K8=0.992)
        assert s == 1.0

    def test_condition_half_is_S_at_K5(self):
        from instream.modules.survival import survival_condition

        s = survival_condition(condition=0.5, S_at_K5=0.8, S_at_K8=0.992)
        np.testing.assert_allclose(s, 0.8, atol=0.01)

    def test_condition_0_8_is_S_at_K8(self):
        from instream.modules.survival import survival_condition

        s = survival_condition(condition=0.8, S_at_K5=0.8, S_at_K8=0.992)
        np.testing.assert_allclose(s, 0.992, atol=0.01)

    def test_decreases_with_lower_condition(self):
        from instream.modules.survival import survival_condition

        s_high = survival_condition(condition=0.9, S_at_K5=0.8, S_at_K8=0.992)
        s_low = survival_condition(condition=0.6, S_at_K5=0.8, S_at_K8=0.992)
        assert s_high > s_low

    def test_bounded_zero_one(self):
        from instream.modules.survival import survival_condition

        for k in [0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0]:
            s = survival_condition(k, S_at_K5=0.8, S_at_K8=0.992)
            assert 0 <= s <= 1.0


def test_survival_condition_returns_python_float():
    """Must return pure Python float, not numpy scalar."""
    from instream.modules.survival import survival_condition

    result = survival_condition(0.85)
    assert type(result) is float
    assert 0.0 <= result <= 1.0


def test_survival_condition_zero_is_lethal():
    from instream.modules.survival import survival_condition

    assert survival_condition(0.0) == 0.0


def test_survival_condition_negative_is_lethal():
    from instream.modules.survival import survival_condition

    assert survival_condition(-0.5) == 0.0


class TestFishPredationSurvival:
    def test_large_fish_safer(self):
        from instream.modules.survival import survival_fish_predation

        s_small = survival_fish_predation(
            length=3.0,
            depth=30.0,
            light=20.0,
            pisciv_density=1e-6,
            temperature=10.0,
            activity="drift",
            min_surv=0.97,
            L1=3.0,
            L9=6.0,
            D1=35.0,
            D9=5.0,
            P1=5e-6,
            P9=-5.0,
            I1=50.0,
            I9=-50.0,
            T1=6.0,
            T9=2.0,
            hiding_factor=0.5,
        )
        s_large = survival_fish_predation(
            length=15.0,
            depth=30.0,
            light=20.0,
            pisciv_density=1e-6,
            temperature=10.0,
            activity="drift",
            min_surv=0.97,
            L1=3.0,
            L9=6.0,
            D1=35.0,
            D9=5.0,
            P1=5e-6,
            P9=-5.0,
            I1=50.0,
            I9=-50.0,
            T1=6.0,
            T9=2.0,
            hiding_factor=0.5,
        )
        assert s_large > s_small

    def test_hiding_improves_survival(self):
        from instream.modules.survival import survival_fish_predation

        kwargs = dict(
            length=5.0,
            depth=30.0,
            light=20.0,
            pisciv_density=1e-6,
            temperature=10.0,
            min_surv=0.97,
            L1=3.0,
            L9=6.0,
            D1=35.0,
            D9=5.0,
            P1=5e-6,
            P9=-5.0,
            I1=50.0,
            I9=-50.0,
            T1=6.0,
            T9=2.0,
            hiding_factor=0.5,
        )
        s_drift = survival_fish_predation(activity="drift", **kwargs)
        s_hide = survival_fish_predation(activity="hide", **kwargs)
        assert s_hide >= s_drift

    def test_bounded(self):
        from instream.modules.survival import survival_fish_predation

        s = survival_fish_predation(
            length=5.0,
            depth=30.0,
            light=20.0,
            pisciv_density=1e-6,
            temperature=10.0,
            activity="drift",
            min_surv=0.97,
            L1=3.0,
            L9=6.0,
            D1=35.0,
            D9=5.0,
            P1=5e-6,
            P9=-5.0,
            I1=50.0,
            I9=-50.0,
            T1=6.0,
            T9=2.0,
            hiding_factor=0.5,
        )
        assert 0.97 <= s <= 1.0  # bounded by min_surv


class TestTerrestrialPredationSurvival:
    def test_deep_water_safer(self):
        from instream.modules.survival import survival_terrestrial_predation

        kwargs = dict(
            length=5.0,
            velocity=30.0,
            light=20.0,
            dist_escape=100.0,
            activity="drift",
            available_hiding=5,
            superind_rep=1,
            min_surv=0.94,
            L1=6.0,
            L9=3.0,
            D1=0.0,
            D9=200.0,
            V1=20.0,
            V9=300.0,
            I1=50.0,
            I9=-10.0,
            H1=200.0,
            H9=-50.0,
            hiding_factor=0.8,
        )
        s_shallow = survival_terrestrial_predation(depth=5.0, **kwargs)
        s_deep = survival_terrestrial_predation(depth=100.0, **kwargs)
        assert s_deep > s_shallow

    def test_hiding_improves_survival(self):
        from instream.modules.survival import survival_terrestrial_predation

        kwargs = dict(
            length=5.0,
            depth=30.0,
            velocity=30.0,
            light=20.0,
            dist_escape=100.0,
            min_surv=0.94,
            available_hiding=5,
            superind_rep=1,
            L1=6.0,
            L9=3.0,
            D1=0.0,
            D9=200.0,
            V1=20.0,
            V9=300.0,
            I1=50.0,
            I9=-10.0,
            H1=200.0,
            H9=-50.0,
            hiding_factor=0.8,
        )
        s_drift = survival_terrestrial_predation(activity="drift", **kwargs)
        s_hide = survival_terrestrial_predation(activity="hide", **kwargs)
        assert s_hide >= s_drift

    def test_bounded(self):
        from instream.modules.survival import survival_terrestrial_predation

        s = survival_terrestrial_predation(
            length=5.0,
            depth=30.0,
            velocity=30.0,
            light=20.0,
            dist_escape=100.0,
            activity="drift",
            available_hiding=5,
            superind_rep=1,
            min_surv=0.94,
            L1=6.0,
            L9=3.0,
            D1=0.0,
            D9=200.0,
            V1=20.0,
            V9=300.0,
            I1=50.0,
            I9=-10.0,
            H1=200.0,
            H9=-50.0,
            hiding_factor=0.8,
        )
        assert 0.94 <= s <= 1.0


class TestCombinedSurvival:
    def test_product_of_sources(self):
        from instream.modules.survival import non_starve_survival

        s = non_starve_survival(
            s_high_temp=0.99, s_stranding=1.0, s_fish_pred=0.98, s_terr_pred=0.96
        )
        expected = 0.99 * 1.0 * 0.98 * 0.96
        np.testing.assert_allclose(s, expected, rtol=1e-10)

    def test_step_length_exponent(self):
        from instream.modules.survival import non_starve_survival

        daily = non_starve_survival(
            s_high_temp=0.9, s_stranding=1.0, s_fish_pred=0.95, s_terr_pred=0.95
        )
        half_day = daily**0.5
        assert half_day > daily  # shorter step -> higher survival


class TestApplyMortality:
    def test_survival_one_nobody_dies(self):
        from instream.modules.survival import apply_mortality

        alive = np.array([True, True, True, True, True])
        probs = np.ones(5)
        rng = np.random.default_rng(42)
        apply_mortality(alive, probs, rng)
        assert np.all(alive)

    def test_survival_zero_everybody_dies(self):
        from instream.modules.survival import apply_mortality

        alive = np.array([True, True, True, True, True])
        probs = np.zeros(5)
        rng = np.random.default_rng(42)
        apply_mortality(alive, probs, rng)
        assert not np.any(alive)

    def test_roughly_half_die(self):
        from instream.modules.survival import apply_mortality

        n = 1000
        alive = np.ones(n, dtype=bool)
        probs = np.full(n, 0.5)
        rng = np.random.default_rng(42)
        apply_mortality(alive, probs, rng)
        survived = np.sum(alive)
        assert 400 < survived < 600  # roughly half

    def test_dead_fish_stay_dead(self):
        from instream.modules.survival import apply_mortality

        alive = np.array([True, False, True])
        probs = np.ones(3)  # survival=1 -> nobody should die
        rng = np.random.default_rng(42)
        apply_mortality(alive, probs, rng)
        assert alive[0] and not alive[1] and alive[2]

    def test_deterministic_with_seed(self):
        from instream.modules.survival import apply_mortality

        alive1 = np.ones(100, dtype=bool)
        alive2 = np.ones(100, dtype=bool)
        probs = np.full(100, 0.5)
        apply_mortality(alive1, probs, np.random.default_rng(42))
        apply_mortality(alive2, probs, np.random.default_rng(42))
        np.testing.assert_array_equal(alive1, alive2)
