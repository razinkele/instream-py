import numpy as np
from instream.modules.migration import stochastic_should_migrate


def test_larger_fish_migrate_more():
    rng = np.random.default_rng(42)
    n_trials = 10000
    small_count = sum(
        stochastic_should_migrate(10.0, L1=8.0, L9=15.0, life_history=1, rng=rng)
        for _ in range(n_trials)
    )
    large_count = sum(
        stochastic_should_migrate(14.0, L1=8.0, L9=15.0, life_history=1, rng=rng)
        for _ in range(n_trials)
    )
    assert large_count > small_count * 2


def test_non_parr_never_migrate():
    rng = np.random.default_rng(42)
    assert not stochastic_should_migrate(20.0, L1=8.0, L9=15.0, life_history=0, rng=rng)
    assert not stochastic_should_migrate(20.0, L1=8.0, L9=15.0, life_history=2, rng=rng)
