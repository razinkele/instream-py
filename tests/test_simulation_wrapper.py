"""Tests for the simulation wrapper."""

import sys
from pathlib import Path

import pandas as pd

# Add app/ to path so we can import simulation
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "app"))

from simulation import run_simulation


class TestRunSimulation:
    """Integration tests using Example A fixture data."""

    CONFIG = str(PROJECT_ROOT / "configs" / "example_a.yaml")
    DATA_DIR = str(PROJECT_ROOT / "tests" / "fixtures" / "example_a")

    def test_returns_results_dict(self):
        """run_simulation returns a dict with all required keys."""
        results = run_simulation(
            self.CONFIG,
            overrides={"simulation": {"end_date": "2011-04-10"}},
            data_dir=self.DATA_DIR,
        )
        assert isinstance(results, dict)
        for key in (
            "daily",
            "environment",
            "cells",
            "snapshots",
            "redds",
            "config",
            "summary",
        ):
            assert key in results, f"Missing key: {key}"

    def test_daily_dataframe_columns(self):
        """daily DataFrame has expected columns and per-species rows."""
        results = run_simulation(
            self.CONFIG,
            overrides={"simulation": {"end_date": "2011-04-10"}},
            data_dir=self.DATA_DIR,
        )
        df = results["daily"]
        assert isinstance(df, pd.DataFrame)
        for col in (
            "date",
            "species",
            "alive",
            "mean_length",
            "mean_weight",
            "redd_count",
            "eggs_total",
            "emerged_cumulative",
            "outmigrants_cumulative",
        ):
            assert col in df.columns, f"Missing column: {col}"
        assert len(df) > 0

    def test_environment_dataframe(self):
        """environment DataFrame has date, reach, temperature, flow, turbidity."""
        results = run_simulation(
            self.CONFIG,
            overrides={"simulation": {"end_date": "2011-04-10"}},
            data_dir=self.DATA_DIR,
        )
        df = results["environment"]
        assert isinstance(df, pd.DataFrame)
        for col in ("date", "reach", "temperature", "flow", "turbidity"):
            assert col in df.columns, f"Missing column: {col}"

    def test_cells_geodataframe(self):
        """cells GeoDataFrame has geometry and expected columns."""
        import geopandas as gpd

        results = run_simulation(
            self.CONFIG,
            overrides={"simulation": {"end_date": "2011-04-10"}},
            data_dir=self.DATA_DIR,
        )
        gdf = results["cells"]
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert "geometry" in gdf.columns
        for col in (
            "cell_id",
            "reach",
            "depth",
            "velocity",
            "fish_count",
            "frac_spawn",
        ):
            assert col in gdf.columns, f"Missing column: {col}"

    def test_progress_queue(self):
        """Progress updates are sent to queue when provided."""
        import queue

        q = queue.Queue()
        run_simulation(
            self.CONFIG,
            overrides={"simulation": {"end_date": "2011-04-10"}},
            progress_queue=q,
            data_dir=self.DATA_DIR,
        )
        # Should have received at least one progress update
        assert not q.empty()
        step, total = q.get()
        assert isinstance(step, int)
        assert isinstance(total, int)
        assert total > 0

    def test_summary_dict(self):
        """summary contains expected keys."""
        results = run_simulation(
            self.CONFIG,
            overrides={"simulation": {"end_date": "2011-04-10"}},
            data_dir=self.DATA_DIR,
        )
        s = results["summary"]
        for key in ("final_date", "fish_alive", "redds_alive", "total_outmigrants"):
            assert key in s
