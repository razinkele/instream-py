"""Tests for the MarineBackend Protocol + numpy impl (v0.15.0 Phase 4)."""

from __future__ import annotations

import datetime
import numpy as np
import pytest

from instream.backends._interface import MarineBackend
from instream.backends.numpy_backend.marine import NumpyMarineBackend
from instream.marine.config import (
    GearConfig,
    MarineConfig,
    MarineFishingConfig,
    ZoneConfig,
)


@pytest.fixture
def cfg():
    return MarineConfig(
        zones=[
            ZoneConfig(name="estuary", area_km2=10.0),
            ZoneConfig(name="coastal", area_km2=100.0),
            ZoneConfig(name="baltic", area_km2=1000.0),
        ],
        marine_fishing=MarineFishingConfig(
            min_legal_length=60.0,
            gear_types={
                "trap_net": GearConfig(
                    selectivity_type="logistic",
                    selectivity_L50=55.0,
                    selectivity_slope=3.0,
                    bycatch_mortality=0.10,
                    zones=["estuary", "coastal"],
                    open_months=[6, 7, 8, 9],
                    daily_effort=1.0,
                )
            },
        ),
    )


class TestProtocolCompliance:
    def test_numpy_backend_is_marine_backend(self):
        backend = NumpyMarineBackend()
        assert isinstance(backend, MarineBackend)


class TestGrowthDelegation:
    def test_returns_vector(self, cfg):
        backend = NumpyMarineBackend()
        delta = backend.marine_growth(
            weights=np.array([500.0, 1000.0]),
            temperatures=np.array([12.0, 12.0]),
            prey_indices=np.array([1.0, 1.0]),
            conditions=np.array([1.0, 1.0]),
            cmax_A=cfg.marine_cmax_A,
            cmax_B=cfg.marine_cmax_B,
            cmax_topt=cfg.marine_cmax_topt,
            cmax_tmax=cfg.marine_cmax_tmax,
            resp_A=cfg.marine_resp_A,
            resp_B=cfg.marine_resp_B,
            resp_Q10=cfg.marine_resp_Q10,
            growth_efficiency=cfg.marine_growth_efficiency,
        )
        assert delta.shape == (2,)
        assert np.all(delta > 0)


class TestSurvivalDelegation:
    def test_returns_probabilities(self, cfg):
        backend = NumpyMarineBackend()
        surv = backend.marine_survival(
            lengths=np.array([20.0, 80.0]),
            zone_indices=np.array([0, 2]),
            temperatures=np.array([10.0, 10.0]),
            days_since_ocean_entry=np.array([0, 365]),
            cormorant_zone_indices=np.array([0, 1]),
            config=cfg,
        )
        assert surv.shape == (2,)
        assert np.all((surv >= 0) & (surv <= 1))


class TestFishingDelegation:
    def test_legal_fish_killed(self, cfg):
        backend = NumpyMarineBackend()
        rng = np.random.default_rng(0)
        survival, tally = backend.fishing_mortality(
            lengths=np.array([100.0]),
            zone_indices=np.array([0]),
            current_date=datetime.date(2020, 7, 15),
            zone_name_by_idx=["estuary", "coastal", "baltic"],
            gear_configs=cfg.marine_fishing.gear_types,
            min_legal_length=cfg.marine_fishing.min_legal_length,
            rng=rng,
        )
        assert survival[0] == 0.0
        assert tally.get("trap_net", 0) == 1
