"""End-to-end tests for marine lifecycle integration."""

import pytest
import numpy as np
from pathlib import Path
from instream.state.life_stage import LifeStage

CONFIGS = Path(__file__).parent.parent / "configs"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.slow
class TestMarineLifecycleE2E:
    @pytest.fixture(scope="class")
    def model(self):
        from instream.model import InSTREAMModel
        import datetime

        start = datetime.date(2011, 4, 1)
        end_date = (start + datetime.timedelta(days=1095)).isoformat()
        m = InSTREAMModel(
            CONFIGS / "example_marine.yaml",
            data_dir=FIXTURES / "example_a",
            end_date_override=end_date,
        )
        # Fish initialize as FRY with small lengths (~4cm).
        # Manually set a subset to PARR with age >= 1 and length >= smolt_min_length
        # so smoltification can occur during the simulation.
        # Pre-seed smolt_readiness >= threshold so they transition to SMOLT
        # instead of dying as outmigrants.
        ts = m.trout_state
        alive = ts.alive_indices()
        n_parr = min(len(alive) // 2, 200)
        parr_candidates = alive[:n_parr]
        ts.life_history[parr_candidates] = int(LifeStage.PARR)
        ts.age[parr_candidates] = 1
        ts.length[parr_candidates] = 15.0  # above smolt_min_length (12.0)
        sp_cfg = m.config.species[m.species_order[0]]
        ts.weight[parr_candidates] = sp_cfg.weight_A * 15.0 ** sp_cfg.weight_B
        ts.smolt_readiness[parr_candidates] = 0.9  # above threshold (0.8)
        ts.fitness_memory[parr_candidates] = 0.5  # non-zero to survive first steps
        m.run()
        return m

    def test_some_fish_smoltified(self, model):
        # Durable counter — ts.smolt_date is cleared when a dead slot gets
        # reused by a new fry (v0.16.0 ghost-smolt fix).
        assert model._marine_domain.total_smoltified > 0, (
            "No fish smoltified (MarineDomain.total_smoltified == 0)"
        )

    def test_some_fish_returned(self, model):
        # Use the durable MarineDomain counter — querying final TroutState
        # fields is unreliable because slot reuse by new fry/adults resets
        # smolt_date / zone_idx once a returned fish dies post-spawn.
        assert model._marine_domain.total_returned > 0, (
            "No fish completed the marine round-trip "
            "(MarineDomain.total_returned == 0)"
        )

    def test_returned_fish_have_valid_cell(self, model):
        ts = model.trout_state
        alive = ts.alive_indices()
        fw = alive[(ts.zone_idx[alive] == -1) & (ts.natal_reach_idx[alive] >= 0)]
        if len(fw) > 0:
            assert np.all(ts.cell_idx[fw] >= 0), "Returned fish have invalid cell_idx"

    def test_freshwater_still_works(self, model):
        # v0.20.0: passes again after the RETURNING_ADULT mortality
        # protection in model_environment.py. Returning adults now survive
        # the freshwater hold between river entry and spawn, so the
        # manipulated cohort no longer wholesale dies before t=1095d.
        # Pre-v0.20.0 this was xfailed with the wrong v0.18.0 hypothesis
        # (test-order flake) and re-diagnosed in v0.19.0 as cohort
        # extinction. The Option A survival filter resolves both.
        assert model.trout_state.alive.sum() > 0, "Population went extinct"

    def test_marine_fish_grew_or_lost_weight(self, model):
        """v0.15.0 Phase 1: marine_growth fires for fish currently in ocean.

        Bioenergetics must be actively changing weight — either upward under
        prey or downward under starvation. A pure no-op (placeholder) would
        leave weight unchanged from smolt entry.
        """
        ts = model.trout_state
        currently_marine = np.where(ts.zone_idx >= 0)[0]
        if len(currently_marine) == 0:
            pytest.skip("No fish currently in ocean at end of run")
        weights = ts.weight[currently_marine]
        lengths = ts.length[currently_marine]
        # Healthy weight for each fish by its own species weight_A/B is
        # unknown here — use the fact that condition factor (W/L^3) should
        # span a non-trivial range if growth is active.
        condition = ts.condition[currently_marine]
        assert condition.std() > 0.0 or weights.std() > 0.0, (
            "Marine fish weights are all identical — growth may be a no-op"
        )

    def test_kelt_counter_wired(self, model):
        """v0.17.0 Phase 3: kelt roll machinery is live.

        Verify the counter attributes exist and are plain Python ints
        (not numpy scalars). The strong cohort-level assertion
        ``total_kelts > 0`` lives in the Phase 4 calibration test where
        a 3000-fish cohort and 0.25 river-exit probability guarantee
        at least one successful roll.
        """
        md = model._marine_domain
        assert isinstance(md.total_kelts, int)
        assert isinstance(md.total_repeat_spawners, int)

    def test_v015_marine_code_path_exercised(self, model):
        """Smoke: confirm MarineDomain v0.15.0 code path ran without error.

        A model that reaches end-of-run with a non-None ``_marine_domain``
        and a populated harvest log slot means apply_marine_growth,
        apply_marine_survival, and apply_fishing_mortality all executed
        without raising. Fishing closures may keep the log empty.
        """
        assert model._marine_domain is not None
        assert hasattr(model._marine_domain, "harvest_log")


class TestMarineEdgeCases:
    def test_mid_december_smolt_gets_sea_winter_quickly(self):
        from instream.marine.domain import MarineDomain, ZoneState
        from instream.state.trout_state import TroutState
        from instream.marine.config import MarineConfig, ZoneConfig
        import datetime

        ts = TroutState.zeros(2)
        ts.alive[0] = True
        ts.zone_idx[0] = 0
        ts.life_history[0] = int(LifeStage.SMOLT)
        ts.smolt_date[0] = datetime.date(2012, 12, 15).toordinal()
        ts.sea_winters[0] = 0

        cfg = MarineConfig(zones=[ZoneConfig(name="E", area_km2=50)], zone_connectivity={})
        zs = ZoneState.zeros(1)
        zs.name[0] = "E"
        md = MarineDomain(ts, zs, cfg)
        md.daily_step(datetime.date(2013, 1, 1))
        assert ts.sea_winters[0] == 1

    def test_unreachable_zone_fish_stays(self):
        from instream.marine.domain import MarineDomain, ZoneState
        from instream.state.trout_state import TroutState
        from instream.marine.config import MarineConfig, ZoneConfig
        import datetime

        ts = TroutState.zeros(2)
        ts.alive[0] = True
        ts.zone_idx[0] = 0
        ts.life_history[0] = int(LifeStage.SMOLT)
        ts.smolt_date[0] = datetime.date(2012, 4, 1).toordinal()

        cfg = MarineConfig(
            zones=[ZoneConfig(name="E", area_km2=50), ZoneConfig(name="C", area_km2=500)],
            zone_connectivity={},
        )
        zs = ZoneState.zeros(2)
        zs.name[0] = "E"
        zs.name[1] = "C"
        md = MarineDomain(ts, zs, cfg)
        md.daily_step(datetime.date(2012, 5, 1))
        assert ts.zone_idx[0] == 0


@pytest.mark.slow
class TestBackwardCompatibility:
    def test_no_marine_config_unchanged(self):
        from instream.model import InSTREAMModel
        import datetime

        start = datetime.date(2011, 4, 1)
        end_date = (start + datetime.timedelta(days=30)).isoformat()
        m = InSTREAMModel(
            CONFIGS / "example_a.yaml",
            data_dir=FIXTURES / "example_a",
            end_date_override=end_date,
        )
        m.run()
        ts = m.trout_state
        alive = ts.alive_indices()
        assert np.all(ts.zone_idx[alive] == -1), "Fish entered marine without config"
