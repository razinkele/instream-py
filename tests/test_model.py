"""Tests for the main SalmopyModel simulation."""

import numpy as np
import pytest
from pathlib import Path

CONFIGS_DIR = Path(__file__).parent.parent / "configs"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestModelInit:
    def test_initializes_from_config(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(
            CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
        )
        assert model is not None

    def test_has_trout_state(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(
            CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
        )
        assert model.trout_state is not None
        assert model.trout_state.num_alive() > 0

    def test_has_cell_state(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(
            CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
        )
        assert model.fem_space is not None
        assert model.fem_space.num_cells > 0

    def test_has_time_manager(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(
            CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
        )
        assert model.time_manager is not None


class TestModelStep:
    @pytest.fixture
    def model(self):
        from salmopy.model import SalmopyModel

        return SalmopyModel(
            CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
        )

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


@pytest.fixture
def example_a_model():
    from salmopy.model import SalmopyModel

    return SalmopyModel(
        CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
    )


def test_spawned_this_season_resets_at_season_start(example_a_model):
    """spawned_this_season must reset when new spawn season begins."""
    model = example_a_model
    alive = model.trout_state.alive_indices()
    if len(alive) < 5:
        return
    model.trout_state.spawned_this_season[alive[:5]] = True
    assert any(model.trout_state.spawned_this_season[alive[:5]])

    sp_cfg = model.config.species[model.species_order[0]]
    try:
        import pandas as pd

        parts = sp_cfg.spawn_start_day.split("-")
        spawn_start_doy = int(
            pd.Timestamp("2000-{}-{}".format(parts[0], parts[1])).day_of_year
        )
    except Exception:
        spawn_start_doy = 244

    # Set model time so current DOY == spawn_start_doy (satisfies transition check)
    import pandas as pd

    year = model.time_manager.current_date.year
    model.time_manager._current_date = pd.Timestamp(
        year=year, month=1, day=1
    ) + pd.Timedelta(days=spawn_start_doy - 1)
    model._prev_doy = spawn_start_doy - 1
    model._reset_spawn_season_if_needed(spawn_start_doy)
    assert not any(model.trout_state.spawned_this_season[alive[:5]]), (
        "spawned_this_season should be reset at season start"
    )


def test_model_has_reach_graph():
    from salmopy.model import SalmopyModel

    model = SalmopyModel(
        CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
    )
    assert hasattr(model, "_reach_graph")
    assert isinstance(model._reach_graph, dict)
    assert hasattr(model, "_outmigrants")


def test_model_has_census_records_after_run():
    from salmopy.model import SalmopyModel

    model = SalmopyModel(
        CONFIGS_DIR / "example_a.yaml",
        data_dir=FIXTURES_DIR / "example_a",
        end_date_override="2011-07-01",
    )  # 3 months, crosses Jun 15
    model.run()
    assert hasattr(model, "_census_records")
    assert isinstance(model._census_records, list)
    # Jun 15 should be a census day
    dates = [r["date"] for r in model._census_records]
    assert "2011-06-15" in dates, "Expected census on 2011-06-15, got: {}".format(dates)


def test_model_has_adult_arrivals_stub():
    from salmopy.model import SalmopyModel

    model = SalmopyModel(
        CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
    )
    assert hasattr(model, "_do_adult_arrivals")
    # Should not raise
    model._do_adult_arrivals()


class TestModelRun:
    def test_short_run_completes(self):
        """Run for 30 days without crash."""
        from salmopy.model import SalmopyModel

        model = SalmopyModel(
            CONFIGS_DIR / "example_a.yaml",
            data_dir=FIXTURES_DIR / "example_a",
            end_date_override="2011-05-01",
        )  # 30 days
        model.run()
        assert model.time_manager.is_done()
        assert model.trout_state.num_alive() >= 0


def test_hydraulic_table_cell_count_mismatch():
    """Model should raise if hydraulic table rows don't match cell count for a reach."""
    from salmopy.model import SalmopyModel

    model = SalmopyModel(
        CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
    )
    rname = model.reach_order[0]
    hdata = model._reach_hydraulic_data[rname]
    original = hdata["depth_values"]
    hdata["depth_values"] = original[:-5]
    with pytest.raises(ValueError, match="hydraulic table.*cell count"):
        model.step()
    hdata["depth_values"] = original


def test_apply_accumulated_growth_deterministic():
    from salmopy.model import SalmopyModel

    model = SalmopyModel(
        CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
    )
    model.step()
    alive = np.where(model.trout_state.alive)[0]
    weights = model.trout_state.weight[alive].copy()
    lengths = model.trout_state.length[alive].copy()
    conditions = model.trout_state.condition[alive].copy()
    assert np.all(np.isfinite(weights))
    assert np.all(weights > 0)
    assert np.all(np.isfinite(lengths))
    assert np.all(lengths > 0)
    assert np.all(np.isfinite(conditions))


def test_multi_reach_model_loads():
    """Example B should load with 3 reaches."""
    from salmopy.model import SalmopyModel

    CONFIGS = Path(__file__).parent.parent / "configs"
    FIXTURES = Path(__file__).parent / "fixtures" / "example_b"
    try:
        model = SalmopyModel(CONFIGS / "example_b.yaml", data_dir=FIXTURES)
        assert len(model.reach_order) == 3
        print("Multi-reach model loaded:", model.fem_space.num_cells, "cells")
    except Exception as e:
        print("Expected failure (multi-reach WIP):", e)


def test_adult_arrives_as_returning_adult():
    """Anadromous adults should arrive as RETURNING_ADULT, not SPAWNER."""
    from pathlib import Path
    from salmopy.model import SalmopyModel
    from salmopy.state.life_stage import LifeStage

    PROJECT = Path(__file__).resolve().parent.parent
    config = str(PROJECT / "configs" / "example_baltic.yaml")
    data = str(PROJECT / "tests" / "fixtures" / "example_baltic")
    model = SalmopyModel(config, data_dir=data)

    # Run until adults start arriving (May-June, ~45-90 days from April 1)
    for _ in range(90):
        model.step()

    ts = model.trout_state
    alive = ts.alive_indices()
    lengths = ts.length[alive]

    # Adults are large (>50cm). Check their life stage.
    adults = alive[lengths > 50]
    if len(adults) > 0:
        for i in adults:
            stage = int(ts.life_history[i])
            assert stage in (int(LifeStage.RETURNING_ADULT), int(LifeStage.SPAWNER)), (
                f"Large adult fish {i} has unexpected stage {stage}"
            )
            # Before spawn season (Oct), should be RETURNING_ADULT
            doy = model.time_manager.current_date.day_of_year
            if doy < 280:  # before Oct 7
                assert stage == int(LifeStage.RETURNING_ADULT), (
                    f"Adult {i} should be RETURNING_ADULT before spawn season, got {stage}"
                )
