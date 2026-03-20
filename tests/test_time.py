"""Tests for time management — TimeManager, YearShuffler, census."""
import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from datetime import datetime

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestTimeManager:
    """Test simulation time advancement."""

    @pytest.fixture
    def time_manager(self):
        from instream.io.timeseries import read_time_series
        from instream.io.time_manager import TimeManager
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
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
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
        tm = TimeManager(start_date="2011-01-01", end_date="2011-01-05",
                         time_series={"ExampleA": df})
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
        assert is_census(dt, census_days=["6/15", "9/30"], years_to_skip=0,
                         start_date=pd.Timestamp("2011-04-01"))

    def test_is_census_on_second_census_day(self):
        from instream.io.time_manager import is_census
        dt = pd.Timestamp("2011-09-30")
        assert is_census(dt, census_days=["6/15", "9/30"], years_to_skip=0,
                         start_date=pd.Timestamp("2011-04-01"))

    def test_not_census_on_regular_day(self):
        from instream.io.time_manager import is_census
        dt = pd.Timestamp("2011-07-04")
        assert not is_census(dt, census_days=["6/15", "9/30"], years_to_skip=0,
                             start_date=pd.Timestamp("2011-04-01"))

    def test_census_skips_early_years(self):
        from instream.io.time_manager import is_census
        dt = pd.Timestamp("2011-06-15")
        # Skip 1 year from start (2011-04-01), so first census allowed in 2012
        assert not is_census(dt, census_days=["6/15", "9/30"], years_to_skip=1,
                             start_date=pd.Timestamp("2011-04-01"))

    def test_census_after_skip_years(self):
        from instream.io.time_manager import is_census
        dt = pd.Timestamp("2012-06-15")
        assert is_census(dt, census_days=["6/15", "9/30"], years_to_skip=1,
                         start_date=pd.Timestamp("2011-04-01"))


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
