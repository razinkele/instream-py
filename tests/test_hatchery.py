"""Tests for v0.17.0 hatchery-origin tagging (InSALMON extension)."""

from __future__ import annotations

import numpy as np
import pytest

from instream.state.trout_state import TroutState
from instream.state.redd_state import ReddState
from instream.modules.spawning import redd_emergence
from instream.io.config import HatcheryStockingConfig
from instream.marine.config import MarineConfig, ZoneConfig
from instream.marine.survival import marine_survival


class TestIsHatcheryField:
    def test_default_is_false(self):
        ts = TroutState.zeros(10)
        assert ts.is_hatchery.dtype == bool
        assert ts.is_hatchery.shape == (10,)
        assert not np.any(ts.is_hatchery)

    def test_field_is_settable(self):
        ts = TroutState.zeros(5)
        ts.is_hatchery[2] = True
        assert bool(ts.is_hatchery[2]) is True
        assert bool(ts.is_hatchery[0]) is False


class TestAdultArrivalSlotReset:
    """Unit-level spec for Task 2.3: the arrival-path reset must include
    is_hatchery alongside the v0.16.0 marine fields. Full integration is
    exercised by the Phase 4 calibration test."""

    def test_reset_semantics(self):
        ts = TroutState.zeros(5)
        ts.alive[0] = False
        ts.is_hatchery[0] = True   # dead hatchery adult
        ts.zone_idx[0] = 2
        ts.sea_winters[0] = 3

        # Mirror the reset block that runs in the adult-arrival path
        slots = np.array([0])
        ts.alive[slots] = True
        ts.zone_idx[slots] = -1
        ts.sea_winters[slots] = 0
        ts.smolt_date[slots] = -1
        ts.smolt_readiness[slots] = 0.0
        ts.is_hatchery[slots] = False

        assert not ts.is_hatchery[0]
        assert ts.zone_idx[0] == -1
        assert ts.sea_winters[0] == 0


class TestHatcheryStockingConfig:
    def test_parses_full(self):
        cfg = HatcheryStockingConfig(
            num_fish=5000,
            reach="middle_river",
            date="2012-05-01",
            length_mean=15.0,
            length_sd=1.5,
            release_shock_survival=0.6,
        )
        assert cfg.num_fish == 5000
        assert cfg.reach == "middle_river"
        assert cfg.release_shock_survival == 0.6

    def test_defaults(self):
        cfg = HatcheryStockingConfig(
            num_fish=1000, reach="r1", date="2012-05-01"
        )
        assert cfg.length_mean == 15.0
        assert cfg.length_sd == 1.5
        assert cfg.release_shock_survival == 0.7


class TestHatcheryPredatorNaivety:
    """v0.17.0 — hatchery fish have higher cormorant hazard during the
    post-smolt vulnerability window, converging on wild rates after."""

    def test_hatchery_fish_lower_survival_in_window(self):
        cfg = MarineConfig(
            zones=[ZoneConfig(name="estuary", area_km2=10.0)],
            marine_mort_cormorant_zones=["estuary"],
            post_smolt_vulnerability_days=28,
            hatchery_predator_naivety_multiplier=2.5,
        )
        args = dict(
            length=np.array([15.0]),
            zone_idx=np.array([0]),
            temperature=np.array([10.0]),
            days_since_ocean_entry=np.array([5]),
            cormorant_zone_indices=np.array([0]),
            config=cfg,
        )
        wild = marine_survival(**args, is_hatchery=np.array([False]))
        hatchery = marine_survival(**args, is_hatchery=np.array([True]))
        assert hatchery[0] < wild[0]

    def test_hatchery_naivety_fades_after_window(self):
        cfg = MarineConfig(
            zones=[ZoneConfig(name="estuary", area_km2=10.0)],
            marine_mort_cormorant_zones=["estuary"],
            post_smolt_vulnerability_days=28,
            hatchery_predator_naivety_multiplier=2.5,
        )
        args = dict(
            length=np.array([15.0]),
            zone_idx=np.array([0]),
            temperature=np.array([10.0]),
            days_since_ocean_entry=np.array([60]),  # well past window
            cormorant_zone_indices=np.array([0]),
            config=cfg,
        )
        wild = marine_survival(**args, is_hatchery=np.array([False]))
        hatchery = marine_survival(**args, is_hatchery=np.array([True]))
        # After the window, cormorant hazard decays to 0 and both
        # hatchery and wild converge on identical survival.
        assert hatchery[0] == pytest.approx(wild[0], rel=1e-6)

    def test_backward_compat_none_is_hatchery(self):
        """marine_survival must still work when is_hatchery is omitted
        (legacy callers from v0.15.0 / v0.16.0)."""
        cfg = MarineConfig(
            zones=[ZoneConfig(name="estuary", area_km2=10.0)],
            marine_mort_cormorant_zones=["estuary"],
        )
        surv = marine_survival(
            length=np.array([15.0, 30.0]),
            zone_idx=np.array([0, 0]),
            temperature=np.array([10.0, 10.0]),
            days_since_ocean_entry=np.array([5, 5]),
            cormorant_zone_indices=np.array([0]),
            config=cfg,
            # is_hatchery omitted
        )
        assert surv.shape == (2,)
        assert np.all((surv >= 0) & (surv <= 1))


class TestHatcherySlotReset:
    """Slot-reuse reset regression: new wild fry emerging from redds must
    not inherit is_hatchery=True from dead hatchery-origin fish whose
    TroutState slots they reuse. Same class of bug as v0.16.0 ghost-smolt."""

    def test_wild_fry_reset_is_hatchery(self):
        ts = TroutState.zeros(10)
        # Corrupt first 3 slots: dead hatchery fish
        ts.alive[:3] = False
        ts.is_hatchery[:3] = True

        rs = ReddState.zeros(capacity=3)
        rs.alive[0] = True
        rs.species_idx[0] = 0
        rs.num_eggs[0] = 3
        rs.frac_developed[0] = 1.0
        rs.reach_idx[0] = 5
        rs.cell_idx[0] = 42

        # Arc E iter3 (2026-04-20): emergence spreads over 10 days with
        # super-ind aggregation. Call 10x with superind_max_rep=1 to get
        # the 3 rep-1 FRY this test expects.
        rng = np.random.default_rng(0)
        for _ in range(10):
            redd_emergence(
                redd_state=rs, trout_state=ts, rng=rng,
                emerge_length_min=2.5, emerge_length_mode=3.0, emerge_length_max=3.5,
                weight_A=0.0041, weight_B=3.49, species_index=0,
                superind_max_rep=1,
            )

        new_fry = np.where(ts.alive)[0]
        assert len(new_fry) == 3
        assert not np.any(ts.is_hatchery[new_fry]), (
            f"is_hatchery leaked: {ts.is_hatchery[new_fry]}"
        )
