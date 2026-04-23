"""Reference-implementation tests for habitat_fitness.expected_fitness.

Targets NetLogo InSALMO 7.3 fitness-for (lines 2798-2840). The formula:

    fitness = (daily_survival * mean_starv_survival_to_horizon) ^ time_horizon
    if length < fitness_length:
        fitness *= min(1.0, length_at_horizon / fitness_length)

Hand-computed expected values assume mean_starv_survival=1.0 unless
otherwise stated — starvation survival is its own module.
"""
import pytest


class TestExpectedFitness:
    def test_perfect_survival_no_growth_penalty(self):
        """Survival=1, length>=fitness_length -> fitness=1."""
        from salmopy.modules.habitat_fitness import expected_fitness

        f = expected_fitness(
            daily_survival=1.0,
            mean_starv_survival=1.0,
            length=10.0,
            daily_growth=0.1,
            time_horizon=90,
            fitness_length=6.0,
        )
        assert f == pytest.approx(1.0)

    def test_survival_power_horizon(self):
        """fitness = survival^horizon when starv_survival=1 and length>=fit_length."""
        from salmopy.modules.habitat_fitness import expected_fitness

        f = expected_fitness(
            daily_survival=0.99,
            mean_starv_survival=1.0,
            length=10.0,
            daily_growth=0.0,
            time_horizon=90,
            fitness_length=6.0,
        )
        assert f == pytest.approx(0.99 ** 90, rel=1e-9)

    def test_undersized_fish_length_penalty(self):
        """If length < fitness_length, fitness scales by length_at_horizon/fitness_length."""
        from salmopy.modules.habitat_fitness import expected_fitness

        f = expected_fitness(
            daily_survival=1.0,
            mean_starv_survival=1.0,
            length=3.0,
            daily_growth=0.01,
            time_horizon=90,
            fitness_length=6.0,
        )
        # Expected: fitness = 1 * (3 + 90*0.01) / 6 = 3.9 / 6 = 0.65
        assert f == pytest.approx(3.9 / 6.0, rel=1e-6)

    def test_bounded_0_1(self):
        """fitness must be in [0, 1] for any plausible inputs."""
        from salmopy.modules.habitat_fitness import expected_fitness

        for ds in [0.1, 0.5, 0.99, 1.0]:
            for ss in [0.1, 0.5, 1.0]:
                for L in [3.0, 6.0, 12.0]:
                    for g in [0.0, 0.01, 0.1]:
                        f = expected_fitness(ds, ss, L, g, 90, 6.0)
                        assert 0.0 <= f <= 1.0, (ds, ss, L, g, f)

    def test_zero_survival_zero_fitness(self):
        from salmopy.modules.habitat_fitness import expected_fitness

        f = expected_fitness(0.0, 1.0, 10.0, 0.1, 90, 6.0)
        assert f == 0.0

    def test_starv_survival_multiplies(self):
        from salmopy.modules.habitat_fitness import expected_fitness

        f = expected_fitness(
            daily_survival=1.0,
            mean_starv_survival=0.5,
            length=10.0,
            daily_growth=0.1,
            time_horizon=10,
            fitness_length=6.0,
        )
        # (1 * 0.5)^10 = 0.5^10
        assert f == pytest.approx(0.5 ** 10, rel=1e-9)
