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
