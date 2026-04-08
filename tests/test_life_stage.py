"""Tests for LifeStage IntEnum."""
from instream.agents.life_stage import LifeStage


def test_life_stage_values():
    assert LifeStage.FRY == 0
    assert LifeStage.PARR == 1
    assert LifeStage.SPAWNER == 2
    assert LifeStage.SMOLT == 3
    assert LifeStage.OCEAN_JUVENILE == 4
    assert LifeStage.OCEAN_ADULT == 5
    assert LifeStage.RETURNING_ADULT == 6


def test_life_stage_domain_helpers():
    assert LifeStage.FRY.is_freshwater
    assert LifeStage.PARR.is_freshwater
    assert LifeStage.SPAWNER.is_freshwater
    assert LifeStage.RETURNING_ADULT.is_freshwater
    assert LifeStage.SMOLT.is_marine
    assert LifeStage.OCEAN_JUVENILE.is_marine
    assert LifeStage.OCEAN_ADULT.is_marine
    assert not LifeStage.FRY.is_marine
