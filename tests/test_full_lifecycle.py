"""End-to-end: single fish through ocean and back."""
import numpy as np
from datetime import date
from instream.state.trout_state import TroutState
from instream.domains.marine import MarineDomain
from instream.space.marine_space import MarineSpace
from instream.io.env_drivers.static_driver import StaticDriver
from instream.agents.life_stage import LifeStage


def _make_test_domain():
    zone_config = {
        "estuary": {"area_km2": 50, "connections": ["coastal"]},
        "coastal": {"area_km2": 5000, "connections": ["estuary"]},
    }
    static_config = {
        "estuary": {"temperature": {1: 4.0, 4: 8.0, 7: 16.0, 10: 8.0},
                     "prey_index": {1: 0.3, 5: 0.7, 8: 0.6, 11: 0.3}},
        "coastal": {"temperature": {1: 4.0, 4: 7.0, 7: 14.0, 10: 7.0},
                     "prey_index": {1: 0.4, 5: 0.8, 8: 0.7, 11: 0.4}},
    }
    ms = MarineSpace(zone_config)
    driver = StaticDriver(static_config, ms.zone_names, ms.zone_areas)
    sp = {
        "marine_cmax_A": 0.303, "marine_cmax_B": -0.275,
        "marine_growth_efficiency": 0.50,
        "resp_A": 0.03, "resp_B": -0.25, "temp_opt": 12.0, "temp_max": 24.0,
        "marine_mort_seal_L1": 999.0, "marine_mort_seal_L9": 9999.0,
        "marine_mort_base": 0.0,  # zero background for deterministic test
        "marine_mort_m74_prob": 0.0,
        "marine_mort_cormorant_L1": 999.0, "marine_mort_cormorant_L9": 9999.0,
        "marine_mort_cormorant_zones": [],  # no cormorant zones
        "post_smolt_window": 60, "temp_threshold": 25.0,
        "maturation_min_sea_winters": 1,
        "maturation_probs": {1: 1.0},  # deterministic return after 1SW
        "maturation_min_length": 0.0,
        "maturation_min_condition": 0.0,
    }
    return MarineDomain(ms, driver, sp, gear_configs=[])


def test_full_lifecycle_smolt_to_return():
    """Single fish: smolt enters ocean, grows, returns after 1SW."""
    md = _make_test_domain()
    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = int(LifeStage.SMOLT)
    ts.zone_idx[0] = 0  # estuary
    ts.length[0] = 15.0
    ts.weight[0] = 40.0
    ts.condition[0] = 1.0
    ts.natal_reach_idx[0] = 5
    ts.smolt_date[0] = date(2025, 5, 1).toordinal()
    ts.sea_winters[0] = 0

    rng = np.random.default_rng(42)
    start = date(2025, 5, 1)
    returned = False

    for day_offset in range(400):  # >1 year
        d = date.fromordinal(start.toordinal() + day_offset)
        md.update_environment(d)
        md.daily_step(ts, d, rng)

        if not ts.alive[0]:
            break
        if ts.life_history[0] == int(LifeStage.RETURNING_ADULT):
            returned = True
            break

    assert returned, "Fish should have returned after 1SW (maturation_prob=1.0)"
    assert ts.zone_idx[0] == -1, "Returning fish should be in freshwater"
    assert ts.reach_idx[0] == 5, "Should home to natal reach"
    assert ts.weight[0] > 40.0, "Fish should have grown in ocean"
    assert ts.length[0] > 15.0, "Length should have increased"


def test_marine_growth_over_time():
    """Fish in ocean should grow substantially over months."""
    md = _make_test_domain()
    # Override maturation to prevent early return
    md.sp["maturation_probs"] = {1: 0.0, 2: 0.0, 3: 0.0}

    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = int(LifeStage.OCEAN_JUVENILE)
    ts.zone_idx[0] = 1  # coastal
    ts.length[0] = 15.0
    ts.weight[0] = 40.0
    ts.condition[0] = 1.0
    ts.smolt_date[0] = date(2025, 5, 1).toordinal()

    rng = np.random.default_rng(42)
    start = date(2025, 6, 1)

    for day_offset in range(180):  # 6 months
        d = date.fromordinal(start.toordinal() + day_offset)
        md.update_environment(d)
        md.daily_step(ts, d, rng)
        if not ts.alive[0]:
            break

    if ts.alive[0]:
        assert ts.weight[0] > 100, f"After 6 months, weight should be >100g, got {ts.weight[0]:.1f}"
        assert ts.length[0] > 20, f"After 6 months, length should be >20cm, got {ts.length[0]:.1f}"
