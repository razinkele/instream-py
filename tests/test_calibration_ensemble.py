"""Tests for replicate ensemble aggregation."""
import pytest


class TestAggregateScalars:
    def test_empty_returns_empty_frame(self):
        from instream.calibration import aggregate_scalars

        df = aggregate_scalars([])
        assert len(df) == 0
        assert "mean" in df.columns

    def test_single_metric_across_seeds(self):
        from instream.calibration import aggregate_scalars

        per_seed = [{"x": v} for v in [1.0, 2.0, 3.0, 4.0, 5.0]]
        df = aggregate_scalars(per_seed, percentiles=(2.5, 97.5))
        row = df.loc["x"]
        assert row["mean"] == pytest.approx(3.0)
        assert row["p_median"] == pytest.approx(3.0)
        # p_low of [1,2,3,4,5] at 2.5% ≈ 1.1
        assert 1.0 <= row["p_low"] <= 1.5
        assert 4.5 <= row["p_high"] <= 5.0
        assert int(row["n"]) == 5

    def test_multi_metric(self):
        from instream.calibration import aggregate_scalars

        per_seed = [
            {"a": 10.0, "b": 20.0},
            {"a": 12.0, "b": 22.0},
            {"a": 14.0, "b": 24.0},
        ]
        df = aggregate_scalars(per_seed)
        assert df.loc["a", "mean"] == pytest.approx(12.0)
        assert df.loc["b", "mean"] == pytest.approx(22.0)
        assert df.loc["a", "n"] == 3
        assert df.loc["b", "n"] == 3

    def test_nan_values_skipped(self):
        import math
        from instream.calibration import aggregate_scalars

        per_seed = [
            {"x": 1.0},
            {"x": float("nan")},
            {"x": 3.0},
            {"x": float("inf")},
        ]
        df = aggregate_scalars(per_seed)
        # Only 1.0 and 3.0 should be counted
        assert df.loc["x", "n"] == 2
        assert df.loc["x", "mean"] == pytest.approx(2.0)

    def test_missing_metric_in_some_seeds(self):
        from instream.calibration import aggregate_scalars

        per_seed = [
            {"a": 1.0, "b": 10.0},
            {"a": 2.0},  # b missing
            {"a": 3.0, "b": 20.0},
        ]
        df = aggregate_scalars(per_seed)
        assert df.loc["a", "n"] == 3
        assert df.loc["b", "n"] == 2


class TestAggregateTrajectories:
    def test_empty_returns_empty_frame(self):
        from instream.calibration import aggregate_trajectories

        df = aggregate_trajectories([])
        assert df.empty

    def test_three_replicates_same_grid(self):
        import pandas as pd
        from instream.calibration import aggregate_trajectories

        # Three seeds sharing dates 1,2,3 with value col 'pop'
        per_seed = [
            pd.DataFrame({"date": [1, 2, 3], "pop": [10, 20, 30]}),
            pd.DataFrame({"date": [1, 2, 3], "pop": [12, 22, 32]}),
            pd.DataFrame({"date": [1, 2, 3], "pop": [14, 24, 34]}),
        ]
        agg = aggregate_trajectories(per_seed, time_col="date")
        assert list(agg.index) == [1, 2, 3]
        assert agg.loc[1, ("pop", "mean")] == pytest.approx(12.0)
        assert agg.loc[2, ("pop", "mean")] == pytest.approx(22.0)
        assert agg.loc[3, ("pop", "mean")] == pytest.approx(32.0)
        assert agg.loc[2, ("pop", "p_median")] == pytest.approx(22.0)

    def test_value_cols_filter(self):
        import pandas as pd
        from instream.calibration import aggregate_trajectories

        per_seed = [
            pd.DataFrame({"date": [1, 2], "a": [1, 2], "b": [10, 20]}),
            pd.DataFrame({"date": [1, 2], "a": [3, 4], "b": [30, 40]}),
        ]
        agg = aggregate_trajectories(per_seed, time_col="date", value_cols=["a"])
        # Only 'a' aggregated, not 'b'
        cols = set(c[0] for c in agg.columns)
        assert cols == {"a"}

    def test_intersection_of_time_grids(self):
        """If replicates have different time ranges, aggregate on intersection."""
        import pandas as pd
        from instream.calibration import aggregate_trajectories

        per_seed = [
            pd.DataFrame({"date": [1, 2, 3, 4], "x": [10, 20, 30, 40]}),
            pd.DataFrame({"date": [2, 3], "x": [22, 33]}),
        ]
        agg = aggregate_trajectories(per_seed, time_col="date")
        # Only dates 2 and 3 are common
        assert list(agg.index) == [2, 3]


class TestRunReplicates:
    def test_sequential_execution(self):
        from instream.calibration import run_replicates

        def eval_fn(seed: int) -> dict:
            return {"x": float(seed * 10)}

        results = run_replicates(eval_fn, seeds=[1, 2, 3])
        assert results == [{"x": 10.0}, {"x": 20.0}, {"x": 30.0}]
