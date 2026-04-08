"""Tests for smolt transition in migration.py."""
from datetime import date
from instream.state.trout_state import TroutState
from instream.modules.migration import migrate_fish_downstream
from instream.agents.life_stage import LifeStage
import numpy as np


def test_anadromous_smolt_transition():
    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = int(LifeStage.PARR)
    ts.reach_idx[0] = 2
    ts.length[0] = 15.0
    ts.species_idx[0] = 0

    reach_graph = {0: [1], 1: [2], 2: []}
    is_anadromous = np.array([True])

    out = migrate_fish_downstream(ts, 0, reach_graph,
                                   is_anadromous=is_anadromous,
                                   current_date=date(2025, 5, 15))
    assert ts.alive[0]
    assert ts.life_history[0] == LifeStage.SMOLT
    assert ts.zone_idx[0] == 0
    assert ts.natal_reach_idx[0] == 2
    assert ts.smolt_date[0] == date(2025, 5, 15).toordinal()
    assert len(out) == 1


def test_resident_still_dies():
    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = int(LifeStage.PARR)
    ts.reach_idx[0] = 0
    ts.species_idx[0] = 0

    reach_graph = {0: []}
    is_anadromous = np.array([False])

    out = migrate_fish_downstream(ts, 0, reach_graph, is_anadromous=is_anadromous)
    assert not ts.alive[0]
    assert len(out) == 1


def test_no_anadromous_flag_still_dies():
    """When is_anadromous is None (legacy), fish dies at boundary."""
    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = int(LifeStage.PARR)
    ts.reach_idx[0] = 0
    ts.species_idx[0] = 0

    reach_graph = {0: []}
    out = migrate_fish_downstream(ts, 0, reach_graph)
    assert not ts.alive[0]


def test_downstream_reach_exists_no_transition():
    """Fish with a downstream reach just moves, no smolt transition."""
    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = int(LifeStage.PARR)
    ts.reach_idx[0] = 0
    ts.species_idx[0] = 0

    reach_graph = {0: [1], 1: []}
    is_anadromous = np.array([True])

    out = migrate_fish_downstream(ts, 0, reach_graph, is_anadromous=is_anadromous)
    assert ts.alive[0]
    assert ts.reach_idx[0] == 1
    assert ts.life_history[0] == int(LifeStage.PARR)  # no transition
    assert len(out) == 0
