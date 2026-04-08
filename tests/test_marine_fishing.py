import numpy as np
from instream.modules.marine_fishing import (
    logistic_selectivity, normal_selectivity, apply_fishing_mortality,
)

def test_logistic_selectivity():
    lengths = np.array([40.0, 55.0, 70.0, 85.0])
    sel = logistic_selectivity(lengths, L50=55.0, slope=3.0)
    assert sel[0] < 0.5
    assert abs(sel[1] - 0.5) < 0.01
    assert sel[3] > 0.9

def test_normal_selectivity():
    lengths = np.array([50.0, 70.0, 90.0])
    sel = normal_selectivity(lengths, mean=70.0, sd=8.0)
    assert sel[1] > sel[0]
    assert sel[1] > sel[2]

def test_closed_season_no_catch():
    rng = np.random.default_rng(42)
    gear = {"selectivity_type": "logistic", "selectivity_L50": 55.0,
            "selectivity_slope": 3.0, "bycatch_mortality": 0.1,
            "zones": ["estuary"], "open_months": [6, 7, 8],
            "daily_effort": 0.5}
    landed, dead = apply_fishing_mortality(
        np.array([70.0, 80.0]), np.array([0, 0]), current_month=1,
        gear_configs=[gear], zone_names=["estuary", "coastal"],
        min_legal_length=60.0, rng=rng)
    assert np.sum(landed) == 0
    assert np.sum(dead) == 0

def test_undersized_bycatch():
    rng = np.random.default_rng(42)
    gear = {"selectivity_type": "logistic", "selectivity_L50": 40.0,
            "selectivity_slope": 3.0, "bycatch_mortality": 0.5,
            "zones": ["estuary"], "open_months": [6],
            "daily_effort": 1.0}
    landed, dead = apply_fishing_mortality(
        np.array([45.0] * 1000), np.array([0] * 1000), current_month=6,
        gear_configs=[gear], zone_names=["estuary"],
        min_legal_length=60.0, rng=rng)
    assert np.sum(landed) == 0
    assert np.sum(dead) > 0
