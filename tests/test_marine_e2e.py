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
        ts = model.trout_state
        assert np.any(ts.smolt_date >= 0), "No fish ever smoltified"

    def test_some_fish_returned(self, model):
        ts = model.trout_state
        # Fish that smoltified (smolt_date >= 0) and later returned to
        # freshwater (zone_idx == -1) prove the full marine round-trip.
        # They may be alive (as RETURNING_ADULT or SPAWNER) or dead
        # (post-spawn mortality), so check all fish, not just alive.
        smoltified = np.where(ts.smolt_date >= 0)[0]
        returned = smoltified[ts.zone_idx[smoltified] == -1]
        assert len(returned) > 0, "No fish returned from marine domain"

    def test_returned_fish_have_valid_cell(self, model):
        ts = model.trout_state
        alive = ts.alive_indices()
        fw = alive[(ts.zone_idx[alive] == -1) & (ts.natal_reach_idx[alive] >= 0)]
        if len(fw) > 0:
            assert np.all(ts.cell_idx[fw] >= 0), "Returned fish have invalid cell_idx"

    def test_freshwater_still_works(self, model):
        assert model.trout_state.alive.sum() > 0, "Population went extinct"


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
