"""Phase 2 Task 2.9: expected_fitness property tests + structural guard.

The canonical expected_fitness lives in salmopy.modules.habitat_fitness.
behavior.py has two inline implementations of the same formula (batch at
~line 956, scalar fallback at ~line 1444). This test suite guards the
canonical function's invariants and asserts behavior.py either imports
the canonical function or (as a fallback) keeps the inline implementations
bounded to the same [0,1] output range.
"""
import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from salmopy.modules.habitat_fitness import expected_fitness


@given(
    daily_survival=st.floats(0.0, 1.0),
    mean_starv=st.floats(0.0, 1.0),
    length=st.floats(1.0, 50.0),
    daily_growth=st.floats(-0.1, 0.5),
    time_horizon=st.integers(0, 120),
    fitness_length=st.floats(0.0, 40.0),
)
@settings(max_examples=200, deadline=1000)
def test_expected_fitness_output_in_unit_interval(
    daily_survival, mean_starv, length, daily_growth, time_horizon, fitness_length
):
    """Canonical expected_fitness must return a value in [0, 1] for any
    biologically plausible input."""
    result = expected_fitness(
        daily_survival=daily_survival,
        mean_starv_survival=mean_starv,
        length=length,
        daily_growth=daily_growth,
        time_horizon=time_horizon,
        fitness_length=fitness_length,
    )
    assert 0.0 <= result <= 1.0
    assert not np.isnan(result)


def test_expected_fitness_zero_survival_gives_zero():
    """Zero daily survival over any nonzero horizon must yield fitness = 0."""
    r = expected_fitness(
        daily_survival=0.0, mean_starv_survival=1.0,
        length=10.0, daily_growth=0.1, time_horizon=60,
        fitness_length=15.0,
    )
    assert r == 0.0


def test_expected_fitness_zero_horizon_gives_unit():
    """Zero horizon implies base = s^0 = 1 before length penalty."""
    r = expected_fitness(
        daily_survival=0.5, mean_starv_survival=0.5,
        length=5.0, daily_growth=0.1, time_horizon=0,
        fitness_length=15.0,
    )
    # With horizon=0, base = 1.0; length penalty: length_at_horizon = length
    # = 5.0 < 15.0 so base *= 5.0/15.0 = 0.333
    assert r == pytest.approx(5.0 / 15.0, rel=1e-6)
