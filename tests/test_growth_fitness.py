import math
from instream.modules.behavior import insalmo_growth_fitness


def test_growth_fitness_encourages_small_fish():
    small = insalmo_growth_fitness(expected_length=5.0, biggest_length=30.0)
    big = insalmo_growth_fitness(expected_length=25.0, biggest_length=30.0)
    assert small > 0, "Small fish get positive fitness"
    assert big > small, "Bigger expected length = higher fitness"
    assert big < 1.0, "Bounded below ln(2)"


def test_growth_fitness_formula():
    result = insalmo_growth_fitness(expected_length=10.0, biggest_length=20.0)
    expected = math.log(1 + 10.0 / 20.0)
    assert abs(result - expected) < 1e-10


def test_growth_fitness_zero_biggest():
    result = insalmo_growth_fitness(expected_length=10.0, biggest_length=0.0)
    assert result == 0.0
