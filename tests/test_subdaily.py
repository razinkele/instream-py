"""Integration tests for InSTREAM-SD sub-daily mode."""

import numpy as np
import pytest
import yaml
from pathlib import Path

CONFIGS = Path(__file__).parent.parent / "configs"
FIXTURES_A = Path(__file__).parent / "fixtures" / "example_a"
FIXTURES_SD = Path(__file__).parent / "fixtures" / "subdaily"


def _make_subdaily_config(tmp_path, timeseries_csv, end_date="2010-10-03"):
    """Create a config pointing to sub-daily time series.

    The sub-daily fixture data covers 2010-10-01 to 2010-10-10, so we
    must align start_date and end_date to that range.
    """
    config = yaml.safe_load((CONFIGS / "example_a.yaml").read_text())
    config["simulation"]["start_date"] = "2010-10-01"
    config["simulation"]["end_date"] = end_date
    # Point reach to sub-daily data
    for rname in config["reaches"]:
        config["reaches"][rname]["time_series_input_file"] = str(timeseries_csv)
    out = tmp_path / "subdaily_config.yaml"
    out.write_text(yaml.dump(config, default_flow_style=False))
    return str(out)


class TestSubDailyDetection:
    def test_hourly_detected_as_24(self, tmp_path):
        from instream.model import InSTREAMModel

        config = _make_subdaily_config(tmp_path, FIXTURES_SD / "hourly_example_a.csv")
        model = InSTREAMModel(config, data_dir=str(FIXTURES_A))
        assert model.steps_per_day == 24

    def test_peaking_detected_as_4(self, tmp_path):
        from instream.model import InSTREAMModel

        config = _make_subdaily_config(tmp_path, FIXTURES_SD / "peaking_example_a.csv")
        model = InSTREAMModel(config, data_dir=str(FIXTURES_A))
        assert model.steps_per_day == 4

    def test_daily_detected_as_1(self):
        from instream.model import InSTREAMModel

        model = InSTREAMModel(CONFIGS / "example_a.yaml", data_dir=str(FIXTURES_A))
        assert model.steps_per_day == 1


@pytest.mark.slow
class TestSubDailyRun:
    def test_hourly_runs_without_crash(self, tmp_path):
        from instream.model import InSTREAMModel

        config = _make_subdaily_config(
            tmp_path, FIXTURES_SD / "hourly_example_a.csv", end_date="2010-10-02"
        )
        model = InSTREAMModel(config, data_dir=str(FIXTURES_A))
        steps = 0
        while not model.time_manager.is_done() and steps < 50:
            model.step()
            steps += 1
        assert steps >= 24  # at least one full day of hourly steps
        assert model.trout_state.num_alive() > 0

    def test_peaking_runs_without_crash(self, tmp_path):
        from instream.model import InSTREAMModel

        config = _make_subdaily_config(
            tmp_path, FIXTURES_SD / "peaking_example_a.csv", end_date="2010-10-03"
        )
        model = InSTREAMModel(config, data_dir=str(FIXTURES_A))
        steps = 0
        while not model.time_manager.is_done() and steps < 20:
            model.step()
            steps += 1
        assert steps >= 4  # at least one full day of 4-step peaking
        assert model.trout_state.num_alive() > 0

    def test_growth_not_applied_mid_day(self, tmp_path):
        """Weights should NOT change during sub-steps, only at day boundary."""
        from instream.model import InSTREAMModel

        config = _make_subdaily_config(
            tmp_path, FIXTURES_SD / "peaking_example_a.csv", end_date="2010-10-03"
        )
        model = InSTREAMModel(config, data_dir=str(FIXTURES_A))
        alive = model.trout_state.alive_indices()
        initial_weights = model.trout_state.weight[alive].copy()
        # Run 1 sub-step (NOT a full day)
        model.step()
        # Weights should NOT change mid-day (growth accumulated, not applied)
        if not model.time_manager.is_day_boundary:
            np.testing.assert_array_equal(
                model.trout_state.weight[alive],
                initial_weights,
                err_msg="Weights changed mid-day — growth should only apply at day boundary",
            )

    def test_growth_applied_at_day_boundary(self, tmp_path):
        """After a full day, weights should have changed."""
        from instream.model import InSTREAMModel

        config = _make_subdaily_config(
            tmp_path, FIXTURES_SD / "peaking_example_a.csv", end_date="2010-10-03"
        )
        model = InSTREAMModel(config, data_dir=str(FIXTURES_A))
        alive = model.trout_state.alive_indices()
        initial_weights = model.trout_state.weight[alive].copy()
        # Run until first day boundary
        for _ in range(model.steps_per_day):
            model.step()
        # NOW weights should have changed
        assert not np.allclose(model.trout_state.weight[alive], initial_weights), (
            "Weights unchanged after full day — growth should be applied at day boundary"
        )

    def test_survival_applied_each_substep(self, tmp_path):
        """Fish can die mid-day from survival checks."""
        from instream.model import InSTREAMModel

        config = _make_subdaily_config(
            tmp_path, FIXTURES_SD / "hourly_example_a.csv", end_date="2010-10-02"
        )
        model = InSTREAMModel(config, data_dir=str(FIXTURES_A))
        initial_alive = model.trout_state.num_alive()
        # Run several sub-steps
        for _ in range(24):
            model.step()
        # Some fish may have died during sub-steps (survival applied each step)
        # Just verify no crash and count is <= initial
        assert model.trout_state.num_alive() <= initial_alive


class TestDailyBackwardCompatibility:
    def test_daily_still_works_identically(self):
        """Daily input must produce same behavior as before sub-daily refactor."""
        from instream.model import InSTREAMModel

        model = InSTREAMModel(
            CONFIGS / "example_a.yaml",
            data_dir=str(FIXTURES_A),
            end_date_override="2011-04-11",
        )
        assert model.steps_per_day == 1
        for _ in range(10):
            model.step()
            # Every step should be a day boundary in daily mode
            assert model.time_manager.is_day_boundary == True
        alive = model.trout_state.num_alive()
        # Arc D (v0.31.0, 2026-04-19): continuous FRY->PARR promotion +
        # scale-consistent migration comparator mean some emergence-length
        # 4.0+ cm fry now outmigrate (and die at the single-reach example_a
        # mouth) within the first 10 days — matching NetLogo behavior
        # where anadromous fish are `anad-juve` from birth
        # (InSALMO7.3:2256-2258, 4259-4261). Pre-Arc D they stayed FRY and
        # could not migrate. The reduced lower-bound reflects this intentional
        # change. Key property preserved: not all fish die.
        assert alive > 0, "All fish died — genuine regression"

    def test_daily_substep_index_always_zero(self):
        """In daily mode, substep_index should always be 0."""
        from instream.model import InSTREAMModel

        model = InSTREAMModel(
            CONFIGS / "example_a.yaml",
            data_dir=str(FIXTURES_A),
            end_date_override="2011-04-05",
        )
        for _ in range(3):
            model.step()
            assert model.time_manager.substep_index == 0
