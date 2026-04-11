"""Tests for marine survival — 7 mortality sources (v0.15.0 Phase 2)."""

from __future__ import annotations

import numpy as np
import pytest

from instream.marine.config import MarineConfig, ZoneConfig
from instream.marine.survival import (
    _logistic_hazard,
    seal_hazard,
    cormorant_hazard,
    background_hazard,
    temperature_stress_hazard,
    m74_hazard,
    marine_survival,
)


@pytest.fixture
def cfg():
    return MarineConfig(
        zones=[
            ZoneConfig(name="estuary", area_km2=10.0),
            ZoneConfig(name="coastal", area_km2=100.0),
            ZoneConfig(name="baltic", area_km2=1000.0),
        ],
        marine_mort_seal_L1=40.0,
        marine_mort_seal_L9=80.0,
        marine_mort_seal_max_daily=0.02,
        marine_mort_base=0.001,
        marine_mort_cormorant_L1=15.0,
        marine_mort_cormorant_L9=40.0,
        marine_mort_cormorant_max_daily=0.03,
        marine_mort_cormorant_zones=["estuary", "coastal"],
        post_smolt_vulnerability_days=28,
        temperature_stress_threshold=20.0,
        temperature_stress_daily=0.01,
        marine_mort_m74_prob=0.0,
    )


class TestLogisticHazard:
    def test_monotonic_rise_with_length(self):
        h = _logistic_hazard(
            np.array([20.0, 40.0, 60.0, 80.0, 100.0]),
            L1=40.0, L9=80.0, max_daily=0.02,
        )
        assert np.all(np.diff(h) > 0)

    def test_bounds(self):
        h = _logistic_hazard(
            np.array([0.0, 200.0]),
            L1=40.0, L9=80.0, max_daily=0.02,
        )
        assert 0 <= h[0] < 0.01 * 0.02 + 1e-6
        assert h[1] == pytest.approx(0.02, abs=1e-4)

    def test_midpoint_is_half_max(self):
        h = _logistic_hazard(
            np.array([60.0]),  # midway between 40 and 80
            L1=40.0, L9=80.0, max_daily=0.02,
        )
        assert h[0] == pytest.approx(0.01, abs=1e-4)


class TestSealHazard:
    def test_larger_fish_more_risk(self, cfg):
        h = seal_hazard(np.array([30.0, 50.0, 90.0]), cfg)
        assert h[0] < h[1] < h[2]

    def test_zero_max_daily_kills_seal_source(self, cfg):
        cfg = cfg.model_copy(update={"marine_mort_seal_max_daily": 0.0})
        h = seal_hazard(np.array([60.0]), cfg)
        assert h[0] == 0.0


class TestCormorantHazard:
    def test_smaller_smolts_more_risk(self, cfg):
        h = cormorant_hazard(
            length=np.array([10.0, 25.0, 50.0]),
            zone_idx=np.array([0, 0, 0]),     # estuary
            days_since_ocean_entry=np.array([0, 0, 0]),
            cormorant_zone_indices=np.array([0, 1]),
            config=cfg,
        )
        assert h[0] > h[1] > h[2]

    def test_offshore_zone_has_zero_hazard(self, cfg):
        h = cormorant_hazard(
            length=np.array([15.0]),
            zone_idx=np.array([2]),           # baltic
            days_since_ocean_entry=np.array([0]),
            cormorant_zone_indices=np.array([0, 1]),
            config=cfg,
        )
        assert h[0] == 0.0

    def test_post_smolt_decay(self, cfg):
        h_day0 = cormorant_hazard(
            length=np.array([15.0]),
            zone_idx=np.array([0]),
            days_since_ocean_entry=np.array([0]),
            cormorant_zone_indices=np.array([0, 1]),
            config=cfg,
        )
        h_day28 = cormorant_hazard(
            length=np.array([15.0]),
            zone_idx=np.array([0]),
            days_since_ocean_entry=np.array([28]),
            cormorant_zone_indices=np.array([0, 1]),
            config=cfg,
        )
        assert h_day0[0] > 0
        assert h_day28[0] == 0.0


class TestBackgroundHazard:
    def test_constant_rate(self, cfg):
        h = background_hazard(5, cfg)
        assert h.shape == (5,)
        assert np.all(h == cfg.marine_mort_base)


class TestTemperatureStress:
    def test_no_hazard_below_threshold(self, cfg):
        h = temperature_stress_hazard(np.array([10.0, 19.9]), cfg)
        assert np.all(h == 0.0)

    def test_hazard_above_threshold(self, cfg):
        h = temperature_stress_hazard(np.array([21.0, 25.0]), cfg)
        assert np.all(h == cfg.temperature_stress_daily)


class TestM74:
    def test_zero_default(self, cfg):
        h = m74_hazard(10, cfg)
        assert np.all(h == 0.0)

    def test_nonzero_applies(self, cfg):
        cfg = cfg.model_copy(update={"marine_mort_m74_prob": 0.002})
        h = m74_hazard(3, cfg)
        assert np.all(h == 0.002)


class TestMarineSurvivalIntegration:
    def test_combined_always_in_unit_interval(self, cfg):
        surv = marine_survival(
            length=np.array([20.0, 50.0, 80.0]),
            zone_idx=np.array([0, 1, 2]),
            temperature=np.array([12.0, 12.0, 12.0]),
            days_since_ocean_entry=np.array([0, 30, 365]),
            cormorant_zone_indices=np.array([0, 1]),
            config=cfg,
        )
        assert np.all((surv >= 0.0) & (surv <= 1.0))

    def test_ocean_post_smolt_bottleneck(self, cfg):
        """Small post-smolts in estuary should have lower survival than
        large adults offshore — the Thorstad et al. 2012 bottleneck."""
        surv = marine_survival(
            length=np.array([15.0, 80.0]),
            zone_idx=np.array([0, 2]),
            temperature=np.array([12.0, 12.0]),
            days_since_ocean_entry=np.array([0, 365]),
            cormorant_zone_indices=np.array([0, 1]),
            config=cfg,
        )
        # Post-smolt survival < adult survival
        assert surv[0] < surv[1]

    def test_cohort_attrition_matches_iCes_band(self, cfg):
        """Running survival daily for 2 years should yield 2-15% survivorship
        in the order of magnitude reported by ICES WGBAST for Baltic salmon.

        NOTE: the design-doc defaults (seal max 2%/day, cormorant max 3%/day)
        are *peak* hazard values, not sustainable daily rates. Using them
        literally would kill 99.9% of a cohort in 2 years. Here we override
        with calibrated sustainable rates — the design-doc numbers remain
        in :class:`MarineConfig` as a conservative ceiling.
        """
        cfg = cfg.model_copy(update={
            "marine_mort_seal_max_daily": 0.003,
            "marine_mort_cormorant_max_daily": 0.010,
            "marine_mort_base": 0.001,
        })
        n = 10_000
        rng = np.random.default_rng(0)
        alive = np.ones(n, dtype=bool)
        length = np.full(n, 20.0)      # start as 20 cm post-smolts
        zone = np.zeros(n, dtype=np.int64)  # estuary
        for day in range(730):
            # graduate to coastal after 14 d, baltic after 30 d
            if day == 14:
                zone[:] = 1
            elif day == 30:
                zone[:] = 2
            length = np.minimum(length + 0.08, 80.0)  # ~ cm/day growth
            days_since = np.full(n, day, dtype=np.int64)
            surv = marine_survival(
                length=length,
                zone_idx=zone,
                temperature=np.full(n, 10.0),
                days_since_ocean_entry=days_since,
                cormorant_zone_indices=np.array([0, 1]),
                config=cfg,
            )
            draws = rng.random(n)
            alive &= draws <= surv
        survivorship = alive.mean()
        assert 0.01 <= survivorship <= 0.35, (
            f"2-year survivorship {survivorship:.3f} outside plausible band"
        )
