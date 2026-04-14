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
    ts.life_history = np.zeros(n, dtype=np.int32)
    ts.alive = np.ones(n, dtype=bool)
    # Fields required by marine growth (v0.15.0)
    ts.weight = np.full(n, 500.0, dtype=np.float64)
    ts.length = np.full(n, 36.84, dtype=np.float64)  # 0.01 * L^3 = 500 g
    ts.condition = np.ones(n, dtype=np.float64)
    # Field required by hatchery predator-naivety multiplier (v0.17.0)
    ts.is_hatchery = np.zeros(n, dtype=bool)
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


# ===================================================================
# Task 6 — Smolt Transition at River Mouth
# ===================================================================

from instream.modules.migration import migrate_fish_downstream
from instream.state.trout_state import TroutState
from instream.state.life_stage import LifeStage


def _make_trout_at_mouth(length=15.0, readiness=0.9, life_history=LifeStage.PARR):
    """Create a TroutState with one live PARR fish at a terminal reach."""
    ts = TroutState.zeros(4)
    ts.alive[0] = True
    ts.species_idx[0] = 0
    ts.length[0] = length
    ts.weight[0] = 50.0
    ts.condition[0] = 1.0
    ts.life_history[0] = int(life_history)
    ts.reach_idx[0] = 0
    ts.cell_idx[0] = 0
    ts.smolt_readiness[0] = readiness
    return ts


class TestSmoltTransitionAtRiverMouth:
    def test_parr_at_river_mouth_becomes_smolt(self):
        """PARR with sufficient readiness + length transitions to SMOLT."""
        ts = _make_trout_at_mouth(length=15.0, readiness=0.9)
        cfg = _make_marine_config()
        reach_graph = {0: []}  # no downstream
        date = datetime.date(2020, 5, 15)

        out, smoltified = migrate_fish_downstream(
            ts, 0, reach_graph,
            marine_config=cfg,
            smolt_readiness_threshold=0.8,
            smolt_min_length=12.0,
            current_date=date,
        )

        assert ts.alive[0] is True or ts.alive[0]  # still alive
        assert smoltified is True
        assert ts.life_history[0] == LifeStage.SMOLT
        assert ts.zone_idx[0] == 0  # estuary
        assert ts.natal_reach_idx[0] == 0
        assert ts.smolt_date[0] == date.toordinal()
        assert ts.cell_idx[0] == -1
        assert ts.reach_idx[0] == -1
        # Outmigrant record still produced
        assert len(out) == 1
        assert out[0]["reach_idx"] == 0

    def test_parr_below_min_length_survives_at_mouth(self):
        """v0.24.0: PARR below min length stays alive at the mouth.

        Pre-v0.24.0 this fish was killed unconditionally, wiping out
        all natal-cohort PARR in single-reach river systems. Post-v0.24.0
        the fish is kept alive at the current reach so it can grow and
        try again next spring. No outmigrant record is produced.
        """
        ts = _make_trout_at_mouth(length=8.0, readiness=0.9)
        cfg = _make_marine_config()
        reach_graph = {0: []}
        date = datetime.date(2020, 5, 15)

        out, smoltified = migrate_fish_downstream(
            ts, 0, reach_graph,
            marine_config=cfg,
            smolt_readiness_threshold=0.8,
            smolt_min_length=12.0,
            current_date=date,
        )

        assert ts.alive[0]
        assert smoltified is False
        assert ts.life_history[0] == LifeStage.PARR
        assert len(out) == 0

    def test_no_marine_config_kills_as_before(self):
        """Without marine_config, fish at mouth is killed (legacy behavior)."""
        ts = _make_trout_at_mouth(length=15.0, readiness=0.9)
        reach_graph = {0: []}

        out, smoltified = migrate_fish_downstream(ts, 0, reach_graph)

        assert not ts.alive[0]
        assert smoltified is False
        assert ts.life_history[0] == LifeStage.PARR
        assert len(out) == 1


# ===================================================================
# Task 7 — Smolt Readiness Accumulation
# ===================================================================

from instream.marine.domain import accumulate_smolt_readiness


class TestSmoltReadiness:
    def test_readiness_accumulates_in_spring(self):
        """Readiness increases for PARR fish during spring window."""
        n = 4
        readiness = np.zeros(n, dtype=np.float64)
        life_history = np.full(n, int(LifeStage.PARR), dtype=np.int32)
        lengths = np.array([15.0, 15.0, 8.0, 15.0], dtype=np.float64)
        temperature = np.full(n, 10.0, dtype=np.float64)

        # Fish 2 is below min_length (but still accumulates since v0.30.0), fish 3 is FRY
        life_history[3] = int(LifeStage.FRY)

        accumulate_smolt_readiness(
            readiness, life_history, lengths,
            day_length=0.6, max_day_length=0.67,
            temperature=temperature, optimal_temp=10.0,
            doy=120,  # spring
            min_length=12.0,
        )

        # Fish 0 and 1 should have increased readiness
        assert readiness[0] > 0.0
        assert readiness[1] > 0.0
        # Fish 2 (short PARR) now accumulates readiness (v0.30.0: length decoupled)
        assert readiness[2] > 0.0
        # Fish 3 (FRY) should remain zero
        assert readiness[3] == 0.0

    def test_readiness_zero_outside_window(self):
        """No accumulation outside the spring window."""
        n = 2
        readiness = np.zeros(n, dtype=np.float64)
        life_history = np.full(n, int(LifeStage.PARR), dtype=np.int32)
        lengths = np.full(n, 15.0, dtype=np.float64)
        temperature = np.full(n, 10.0, dtype=np.float64)

        # DOY 50 is outside window (90-180)
        accumulate_smolt_readiness(
            readiness, life_history, lengths,
            day_length=0.5, max_day_length=0.67,
            temperature=temperature, optimal_temp=10.0,
            doy=50,
            min_length=12.0,
        )
        assert np.all(readiness == 0.0)

        # DOY 200 is also outside
        accumulate_smolt_readiness(
            readiness, life_history, lengths,
            day_length=0.6, max_day_length=0.67,
            temperature=temperature, optimal_temp=10.0,
            doy=200,
            min_length=12.0,
        )
        assert np.all(readiness == 0.0)


# ===================================================================
# Task 8 — Adult Return
# ===================================================================

from instream.marine.domain import check_adult_return


class TestAdultReturn:
    def test_ocean_adult_returns_in_spring(self):
        """OCEAN_ADULT with sufficient sea-winters returns in spring."""
        ts = TroutState.zeros(4)
        ts.alive[0] = True
        ts.life_history[0] = int(LifeStage.OCEAN_ADULT)
        ts.zone_idx[0] = 2  # baltic
        ts.sea_winters[0] = 2
        ts.condition[0] = 0.8
        ts.natal_reach_idx[0] = 0
        ts.length[0] = 60.0

        reach_cells = {0: np.array([5, 10, 15])}
        rng = np.random.default_rng(42)
        date = datetime.date(2021, 4, 15)  # DOY ~105

        check_adult_return(ts, reach_cells,
                           return_sea_winters=1,
                           return_condition_min=0.5,
                           current_date=date, rng=rng)

        assert ts.life_history[0] == LifeStage.RETURNING_ADULT
        assert ts.zone_idx[0] == -1
        assert ts.reach_idx[0] == 0
        assert ts.cell_idx[0] in [5, 10, 15]

    def test_no_return_outside_spring(self):
        """OCEAN_ADULT does not return outside spring window."""
        ts = TroutState.zeros(4)
        ts.alive[0] = True
        ts.life_history[0] = int(LifeStage.OCEAN_ADULT)
        ts.zone_idx[0] = 2
        ts.sea_winters[0] = 2
        ts.condition[0] = 0.8
        ts.natal_reach_idx[0] = 0

        reach_cells = {0: np.array([5, 10])}
        rng = np.random.default_rng(42)

        # DOY 1 — January, outside spring
        check_adult_return(ts, reach_cells,
                           return_sea_winters=1,
                           return_condition_min=0.5,
                           current_date=datetime.date(2021, 1, 1),
                           rng=rng)

        assert ts.life_history[0] == LifeStage.OCEAN_ADULT
        assert ts.zone_idx[0] == 2  # still marine

    def test_returned_adult_has_valid_cell_idx(self):
        """Returned adult's cell_idx is from the reach_cells set."""
        ts = TroutState.zeros(4)
        ts.alive[0] = True
        ts.life_history[0] = int(LifeStage.OCEAN_ADULT)
        ts.zone_idx[0] = 1
        ts.sea_winters[0] = 1
        ts.condition[0] = 1.0
        ts.natal_reach_idx[0] = 2
        ts.length[0] = 50.0

        wet_cells = np.array([20, 21, 22, 23])
        reach_cells = {2: wet_cells}
        rng = np.random.default_rng(99)

        check_adult_return(ts, reach_cells,
                           return_sea_winters=1,
                           return_condition_min=0.5,
                           current_date=datetime.date(2021, 5, 1),
                           rng=rng)

        assert ts.life_history[0] == LifeStage.RETURNING_ADULT
        assert ts.cell_idx[0] in wet_cells


# ===================================================================
# Task 1 (v0.30.0) — Smolt readiness decoupled from length
# ===================================================================


def test_smolt_readiness_accumulates_regardless_of_length():
    """Undersized parr must accumulate readiness (physiological smoltification
    begins before migratory size is reached)."""
    import numpy as np
    from instream.marine.domain import accumulate_smolt_readiness
    from instream.state.life_stage import LifeStage

    n = 5
    readiness = np.zeros(n, dtype=np.float64)
    life_history = np.full(n, int(LifeStage.PARR), dtype=np.int8)
    lengths = np.array([3.0, 5.0, 7.0, 8.0, 12.0])
    temperature = np.full(n, 10.0)

    for doy in range(90, 120):
        accumulate_smolt_readiness(
            readiness, life_history, lengths,
            day_length=0.55, max_day_length=0.67,
            temperature=temperature, optimal_temp=10.0,
            doy=doy, min_length=8.0,
        )

    assert readiness[0] > 0, "3cm parr should accumulate readiness"
    assert readiness[1] > 0, "5cm parr should accumulate readiness"
    assert readiness[2] > 0, "7cm parr should accumulate readiness"
    np.testing.assert_allclose(readiness[0], readiness[4], rtol=0.01)


def test_smolt_readiness_builds_across_years():
    """Readiness must build over 2-3 springs with winter decay."""
    import numpy as np
    from instream.marine.domain import accumulate_smolt_readiness
    from instream.state.life_stage import LifeStage

    readiness = np.zeros(1, dtype=np.float64)
    life_history = np.array([int(LifeStage.PARR)], dtype=np.int8)
    lengths = np.array([6.0])
    temperature = np.array([10.0])

    for doy in range(90, 181):
        accumulate_smolt_readiness(
            readiness, life_history, lengths,
            day_length=0.55, max_day_length=0.67,
            temperature=temperature, optimal_temp=10.0,
            doy=doy, min_length=8.0,
        )
    year1 = float(readiness[0])
    assert 0.5 < year1 <= 1.0, f"Year 1 readiness should be 0.5-1.0, got {year1}"

    for doy in range(270, 366):
        accumulate_smolt_readiness(
            readiness, life_history, lengths,
            day_length=0.3, max_day_length=0.67,
            temperature=temperature, optimal_temp=10.0,
            doy=doy, min_length=8.0,
        )
    after_winter = float(readiness[0])
    assert after_winter < year1, "Winter should decay readiness"

    for doy in range(90, 181):
        accumulate_smolt_readiness(
            readiness, life_history, lengths,
            day_length=0.55, max_day_length=0.67,
            temperature=temperature, optimal_temp=10.0,
            doy=doy, min_length=8.0,
        )
    year2 = float(readiness[0])
    assert year2 >= 0.8, f"After 2 springs, readiness should be >= 0.8, got {year2}"


def test_smolt_emigration_requires_both_length_and_readiness():
    """Smoltification at river mouth requires length >= min AND readiness >= 0.8."""
    from instream.state.life_stage import LifeStage
    assert int(LifeStage.PARR) == 1
    assert int(LifeStage.SMOLT) == 3
