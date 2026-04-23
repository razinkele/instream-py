"""Expected-fitness translation of NetLogo InSALMO 7.3 fitness-for (2798-2840).

NetLogo computes, per candidate cell x activity:

    fitness = (daily_survival * mean_starv_survival_to_horizon) ** time_horizon

If the fish's expected length at horizon is below species-level
trout-fitness-length, fitness is additionally multiplied by
(length_at_horizon / fitness_length) — i.e. undersized fish can't
claim full fitness even in a survivable cell.

Output is always in [0, 1], making it directly comparable against
migration_fitness (a size-only logistic in [0.1, 0.9]) on the same
probability scale. This is the comparator Arc D introduces to replace
Python's scale-inconsistent fitness_memory EMA.
"""
from __future__ import annotations


def expected_fitness(
    daily_survival: float,
    mean_starv_survival: float,
    length: float,
    daily_growth: float,
    time_horizon: int,
    fitness_length: float,
) -> float:
    """Return expected fitness in [0, 1] for one fish-cell-activity triple."""
    base = (daily_survival * mean_starv_survival) ** time_horizon
    if length >= fitness_length or fitness_length <= 0.0:
        return max(0.0, min(1.0, base))
    length_at_horizon = length + daily_growth * time_horizon
    if length_at_horizon < fitness_length:
        base *= length_at_horizon / fitness_length
    return max(0.0, min(1.0, base))
