"""Tests for MarineDomain integration."""
import numpy as np
from datetime import date
from instream.domains.marine import MarineDomain
from instream.state.trout_state import TroutState
from instream.space.marine_space import MarineSpace
from instream.io.env_drivers.static_driver import StaticDriver
from instream.agents.life_stage import LifeStage


def _make_marine_domain():
    zone_config = {
        "estuary": {"area_km2": 50, "connections": ["coastal"]},
        "coastal": {"area_km2": 5000, "connections": ["estuary"]},
    }
    static_config = {
        "estuary": {"temperature": {1: 2.0, 7: 18.0}, "prey_index": {1: 0.2, 7: 0.8}},
        "coastal": {"temperature": {1: 3.0, 7: 15.0}, "prey_index": {1: 0.3, 7: 0.7}},
    }
    ms = MarineSpace(zone_config)
    driver = StaticDriver(static_config, ms.zone_names, ms.zone_areas)
    sp = {
        "marine_cmax_A": 0.303, "marine_cmax_B": -0.275,
        "marine_growth_efficiency": 0.50,
        "resp_A": 0.03, "resp_B": -0.25, "temp_opt": 12.0, "temp_max": 24.0,
        "marine_mort_seal_L1": 40.0, "marine_mort_seal_L9": 80.0,
        "marine_mort_base": 0.0, "marine_mort_m74_prob": 0.0,
        "marine_mort_cormorant_L1": 15.0, "marine_mort_cormorant_L9": 40.0,
        "marine_mort_cormorant_zones": [0, 1],
        "post_smolt_window": 60, "temp_threshold": 25.0,
        "maturation_min_sea_winters": 1,
        "maturation_probs": {1: 1.0},
        "maturation_min_length": 0.0, "maturation_min_condition": 0.0,
    }
    return MarineDomain(ms, driver, sp, gear_configs=[])


def test_marine_domain_processes_marine_fish():
    md = _make_marine_domain()
    ts = TroutState.zeros(2)
    ts.alive[0] = True
    ts.life_history[0] = int(LifeStage.FRY)
    ts.zone_idx[0] = -1  # freshwater
    ts.alive[1] = True
    ts.life_history[1] = int(LifeStage.SMOLT)
    ts.zone_idx[1] = 0
    ts.length[1] = 15.0
    ts.weight[1] = 40.0
    ts.condition[1] = 1.0
    ts.smolt_date[1] = date(2025, 5, 1).toordinal()

    rng = np.random.default_rng(42)
    md.update_environment(date(2025, 7, 1))
    md.daily_step(ts, date(2025, 7, 1), rng)

    assert ts.weight[0] == 0.0  # freshwater fish untouched
    assert ts.weight[1] != 40.0 or not ts.alive[1]  # marine fish processed


def test_sea_winters_increment():
    md = _make_marine_domain()
    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = int(LifeStage.OCEAN_JUVENILE)
    ts.zone_idx[0] = 1
    ts.length[0] = 40.0
    ts.weight[0] = 700.0
    ts.condition[0] = 1.0
    entry = date(2025, 5, 1)
    ts.smolt_date[0] = entry.toordinal()
    ts.sea_winters[0] = 0

    rng = np.random.default_rng(42)
    # Run just past 1 year
    d = date(2026, 5, 2)
    md.update_environment(d)
    md.daily_step(ts, d, rng)
    if ts.alive[0]:
        assert ts.sea_winters[0] >= 1


def test_marine_space_zone_graph():
    zone_config = {
        "estuary": {"area_km2": 50, "connections": ["coastal"]},
        "coastal": {"area_km2": 5000, "connections": ["estuary"]},
    }
    ms = MarineSpace(zone_config)
    assert ms.num_zones == 2
    assert ms.name_to_idx("estuary") == 0
    assert ms.name_to_idx("coastal") == 1
    assert ms.zone_graph[0] == [1]
    assert ms.zone_graph[1] == [0]


def test_maturation_sets_returning_adult():
    """Fish with enough sea winters and 100% maturation prob should return."""
    md = _make_marine_domain()
    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = int(LifeStage.OCEAN_ADULT)
    ts.zone_idx[0] = 1
    ts.length[0] = 70.0
    ts.weight[0] = 3500.0
    ts.condition[0] = 1.0
    ts.sea_winters[0] = 1
    ts.natal_reach_idx[0] = 5
    entry = date(2024, 5, 1)
    ts.smolt_date[0] = entry.toordinal()

    rng = np.random.default_rng(42)
    d = date(2025, 7, 1)
    md.update_environment(d)
    md.daily_step(ts, d, rng)

    if ts.alive[0]:
        assert ts.life_history[0] == int(LifeStage.RETURNING_ADULT)
        assert ts.zone_idx[0] == -1
        assert ts.reach_idx[0] == 5
