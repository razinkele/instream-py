"""Property-based tests using hypothesis for mathematical invariants."""
import numpy as np
from hypothesis import given, strategies as st, assume

from salmopy.modules.survival import (
    survival_high_temperature, survival_stranding, survival_condition,
)
from salmopy.modules.growth import apply_growth, drift_intake
from salmopy.modules.behavior import evaluate_logistic

reasonable_float = st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)
positive_float = st.floats(min_value=0.01, max_value=1000, allow_nan=False, allow_infinity=False)


@given(temp=reasonable_float)
def test_survival_high_temp_in_01(temp):
    s = survival_high_temperature(temp)
    assert 0.0 <= s <= 1.0


@given(condition=st.floats(min_value=0.0, max_value=2.0, allow_nan=False))
def test_survival_condition_in_01(condition):
    s = survival_condition(condition)
    assert 0.0 <= s <= 1.0


@given(x=reasonable_float, L1=reasonable_float, L9=reasonable_float)
def test_logistic_in_01(x, L1, L9):
    result = evaluate_logistic(x, L1, L9)
    assert 0.0 <= result <= 1.0


@given(weight=positive_float, length=positive_float,
       growth=st.floats(min_value=-50, max_value=50, allow_nan=False))
def test_apply_growth_weight_non_negative(weight, length, growth):
    new_w, new_l, new_k = apply_growth(weight, length, 1.0, growth, 0.000247, 2.9)
    assert new_w >= 0.0
    assert new_l >= length
    assert new_k >= 0.0


@given(length=positive_float, depth=positive_float, velocity=positive_float)
def test_drift_intake_non_negative(length, depth, velocity):
    assume(velocity < 200)
    result = drift_intake(
        length=length, depth=depth, velocity=velocity, light=100.0,
        turbidity=0.0, drift_conc=0.001, max_swim_speed=100.0,
        c_stepmax_val=10.0, available_drift=100.0, superind_rep=1,
        react_dist_A=1.0, react_dist_B=0.1,
        turbid_threshold=10.0, turbid_min=0.1, turbid_exp=-0.1,
        light_threshold=50.0, light_min=0.1, light_exp=-0.1,
        capture_R1=1.3, capture_R9=0.4,
    )
    assert result >= 0.0
    assert np.isfinite(result)
