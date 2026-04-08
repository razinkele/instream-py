"""Tests for marine state fields on TroutState."""

import numpy as np
from instream.state.trout_state import TroutState


def test_trout_state_has_marine_fields():
    ts = TroutState.zeros(10)
    assert ts.zone_idx.shape == (10,)
    assert ts.zone_idx.dtype == np.int32
    assert np.all(ts.zone_idx == -1)  # freshwater by default

    assert ts.sea_winters.shape == (10,)
    assert np.all(ts.sea_winters == 0)

    assert ts.smolt_date.shape == (10,)
    assert np.all(ts.smolt_date == 0)

    assert ts.natal_reach_idx.shape == (10,)
    assert np.all(ts.natal_reach_idx == -1)

    assert ts.smolt_readiness.shape == (10,)
    assert np.all(ts.smolt_readiness == 0.0)


def test_marine_fields_inert_for_freshwater():
    ts = TroutState.zeros(5)
    ts.alive[0] = True
    ts.life_history[0] = 0  # FRY
    assert ts.zone_idx[0] == -1  # freshwater
