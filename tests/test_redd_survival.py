"""Tests for redd (egg) survival."""
import numpy as np
import pytest


class TestReddLoTempSurvival:
    def test_cold_kills_eggs(self):
        from salmopy.modules.survival import redd_survival_lo_temp
        frac = redd_survival_lo_temp(temperature=0.0, T1=1.7, T9=4.0, step_length=1.0)
        assert frac < 1.0  # significant mortality at T=0

    def test_warm_no_mortality(self):
        from salmopy.modules.survival import redd_survival_lo_temp
        frac = redd_survival_lo_temp(temperature=15.0, T1=1.7, T9=4.0, step_length=1.0)
        np.testing.assert_allclose(frac, 1.0, atol=0.01)

    def test_bounded_zero_one(self):
        from salmopy.modules.survival import redd_survival_lo_temp
        for t in [0, 1, 2, 3, 5, 10, 20]:
            f = redd_survival_lo_temp(t, T1=1.7, T9=4.0, step_length=1.0)
            assert 0 <= f <= 1.0


class TestReddHiTempSurvival:
    def test_hot_kills_eggs(self):
        from salmopy.modules.survival import redd_survival_hi_temp
        frac = redd_survival_hi_temp(temperature=25.0, T1=23.0, T9=17.5, step_length=1.0)
        assert frac < 1.0

    def test_cool_no_mortality(self):
        from salmopy.modules.survival import redd_survival_hi_temp
        frac = redd_survival_hi_temp(temperature=10.0, T1=23.0, T9=17.5, step_length=1.0)
        np.testing.assert_allclose(frac, 1.0, atol=0.01)


class TestReddDewateringSurvival:
    def test_dry_cell_kills_fraction(self):
        from salmopy.modules.survival import redd_survival_dewatering
        frac = redd_survival_dewatering(depth=0.0, dewater_surv=0.9)
        assert frac == pytest.approx(0.9)

    def test_wet_cell_no_mortality(self):
        from salmopy.modules.survival import redd_survival_dewatering
        frac = redd_survival_dewatering(depth=50.0, dewater_surv=0.9)
        assert frac == 1.0


class TestReddScourSurvival:
    def test_high_flow_kills_all(self):
        from salmopy.modules.survival import redd_survival_scour
        frac = redd_survival_scour(
            flow=100.0, is_flow_peak=True,
            shear_A=0.013, shear_B=0.40, scour_depth=20.0)
        # Use a low scour_depth threshold so high flow triggers scour
        frac_extreme = redd_survival_scour(
            flow=10000.0, is_flow_peak=True,
            shear_A=0.013, shear_B=0.40, scour_depth=0.1)
        assert frac_extreme == 0.0

    def test_no_scour_when_not_peak(self):
        from salmopy.modules.survival import redd_survival_scour
        frac = redd_survival_scour(
            flow=10000.0, is_flow_peak=False,
            shear_A=0.013, shear_B=0.40, scour_depth=20.0)
        assert frac == 1.0

    def test_low_flow_no_scour(self):
        from salmopy.modules.survival import redd_survival_scour
        frac = redd_survival_scour(
            flow=1.0, is_flow_peak=True,
            shear_A=0.013, shear_B=0.40, scour_depth=20.0)
        assert frac == 1.0


class TestApplyReddSurvival:
    def test_eggs_decrease_in_cold(self):
        from salmopy.modules.survival import apply_redd_survival
        num_eggs = np.array([100, 200])
        frac_developed = np.array([0.5, 0.5])
        temperatures = np.array([0.0, 15.0])
        depths = np.array([50.0, 50.0])
        flows = np.array([5.0, 5.0])
        is_peak = np.array([False, False])
        new_eggs, lo, hi, dw, sc = apply_redd_survival(
            num_eggs, frac_developed, temperatures, depths, flows, is_peak,
            step_length=1.0,
            lo_T1=1.7, lo_T9=4.0, hi_T1=23.0, hi_T9=17.5,
            dewater_surv=0.9,
            shear_A=0.013, shear_B=0.4, scour_depth=20.0)
        assert new_eggs[0] < 100  # cold cell lost eggs
        assert new_eggs[1] == pytest.approx(200, abs=5)  # warm cell negligible loss
        assert lo[0] > 0  # low temp deaths recorded

    def test_eggs_never_negative(self):
        from salmopy.modules.survival import apply_redd_survival
        num_eggs = np.array([1])
        new_eggs, _, _, _, _ = apply_redd_survival(
            num_eggs, np.array([0.5]), np.array([0.0]), np.array([0.0]),
            np.array([10000.0]), np.array([True]),
            step_length=1.0,
            lo_T1=1.7, lo_T9=4.0, hi_T1=23.0, hi_T9=17.5,
            dewater_surv=0.1, shear_A=0.013, shear_B=0.4, scour_depth=20.0)
        assert new_eggs[0] >= 0
