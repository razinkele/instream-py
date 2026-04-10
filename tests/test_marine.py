"""Tests for the marine domain package."""

from __future__ import annotations

import datetime

import numpy as np
import pytest
from pydantic import ValidationError

from instream.marine.config import MarineConfig, ZoneConfig, ZoneDriverData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _monthly_constant(value: float) -> list[float]:
    """Return 12 identical monthly values."""
    return [value] * 12


def _make_marine_config(num_zones: int = 3) -> MarineConfig:
    """Build a minimal MarineConfig with *num_zones* zones."""
    zone_names = ["estuary", "coastal", "baltic"][:num_zones]
    zones = [ZoneConfig(name=n, area_km2=100.0 * (i + 1)) for i, n in enumerate(zone_names)]
    connectivity: dict[str, list[str]] = {}
    for i in range(num_zones - 1):
        connectivity[zone_names[i]] = [zone_names[i + 1]]
    static_driver = {
        n: ZoneDriverData(
            temperature=_monthly_constant(8.0 + i),
            salinity=_monthly_constant(10.0 + i * 5),
            prey_index=_monthly_constant(0.5),
            predation_risk=_monthly_constant(0.1),
        )
        for i, n in enumerate(zone_names)
    }
    return MarineConfig(
        zones=zones,
        zone_connectivity=connectivity,
        static_driver=static_driver,
    )


# ===================================================================
# Task 2 — MarineConfig
# ===================================================================

class TestMarineConfig:
    def test_round_trip(self):
        cfg = _make_marine_config()
        assert len(cfg.zones) == 3
        assert cfg.zones[0].name == "estuary"
        assert cfg.zones[2].area_km2 == 300.0

    def test_zone_driver_data_validation(self):
        with pytest.raises(ValidationError):
            ZoneDriverData(
                temperature=[1.0, 2.0],  # too few
                salinity=_monthly_constant(0),
                prey_index=_monthly_constant(0),
                predation_risk=_monthly_constant(0),
            )

    def test_defaults(self):
        cfg = MarineConfig(zones=[ZoneConfig(name="x", area_km2=1.0)])
        assert cfg.smolt_min_length == 12.0
        assert cfg.return_min_sea_winters == 1
        assert cfg.zone_connectivity == {}
        assert cfg.static_driver == {}

    def test_model_config_marine_optional(self):
        """ModelConfig.marine is None by default."""
        from instream.io.config import ModelConfig, SimulationConfig
        mc = ModelConfig(simulation=SimulationConfig(start_date="2020-01-01", end_date="2020-12-31"))
        assert mc.marine is None

    def test_model_config_with_marine(self):
        from instream.io.config import ModelConfig, SimulationConfig
        cfg = _make_marine_config(num_zones=2)
        mc = ModelConfig(
            simulation=SimulationConfig(start_date="2020-01-01", end_date="2020-12-31"),
            marine=cfg,
        )
        assert mc.marine is not None
        assert len(mc.marine.zones) == 2


# ===================================================================
# Task 3 — ZoneState + StaticDriver
# ===================================================================

from instream.marine.domain import ZoneState, StaticDriver


class TestZoneState:
    def test_zeros_factory(self):
        zs = ZoneState.zeros(3)
        assert zs.num_zones == 3
        assert zs.temperature.shape == (3,)
        assert np.all(zs.temperature == 0.0)
        assert np.all(zs.salinity == 0.0)
        assert np.all(zs.prey_index == 0.0)
        assert np.all(zs.predation_risk == 0.0)
        assert np.all(zs.area_km2 == 0.0)
        assert all(n == "" for n in zs.name)

    def test_zeros_single_zone(self):
        zs = ZoneState.zeros(1)
        assert zs.num_zones == 1
        assert zs.temperature.shape == (1,)


class TestStaticDriver:
    def test_get_conditions_january(self):
        cfg = _make_marine_config()
        driver = StaticDriver(cfg)
        zs = ZoneState.zeros(3)
        driver.get_conditions(datetime.date(2020, 1, 15), zs)
        # Zone 0 (estuary) temperature = 8.0
        assert zs.temperature[0] == pytest.approx(8.0)
        # Zone 1 (coastal) temperature = 9.0
        assert zs.temperature[1] == pytest.approx(9.0)
        # Zone 2 (baltic) temperature = 10.0
        assert zs.temperature[2] == pytest.approx(10.0)
        # Salinity: 10, 15, 20
        assert zs.salinity[0] == pytest.approx(10.0)
        assert zs.salinity[2] == pytest.approx(20.0)
        # Names populated
        assert zs.name[0] == "estuary"
        assert zs.name[2] == "baltic"
        # Area
        assert zs.area_km2[0] == pytest.approx(100.0)
        assert zs.area_km2[2] == pytest.approx(300.0)

    def test_num_zones(self):
        cfg = _make_marine_config(num_zones=2)
        driver = StaticDriver(cfg)
        assert driver.num_zones == 2

    def test_missing_driver_data(self):
        """Zones without static_driver data get zeros."""
        cfg = MarineConfig(zones=[ZoneConfig(name="orphan", area_km2=50.0)])
        driver = StaticDriver(cfg)
        zs = ZoneState.zeros(1)
        driver.get_conditions(datetime.date(2020, 6, 1), zs)
        assert zs.temperature[0] == 0.0
        assert zs.area_km2[0] == pytest.approx(50.0)


# ===================================================================
# Task 4 — MarineDomain
# ===================================================================

from instream.marine.domain import MarineDomain


def _make_mock_trout_state(n: int = 10):
    """Create a minimal namespace mimicking TroutState for testing."""

    class _MockTroutState:
        pass

    ts = _MockTroutState()
    ts.zone_idx = np.full(n, -1, dtype=np.int32)
    ts.sea_winters = np.zeros(n, dtype=np.int32)
    ts.smolt_date = np.full(n, -1, dtype=np.int32)
    ts.natal_reach_idx = np.full(n, -1, dtype=np.int32)
    ts.smolt_readiness = np.zeros(n, dtype=np.float64)
    ts.is_alive = np.ones(n, dtype=bool)
    return ts


class TestMarineDomain:
    def test_daily_step_skips_freshwater(self):
        """Fish with zone_idx == -1 are untouched."""
        cfg = _make_marine_config()
        ts = _make_mock_trout_state(5)
        zs = ZoneState.zeros(3)
        md = MarineDomain(ts, zs, cfg)
        md.daily_step(datetime.date(2021, 1, 1))
        # All still freshwater
        assert np.all(ts.zone_idx == -1)
        # Sea-winters not incremented
        assert np.all(ts.sea_winters == 0)

    def test_sea_winters_increment_jan1(self):
        """Marine fish get +1 sea-winter on Jan 1."""
        cfg = _make_marine_config()
        ts = _make_mock_trout_state(4)
        # Fish 0 and 1 are marine (in estuary)
        ts.zone_idx[0] = 0
        ts.zone_idx[1] = 0
        ts.smolt_date[0] = datetime.date(2020, 5, 1).toordinal()
        ts.smolt_date[1] = datetime.date(2020, 5, 1).toordinal()
        # Fish 2 is freshwater
        ts.zone_idx[2] = -1
        zs = ZoneState.zeros(3)
        md = MarineDomain(ts, zs, cfg)

        md.daily_step(datetime.date(2021, 1, 1))
        assert ts.sea_winters[0] == 1
        assert ts.sea_winters[1] == 1
        assert ts.sea_winters[2] == 0  # freshwater, untouched
        assert ts.sea_winters[3] == 0  # freshwater, untouched

    def test_sea_winters_no_increment_other_days(self):
        cfg = _make_marine_config()
        ts = _make_mock_trout_state(2)
        ts.zone_idx[0] = 0
        ts.smolt_date[0] = datetime.date(2020, 5, 1).toordinal()
        zs = ZoneState.zeros(3)
        md = MarineDomain(ts, zs, cfg)
        md.daily_step(datetime.date(2021, 3, 15))
        assert ts.sea_winters[0] == 0

    def test_estuary_to_coastal_migration(self):
        """Fish in estuary move to coastal after 14 days."""
        cfg = _make_marine_config()
        ts = _make_mock_trout_state(2)
        smolt_ord = datetime.date(2020, 5, 1).toordinal()
        ts.zone_idx[0] = 0  # estuary
        ts.smolt_date[0] = smolt_ord
        zs = ZoneState.zeros(3)
        md = MarineDomain(ts, zs, cfg)

        # Day 13 — still in estuary
        md.daily_step(datetime.date(2020, 5, 14))
        assert ts.zone_idx[0] == 0

        # Day 14 — promoted to coastal
        md.daily_step(datetime.date(2020, 5, 15))
        assert ts.zone_idx[0] == 1  # coastal

    def test_coastal_to_baltic_migration(self):
        """Fish in coastal move to baltic after 30 days."""
        cfg = _make_marine_config()
        ts = _make_mock_trout_state(2)
        smolt_ord = datetime.date(2020, 5, 1).toordinal()
        ts.zone_idx[0] = 1  # coastal
        ts.smolt_date[0] = smolt_ord
        zs = ZoneState.zeros(3)
        md = MarineDomain(ts, zs, cfg)

        # Day 29 — still coastal
        md.daily_step(datetime.date(2020, 5, 30))
        assert ts.zone_idx[0] == 1

        # Day 30 — promoted to baltic
        md.daily_step(datetime.date(2020, 5, 31))
        assert ts.zone_idx[0] == 2  # baltic

    def test_update_environment(self):
        cfg = _make_marine_config()
        zs = ZoneState.zeros(3)
        ts = _make_mock_trout_state(1)
        md = MarineDomain(ts, zs, cfg)
        md.update_environment(datetime.date(2020, 7, 1))
        assert zs.temperature[0] == pytest.approx(8.0)
        assert zs.name[1] == "coastal"

    def test_connectivity_graph_built(self):
        cfg = _make_marine_config()
        ts = _make_mock_trout_state(1)
        zs = ZoneState.zeros(3)
        md = MarineDomain(ts, zs, cfg)
        # estuary(0) -> [coastal(1)]
        assert md._adjacency[0] == [1]
        # coastal(1) -> [baltic(2)]
        assert md._adjacency[1] == [2]
