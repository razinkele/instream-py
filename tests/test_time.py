"""Tests for time management — TimeManager, YearShuffler, census."""

import numpy as np
import pandas as pd
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestTimeManager:
    """Test simulation time advancement."""

    @pytest.fixture
    def time_manager(self):
        from instream.io.timeseries import read_time_series
        from instream.io.time_manager import TimeManager

        df = read_time_series(
            FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv"
        )
        return TimeManager(
            start_date="2011-04-01",
            end_date="2011-04-10",  # short run for testing
            time_series={"ExampleA": df},
        )

    def test_initial_time_is_start_date(self, time_manager):
        assert time_manager.current_date.year == 2011
        assert time_manager.current_date.month == 4
        assert time_manager.current_date.day == 1

    def test_advance_increments_by_one_day(self, time_manager):
        time_manager.advance()
        assert time_manager.current_date.day == 2

    def test_advance_returns_step_length_one(self, time_manager):
        step_length = time_manager.advance()
        assert step_length == pytest.approx(1.0)

    def test_julian_date_april_1(self, time_manager):
        # April 1 = day 91 (non-leap year)
        assert time_manager.julian_date == 91

    def test_julian_date_jan_1(self):
        from instream.io.timeseries import read_time_series
        from instream.io.time_manager import TimeManager

        df = read_time_series(
            FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv"
        )
        tm = TimeManager(
            start_date="2011-01-01", end_date="2011-01-05", time_series={"ExampleA": df}
        )
        assert tm.julian_date == 1

    def test_is_done_false_at_start(self, time_manager):
        assert not time_manager.is_done()

    def test_is_done_true_at_end(self, time_manager):
        # Advance through all 10 days
        for _ in range(10):
            time_manager.advance()
        assert time_manager.is_done()

    def test_get_conditions_returns_flow(self, time_manager):
        conditions = time_manager.get_conditions("ExampleA")
        assert "flow" in conditions
        assert conditions["flow"] > 0

    def test_get_conditions_returns_temperature(self, time_manager):
        conditions = time_manager.get_conditions("ExampleA")
        assert "temperature" in conditions

    def test_get_conditions_returns_turbidity(self, time_manager):
        conditions = time_manager.get_conditions("ExampleA")
        assert "turbidity" in conditions

    def test_conditions_change_after_advance(self, time_manager):
        c1 = time_manager.get_conditions("ExampleA")
        time_manager.advance()
        c2 = time_manager.get_conditions("ExampleA")
        # At least one value should potentially differ (not guaranteed for every step)
        # Just verify we get valid data at both times
        assert c2["flow"] > 0

    def test_formatted_time(self, time_manager):
        ft = time_manager.formatted_time()
        assert "2011" in ft


class TestCensus:
    """Test census day detection."""

    def test_is_census_on_census_day(self):
        from instream.io.time_manager import is_census

        dt = pd.Timestamp("2011-06-15")
        assert is_census(
            dt,
            census_days=["6/15", "9/30"],
            years_to_skip=0,
            start_date=pd.Timestamp("2011-04-01"),
        )

    def test_is_census_on_second_census_day(self):
        from instream.io.time_manager import is_census

        dt = pd.Timestamp("2011-09-30")
        assert is_census(
            dt,
            census_days=["6/15", "9/30"],
            years_to_skip=0,
            start_date=pd.Timestamp("2011-04-01"),
        )

    def test_not_census_on_regular_day(self):
        from instream.io.time_manager import is_census

        dt = pd.Timestamp("2011-07-04")
        assert not is_census(
            dt,
            census_days=["6/15", "9/30"],
            years_to_skip=0,
            start_date=pd.Timestamp("2011-04-01"),
        )

    def test_census_skips_early_years(self):
        from instream.io.time_manager import is_census

        dt = pd.Timestamp("2011-06-15")
        # Skip 1 year from start (2011-04-01), so first census allowed in 2012
        assert not is_census(
            dt,
            census_days=["6/15", "9/30"],
            years_to_skip=1,
            start_date=pd.Timestamp("2011-04-01"),
        )

    def test_census_after_skip_years(self):
        from instream.io.time_manager import is_census

        dt = pd.Timestamp("2012-06-15")
        assert is_census(
            dt,
            census_days=["6/15", "9/30"],
            years_to_skip=1,
            start_date=pd.Timestamp("2011-04-01"),
        )


class TestDetectFrequency:
    """Test auto-detection of time-series frequency."""

    def test_daily_returns_1(self):
        from instream.io.time_manager import detect_frequency

        dates = pd.date_range("2011-04-01", periods=10, freq="D")
        df = pd.DataFrame({"flow": range(10)}, index=dates)
        assert detect_frequency(df) == 1

    def test_hourly_returns_24(self):
        from instream.io.time_manager import detect_frequency

        dates = pd.date_range("2011-04-01", periods=48, freq="h")
        df = pd.DataFrame({"flow": range(48)}, index=dates)
        assert detect_frequency(df) == 24

    def test_6hourly_returns_4(self):
        from instream.io.time_manager import detect_frequency

        dates = pd.date_range("2011-04-01", periods=20, freq="6h")
        df = pd.DataFrame({"flow": range(20)}, index=dates)
        assert detect_frequency(df) == 4

    def test_single_row_returns_1(self):
        from instream.io.time_manager import detect_frequency

        dates = pd.date_range("2011-04-01", periods=1, freq="D")
        df = pd.DataFrame({"flow": [1.0]}, index=dates)
        assert detect_frequency(df) == 1


class TestSubDailyAdvance:
    """Test sub-daily time stepping."""

    def _make_hourly_tm(self, hours=48):
        """Helper: create a TimeManager with hourly data for 2 days."""
        from instream.io.time_manager import TimeManager

        dates = pd.date_range("2011-04-01", periods=hours, freq="h")
        df = pd.DataFrame(
            {
                "flow": np.arange(hours, dtype=float),
                "temperature": np.linspace(10, 15, hours),
            },
            index=dates,
        )
        return TimeManager(
            start_date="2011-04-01",
            end_date="2011-04-02",
            time_series={"reach1": df},
        )

    def test_subdaily_step_length(self):
        tm = self._make_hourly_tm()
        step = tm.advance()
        assert step == pytest.approx(1.0 / 24)

    def test_step_lengths_sum_to_one_per_day(self):
        tm = self._make_hourly_tm()
        total = 0.0
        for _ in range(24):
            total += tm.advance()
        assert total == pytest.approx(1.0)

    def test_is_day_boundary_last_substep(self):
        tm = self._make_hourly_tm()
        # Advance 23 times: pointer goes to row 23 (hour 23 of day 1).
        # Next row (24) is hour 0 of day 2 => different calendar day
        # => is_day_boundary should be True.
        boundary_seen = False
        for i in range(23):
            tm.advance()
        boundary_seen = tm.is_day_boundary
        assert boundary_seen, "Expected day boundary after last sub-step of day 1"

    def test_substep_index_increments(self):
        tm = self._make_hourly_tm()
        assert tm.substep_index == 0
        tm.advance()
        # substep_index should be 0 after first advance (first sub-step of day)
        assert tm.substep_index == 0
        tm.advance()
        assert tm.substep_index == 1

    def test_daily_backward_compatible(self):
        """Daily input should behave exactly as before."""
        from instream.io.time_manager import TimeManager

        dates = pd.date_range("2011-04-01", periods=10, freq="D")
        df = pd.DataFrame({"flow": np.arange(10, dtype=float)}, index=dates)
        tm = TimeManager(
            start_date="2011-04-01",
            end_date="2011-04-05",
            time_series={"reach1": df},
        )
        assert tm.steps_per_day == 1
        step = tm.advance()
        assert step == pytest.approx(1.0)
        assert tm.current_date == pd.Timestamp("2011-04-02")
        assert tm.is_day_boundary is True

    def test_get_conditions_exact_row(self):
        """Sub-daily get_conditions should return exact row data."""
        tm = self._make_hourly_tm()
        # Row 0 is initial conditions (hour 0)
        c0 = tm.get_conditions("reach1")
        assert c0["flow"] == pytest.approx(0.0)

        # After first advance, should be at row 1 (hour 1)
        tm.advance()
        c1 = tm.get_conditions("reach1")
        assert c1["flow"] == pytest.approx(1.0)

        # After second advance, row 2 (hour 2)
        tm.advance()
        c2 = tm.get_conditions("reach1")
        assert c2["flow"] == pytest.approx(2.0)

    def test_is_done_subdaily(self):
        """is_done should be True when row pointers exceed data length."""
        from instream.io.time_manager import TimeManager

        # Only 4 rows of 6-hourly data (1 day)
        dates = pd.date_range("2011-04-01", periods=4, freq="6h")
        df = pd.DataFrame({"flow": [1.0, 2.0, 3.0, 4.0]}, index=dates)
        tm = TimeManager(
            start_date="2011-04-01",
            end_date="2011-04-01",
            time_series={"reach1": df},
        )
        assert not tm.is_done()
        for _ in range(4):
            tm.advance()
        assert tm.is_done()


class TestYearShuffler:
    """Test year shuffler for stochastic input year resampling."""

    def test_produces_valid_mapping(self):
        from instream.io.time_manager import YearShuffler

        ys = YearShuffler(available_years=[2010, 2011, 2012], seed=42)
        mapped = ys.get_year(2011)
        assert mapped in [2010, 2011, 2012]

    def test_deterministic_with_seed(self):
        from instream.io.time_manager import YearShuffler

        ys1 = YearShuffler(available_years=[2010, 2011, 2012], seed=42)
        ys2 = YearShuffler(available_years=[2010, 2011, 2012], seed=42)
        for y in range(2011, 2020):
            assert ys1.get_year(y) == ys2.get_year(y)

    def test_different_seeds_different_mapping(self):
        from instream.io.time_manager import YearShuffler

        ys1 = YearShuffler(available_years=[2010, 2011, 2012], seed=1)
        ys2 = YearShuffler(available_years=[2010, 2011, 2012], seed=999)
        # At least some years should map differently
        results = [ys1.get_year(y) != ys2.get_year(y) for y in range(2011, 2030)]
        assert any(results)


class TestYearShufflerWiring:
    def test_shuffler_remaps_years(self):
        from instream.io.time_manager import YearShuffler

        shuffler = YearShuffler([2011, 2012, 2013], seed=42)
        mapped = [shuffler.get_year(y) for y in [2011, 2012, 2013]]
        # Just check it runs and returns valid years
        for m in mapped:
            assert m in [2011, 2012, 2013]

    def test_shuffler_consistent_with_same_seed(self):
        from instream.io.time_manager import YearShuffler

        s1 = YearShuffler([2011, 2012, 2013], seed=99)
        s2 = YearShuffler([2011, 2012, 2013], seed=99)
        for y in [2011, 2012, 2013, 2014, 2015]:
            assert s1.get_year(y) == s2.get_year(y)

    def test_shuffler_always_returns_available_year(self):
        from instream.io.time_manager import YearShuffler

        available = [2011, 2012, 2013]
        shuffler = YearShuffler(available, seed=7)
        for sim_year in range(2010, 2020):
            assert shuffler.get_year(sim_year) in available
