"""Tests for marine fishing module (v0.15.0 Phase 3)."""

from __future__ import annotations

import datetime
import numpy as np
import pytest

from salmopy.marine.config import GearConfig
from salmopy.marine.fishing import (
    logistic_selectivity,
    normal_selectivity,
    gear_selectivity,
    fishing_mortality,
)


# ---------------------------------------------------------------------------
# Selectivity curves
# ---------------------------------------------------------------------------


class TestLogisticSelectivity:
    def test_midpoint_is_half(self):
        r = logistic_selectivity(np.array([55.0]), L50=55.0, slope=3.0)
        assert r[0] == pytest.approx(0.5, abs=1e-4)

    def test_monotonic(self):
        r = logistic_selectivity(
            np.array([30.0, 50.0, 70.0, 100.0]), L50=55.0, slope=3.0
        )
        assert np.all(np.diff(r) > 0)


class TestNormalSelectivity:
    def test_peak_at_mean(self):
        r = normal_selectivity(np.array([70.0]), mean=70.0, sd=8.0)
        assert r[0] == pytest.approx(1.0, abs=1e-6)

    def test_decays_symmetrically(self):
        r = normal_selectivity(
            np.array([60.0, 70.0, 80.0]), mean=70.0, sd=8.0
        )
        assert r[0] == pytest.approx(r[2], abs=1e-6)
        assert r[1] > r[0]


class TestGearDispatch:
    def test_logistic_dispatch(self):
        gear = GearConfig(selectivity_type="logistic", selectivity_L50=50.0, selectivity_slope=4.0)
        r = gear_selectivity(np.array([50.0]), gear)
        assert r[0] == pytest.approx(0.5, abs=1e-4)

    def test_normal_dispatch(self):
        gear = GearConfig(selectivity_type="normal", selectivity_mean=70.0, selectivity_sd=8.0)
        r = gear_selectivity(np.array([70.0]), gear)
        assert r[0] == pytest.approx(1.0, abs=1e-6)

    def test_unknown_type_raises(self):
        gear = GearConfig(selectivity_type="logistic")
        gear.selectivity_type = "bogus"  # bypass Literal validation post-construction
        with pytest.raises(ValueError):
            gear_selectivity(np.array([50.0]), gear)


# ---------------------------------------------------------------------------
# Full fishing_mortality
# ---------------------------------------------------------------------------


def _trap_net() -> GearConfig:
    return GearConfig(
        selectivity_type="logistic",
        selectivity_L50=55.0,
        selectivity_slope=3.0,
        bycatch_mortality=0.10,
        zones=["estuary", "coastal"],
        open_months=[6, 7, 8, 9],
        daily_effort=1.0,  # deterministic: always encountered
    )


class TestFishingMortality:
    def test_closed_season_no_mortality(self):
        gear = _trap_net()
        rng = np.random.default_rng(0)
        survival, tally = fishing_mortality(
            lengths=np.array([70.0, 70.0]),
            zone_idx=np.array([0, 1]),
            current_date=datetime.date(2020, 1, 15),   # January -> closed
            zone_name_by_idx=["estuary", "coastal", "baltic"],
            gear_configs={"trap_net": gear},
            min_legal_length=60.0,
            rng=rng,
        )
        assert np.all(survival == 1.0)
        assert tally == {}

    def test_wrong_zone_no_mortality(self):
        gear = _trap_net()
        rng = np.random.default_rng(0)
        survival, tally = fishing_mortality(
            lengths=np.array([70.0]),
            zone_idx=np.array([2]),      # baltic — not in gear.zones
            current_date=datetime.date(2020, 7, 15),
            zone_name_by_idx=["estuary", "coastal", "baltic"],
            gear_configs={"trap_net": gear},
            min_legal_length=60.0,
            rng=rng,
        )
        assert survival[0] == 1.0

    def test_legal_fish_landed(self):
        gear = _trap_net()
        rng = np.random.default_rng(1)
        # deterministic encounter (daily_effort=1.0) and retention (L=100 >> L50)
        survival, tally = fishing_mortality(
            lengths=np.array([100.0, 100.0, 100.0]),
            zone_idx=np.array([0, 0, 0]),
            current_date=datetime.date(2020, 7, 15),
            zone_name_by_idx=["estuary", "coastal", "baltic"],
            gear_configs={"trap_net": gear},
            min_legal_length=60.0,
            rng=rng,
        )
        assert np.all(survival == 0.0)
        assert tally.get("trap_net", 0) == 3

    def test_sublegal_bycatch_partial_mortality(self):
        gear = _trap_net()
        # Large cohort just above L50 (so retention is high) but below legal (60)
        n = 2000
        rng = np.random.default_rng(42)
        survival, tally = fishing_mortality(
            lengths=np.full(n, 58.0),    # retained but sublegal
            zone_idx=np.zeros(n, dtype=np.int64),
            current_date=datetime.date(2020, 7, 15),
            zone_name_by_idx=["estuary", "coastal", "baltic"],
            gear_configs={"trap_net": gear},
            min_legal_length=60.0,
            rng=rng,
        )
        killed = np.sum(survival == 0.0)
        # Expected bycatch mortality ~10% of retained fish
        assert 0.05 * n < killed < 0.18 * n

    def test_no_gear_no_mortality(self):
        rng = np.random.default_rng(0)
        survival, tally = fishing_mortality(
            lengths=np.array([70.0]),
            zone_idx=np.array([0]),
            current_date=datetime.date(2020, 7, 15),
            zone_name_by_idx=["estuary", "coastal", "baltic"],
            gear_configs={},
            min_legal_length=60.0,
            rng=rng,
        )
        assert survival[0] == 1.0
        assert tally == {}
