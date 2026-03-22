"""Performance regression tests — ensure optimizations aren't accidentally reverted."""

import time
import pytest


@pytest.mark.slow
class TestScalarFunctionOverhead:
    """Key scalar functions must stay below overhead thresholds."""

    def test_survival_condition_fast(self):
        """survival_condition must not use np.clip (threshold: 1us)."""
        from instream.modules.survival import survival_condition

        n = 50000
        t0 = time.perf_counter()
        for _ in range(n):
            survival_condition(0.85)
        us_per_call = (time.perf_counter() - t0) / n * 1e6
        assert us_per_call < 1.0, (
            "survival_condition too slow: {:.2f}us (limit 1.0us)".format(us_per_call)
        )

    def test_evaluate_logistic_fast(self):
        """evaluate_logistic must use math.exp (threshold: 1us)."""
        from instream.modules.behavior import evaluate_logistic

        n = 50000
        t0 = time.perf_counter()
        for _ in range(n):
            evaluate_logistic(15.0, 10.0, 20.0)
        us_per_call = (time.perf_counter() - t0) / n * 1e6
        assert us_per_call < 1.0, (
            "evaluate_logistic too slow: {:.2f}us (limit 1.0us)".format(us_per_call)
        )

    def test_cmax_temp_function_fast(self):
        """cmax_temp_function must use bisect (threshold: 1us)."""
        from instream.modules.growth import cmax_temp_function

        table_x = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
        table_y = [0.0, 0.2, 0.5, 0.8, 1.0, 0.7, 0.1]
        n = 50000
        t0 = time.perf_counter()
        for _ in range(n):
            cmax_temp_function(12.0, table_x, table_y)
        us_per_call = (time.perf_counter() - t0) / n * 1e6
        assert us_per_call < 1.0, (
            "cmax_temp_function too slow: {:.2f}us (limit 1.0us)".format(us_per_call)
        )

    def test_survival_condition_returns_float(self):
        """Must return pure Python float, not numpy scalar."""
        from instream.modules.survival import survival_condition

        result = survival_condition(0.85)
        assert type(result) is float

    def test_evaluate_logistic_returns_float(self):
        """Must return pure Python float, not numpy scalar."""
        from instream.modules.behavior import evaluate_logistic

        result = evaluate_logistic(15.0, 10.0, 20.0)
        assert type(result) is float
