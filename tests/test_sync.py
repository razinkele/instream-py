"""Tests for Mesa <-> SoA synchronization."""
import mesa
import numpy as np
import pytest

from instream.state.trout_state import TroutState


class MockModel(mesa.Model):
    """Minimal model mock for sync testing."""
    def __init__(self, trout_state, redd_state=None):
        super().__init__()
        self.trout_state = trout_state
        self.redd_state = redd_state
        self._trout_agents = {}  # idx -> TroutAgent
        self._redd_agents = {}


class TestSyncMesaFromState:
    def test_creates_agents_for_alive_fish(self):
        from instream.sync import sync_trout_agents
        ts = TroutState.zeros(10)
        ts.alive[0] = True
        ts.alive[3] = True
        ts.alive[7] = True
        model = MockModel(ts)
        sync_trout_agents(model)
        assert len(model._trout_agents) == 3
        assert set(model._trout_agents.keys()) == {0, 3, 7}

    def test_removes_dead_agents(self):
        from instream.sync import sync_trout_agents
        ts = TroutState.zeros(10)
        ts.alive[0] = True
        ts.alive[1] = True
        model = MockModel(ts)
        sync_trout_agents(model)
        assert len(model._trout_agents) == 2
        # Kill fish 0
        ts.alive[0] = False
        sync_trout_agents(model)
        assert len(model._trout_agents) == 1
        assert 0 not in model._trout_agents

    def test_adds_born_agents(self):
        from instream.sync import sync_trout_agents
        ts = TroutState.zeros(10)
        ts.alive[0] = True
        model = MockModel(ts)
        sync_trout_agents(model)
        assert len(model._trout_agents) == 1
        # Birth: new fish at slot 5
        ts.alive[5] = True
        sync_trout_agents(model)
        assert len(model._trout_agents) == 2
        assert 5 in model._trout_agents

    def test_idempotent(self):
        from instream.sync import sync_trout_agents
        ts = TroutState.zeros(10)
        ts.alive[0] = True
        model = MockModel(ts)
        sync_trout_agents(model)
        sync_trout_agents(model)  # second call
        assert len(model._trout_agents) == 1

    def test_handles_no_changes(self):
        from instream.sync import sync_trout_agents
        ts = TroutState.zeros(10)
        model = MockModel(ts)
        sync_trout_agents(model)  # no alive fish
        assert len(model._trout_agents) == 0
