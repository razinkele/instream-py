"""Tests for Mesa agent shells."""
import mesa
import numpy as np
import pytest

from instream.state.trout_state import TroutState
from instream.state.redd_state import ReddState


class MockTroutModel(mesa.Model):
    """Minimal Mesa model with trout_state."""
    def __init__(self, trout_state):
        super().__init__()
        self.trout_state = trout_state


class MockReddModel(mesa.Model):
    """Minimal Mesa model with redd_state."""
    def __init__(self, redd_state):
        super().__init__()
        self.redd_state = redd_state


class TestTroutAgent:
    def test_has_length_property(self):
        from instream.agents.trout import TroutAgent
        ts = TroutState.zeros(10)
        ts.alive[0] = True
        ts.length[0] = 12.5
        agent = TroutAgent(MockTroutModel(ts), idx=0)
        assert agent.length == pytest.approx(12.5)

    def test_has_weight_property(self):
        from instream.agents.trout import TroutAgent
        ts = TroutState.zeros(10)
        ts.alive[0] = True
        ts.weight[0] = 8.3
        agent = TroutAgent(MockTroutModel(ts), idx=0)
        assert agent.weight == pytest.approx(8.3)

    def test_idx_matches_state(self):
        from instream.agents.trout import TroutAgent
        ts = TroutState.zeros(10)
        ts.alive[3] = True
        ts.length[3] = 15.0
        agent = TroutAgent(MockTroutModel(ts), idx=3)
        assert agent.idx == 3
        assert agent.length == pytest.approx(15.0)

    def test_step_is_noop(self):
        from instream.agents.trout import TroutAgent
        ts = TroutState.zeros(5)
        ts.alive[0] = True
        agent = TroutAgent(MockTroutModel(ts), idx=0)
        agent.step()  # should not raise


class TestReddAgent:
    def test_has_egg_count(self):
        from instream.agents.redd import ReddAgent
        rs = ReddState.zeros(10)
        rs.alive[0] = True
        rs.num_eggs[0] = 250
        agent = ReddAgent(MockReddModel(rs), idx=0)
        assert agent.num_eggs == 250
