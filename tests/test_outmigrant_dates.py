"""Tests for outmigrant date recording (virtual screw-trap output)."""
from datetime import date
from instream.state.trout_state import TroutState
from instream.modules.migration import migrate_fish_downstream


def test_outmigrant_record_has_date():
    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = 1
    ts.reach_idx[0] = 0
    ts.length[0] = 15.0
    ts.species_idx[0] = 0

    reach_graph = {0: []}
    outmigrants = migrate_fish_downstream(ts, 0, reach_graph,
                                           current_date=date(2025, 5, 15))
    assert len(outmigrants) == 1
    assert outmigrants[0]["date"] == date(2025, 5, 15)
    assert outmigrants[0]["day_of_year"] == 135


def test_outmigrant_without_date_still_works():
    """Backward compat: no date param = no date in record."""
    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = 1
    ts.reach_idx[0] = 0
    ts.length[0] = 15.0
    ts.species_idx[0] = 0

    reach_graph = {0: []}
    outmigrants = migrate_fish_downstream(ts, 0, reach_graph)
    assert len(outmigrants) == 1
    assert "date" not in outmigrants[0]
    assert "day_of_year" not in outmigrants[0]
