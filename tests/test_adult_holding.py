"""Tests for adult holding behavior (anadromous spawners skip feeding)."""

from instream.agents.life_stage import LifeStage
from instream.modules.behavior import should_skip_feeding


def test_anadromous_spawner_skips_feeding():
    assert should_skip_feeding(int(LifeStage.SPAWNER), is_anadromous=True)


def test_resident_spawner_does_not_skip():
    assert not should_skip_feeding(int(LifeStage.SPAWNER), is_anadromous=False)


def test_non_spawner_does_not_skip():
    assert not should_skip_feeding(int(LifeStage.FRY), is_anadromous=True)
    assert not should_skip_feeding(int(LifeStage.PARR), is_anadromous=True)
