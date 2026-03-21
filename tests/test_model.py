"""Tests for the main InSTREAMModel simulation."""
import numpy as np
import pytest
from pathlib import Path

CONFIGS_DIR = Path(__file__).parent.parent / "configs"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestModelInit:
    def test_initializes_from_config(self):
        from instream.model import InSTREAMModel
        model = InSTREAMModel(CONFIGS_DIR / "example_a.yaml",
                              data_dir=FIXTURES_DIR / "example_a")
        assert model is not None

    def test_has_trout_state(self):
        from instream.model import InSTREAMModel
        model = InSTREAMModel(CONFIGS_DIR / "example_a.yaml",
                              data_dir=FIXTURES_DIR / "example_a")
        assert model.trout_state is not None
        assert model.trout_state.num_alive() > 0

    def test_has_cell_state(self):
        from instream.model import InSTREAMModel
        model = InSTREAMModel(CONFIGS_DIR / "example_a.yaml",
                              data_dir=FIXTURES_DIR / "example_a")
        assert model.fem_space is not None
        assert model.fem_space.num_cells > 0

    def test_has_time_manager(self):
        from instream.model import InSTREAMModel
        model = InSTREAMModel(CONFIGS_DIR / "example_a.yaml",
                              data_dir=FIXTURES_DIR / "example_a")
        assert model.time_manager is not None


class TestModelStep:
    @pytest.fixture
    def model(self):
        from instream.model import InSTREAMModel
        return InSTREAMModel(CONFIGS_DIR / "example_a.yaml",
                             data_dir=FIXTURES_DIR / "example_a")

    def test_step_advances_time(self, model):
        date_before = model.time_manager.current_date
        model.step()
        assert model.time_manager.current_date > date_before

    def test_step_updates_hydraulics(self, model):
        model.step()
        # After step, some cells should have positive depth
        assert np.any(model.fem_space.cell_state.depth > 0)

    def test_step_no_crash(self, model):
        model.step()  # should not raise

    def test_10_steps_no_crash(self, model):
        for _ in range(10):
            model.step()
        assert model.trout_state.num_alive() > 0  # some fish should still be alive

    def test_population_changes(self, model):
        initial_pop = model.trout_state.num_alive()
        for _ in range(10):
            model.step()
        # Population should have changed (growth, possible mortality)
        # We just verify it's reasonable, not exact
        final_pop = model.trout_state.num_alive()
        assert final_pop > 0
        assert final_pop <= initial_pop * 2  # shouldn't explode in 10 steps


class TestModelRun:
    def test_short_run_completes(self):
        """Run for 30 days without crash."""
        from instream.model import InSTREAMModel
        model = InSTREAMModel(CONFIGS_DIR / "example_a.yaml",
                              data_dir=FIXTURES_DIR / "example_a",
                              end_date_override="2011-05-01")  # 30 days
        model.run()
        assert model.time_manager.is_done()
        assert model.trout_state.num_alive() >= 0
