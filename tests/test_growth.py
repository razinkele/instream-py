"""Tests for bioenergetics — CMax, consumption, swim speed, intake, respiration, growth."""

import numpy as np


class TestCMaxTemp:
    """Test CMax temperature function (interpolation table lookup)."""

    def test_at_table_point_zero(self):
        from instream.modules.growth import cmax_temp_function

        table_x = np.array([0.0, 2.0, 10.0, 22.0, 23.0, 25.0, 30.0])
        table_y = np.array([0.05, 0.05, 0.5, 1.0, 0.8, 0.5, 0.0])
        result = cmax_temp_function(0.0, table_x, table_y)
        np.testing.assert_allclose(result, 0.05)

    def test_at_table_point_22(self):
        from instream.modules.growth import cmax_temp_function

        table_x = np.array([0.0, 2.0, 10.0, 22.0, 23.0, 25.0, 30.0])
        table_y = np.array([0.05, 0.05, 0.5, 1.0, 0.8, 0.5, 0.0])
        result = cmax_temp_function(22.0, table_x, table_y)
        np.testing.assert_allclose(result, 1.0)

    def test_interpolation_at_16(self):
        from instream.modules.growth import cmax_temp_function

        table_x = np.array([0.0, 2.0, 10.0, 22.0, 23.0, 25.0, 30.0])
        table_y = np.array([0.05, 0.05, 0.5, 1.0, 0.8, 0.5, 0.0])
        result = cmax_temp_function(16.0, table_x, table_y)
        # Linear interp between (10, 0.5) and (22, 1.0): 0.5 + (6/12)*0.5 = 0.75
        np.testing.assert_allclose(result, 0.75, rtol=1e-6)


class TestCStepMax:
    """Test maximum consumption for a time step."""

    def test_positive_at_moderate_temp(self):
        from instream.modules.growth import c_stepmax

        # cmax_wt_term = cmax_A * weight^cmax_B = 0.628 * 10^0.7 ≈ 3.147
        cmax_wt_term = 0.628 * (10.0**0.7)
        cmax_temp = 0.5  # at T=10
        prev_cons = 0.0
        step_length = 1.0
        result = c_stepmax(cmax_wt_term, cmax_temp, prev_cons, step_length)
        expected = cmax_wt_term * cmax_temp  # full daily max
        np.testing.assert_allclose(result, expected, rtol=1e-10)

    def test_zero_when_fully_consumed(self):
        from instream.modules.growth import c_stepmax

        cmax_wt_term = 0.628 * (10.0**0.7)
        cmax_temp = 0.5
        c_max_daily = cmax_wt_term * cmax_temp
        prev_cons = c_max_daily * 2  # already consumed more than max
        step_length = 1.0
        result = c_stepmax(cmax_wt_term, cmax_temp, prev_cons, step_length)
        assert result == 0.0

    def test_decreases_with_prior_consumption(self):
        from instream.modules.growth import c_stepmax

        cmax_wt_term = 0.628 * (10.0**0.7)
        cmax_temp = 0.5
        r1 = c_stepmax(cmax_wt_term, cmax_temp, 0.0, 1.0)
        r2 = c_stepmax(cmax_wt_term, cmax_temp, 0.5, 1.0)
        assert r1 > r2

    def test_scales_with_step_length(self):
        from instream.modules.growth import c_stepmax

        cmax_wt_term = 0.628 * (10.0**0.7)
        cmax_temp = 0.5
        r_full = c_stepmax(cmax_wt_term, cmax_temp, 0.0, 1.0)
        r_half = c_stepmax(cmax_wt_term, cmax_temp, 0.0, 0.5)
        # With zero prev consumption and step_length=0.5:
        # c_stepmax = (cmax_daily - 0) / 0.5 = 2 * cmax_daily
        np.testing.assert_allclose(r_half, r_full * 2, rtol=1e-10)


class TestSwimSpeed:
    """Test swim speed calculations."""

    def test_max_swim_speed_formula(self):
        from instream.modules.growth import max_swim_speed

        # max_speed_len_term = A * length + B = 2.8 * 10 + 21 = 49
        # max_swim_temp_term = C*T² + D*T + E = -0.0029*225 + 0.084*15 + 0.37 = 0.9775
        len_term = 2.8 * 10.0 + 21.0
        temp_term = -0.0029 * 15.0**2 + 0.084 * 15.0 + 0.37
        result = max_swim_speed(len_term, temp_term)
        np.testing.assert_allclose(result, len_term * temp_term, rtol=1e-10)

    def test_increases_with_length(self):
        from instream.modules.growth import max_swim_speed

        temp_term = 1.0
        r_small = max_swim_speed(2.8 * 5 + 21, temp_term)
        r_large = max_swim_speed(2.8 * 20 + 21, temp_term)
        assert r_large > r_small

    def test_drift_speed_with_shelter(self):
        from instream.modules.growth import drift_swim_speed

        # Fish length 5, shelter available (100 > 5²=25 → use shelter)
        speed = drift_swim_speed(
            velocity=50.0,
            fish_length=5.0,
            available_shelter=100.0,
            shelter_speed_frac=0.3,
        )
        # 5²=25, shelter=100 > 25 → use shelter: 50 * 0.3 = 15
        np.testing.assert_allclose(speed, 15.0)

    def test_drift_speed_without_shelter(self):
        from instream.modules.growth import drift_swim_speed

        speed = drift_swim_speed(
            velocity=50.0,
            fish_length=15.0,
            available_shelter=100.0,
            shelter_speed_frac=0.3,
        )
        # 15²=225, shelter=100 < 225 → no shelter: velocity = 50
        np.testing.assert_allclose(speed, 50.0)

    def test_drift_speed_less_than_or_equal_max(self):
        from instream.modules.growth import drift_swim_speed

        speed = drift_swim_speed(
            velocity=50.0,
            fish_length=5.0,
            available_shelter=100.0,
            shelter_speed_frac=0.3,
        )
        assert speed <= 50.0  # shelter reduces speed


class TestDriftIntake:
    """Test drift feeding intake calculation."""

    def test_basic_drift_intake_positive(self):
        from instream.modules.growth import drift_intake

        result = drift_intake(
            length=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            turbidity=2.0,
            drift_conc=3.2e-10,
            max_swim_speed=50.0,
            c_stepmax_val=10.0,
            available_drift=1000.0,
            superind_rep=1,
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
        )
        assert result > 0.0

    def test_limited_by_cstepmax(self):
        from instream.modules.growth import drift_intake

        result = drift_intake(
            length=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            turbidity=2.0,
            drift_conc=3.2e-10,
            max_swim_speed=50.0,
            c_stepmax_val=0.001,  # very small limit
            available_drift=1000.0,
            superind_rep=1,
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
        )
        assert result <= 0.001

    def test_zero_in_dry_cell(self):
        from instream.modules.growth import drift_intake

        result = drift_intake(
            length=10.0,
            depth=0.0,
            velocity=0.0,
            light=0.9,
            turbidity=2.0,
            drift_conc=3.2e-10,
            max_swim_speed=50.0,
            c_stepmax_val=10.0,
            available_drift=1000.0,
            superind_rep=1,
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
        )
        assert result == 0.0

    def test_decreases_in_turbid_water(self):
        from instream.modules.growth import drift_intake

        kwargs = dict(
            length=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            drift_conc=3.2e-10,
            max_swim_speed=50.0,
            c_stepmax_val=100.0,
            available_drift=1000.0,
            superind_rep=1,
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
        )
        r_clear = drift_intake(turbidity=1.0, **kwargs)
        r_turbid = drift_intake(turbidity=20.0, **kwargs)
        assert r_clear > r_turbid

    def test_decreases_in_low_light(self):
        from instream.modules.growth import drift_intake

        kwargs = dict(
            length=10.0,
            depth=50.0,
            velocity=30.0,
            turbidity=2.0,
            drift_conc=3.2e-10,
            max_swim_speed=50.0,
            c_stepmax_val=100.0,
            available_drift=1000.0,
            superind_rep=1,
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
        )
        r_bright = drift_intake(light=100.0, **kwargs)
        r_dark = drift_intake(light=2.0, **kwargs)
        assert r_bright > r_dark

    def test_limited_by_available_drift(self):
        from instream.modules.growth import drift_intake

        result = drift_intake(
            length=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            turbidity=2.0,
            drift_conc=3.2e-10,
            max_swim_speed=50.0,
            c_stepmax_val=100.0,
            available_drift=0.0001,
            superind_rep=1,
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
        )
        assert result <= 0.0001


class TestSearchIntake:
    """Test search feeding intake."""

    def test_positive_when_velocity_below_max(self):
        from instream.modules.growth import search_intake

        result = search_intake(
            velocity=20.0,
            max_swim_speed=50.0,
            search_prod=8e-7,
            search_area=20000.0,
            c_stepmax_val=100.0,
            available_search=1000.0,
            superind_rep=1,
        )
        assert result > 0.0

    def test_zero_when_velocity_exceeds_max(self):
        from instream.modules.growth import search_intake

        result = search_intake(
            velocity=60.0,
            max_swim_speed=50.0,
            search_prod=8e-7,
            search_area=20000.0,
            c_stepmax_val=100.0,
            available_search=1000.0,
            superind_rep=1,
        )
        assert result == 0.0

    def test_limited_by_cstepmax(self):
        from instream.modules.growth import search_intake

        result = search_intake(
            velocity=10.0,
            max_swim_speed=50.0,
            search_prod=8e-7,
            search_area=20000.0,
            c_stepmax_val=0.0001,
            available_search=1000.0,
            superind_rep=1,
        )
        assert result <= 0.0001

    def test_limited_by_available_search(self):
        from instream.modules.growth import search_intake

        result = search_intake(
            velocity=10.0,
            max_swim_speed=50.0,
            search_prod=8e-7,
            search_area=20000.0,
            c_stepmax_val=100.0,
            available_search=0.00001,
            superind_rep=1,
        )
        assert result <= 0.00001


class TestRespiration:
    """Test respiration calculation."""

    def test_positive(self):
        from instream.modules.growth import respiration

        result = respiration(
            resp_std_wt_term=36 * 10**0.783,  # resp_A * weight^resp_B
            resp_temp_term=np.exp(0.002 * 15**2),  # exp(resp_C * T^2)
            swim_speed=30.0,
            max_swim_speed=50.0,
            resp_D=1.4,
        )
        assert result > 0.0

    def test_increases_with_swim_speed(self):
        from instream.modules.growth import respiration

        kwargs = dict(
            resp_std_wt_term=36 * 10**0.783,
            resp_temp_term=np.exp(0.002 * 15**2),
            max_swim_speed=50.0,
            resp_D=1.4,
        )
        r_slow = respiration(swim_speed=10.0, **kwargs)
        r_fast = respiration(swim_speed=40.0, **kwargs)
        assert r_fast > r_slow

    def test_hide_is_minimal(self):
        """Swim speed = 0 -> minimal respiration (standard only)."""
        from instream.modules.growth import respiration

        kwargs = dict(
            resp_std_wt_term=36 * 10**0.783,
            resp_temp_term=np.exp(0.002 * 15**2),
            max_swim_speed=50.0,
            resp_D=1.4,
        )
        r_hide = respiration(swim_speed=0.0, **kwargs)
        r_swim = respiration(swim_speed=30.0, **kwargs)
        assert r_hide < r_swim

    def test_overflow_guard(self):
        """Very high swim speed ratio -> capped at large value."""
        from instream.modules.growth import respiration

        result = respiration(
            resp_std_wt_term=100.0,
            resp_temp_term=1.0,
            swim_speed=1000.0,
            max_swim_speed=1.0,  # ratio=1000 >> 20
            resp_D=1.4,
        )
        assert result == 999999.0

    def test_formula_exact(self):
        """Verify exact formula: resp_standard * exp(resp_D * (speed/max_speed)^2)."""
        from instream.modules.growth import respiration

        std = 36 * 10**0.783
        temp = np.exp(0.002 * 15**2)
        speed = 25.0
        max_speed = 50.0
        resp_D = 1.4
        result = respiration(std, temp, speed, max_speed, resp_D)
        expected = std * temp * np.exp(resp_D * (speed / max_speed) ** 2)
        np.testing.assert_allclose(result, expected, rtol=1e-10)


class TestGrowthRate:
    """Test combined growth rate for all activities."""

    def test_growth_drift_is_intake_minus_respiration(self):
        from instream.modules.growth import growth_rate_for

        result = growth_rate_for(
            activity="drift",
            length=10.0,
            weight=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            turbidity=2.0,
            temperature=15.0,
            drift_conc=3.2e-10,
            search_prod=8e-7,
            search_area=20000.0,
            available_drift=1000.0,
            available_search=1000.0,
            available_shelter=1000.0,
            shelter_speed_frac=0.3,
            superind_rep=1,
            prev_consumption=0.0,
            step_length=1.0,
            # Species params
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            max_swim_temp_term=0.98,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            resp_temp_term=np.exp(0.002 * 225),
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
        )
        # Result should be a float (growth in g/d)
        assert isinstance(result, float)

    def test_growth_hide_is_negative(self):
        from instream.modules.growth import growth_rate_for

        result = growth_rate_for(
            activity="hide",
            length=10.0,
            weight=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            turbidity=2.0,
            temperature=15.0,
            drift_conc=3.2e-10,
            search_prod=8e-7,
            search_area=20000.0,
            available_drift=1000.0,
            available_search=1000.0,
            available_shelter=1000.0,
            shelter_speed_frac=0.3,
            superind_rep=1,
            prev_consumption=0.0,
            step_length=1.0,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            max_swim_temp_term=0.98,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            resp_temp_term=np.exp(0.002 * 225),
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
        )
        assert result < 0.0  # hiding = only respiration cost

    def test_growth_drift_vs_hide(self):
        """Drift should typically yield more growth than hiding."""
        from instream.modules.growth import growth_rate_for

        kwargs = dict(
            length=10.0,
            weight=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            turbidity=2.0,
            temperature=15.0,
            drift_conc=3.2e-10,
            search_prod=8e-7,
            search_area=20000.0,
            available_drift=1000.0,
            available_search=1000.0,
            available_shelter=1000.0,
            shelter_speed_frac=0.3,
            superind_rep=1,
            prev_consumption=0.0,
            step_length=1.0,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            max_swim_temp_term=0.98,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            resp_temp_term=np.exp(0.002 * 225),
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
        )
        g_drift = growth_rate_for(activity="drift", **kwargs)
        g_hide = growth_rate_for(activity="hide", **kwargs)
        assert g_drift > g_hide


class TestGrow:
    """Test weight/length/condition update."""

    def test_positive_growth_increases_weight(self):
        from instream.modules.growth import apply_growth

        new_w, new_l, new_k = apply_growth(
            weight=10.0,
            length=10.0,
            condition=1.0,
            growth=0.5,
            weight_A=0.0041,
            weight_B=3.49,
        )
        assert new_w > 10.0

    def test_negative_growth_decreases_weight(self):
        from instream.modules.growth import apply_growth

        new_w, new_l, new_k = apply_growth(
            weight=10.0,
            length=10.0,
            condition=1.0,
            growth=-0.5,
            weight_A=0.0041,
            weight_B=3.49,
        )
        assert new_w < 10.0

    def test_weight_never_negative(self):
        from instream.modules.growth import apply_growth

        new_w, _, _ = apply_growth(
            weight=0.1,
            length=5.0,
            condition=0.5,
            growth=-10.0,
            weight_A=0.0041,
            weight_B=3.49,
        )
        assert new_w >= 0.0

    def test_condition_drops_with_weight_loss(self):
        from instream.modules.growth import apply_growth

        _, _, new_k = apply_growth(
            weight=10.0,
            length=10.0,
            condition=1.0,
            growth=-2.0,
            weight_A=0.0041,
            weight_B=3.49,
        )
        assert new_k < 1.0

    def test_length_increases_when_weight_exceeds_healthy(self):
        from instream.modules.growth import apply_growth

        healthy_w = 0.0041 * 10.0**3.49
        new_w, new_l, new_k = apply_growth(
            weight=healthy_w,
            length=10.0,
            condition=1.0,
            growth=5.0,
            weight_A=0.0041,
            weight_B=3.49,
        )
        assert new_l > 10.0
        np.testing.assert_allclose(new_k, 1.0)

    def test_length_never_decreases(self):
        from instream.modules.growth import apply_growth

        _, new_l, _ = apply_growth(
            weight=10.0,
            length=10.0,
            condition=1.0,
            growth=-5.0,
            weight_A=0.0041,
            weight_B=3.49,
        )
        assert new_l >= 10.0

    def test_weight_from_length_and_condition(self):
        from instream.modules.growth import weight_from_length_and_condition

        w = weight_from_length_and_condition(10.0, 1.0, 0.0041, 3.49)
        expected = 0.0041 * 10.0**3.49
        np.testing.assert_allclose(w, expected, rtol=1e-10)

    def test_length_for_weight(self):
        from instream.modules.growth import length_for_weight

        w = 0.0041 * 10.0**3.49
        l = length_for_weight(w, 0.0041, 3.49)
        np.testing.assert_allclose(l, 10.0, rtol=1e-10)


class TestSuperindividual:
    """Test superindividual splitting."""

    def test_split_when_above_threshold(self):
        from instream.state.trout_state import TroutState
        from instream.modules.growth import split_superindividuals

        ts = TroutState.zeros(10)
        ts.alive[0] = True
        ts.length[0] = 6.0
        ts.weight[0] = 5.0
        ts.superind_rep[0] = 10
        ts.species_idx[0] = 0
        ts.age[0] = 1
        ts.condition[0] = 1.0
        split_superindividuals(ts, max_length=5.0)
        assert ts.num_alive() == 2
        assert ts.superind_rep[0] == 5
        assert ts.superind_rep[ts.alive_indices()[1]] == 5

    def test_no_split_below_threshold(self):
        from instream.state.trout_state import TroutState
        from instream.modules.growth import split_superindividuals

        ts = TroutState.zeros(10)
        ts.alive[0] = True
        ts.length[0] = 4.0
        ts.superind_rep[0] = 10
        split_superindividuals(ts, max_length=5.0)
        assert ts.num_alive() == 1

    def test_no_split_when_rep_is_one(self):
        from instream.state.trout_state import TroutState
        from instream.modules.growth import split_superindividuals

        ts = TroutState.zeros(10)
        ts.alive[0] = True
        ts.length[0] = 6.0
        ts.superind_rep[0] = 1
        split_superindividuals(ts, max_length=5.0)
        assert ts.num_alive() == 1

    def test_split_preserves_total_rep(self):
        from instream.state.trout_state import TroutState
        from instream.modules.growth import split_superindividuals

        ts = TroutState.zeros(10)
        ts.alive[0] = True
        ts.length[0] = 6.0
        ts.superind_rep[0] = 10
        split_superindividuals(ts, max_length=5.0)
        alive = ts.alive_indices()
        total = sum(ts.superind_rep[i] for i in alive)
        assert total == 10

    def test_no_split_when_full(self):
        from instream.state.trout_state import TroutState
        from instream.modules.growth import split_superindividuals

        ts = TroutState.zeros(2)
        ts.alive[0] = True
        ts.alive[1] = True  # all slots full
        ts.length[0] = 6.0
        ts.superind_rep[0] = 10
        split_superindividuals(ts, max_length=5.0)
        # Can't split — no dead slot. Should not crash.
        assert ts.num_alive() == 2
        assert ts.superind_rep[0] == 10  # unchanged

    def test_odd_rep_splits_correctly(self):
        """Rep=7 should split to 4+3 (integer division)."""
        from instream.state.trout_state import TroutState
        from instream.modules.growth import split_superindividuals

        ts = TroutState.zeros(10)
        ts.alive[0] = True
        ts.length[0] = 6.0
        ts.superind_rep[0] = 7
        split_superindividuals(ts, max_length=5.0)
        alive = ts.alive_indices()
        reps = sorted([ts.superind_rep[i] for i in alive])
        assert reps == [3, 4]  # 7 // 2 = 3, 7 - 3 = 4

    def test_split_copies_memory_arrays(self):
        """Split must copy growth/consumption/survival memory."""
        from instream.state.trout_state import TroutState
        from instream.modules.growth import split_superindividuals

        ts = TroutState.zeros(10, max_steps_per_day=4)
        ts.alive[0] = True
        ts.length[0] = 6.0
        ts.weight[0] = 5.0
        ts.superind_rep[0] = 10
        ts.growth_memory[0, 0] = 0.5
        ts.growth_memory[0, 1] = 0.3
        ts.consumption_memory[0, 0] = 1.2
        ts.resp_std_wt_term[0] = 42.0
        ts.cmax_wt_term[0] = 7.7
        split_superindividuals(ts, max_length=5.0)
        new_idx = ts.alive_indices()[1]
        np.testing.assert_allclose(ts.growth_memory[new_idx, 0], 0.5)
        np.testing.assert_allclose(ts.growth_memory[new_idx, 1], 0.3)
        np.testing.assert_allclose(ts.consumption_memory[new_idx, 0], 1.2)
        np.testing.assert_allclose(ts.resp_std_wt_term[new_idx], 42.0)
        np.testing.assert_allclose(ts.cmax_wt_term[new_idx], 7.7)


def test_drift_intake_equal_capture_R1_R9():
    from instream.modules.growth import drift_intake

    result = drift_intake(
        length=10.0,
        depth=50.0,
        velocity=20.0,
        light=100.0,
        turbidity=0.0,
        drift_conc=0.001,
        max_swim_speed=50.0,
        c_stepmax_val=1.0,
        available_drift=10.0,
        superind_rep=1,
        react_dist_A=1.0,
        react_dist_B=0.1,
        turbid_threshold=10.0,
        turbid_min=0.1,
        turbid_exp=-0.1,
        light_threshold=50.0,
        light_min=0.1,
        light_exp=-0.1,
        capture_R1=0.5,
        capture_R9=0.5,
    )
    import numpy as np

    assert np.isfinite(result)


def test_cmax_temp_bisect_matches_np_interp():
    """bisect-based interp must match np.interp exactly."""
    import numpy as np
    from instream.modules.growth import cmax_temp_function

    table_x = np.array([0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
    table_y = np.array([0.0, 0.2, 0.5, 0.8, 1.0, 0.7, 0.1])
    for temp in [-5.0, 0.0, 2.5, 7.0, 12.0, 20.0, 27.5, 35.0]:
        expected = float(np.interp(temp, table_x, table_y))
        got = cmax_temp_function(temp, table_x, table_y)
        assert abs(got - expected) < 1e-12, f"T={temp}: expected {expected}, got {got}"

    def test_capture_success_decreasing_with_velocity_ratio(self):
        """High velocity ratio → low capture success (R1=1.3 > R9=0.4)."""
        from instream.modules.growth import drift_intake

        kwargs = dict(
            length=10.0,
            depth=50.0,
            light=50.0,
            turbidity=2.0,
            drift_conc=3.2e-10,
            c_stepmax_val=1000.0,
            available_drift=1e6,
            superind_rep=1,
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
        )
        # Low vel ratio (20/50=0.4) → high capture
        r_low = drift_intake(velocity=20.0, max_swim_speed=50.0, **kwargs)
        # High vel ratio (48/50=0.96) → low capture
        r_high = drift_intake(velocity=48.0, max_swim_speed=50.0, **kwargs)
        assert r_low > r_high
