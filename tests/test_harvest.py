"""Tests for angler harvest module."""

import numpy as np


class TestComputeHarvest:
    def test_harvest_kills_eligible_fish(self):
        from instream.state.trout_state import TroutState
        from instream.modules.harvest import compute_harvest

        rng = np.random.default_rng(42)
        ts = TroutState.zeros(10)
        for i in range(10):
            ts.alive[i] = True
            ts.length[i] = 5.0 + i  # lengths 5-14
            ts.weight[i] = 1.0
        records = compute_harvest(
            ts, num_anglers=10, catch_rate=1.0, min_length=10.0, bag_limit=100, rng=rng
        )
        # Only fish with length >= 10 are eligible (indices 5-9, lengths 10-14)
        assert len(records) > 0
        for r in records:
            assert r["length"] >= 10.0
        # Some fish should be dead
        assert np.sum(~ts.alive[:10]) > 0

    def test_bag_limit_caps_harvest(self):
        from instream.state.trout_state import TroutState
        from instream.modules.harvest import compute_harvest

        rng = np.random.default_rng(42)
        ts = TroutState.zeros(20)
        for i in range(20):
            ts.alive[i] = True
            ts.length[i] = 15.0
            ts.weight[i] = 5.0
        records = compute_harvest(
            ts, num_anglers=100, catch_rate=1.0, min_length=5.0, bag_limit=3, rng=rng
        )
        assert len(records) <= 3

    def test_no_harvest_when_zero_anglers(self):
        from instream.state.trout_state import TroutState
        from instream.modules.harvest import compute_harvest

        rng = np.random.default_rng(42)
        ts = TroutState.zeros(5)
        for i in range(5):
            ts.alive[i] = True
            ts.length[i] = 15.0
        records = compute_harvest(
            ts, num_anglers=0, catch_rate=1.0, min_length=5.0, bag_limit=100, rng=rng
        )
        assert len(records) == 0
        assert np.all(ts.alive[:5])

    def test_no_harvest_when_all_undersized(self):
        from instream.state.trout_state import TroutState
        from instream.modules.harvest import compute_harvest

        rng = np.random.default_rng(42)
        ts = TroutState.zeros(5)
        for i in range(5):
            ts.alive[i] = True
            ts.length[i] = 3.0
        records = compute_harvest(
            ts, num_anglers=10, catch_rate=1.0, min_length=10.0, bag_limit=100, rng=rng
        )
        assert len(records) == 0

    def test_harvest_records_contain_species_info(self):
        from instream.state.trout_state import TroutState
        from instream.modules.harvest import compute_harvest

        rng = np.random.default_rng(42)
        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.length[0] = 15.0
        ts.weight[0] = 10.0
        ts.species_idx[0] = 1
        ts.cell_idx[0] = 42
        records = compute_harvest(
            ts, num_anglers=100, catch_rate=1.0, min_length=5.0, bag_limit=100, rng=rng
        )
        assert len(records) == 1
        assert records[0]["species_idx"] == 1
        assert records[0]["length"] == 15.0
        assert records[0]["cell_idx"] == 42
