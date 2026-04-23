"""Tests for fitness-based outmigration probability (Task 9)."""

from salmopy.modules.migration import outmigration_probability


def test_poor_fitness_increases_migration():
    """Lower fitness should yield higher migration probability."""
    p_low = outmigration_probability(fitness=0.3, length=10.0, min_length=8.0)
    p_high = outmigration_probability(fitness=0.8, length=10.0, min_length=8.0)
    assert p_low > p_high


def test_below_min_length_no_migration():
    """Fish below min_length should never migrate."""
    p = outmigration_probability(fitness=0.0, length=5.0, min_length=8.0)
    assert p == 0.0


def test_at_max_prob():
    """Fitness=0 should give exactly max_prob."""
    p = outmigration_probability(fitness=0.0, length=10.0, min_length=8.0, max_prob=0.1)
    assert p == 0.1


def test_perfect_fitness_no_migration():
    """Fitness=1.0 should give zero migration probability."""
    p = outmigration_probability(fitness=1.0, length=10.0, min_length=8.0)
    assert p == 0.0
