"""Tests for marine growth bioenergetics (v0.15.0 Phase 1)."""

from __future__ import annotations

import numpy as np
import pytest

from instream.marine.growth import marine_growth, _cmax_temperature_response


# ---------------------------------------------------------------------------
# Default Hanson et al. 1997 parameters used by every test
# ---------------------------------------------------------------------------

DEFAULTS = dict(
    cmax_A=0.303,
    cmax_B=-0.275,
    cmax_topt=15.0,
    cmax_tmax=22.0,
    resp_A=0.0548,
    resp_B=-0.299,
    resp_Q10=2.1,
    growth_efficiency=0.50,
)


class TestTemperatureResponse:
    """CMax temperature multiplier shape checks."""

    def test_peak_at_topt(self):
        r = _cmax_temperature_response(np.array([15.0]), topt=15.0, tmax=22.0)
        assert r[0] == pytest.approx(1.0)

    def test_zero_above_tmax(self):
        r = _cmax_temperature_response(np.array([25.0]), topt=15.0, tmax=22.0)
        assert r[0] == 0.0

    def test_linear_descent(self):
        # midway between Topt and Tmax should give ~0.5
        r = _cmax_temperature_response(np.array([18.5]), topt=15.0, tmax=22.0)
        assert r[0] == pytest.approx(0.5, abs=0.05)

    def test_cold_water_reduced_consumption(self):
        r = _cmax_temperature_response(np.array([0.0]), topt=15.0, tmax=22.0)
        assert r[0] == 0.0


class TestMarineGrowth:
    """marine_growth() pure-function behaviour."""

    def test_positive_growth_good_conditions(self):
        delta = marine_growth(
            weights=np.array([500.0]),
            temperatures=np.array([15.0]),   # optimal
            prey_indices=np.array([1.0]),    # saturated
            conditions=np.array([1.0]),      # healthy
            **DEFAULTS,
        )
        assert delta[0] > 0

    def test_zero_prey_means_negative_growth(self):
        delta = marine_growth(
            weights=np.array([500.0]),
            temperatures=np.array([15.0]),
            prey_indices=np.array([0.0]),
            conditions=np.array([1.0]),
            **DEFAULTS,
        )
        # Respiration still happens, consumption is zero -> mass loss
        assert delta[0] < 0

    def test_hot_water_no_feeding(self):
        delta = marine_growth(
            weights=np.array([500.0]),
            temperatures=np.array([25.0]),   # above Tmax
            prey_indices=np.array([1.0]),
            conditions=np.array([1.0]),
            **DEFAULTS,
        )
        # Above Tmax CMax -> 0 but respiration still occurs -> starvation
        assert delta[0] < 0

    def test_allometric_scaling(self):
        # Specific growth (per-gram) should decrease with body size
        weights = np.array([100.0, 500.0, 2500.0])
        delta = marine_growth(
            weights=weights,
            temperatures=np.full(3, 15.0),
            prey_indices=np.ones(3),
            conditions=np.ones(3),
            **DEFAULTS,
        )
        specific = delta / weights
        assert specific[0] > specific[1] > specific[2]

    def test_zero_weight_zero_delta(self):
        delta = marine_growth(
            weights=np.array([0.0, 500.0]),
            temperatures=np.array([15.0, 15.0]),
            prey_indices=np.array([1.0, 1.0]),
            conditions=np.array([1.0, 1.0]),
            **DEFAULTS,
        )
        assert delta[0] == 0.0
        assert delta[1] > 0

    def test_condition_modifier(self):
        # Poor condition fish ingest less than healthy ones
        d_healthy = marine_growth(
            weights=np.array([500.0]),
            temperatures=np.array([15.0]),
            prey_indices=np.array([1.0]),
            conditions=np.array([1.0]),
            **DEFAULTS,
        )
        d_poor = marine_growth(
            weights=np.array([500.0]),
            temperatures=np.array([15.0]),
            prey_indices=np.array([1.0]),
            conditions=np.array([0.5]),
            **DEFAULTS,
        )
        assert d_poor[0] < d_healthy[0]

    def test_vectorised_output_shape(self):
        n = 1000
        rng = np.random.default_rng(42)
        delta = marine_growth(
            weights=rng.uniform(50, 5000, size=n),
            temperatures=rng.uniform(5, 20, size=n),
            prey_indices=rng.uniform(0, 1, size=n),
            conditions=rng.uniform(0.5, 1.0, size=n),
            **DEFAULTS,
        )
        assert delta.shape == (n,)
        assert np.isfinite(delta).all()

    def test_realistic_daily_growth_magnitude(self):
        # 500 g post-smolt, optimal temp, saturated prey
        # Expected order of magnitude: 1-10 g/day
        delta = marine_growth(
            weights=np.array([500.0]),
            temperatures=np.array([12.0]),
            prey_indices=np.array([0.8]),
            conditions=np.array([1.0]),
            **DEFAULTS,
        )
        assert 0.5 < delta[0] < 20.0, (
            f"marine growth of 500 g fish is {delta[0]:.2f} g/day, "
            f"expected 0.5..20 g/day"
        )
