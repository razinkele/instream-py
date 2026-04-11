"""Regression test for the v0.16.0 ghost-smoltified-fry fix.

When a marine fish dies and its slot in TroutState is later reused for a new
fry emerging from a redd, the new fry MUST NOT inherit smolt_date, zone_idx,
sea_winters, or smolt_readiness from the corpse. Prior to v0.16.0 the reset
was missing and v0.15.0 E2E runs observed ~170 fry with smolt_date >= 0 but
lengths of 3-4 cm — too small to be viable smolts.
"""

from __future__ import annotations

import numpy as np
import pytest

from instream.state.trout_state import TroutState
from instream.state.redd_state import ReddState
from instream.state.life_stage import LifeStage
from instream.modules.spawning import redd_emergence


def _make_redd_with_ghost_slots(capacity: int = 10) -> tuple[TroutState, ReddState]:
    ts = TroutState.zeros(capacity)
    rs = ReddState.zeros(capacity=3)

    # Corrupt the first 3 slots to simulate stale state from dead smolts
    ts.alive[:3] = False                           # dead = available for reuse
    ts.smolt_date[:3] = 734567                     # ordinal of a past spring day
    ts.zone_idx[:3] = 2                            # previously in Baltic Proper
    ts.sea_winters[:3] = 1
    ts.smolt_readiness[:3] = 0.9

    # Create one redd ready to emerge
    rs.alive[0] = True
    rs.species_idx[0] = 0
    rs.num_eggs[0] = 3
    rs.frac_developed[0] = 1.0
    rs.reach_idx[0] = 5
    rs.cell_idx[0] = 42

    return ts, rs


class TestGhostSmoltFix:
    def test_new_fry_have_clean_marine_state(self):
        ts, rs = _make_redd_with_ghost_slots()
        rng = np.random.default_rng(0)

        redd_emergence(
            redd_state=rs,
            trout_state=ts,
            rng=rng,
            emerge_length_min=2.5,
            emerge_length_mode=3.0,
            emerge_length_max=3.5,
            weight_A=0.0041,
            weight_B=3.49,
            species_index=0,
        )

        # The 3 reused slots should now hold FRY with fully-reset marine state
        new_fry = np.where(ts.alive)[0]
        assert len(new_fry) == 3

        assert np.all(ts.life_history[new_fry] == int(LifeStage.FRY))
        assert np.all(ts.smolt_date[new_fry] == -1), (
            f"smolt_date leaked: {ts.smolt_date[new_fry]}"
        )
        assert np.all(ts.zone_idx[new_fry] == -1), (
            f"zone_idx leaked: {ts.zone_idx[new_fry]}"
        )
        assert np.all(ts.sea_winters[new_fry] == 0), (
            f"sea_winters leaked: {ts.sea_winters[new_fry]}"
        )
        assert np.all(ts.smolt_readiness[new_fry] == 0.0), (
            f"smolt_readiness leaked: {ts.smolt_readiness[new_fry]}"
        )
        assert np.all(ts.natal_reach_idx[new_fry] == 5), (
            "natal_reach_idx should be set to the redd reach"
        )

    def test_length_weight_still_work(self):
        ts, rs = _make_redd_with_ghost_slots()
        rng = np.random.default_rng(0)
        redd_emergence(
            redd_state=rs, trout_state=ts, rng=rng,
            emerge_length_min=2.5, emerge_length_mode=3.0, emerge_length_max=3.5,
            weight_A=0.0041, weight_B=3.49, species_index=0,
        )
        new_fry = np.where(ts.alive)[0]
        assert np.all((ts.length[new_fry] >= 2.5) & (ts.length[new_fry] <= 3.5))
        assert np.all(ts.weight[new_fry] > 0)
