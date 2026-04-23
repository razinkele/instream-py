"""Tests for adult holding behavior (activity=4) for returning adults."""

import numpy as np

from salmopy.state.life_stage import LifeStage


def _make_trout_state(n_fish=1, n_cells=4):
    """Create a minimal TroutState-like object for holding tests."""
    from types import SimpleNamespace

    ts = SimpleNamespace()
    ts.alive = np.ones(n_fish, dtype=bool)
    ts.species_idx = np.zeros(n_fish, dtype=np.int32)
    ts.length = np.full(n_fish, 30.0, dtype=np.float64)
    ts.weight = np.full(n_fish, 200.0, dtype=np.float64)
    ts.condition = np.ones(n_fish, dtype=np.float64)
    ts.age = np.zeros(n_fish, dtype=np.float64)
    ts.cell_idx = np.zeros(n_fish, dtype=np.int32)
    ts.reach_idx = np.zeros(n_fish, dtype=np.int32)
    ts.activity = np.zeros(n_fish, dtype=np.int32)
    ts.sex = np.zeros(n_fish, dtype=np.int32)
    ts.superind_rep = np.ones(n_fish, dtype=np.int32)
    ts.life_history = np.zeros(n_fish, dtype=np.int8)
    ts.in_shelter = np.zeros(n_fish, dtype=bool)
    ts.spawned_this_season = np.zeros(n_fish, dtype=bool)
    ts.last_growth_rate = np.zeros(n_fish, dtype=np.float64)
    ts.fitness_memory = np.zeros(n_fish, dtype=np.float64)
    ts.growth_memory = np.zeros((n_fish, 4), dtype=np.float64)
    ts.consumption_memory = np.zeros((n_fish, 4), dtype=np.float64)

    def alive_indices():
        return np.where(ts.alive)[0]

    ts.alive_indices = alive_indices
    return ts


def _make_fem_space(n_cells=4, velocities=None, depths=None):
    """Create a minimal FEMSpace-like object."""
    from types import SimpleNamespace

    cs = SimpleNamespace()
    cs.depth = np.ones(n_cells, dtype=np.float64) if depths is None else depths
    cs.velocity = (
        np.array([1.0, 0.5, 0.2, 0.8], dtype=np.float64)
        if velocities is None
        else velocities
    )
    cs.light = np.full(n_cells, 100.0, dtype=np.float64)
    cs.available_drift = np.full(n_cells, 1.0, dtype=np.float64)
    cs.available_search = np.full(n_cells, 1.0, dtype=np.float64)
    cs.available_vel_shelter = np.full(n_cells, 10.0, dtype=np.float64)
    cs.available_hiding_places = np.full(n_cells, 10.0, dtype=np.float64)
    cs.dist_escape = np.full(n_cells, 100.0, dtype=np.float64)
    cs.centroid_x = np.linspace(0, 30, n_cells, dtype=np.float64)
    cs.centroid_y = np.zeros(n_cells, dtype=np.float64)
    cs.reach_idx = np.zeros(n_cells, dtype=np.int32)
    cs.area = np.full(n_cells, 10.0, dtype=np.float64)
    cs.frac_vel_shelter = np.full(n_cells, 0.5, dtype=np.float64)

    fem = SimpleNamespace()
    fem.cell_state = cs
    fem.num_cells = n_cells
    # KD-tree stub
    fem.neighbor_indices = np.full((n_cells, 6), -1, dtype=np.int32)
    for c in range(n_cells):
        if c > 0:
            fem.neighbor_indices[c, 0] = c - 1
        if c < n_cells - 1:
            fem.neighbor_indices[c, 1] = c + 1

    def cells_in_radius(cell, radius):
        # Return all cells (small test mesh)
        return np.arange(n_cells, dtype=np.int32)

    def get_neighbor_indices(cell):
        return fem.neighbor_indices[cell]

    fem.cells_in_radius = cells_in_radius
    fem.get_neighbor_indices = get_neighbor_indices
    return fem


def _species_arrays():
    """Create minimal per-species arrays (1 species)."""
    n = 1
    sp = {}
    for key in [
        "cmax_A", "cmax_B", "resp_A", "resp_B", "resp_D",
        "react_dist_A", "react_dist_B", "max_speed_A", "max_speed_B",
        "capture_R1", "capture_R9", "turbid_threshold", "turbid_min",
        "turbid_exp", "light_threshold", "light_min", "light_exp",
        "energy_density", "search_area", "move_radius_max",
        "move_radius_L1", "move_radius_L9",
        "mort_high_temp_T1", "mort_high_temp_T9",
        "mort_condition_S_at_K5", "mort_condition_S_at_K8",
        "mort_condition_K_crit", "mort_strand_survival_when_dry",
        "mort_fish_pred_L1", "mort_fish_pred_L9",
        "mort_fish_pred_D1", "mort_fish_pred_D9",
        "mort_fish_pred_P1", "mort_fish_pred_P9",
        "mort_fish_pred_I1", "mort_fish_pred_I9",
        "mort_fish_pred_T1", "mort_fish_pred_T9",
        "mort_fish_pred_hiding_factor",
        "mort_terr_pred_L1", "mort_terr_pred_L9",
        "mort_terr_pred_D1", "mort_terr_pred_D9",
        "mort_terr_pred_V1", "mort_terr_pred_V9",
        "mort_terr_pred_I1", "mort_terr_pred_I9",
        "mort_terr_pred_H1", "mort_terr_pred_H9",
        "mort_terr_pred_hiding_factor",
    ]:
        sp[key] = np.zeros(n, dtype=np.float64)
    # Set reasonable defaults
    sp["cmax_A"][:] = 0.628
    sp["cmax_B"][:] = 0.3
    sp["resp_A"][:] = 30.0
    sp["resp_B"][:] = 0.784
    sp["resp_D"][:] = 0.03
    sp["max_speed_A"][:] = 2.0
    sp["max_speed_B"][:] = 0.0
    sp["energy_density"][:] = 5900.0
    sp["search_area"][:] = 20000.0
    sp["move_radius_max"][:] = 50.0
    sp["move_radius_L1"][:] = 5.0
    sp["move_radius_L9"][:] = 15.0
    sp["react_dist_A"][:] = 0.0
    sp["react_dist_B"][:] = 0.2
    sp["turbid_threshold"][:] = 10.0
    sp["turbid_min"][:] = 0.1
    sp["turbid_exp"][:] = -0.1
    sp["light_threshold"][:] = 40.0
    sp["light_min"][:] = 0.1
    sp["light_exp"][:] = -0.1
    sp["capture_R1"][:] = 0.5
    sp["capture_R9"][:] = 0.9
    sp["mort_high_temp_T1"][:] = 28.0
    sp["mort_high_temp_T9"][:] = 24.0
    sp["mort_condition_S_at_K5"][:] = 0.8
    sp["mort_condition_S_at_K8"][:] = 0.992
    sp["mort_condition_K_crit"][:] = 0.8
    sp["mort_strand_survival_when_dry"][:] = 0.5
    sp["mort_fish_pred_L1"][:] = 10.0
    sp["mort_fish_pred_L9"][:] = 3.0
    sp["mort_fish_pred_D1"][:] = 50.0
    sp["mort_fish_pred_D9"][:] = 10.0
    sp["mort_fish_pred_hiding_factor"][:] = 0.5
    sp["mort_terr_pred_L1"][:] = 15.0
    sp["mort_terr_pred_L9"][:] = 5.0
    sp["mort_terr_pred_hiding_factor"][:] = 0.5
    return sp


def _reach_arrays():
    """Create minimal per-reach arrays (1 reach)."""
    rp = {}
    for key in [
        "drift_conc", "search_prod", "shelter_speed_frac",
        "prey_energy_density", "fish_pred_min", "terr_pred_min",
    ]:
        rp[key] = np.zeros(1, dtype=np.float64)
    rp["drift_conc"][:] = 1e-10
    rp["search_prod"][:] = 1e-10
    rp["shelter_speed_frac"][:] = 0.3
    rp["prey_energy_density"][:] = 2500.0
    rp["fish_pred_min"][:] = 0.99
    rp["terr_pred_min"][:] = 0.99
    return rp


class TestAdultHolding:
    def test_returning_adult_gets_hold_activity(self):
        """Fish with life_history=RETURNING_ADULT should use hold activity."""
        from salmopy.modules.behavior import select_habitat_and_activity

        ts = _make_trout_state(n_fish=1, n_cells=4)
        ts.life_history[0] = int(LifeStage.RETURNING_ADULT)
        fem = _make_fem_space(n_cells=4)

        sp = _species_arrays()
        rp = _reach_arrays()
        cmax_x = [np.array([0.0, 10.0, 20.0, 30.0])]
        cmax_y = [np.array([0.0, 0.5, 1.0, 0.5])]

        select_habitat_and_activity(
            ts, fem,
            temperature=np.array([15.0]),
            turbidity=np.array([5.0]),
            max_swim_temp_term=np.array([[1.0]]),
            resp_temp_term=np.array([[1.0]]),
            sp_arrays=sp,
            sp_cmax_table_x=cmax_x,
            sp_cmax_table_y=cmax_y,
            rp_arrays=rp,
            step_length=1.0,
            pisciv_densities=np.zeros(4),
        )

        assert ts.activity[0] == 4, f"Expected hold (4), got {ts.activity[0]}"

    def test_returning_adult_picks_lowest_velocity_cell(self):
        """Returning adult should select the cell with the lowest velocity."""
        from salmopy.modules.behavior import select_habitat_and_activity

        velocities = np.array([1.0, 0.5, 0.1, 0.8], dtype=np.float64)
        ts = _make_trout_state(n_fish=1, n_cells=4)
        ts.life_history[0] = int(LifeStage.RETURNING_ADULT)
        fem = _make_fem_space(n_cells=4, velocities=velocities)

        sp = _species_arrays()
        rp = _reach_arrays()
        cmax_x = [np.array([0.0, 10.0, 20.0, 30.0])]
        cmax_y = [np.array([0.0, 0.5, 1.0, 0.5])]

        select_habitat_and_activity(
            ts, fem,
            temperature=np.array([15.0]),
            turbidity=np.array([5.0]),
            max_swim_temp_term=np.array([[1.0]]),
            resp_temp_term=np.array([[1.0]]),
            sp_arrays=sp,
            sp_cmax_table_x=cmax_x,
            sp_cmax_table_y=cmax_y,
            rp_arrays=rp,
            step_length=1.0,
            pisciv_densities=np.zeros(4),
        )

        # Cell 2 has the lowest velocity (0.1)
        assert ts.cell_idx[0] == 2, f"Expected cell 2, got {ts.cell_idx[0]}"

    def test_returning_adult_has_negative_growth(self):
        """Returning adult should have negative growth rate (respiration only)."""
        from salmopy.modules.behavior import select_habitat_and_activity

        ts = _make_trout_state(n_fish=1, n_cells=4)
        ts.life_history[0] = int(LifeStage.RETURNING_ADULT)
        fem = _make_fem_space(n_cells=4)

        sp = _species_arrays()
        rp = _reach_arrays()
        cmax_x = [np.array([0.0, 10.0, 20.0, 30.0])]
        cmax_y = [np.array([0.0, 0.5, 1.0, 0.5])]

        select_habitat_and_activity(
            ts, fem,
            temperature=np.array([15.0]),
            turbidity=np.array([5.0]),
            max_swim_temp_term=np.array([[1.0]]),
            resp_temp_term=np.array([[1.0]]),
            sp_arrays=sp,
            sp_cmax_table_x=cmax_x,
            sp_cmax_table_y=cmax_y,
            rp_arrays=rp,
            step_length=1.0,
            pisciv_densities=np.zeros(4),
        )

        assert ts.last_growth_rate[0] < 0.0, (
            f"Expected negative growth, got {ts.last_growth_rate[0]}"
        )

    def test_non_returning_adult_does_not_hold(self):
        """Fish with life_history != RETURNING_ADULT should NOT get hold activity."""
        from salmopy.modules.behavior import select_habitat_and_activity

        ts = _make_trout_state(n_fish=1, n_cells=4)
        ts.life_history[0] = int(LifeStage.FRY)
        fem = _make_fem_space(n_cells=4)

        sp = _species_arrays()
        rp = _reach_arrays()
        cmax_x = [np.array([0.0, 10.0, 20.0, 30.0])]
        cmax_y = [np.array([0.0, 0.5, 1.0, 0.5])]

        select_habitat_and_activity(
            ts, fem,
            temperature=np.array([15.0]),
            turbidity=np.array([5.0]),
            max_swim_temp_term=np.array([[1.0]]),
            resp_temp_term=np.array([[1.0]]),
            sp_arrays=sp,
            sp_cmax_table_x=cmax_x,
            sp_cmax_table_y=cmax_y,
            rp_arrays=rp,
            step_length=1.0,
            pisciv_densities=np.zeros(4),
        )

        assert ts.activity[0] != 4, "FRY should not get hold activity"
