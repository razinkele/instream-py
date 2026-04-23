"""Tests for the v0.16.0 FRY->PARR automatic transition."""

from __future__ import annotations

import numpy as np
import pytest

from salmopy.state.trout_state import TroutState
from salmopy.state.life_stage import LifeStage


class _StubTimeManager:
    def __init__(self, julian: int) -> None:
        self.julian_date = julian


class _StubSpeciesCfg:
    def __init__(self, is_anadromous: bool = True) -> None:
        self.is_anadromous = is_anadromous


class _StubConfig:
    def __init__(self, anadromous: bool = True) -> None:
        self.species = {"salmo_salar": _StubSpeciesCfg(anadromous)}


class _StubModel:
    """Minimal stand-in for the day-boundary mixin's self."""

    def __init__(self, julian: int, n: int = 5, anadromous: bool = True) -> None:
        self.time_manager = _StubTimeManager(julian)
        self.trout_state = TroutState.zeros(n)
        self.trout_state.alive[:] = True
        self.config = _StubConfig(anadromous=anadromous)
        self.species_order = ["salmo_salar"]


def _bind_method(self):
    import salmopy.model_day_boundary as mdb
    return mdb._ModelDayBoundaryMixin._increment_age_if_new_year(self)


class TestFryToParrAnadromous:
    def test_anadromous_fry_age1_promoted_on_jan1(self):
        m = _StubModel(julian=1, n=4, anadromous=True)
        m.trout_state.life_history[:] = int(LifeStage.FRY)
        m.trout_state.age[:] = 0  # becomes 1 after increment
        _bind_method(m)
        assert np.all(m.trout_state.age == 1)
        assert np.all(m.trout_state.life_history == int(LifeStage.PARR))

    def test_not_promoted_mid_year(self):
        m = _StubModel(julian=180, n=3, anadromous=True)
        m.trout_state.life_history[:] = int(LifeStage.FRY)
        m.trout_state.age[:] = 0
        _bind_method(m)
        assert np.all(m.trout_state.age == 0)
        assert np.all(m.trout_state.life_history == int(LifeStage.FRY))

    def test_parr_unaffected(self):
        m = _StubModel(julian=1, n=3, anadromous=True)
        m.trout_state.life_history[:] = int(LifeStage.PARR)
        m.trout_state.age[:] = 2
        _bind_method(m)
        assert np.all(m.trout_state.age == 3)
        assert np.all(m.trout_state.life_history == int(LifeStage.PARR))

    def test_dead_fish_untouched(self):
        m = _StubModel(julian=1, n=4, anadromous=True)
        m.trout_state.life_history[:] = int(LifeStage.FRY)
        m.trout_state.alive[2] = False
        m.trout_state.age[:] = 0
        _bind_method(m)
        assert m.trout_state.age[2] == 0
        assert m.trout_state.life_history[2] == int(LifeStage.FRY)
        live = np.array([0, 1, 3])
        assert np.all(m.trout_state.age[live] == 1)
        assert np.all(m.trout_state.life_history[live] == int(LifeStage.PARR))


class TestFryToParrNonAnadromous:
    """For non-anadromous species (e.g. rainbow trout) the FRY->PARR rule
    must NOT fire — they don't use the PARR stage."""

    def test_non_anadromous_fry_not_promoted(self):
        m = _StubModel(julian=1, n=3, anadromous=False)
        m.trout_state.life_history[:] = int(LifeStage.FRY)
        m.trout_state.age[:] = 0
        _bind_method(m)
        # Age is still incremented on Jan 1
        assert np.all(m.trout_state.age == 1)
        # But life_history stays FRY
        assert np.all(m.trout_state.life_history == int(LifeStage.FRY))
