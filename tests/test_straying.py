"""Arc O: straying/homing + spawner-origin matrix tests."""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

from salmopy.io.output import write_spawner_origin_matrix


def test_smoltification_preserves_natal_reach_idx():
    """Arc O.1: smoltification must NOT overwrite natal_reach_idx.

    Pre-v0.38, migrate_fish_downstream assigned natal_reach_idx = current_reach
    at the SMOLT transition, destroying the birth-reach signal. v0.38 removes
    that overwrite so birth-reach persists through the full life cycle.
    """
    from salmopy.state.trout_state import TroutState
    from salmopy.state.life_stage import LifeStage
    from salmopy.marine.config import MarineConfig, ZoneConfig
    from salmopy.modules.migration import migrate_fish_downstream

    ts = TroutState.zeros(capacity=10)
    ts.alive[0] = True
    ts.species_idx[0] = 0
    ts.length[0] = 13.0
    ts.life_history[0] = int(LifeStage.PARR)
    ts.natal_reach_idx[0] = 2          # born in reach 2
    ts.reach_idx[0] = 5                # migrating through reach 5
    ts.smolt_readiness[0] = 0.9

    reach_graph = {5: [99]}  # reach 5 routes to marine reach 99
    cfg = MarineConfig(zones=[ZoneConfig(name="Estuary", area_km2=80)])

    # Exercise the smolt branch by calling migrate_fish_downstream; even
    # if other gates prevent the full SMOLT transition, the pre-v0.38 bug
    # would have overwritten natal_reach_idx on ANY downstream move, so
    # this exercises the fix. Key assertion: natal_reach_idx stays at 2.
    migrate_fish_downstream(
        ts, fish_idx=0, reach_graph=reach_graph,
        marine_config=cfg, smolt_min_length=12.0,
        smolt_readiness_threshold=0.0,  # force any move eligible
    )

    assert ts.natal_reach_idx[0] == 2, (
        f"natal_reach_idx overwritten at smoltification: "
        f"got {ts.natal_reach_idx[0]}, expected 2"
    )


def test_spawner_origin_matrix_is_diagonal_under_perfect_homing(tmp_path):
    """Arc O.3: with stray_fraction=0, matrix is diagonal (rep-weighted)."""
    spawners = [
        {"natal_reach_idx": 0, "reach_idx": 0, "superind_rep": 10},
        {"natal_reach_idx": 1, "reach_idx": 1, "superind_rep": 5},
        {"natal_reach_idx": 2, "reach_idx": 2, "superind_rep": 8},
    ]
    path = write_spawner_origin_matrix(
        spawners, reach_names=["A", "B", "C"], year=2020, output_dir=tmp_path,
    )
    # v0.43.5: CSV now uses count_<name> + prop_<name> columns, natal rows
    # keyed by "natal_reach" name column (index is the row order).
    df = pd.read_csv(path).set_index("natal_reach")
    assert df.loc["A", "count_A"] == 10
    assert df.loc["B", "count_B"] == 5
    assert df.loc["C", "count_C"] == 8
    # Off-diagonals zero
    assert df.loc["A", "count_B"] == 0
    assert df.loc["B", "count_C"] == 0
    assert df.loc["C", "count_A"] == 0
    # Proportions: diagonal = 1, off-diagonal = 0 under perfect homing
    assert df.loc["A", "prop_A"] == 1.0
    assert df.loc["B", "prop_B"] == 1.0


def test_spawner_origin_matrix_captures_straying(tmp_path):
    """Off-diagonals populated when natal != spawning reach."""
    spawners = [
        {"natal_reach_idx": 0, "reach_idx": 0, "superind_rep": 8},
        {"natal_reach_idx": 0, "reach_idx": 2, "superind_rep": 2},  # stray
        {"natal_reach_idx": 1, "reach_idx": 1, "superind_rep": 5},
    ]
    path = write_spawner_origin_matrix(
        spawners, reach_names=["A", "B", "C"], year=2020, output_dir=tmp_path,
    )
    df = pd.read_csv(path).set_index("natal_reach")
    assert df.loc["A", "count_A"] == 8
    assert df.loc["A", "count_C"] == 2   # A->C stray detected
    assert df.loc["B", "count_B"] == 5
    # Proportions: A is 8/10 + 2/10 = 0.8 + 0.2
    assert abs(df.loc["A", "prop_A"] - 0.8) < 1e-6
    assert abs(df.loc["A", "prop_C"] - 0.2) < 1e-6


def test_stray_fraction_zero_means_perfect_homing():
    """Arc O.2: default stray_fraction=0 → spawner returns to natal reach."""
    from salmopy.state.trout_state import TroutState
    from salmopy.state.life_stage import LifeStage
    from salmopy.marine.config import MarineConfig, ZoneConfig
    from salmopy.marine.domain import check_adult_return
    import datetime

    ts = TroutState.zeros(capacity=20)
    # Seed 10 fish with natal_reach=3, post-ocean, ready to return
    for i in range(10):
        ts.alive[i] = True
        ts.species_idx[i] = 0
        ts.life_history[i] = int(LifeStage.OCEAN_ADULT)
        ts.natal_reach_idx[i] = 3
        ts.zone_idx[i] = 0
        ts.sea_winters[i] = 2
        ts.condition[i] = 0.9

    reach_cells = {
        0: np.array([0, 1, 2]),
        1: np.array([3, 4]),
        2: np.array([5, 6]),
        3: np.array([7, 8, 9]),
    }
    cfg = MarineConfig(
        zones=[ZoneConfig(name="Estuary", area_km2=80)],
        stray_fraction=0.0,
    )
    n_ret, _ = check_adult_return(
        ts, reach_cells, return_sea_winters=1,
        current_date=datetime.date(2020, 5, 15), rng=np.random.default_rng(42),
        config=cfg,
    )
    assert n_ret == 10
    # All 10 fish should have reach_idx = natal = 3
    returning = [int(ts.reach_idx[i]) for i in range(10) if ts.alive[i]]
    assert all(r == 3 for r in returning), f"perfect homing broken: {returning}"


def test_stray_fraction_positive_produces_off_natal_returns():
    """Arc O.2: stray_fraction=1 → every returning adult strays."""
    from salmopy.state.trout_state import TroutState
    from salmopy.state.life_stage import LifeStage
    from salmopy.marine.config import MarineConfig, ZoneConfig
    from salmopy.marine.domain import check_adult_return
    import datetime

    ts = TroutState.zeros(capacity=20)
    for i in range(10):
        ts.alive[i] = True
        ts.species_idx[i] = 0
        ts.life_history[i] = int(LifeStage.OCEAN_ADULT)
        ts.natal_reach_idx[i] = 3
        ts.zone_idx[i] = 0
        ts.sea_winters[i] = 2
        ts.condition[i] = 0.9

    reach_cells = {
        0: np.array([0, 1, 2]),
        1: np.array([3, 4]),
        2: np.array([5, 6]),
        3: np.array([7, 8, 9]),
    }
    cfg = MarineConfig(
        zones=[ZoneConfig(name="Estuary", area_km2=80)],
        stray_fraction=1.0,
    )
    check_adult_return(
        ts, reach_cells, return_sea_winters=1,
        current_date=datetime.date(2020, 5, 15), rng=np.random.default_rng(42),
        config=cfg,
    )
    returning = [int(ts.reach_idx[i]) for i in range(10) if ts.alive[i]]
    # Every returner must have strayed (reach_idx != 3)
    assert all(r != 3 for r in returning), f"stray=1 but some homed: {returning}"
    # natal_reach_idx must stay 3 for all (genetic property unchanged)
    for i in range(10):
        if ts.alive[i]:
            assert ts.natal_reach_idx[i] == 3
