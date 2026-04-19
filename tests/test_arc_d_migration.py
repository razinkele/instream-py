"""Arc D migration architecture rewrite — behavioral tests.

Covers (1) TroutState.best_habitat_fitness schema, (2) continuous
FRY->PARR promotion, (3) migration comparator scale consistency.
"""
import numpy as np
import pytest


class TestTroutStateBestHabitatFitness:
    def test_array_exists_and_is_float64(self):
        from instream.state.trout_state import TroutState

        ts = TroutState.zeros(capacity=10)
        assert hasattr(ts, "best_habitat_fitness")
        assert ts.best_habitat_fitness.dtype == np.float64
        assert ts.best_habitat_fitness.shape == (10,)

    def test_initial_value_zero(self):
        from instream.state.trout_state import TroutState

        ts = TroutState.zeros(capacity=10)
        assert np.all(ts.best_habitat_fitness == 0.0)

    def test_writable_scalar(self):
        """Sanity: a consumer can write per-fish values."""
        from instream.state.trout_state import TroutState

        ts = TroutState.zeros(capacity=5)
        ts.best_habitat_fitness[:] = [0.1, 0.5, 0.9, 0.0, 1.0]
        np.testing.assert_array_equal(
            ts.best_habitat_fitness, [0.1, 0.5, 0.9, 0.0, 1.0]
        )


class TestMigrationComparatorScale:
    """Arc D Task 5: should_migrate compares migration_fitness against a
    [0,1] best_habitat_fit (not the unbounded fitness_memory EMA)."""

    def test_small_parr_migrates_when_habitat_fitness_low(self):
        """4cm PARR with migration_fit ~0.1 and habitat_fit 0.05 -> migrate."""
        from instream.modules.migration import migration_fitness, should_migrate
        from instream.state.life_stage import LifeStage

        mig_fit = migration_fitness(length=4.0, L1=4.0, L9=10.0)
        assert 0.09 <= mig_fit <= 0.11  # logistic at L1=4 = 0.1

        assert should_migrate(
            migration_fit=mig_fit,
            best_habitat_fit=0.05,
            life_history=int(LifeStage.PARR),
        ) is True

    def test_parr_stays_in_good_habitat(self):
        """4cm PARR with habitat_fit 0.9 -> don't migrate."""
        from instream.modules.migration import migration_fitness, should_migrate
        from instream.state.life_stage import LifeStage

        mig_fit = migration_fitness(length=4.0, L1=4.0, L9=10.0)
        assert should_migrate(
            migration_fit=mig_fit,
            best_habitat_fit=0.9,
            life_history=int(LifeStage.PARR),
        ) is False

    def test_non_parr_never_migrates(self):
        from instream.modules.migration import should_migrate
        from instream.state.life_stage import LifeStage

        for stage in [LifeStage.FRY, LifeStage.SPAWNER, LifeStage.OCEAN_ADULT]:
            assert should_migrate(0.9, 0.1, int(stage)) is False


class TestContinuousPARRPromotion:
    """Arc D Task 4: FRY -> PARR should promote when length >=
    parr_promotion_length OR age >= 1 — NOT only on Jan 1."""

    def test_fry_promoted_mid_year_when_above_length(self):
        """A May FRY at 5.0 cm (above default 4.0 cm threshold) must
        be promoted to PARR on the same daily boundary, not wait for
        next Jan 1."""
        from pathlib import Path
        import datetime
        from instream.model import InSTREAMModel
        from instream.state.life_stage import LifeStage

        configs = Path(__file__).parent.parent / "configs"
        fixtures = Path(__file__).parent / "fixtures"
        # Start model April 1, step one day, then hand-force FRY+size+July date
        start = datetime.date(2011, 4, 1)
        end = (start + datetime.timedelta(days=1)).isoformat()
        model = InSTREAMModel(
            configs / "example_a.yaml",
            data_dir=fixtures / "example_a",
            end_date_override=end,
        )
        model.run()
        ts = model.trout_state
        alive = ts.alive_indices()
        # Force all alive fish into anadromous FRY at 5.0 cm
        ts.life_history[alive] = int(LifeStage.FRY)
        ts.length[alive] = 5.0

        # Replace end_date and step again — but simpler: call the
        # promotion method directly.
        # Force julian_date != 1 so old gate would skip.
        import pandas as pd
        model.time_manager._current_date = pd.Timestamp("2011-07-15")
        model._increment_age_if_new_year()

        lh = ts.life_history[alive]
        assert (lh == int(LifeStage.PARR)).all(), (
            f"expected mid-year promotion to PARR, got {lh.tolist()[:10]}"
        )

    def test_small_fry_stays_fry(self):
        """FRY below length threshold AND age 0 must stay FRY."""
        from pathlib import Path
        import datetime
        from instream.model import InSTREAMModel
        from instream.state.life_stage import LifeStage

        configs = Path(__file__).parent.parent / "configs"
        fixtures = Path(__file__).parent / "fixtures"
        start = datetime.date(2011, 4, 1)
        end = (start + datetime.timedelta(days=1)).isoformat()
        model = InSTREAMModel(
            configs / "example_a.yaml",
            data_dir=fixtures / "example_a",
            end_date_override=end,
        )
        model.run()
        ts = model.trout_state
        alive = ts.alive_indices()
        ts.life_history[alive] = int(LifeStage.FRY)
        ts.length[alive] = 2.5  # below 4.0
        ts.age[alive] = 0

        import pandas as pd
        model.time_manager._current_date = pd.Timestamp("2011-07-15")
        model._increment_age_if_new_year()

        lh = ts.life_history[alive]
        assert (lh == int(LifeStage.FRY)).all()


class TestHabitatFitnessRecording:
    """After a model step, best_habitat_fitness must be in [0, 1] for
    alive freshwater fish (verifies the Arc D post-pass is wired)."""

    def test_best_habitat_fitness_in_bounds_after_step(self):
        """Run example_a for 2 days; alive freshwater fish must have
        best_habitat_fitness in [0, 1]."""
        from pathlib import Path
        import datetime
        from instream.model import InSTREAMModel

        configs = Path(__file__).parent.parent / "configs"
        fixtures = Path(__file__).parent / "fixtures"
        start = datetime.date(2011, 4, 1)
        end = (start + datetime.timedelta(days=2)).isoformat()
        model = InSTREAMModel(
            configs / "example_a.yaml",
            data_dir=fixtures / "example_a",
            end_date_override=end,
        )
        model.run()

        ts = model.trout_state
        alive = ts.alive_indices()
        assert len(alive) > 0
        fw = alive[ts.zone_idx[alive] < 0] if hasattr(ts, "zone_idx") else alive
        vals = ts.best_habitat_fitness[fw]
        assert np.all(vals >= 0.0), "best_habitat_fitness below 0"
        assert np.all(vals <= 1.0), "best_habitat_fitness above 1"
        # At least one fish should have a non-zero value (they're in viable cells)
        assert np.any(vals > 0.0), "no fish recorded best_habitat_fitness"

    def test_differs_from_fitness_memory(self):
        """Proves best_habitat_fitness and fitness_memory are separate
        quantities — not aliased. fitness_memory is an EMA of growth and
        survival, best_habitat_fitness is per-tick survival^horizon."""
        from pathlib import Path
        import datetime
        from instream.model import InSTREAMModel

        configs = Path(__file__).parent.parent / "configs"
        fixtures = Path(__file__).parent / "fixtures"
        start = datetime.date(2011, 4, 1)
        end = (start + datetime.timedelta(days=3)).isoformat()
        model = InSTREAMModel(
            configs / "example_a.yaml",
            data_dir=fixtures / "example_a",
            end_date_override=end,
        )
        model.run()

        ts = model.trout_state
        alive = ts.alive_indices()
        assert not np.array_equal(
            ts.fitness_memory[alive], ts.best_habitat_fitness[alive]
        )
