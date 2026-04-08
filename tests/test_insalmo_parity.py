"""Validate inSTREAM-py inSALMO features.

These tests verify that the new inSALMO-specific features work correctly:
- Adult holding (zero food intake for anadromous spawners)
- Two-piece condition-survival (broken-stick starvation)
- Stochastic outmigration
- Outmigrant date recording
- Spawn-cell perturbation
- Growth fitness term

Reference data from inSALMO 7.4 NetLogo to be added via @netlogo-oracle skill.
"""
import math

import numpy as np
import pytest

from instream.agents.life_stage import LifeStage
from instream.modules.behavior import insalmo_growth_fitness, should_skip_feeding
from instream.modules.migration import stochastic_should_migrate
from instream.modules.spawning import select_spawn_cell
from instream.modules.survival import survival_condition_two_piece


class TestAdultHolding:
    """Verify anadromous spawners don't feed."""

    def test_should_skip_feeding_for_anadromous_spawner(self):
        assert should_skip_feeding(int(LifeStage.SPAWNER), is_anadromous=True)

    def test_should_not_skip_for_resident(self):
        assert not should_skip_feeding(int(LifeStage.SPAWNER), is_anadromous=False)

    def test_should_not_skip_for_juveniles(self):
        for stage in [LifeStage.FRY, LifeStage.PARR]:
            assert not should_skip_feeding(int(stage), is_anadromous=True)


class TestConditionSurvival:
    """Verify two-piece broken-stick starvation function."""

    def test_healthy_fish_high_survival(self):
        surv = survival_condition_two_piece(
            np.array([1.0]),
            breakpoint=0.8,
            S_above_K8=0.99,
            S_below_K5=0.5,
            K5=0.5,
        )
        assert surv[0] > 0.95

    def test_starving_fish_low_survival(self):
        surv = survival_condition_two_piece(
            np.array([0.3]),
            breakpoint=0.8,
            S_above_K8=0.99,
            S_below_K5=0.5,
            K5=0.5,
        )
        assert surv[0] < 0.5

    def test_sharp_drop_below_breakpoint(self):
        conditions = np.array([1.0, 0.8, 0.6, 0.4])
        surv = survival_condition_two_piece(
            conditions,
            breakpoint=0.8,
            S_above_K8=0.99,
            S_below_K5=0.5,
            K5=0.5,
        )
        drop_above = surv[0] - surv[1]
        drop_below = surv[1] - surv[3]
        assert drop_below > drop_above * 2


class TestStochasticMigration:
    """Verify length-dependent stochastic outmigration."""

    def test_migration_probability_increases_with_length(self):
        rng = np.random.default_rng(42)
        n = 5000
        small = sum(
            stochastic_should_migrate(8.0, 8.0, 15.0, int(LifeStage.PARR), rng)
            for _ in range(n)
        )
        large = sum(
            stochastic_should_migrate(14.0, 8.0, 15.0, int(LifeStage.PARR), rng)
            for _ in range(n)
        )
        assert large > small * 2

    def test_only_parr_migrate(self):
        rng = np.random.default_rng(42)
        non_parr = [
            LifeStage.FRY,
            LifeStage.SPAWNER,
            LifeStage.SMOLT,
            LifeStage.OCEAN_JUVENILE,
            LifeStage.OCEAN_ADULT,
            LifeStage.RETURNING_ADULT,
        ]
        for stage in non_parr:
            assert not stochastic_should_migrate(
                20.0, 8.0, 15.0, int(stage), rng
            )


class TestSpawnPerturbation:
    """Verify noise prevents redd clustering."""

    def test_noise_disperses_redd_placement(self):
        rng = np.random.default_rng(42)
        scores = np.array([0.90, 0.89, 0.88])
        candidates = np.array([0, 1, 2])
        selections = [
            select_spawn_cell(scores, candidates, rng=rng, noise_sd=0.15)
            for _ in range(200)
        ]
        assert len(set(selections)) >= 2, "Noise should disperse selections"

    def test_no_noise_is_deterministic(self):
        scores = np.array([0.90, 0.89])
        candidates = np.array([0, 1])
        results = [select_spawn_cell(scores, candidates) for _ in range(50)]
        assert all(r == 0 for r in results), "No noise = always best cell"


class TestGrowthFitness:
    """Verify inSALMO growth fitness function."""

    def test_monotonic_increase(self):
        lengths = [5, 10, 15, 20, 25]
        fitness = [insalmo_growth_fitness(l, 30.0) for l in lengths]
        for i in range(len(fitness) - 1):
            assert fitness[i] < fitness[i + 1]

    def test_bounded(self):
        f = insalmo_growth_fitness(30.0, 30.0)
        assert abs(f - math.log(2)) < 0.01


@pytest.mark.slow
class TestInsalmoParity:
    """Placeholder for NetLogo reference data validation.

    TODO: Use @netlogo-oracle skill to generate reference data from
    inSALMO 7.4 NetLogo for the following metrics:
    - Outmigrant size distribution (mean, SD)
    - Outmigrant timing (peak day-of-year)
    - Post-spawn mortality rate
    - Redd-to-outmigrant survival
    """

    def test_outmigrant_size_distribution(self):
        """Mean outmigrant length should match NetLogo reference +/-10%."""
        pytest.skip("Awaiting NetLogo reference data via @netlogo-oracle")

    def test_outmigrant_timing(self):
        """Peak outmigration DOY should match NetLogo reference +/-14 days."""
        pytest.skip("Awaiting NetLogo reference data via @netlogo-oracle")

    def test_post_spawn_mortality(self):
        """All anadromous spawners should die within days of spawning."""
        pytest.skip("Awaiting NetLogo reference data via @netlogo-oracle")
