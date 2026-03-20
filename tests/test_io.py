"""Tests for I/O readers."""
import numpy as np
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestHydraulicReader:
    """Test CSV depth/velocity table reader."""

    def test_read_depth_table_example_a_shape(self):
        from instream.io.hydraulics_reader import read_depth_table
        flows, depths = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        assert flows.shape == (26,), f"Expected 26 flows, got {flows.shape}"
        assert depths.shape == (1373, 26), f"Expected (1373,26), got {depths.shape}"

    def test_read_depth_table_example_a_first_flow(self):
        from instream.io.hydraulics_reader import read_depth_table
        flows, _ = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        np.testing.assert_allclose(flows[0], 1.42)

    def test_read_depth_table_example_a_last_flow(self):
        from instream.io.hydraulics_reader import read_depth_table
        flows, _ = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        np.testing.assert_allclose(flows[-1], 1416.0)

    def test_read_depth_table_example_a_cell_1_at_first_flow(self):
        from instream.io.hydraulics_reader import read_depth_table
        _, depths = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        # Cell 1 (index 0), flow 1.42 (index 0) — from the CSV data
        np.testing.assert_allclose(depths[0, 0], 0.029690755, rtol=1e-6)

    def test_read_depth_table_handles_comment_lines(self):
        from instream.io.hydraulics_reader import read_depth_table
        # The file has 3 comment lines at the top (starting with ; or ")
        # If comments are handled, it should load without error
        flows, depths = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        assert len(flows) > 0

    def test_read_velocity_table_example_a_shape(self):
        from instream.io.hydraulics_reader import read_velocity_table
        flows, vels = read_velocity_table(FIXTURES_DIR / "example_a" / "ExampleA-Vels.csv")
        assert flows.shape == (26,)
        assert vels.shape == (1373, 26)

    def test_read_depth_table_returns_float64(self):
        from instream.io.hydraulics_reader import read_depth_table
        flows, depths = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        assert flows.dtype == np.float64
        assert depths.dtype == np.float64

    def test_read_depth_table_example_b_downstream(self):
        from instream.io.hydraulics_reader import read_depth_table
        flows, depths = read_depth_table(FIXTURES_DIR / "example_b" / "DownstreamReach-Depths.csv")
        assert len(flows) > 0
        assert depths.shape[0] > 0  # has cells
        assert depths.shape[1] == len(flows)  # cells x flows

    def test_read_depth_table_cell_numbers_are_sequential(self):
        """Cell numbers in the CSV are 1-based integers. Verify we get all cells."""
        from instream.io.hydraulics_reader import read_depth_table
        flows, depths = read_depth_table(FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv")
        # 1373 cells numbered 1-1373 in the CSV
        assert depths.shape[0] == 1373

    def test_read_returns_cell_ids(self):
        """The reader should also return cell ID numbers for mapping to shapefiles."""
        from instream.io.hydraulics_reader import read_depth_table
        flows, depths, cell_ids = read_depth_table(
            FIXTURES_DIR / "example_a" / "ExampleA-Depths.csv",
            return_cell_ids=True
        )
        assert len(cell_ids) == 1373
        assert cell_ids[0] == "1"  # first cell ID as string

    def test_read_returns_cell_ids_example_b(self):
        """Example B has non-integer cell IDs like 'I-1'."""
        from instream.io.hydraulics_reader import read_depth_table
        flows, depths, cell_ids = read_depth_table(
            FIXTURES_DIR / "example_b" / "DownstreamReach-Depths.csv",
            return_cell_ids=True
        )
        assert cell_ids[0] == "I-1"


class TestTimeSeriesReader:
    """Test CSV time-series input reader."""

    def test_read_example_a_returns_dataframe(self):
        from instream.io.timeseries import read_time_series
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
        import pandas as pd
        assert isinstance(df, pd.DataFrame)

    def test_read_example_a_has_datetime_index(self):
        from instream.io.timeseries import read_time_series
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
        import pandas as pd
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_read_example_a_date_range(self):
        from instream.io.timeseries import read_time_series
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
        assert df.index[0].month == 10
        assert df.index[0].day == 1
        assert df.index[0].year == 2010

    def test_read_example_a_columns(self):
        from instream.io.timeseries import read_time_series
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
        assert "temperature" in df.columns
        assert "flow" in df.columns
        assert "turbidity" in df.columns

    def test_read_example_a_first_row_values(self):
        from instream.io.timeseries import read_time_series
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
        np.testing.assert_allclose(df["temperature"].iloc[0], 11.1)
        np.testing.assert_allclose(df["flow"].iloc[0], 6.37)
        np.testing.assert_allclose(df["turbidity"].iloc[0], 2.0)

    def test_read_timeseries_ignores_comment_lines(self):
        from instream.io.timeseries import read_time_series
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
        # If comments handled, we get data rows only, no errors
        assert len(df) > 100

    def test_read_example_a_row_count(self):
        from instream.io.timeseries import read_time_series
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
        # ~12 years of daily data (Oct 2010 – Oct 2022)
        assert 4000 < len(df) < 4500

    def test_check_gaps_clean_data_passes(self):
        from instream.io.timeseries import read_time_series, check_gaps
        df = read_time_series(FIXTURES_DIR / "example_a" / "ExampleA-TimeSeriesInputs.csv")
        gaps = check_gaps(df, max_gap_days=1.0)
        assert len(gaps) == 0, f"Unexpected gaps found: {gaps}"

    def test_check_gaps_detects_missing_day(self):
        from instream.io.timeseries import check_gaps
        import pandas as pd
        # Create data with a 3-day gap
        dates = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-05", "2020-01-06"])
        df = pd.DataFrame({"temperature": [10, 11, 12, 13], "flow": [1, 2, 3, 4]}, index=dates)
        gaps = check_gaps(df, max_gap_days=1.0)
        assert len(gaps) > 0  # should detect the gap between Jan 2 and Jan 5

    def test_read_example_b_downstream(self):
        from instream.io.timeseries import read_time_series
        df = read_time_series(FIXTURES_DIR / "example_b" / "DownstreamReach-TimeSeriesInput.csv")
        assert "temperature" in df.columns
        assert len(df) > 0
