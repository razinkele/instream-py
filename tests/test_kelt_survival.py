"""Tests for v0.17.0 kelt survival / iteroparous spawning.

InSALMON extension — no NetLogo InSALMO 7.3 / InSTREAM 7.4 counterpart.
NetLogo uses only three life-history types (anad-adult, anad-juve,
resident) and has no kelt stage or post-spawn Bernoulli survival rule.
"""

from __future__ import annotations

import datetime
import numpy as np
import pytest

from instream.state.life_stage import LifeStage
from instream.state.trout_state import TroutState
from instream.marine.config import MarineConfig, ZoneConfig
from instream.marine.domain import MarineDomain, ZoneState


class TestLifeStageKelt:
    def test_kelt_value(self):
        assert LifeStage.KELT == 7

    def test_kelt_distinct(self):
        values = [int(s) for s in LifeStage]
        assert len(values) == len(set(values))

    def test_kelt_is_last(self):
        assert max(int(s) for s in LifeStage) == int(LifeStage.KELT)


class TestPostSpawnKeltSurvival:
    """River-exit survival: SPAWNERs that survive the spawning act and
    successfully transition to KELT with depleted condition (Jonsson 1997,
    Bordeleau et al. 2019 — 40-70% post-spawn energy depletion).
    """

    def _setup(self, n=5, condition=0.9, spawned=True, life_stage=LifeStage.SPAWNER):
        ts = TroutState.zeros(n)
        ts.alive[:] = True
        ts.life_history[:] = int(life_stage)
        ts.condition[:] = condition
        ts.spawned_this_season[:] = spawned
        return ts

    def test_low_condition_never_becomes_kelt(self):
        from instream.modules.spawning import apply_post_spawn_kelt_survival
        ts = self._setup(condition=0.3)
        n = apply_post_spawn_kelt_survival(
            ts, kelt_survival_prob=1.0, min_kelt_condition=0.5,
            rng=np.random.default_rng(0),
        )
        assert n == 0
        assert not np.any(ts.life_history == int(LifeStage.KELT))

    def test_high_condition_prob_1_all_promoted(self):
        from instream.modules.spawning import apply_post_spawn_kelt_survival
        ts = self._setup(condition=0.9)
        n = apply_post_spawn_kelt_survival(
            ts, kelt_survival_prob=1.0, min_kelt_condition=0.5,
            rng=np.random.default_rng(0),
        )
        assert n == 5
        assert np.all(ts.life_history == int(LifeStage.KELT))
        assert np.all(ts.alive)

    def test_prob_0_never_promoted(self):
        from instream.modules.spawning import apply_post_spawn_kelt_survival
        ts = self._setup(condition=0.9)
        n = apply_post_spawn_kelt_survival(
            ts, kelt_survival_prob=0.0, min_kelt_condition=0.5,
            rng=np.random.default_rng(0),
        )
        assert n == 0
        assert not np.any(ts.life_history == int(LifeStage.KELT))

    def test_only_affects_spawned_spawners(self):
        from instream.modules.spawning import apply_post_spawn_kelt_survival
        ts = TroutState.zeros(5)
        ts.alive[:] = True
        ts.life_history[0] = int(LifeStage.FRY)
        ts.life_history[1] = int(LifeStage.PARR)
        ts.life_history[2] = int(LifeStage.SPAWNER)
        ts.life_history[3] = int(LifeStage.OCEAN_ADULT)
        ts.life_history[4] = int(LifeStage.SMOLT)
        ts.condition[:] = 0.9
        ts.spawned_this_season[2] = True
        apply_post_spawn_kelt_survival(
            ts, kelt_survival_prob=1.0, min_kelt_condition=0.5,
            rng=np.random.default_rng(0),
        )
        assert ts.life_history[2] == int(LifeStage.KELT)
        assert ts.life_history[0] == int(LifeStage.FRY)
        assert ts.life_history[3] == int(LifeStage.OCEAN_ADULT)

    def test_non_spawned_spawner_ignored(self):
        """A SPAWNER that has not yet spawned this season cannot become kelt."""
        from instream.modules.spawning import apply_post_spawn_kelt_survival
        ts = self._setup(condition=0.9, spawned=False)
        n = apply_post_spawn_kelt_survival(
            ts, kelt_survival_prob=1.0, min_kelt_condition=0.5,
            rng=np.random.default_rng(0),
        )
        assert n == 0

    def test_condition_depletes_multiplicatively(self):
        """Kelts must have their condition halved (capped below 0.3)."""
        from instream.modules.spawning import apply_post_spawn_kelt_survival
        ts = self._setup(condition=0.8)
        apply_post_spawn_kelt_survival(
            ts, kelt_survival_prob=1.0, min_kelt_condition=0.5,
            rng=np.random.default_rng(0),
        )
        # 0.8 * 0.5 = 0.4, above floor
        assert np.all(ts.condition == pytest.approx(0.4))

    def test_condition_floor_0_3(self):
        """Extremely depleted kelts hit the 0.3 floor, not 0."""
        from instream.modules.spawning import apply_post_spawn_kelt_survival
        ts = self._setup(condition=0.5)  # just above eligibility
        apply_post_spawn_kelt_survival(
            ts, kelt_survival_prob=1.0, min_kelt_condition=0.5,
            rng=np.random.default_rng(0),
        )
        # 0.5 * 0.5 = 0.25, below floor → clamped to 0.3
        assert np.all(ts.condition == pytest.approx(0.3))


class TestKeltReentry:
    """KELT at the river mouth re-enters the ocean as OCEAN_ADULT with
    preserved sea_winters and smolt_date (InSALMON extension)."""

    def test_kelt_at_mouth_reenters_as_ocean_adult(self):
        from instream.modules.migration import migrate_fish_downstream
        ts = TroutState.zeros(3)
        ts.alive[0] = True
        ts.reach_idx[0] = 0
        ts.life_history[0] = int(LifeStage.KELT)
        ts.length[0] = 75.0
        ts.sea_winters[0] = 2
        ts.smolt_date[0] = 734000
        ts.natal_reach_idx[0] = 0

        cfg = MarineConfig(zones=[ZoneConfig(name="estuary", area_km2=10)])
        reach_graph = {0: []}  # river mouth
        date = datetime.date(2013, 5, 1)

        out, smoltified = migrate_fish_downstream(
            ts, 0, reach_graph,
            marine_config=cfg,
            smolt_readiness_threshold=0.8,
            smolt_min_length=12.0,
            current_date=date,
        )
        assert ts.alive[0]
        assert ts.life_history[0] == int(LifeStage.OCEAN_ADULT)
        assert ts.zone_idx[0] == 0
        assert ts.sea_winters[0] == 2, "sea_winters must be preserved"
        assert ts.smolt_date[0] == 734000, "smolt_date must be preserved"
        assert smoltified is False, "KELT re-entry is not a smoltification"

    def test_kelt_without_marine_config_falls_through(self):
        """If there is no marine config, a KELT at the river mouth is
        killed the same way any non-smoltifiable fish is killed — we do
        not add special handling for the no-marine case."""
        from instream.modules.migration import migrate_fish_downstream
        ts = TroutState.zeros(3)
        ts.alive[0] = True
        ts.reach_idx[0] = 0
        ts.life_history[0] = int(LifeStage.KELT)
        ts.length[0] = 75.0
        reach_graph = {0: []}

        out, smoltified = migrate_fish_downstream(
            ts, 0, reach_graph,
            marine_config=None,
        )
        assert not ts.alive[0]
        assert smoltified is False


class TestMarineDomainCounters:
    def test_new_counters_start_at_zero(self):
        ts = TroutState.zeros(5)
        zs = ZoneState.zeros(1)
        zs.name[0] = "estuary"
        cfg = MarineConfig(zones=[ZoneConfig(name="estuary", area_km2=10)])
        md = MarineDomain(ts, zs, cfg)
        assert md.total_kelts == 0
        assert md.total_repeat_spawners == 0
        assert isinstance(md.total_kelts, int)
        assert isinstance(md.total_repeat_spawners, int)
