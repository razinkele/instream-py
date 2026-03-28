"""Tests for live dashboard metrics collection and payload building."""

import queue
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "app"))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = PROJECT_ROOT / "configs"
DATA_DIR = str(FIXTURES_DIR / "example_a")


class TestMetricsSnapshot:
    """Verify metrics_queue receives correct snapshots during simulation."""

    def test_metrics_queue_receives_snapshots(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-10"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(
            config,
            overrides,
            progress_queue=None,
            metrics_queue=metrics_q,
            data_dir=DATA_DIR,
        )
        snapshots = []
        while not metrics_q.empty():
            snapshots.append(metrics_q.get_nowait())
        assert len(snapshots) > 0

    def test_snapshot_has_required_keys(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-05"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(
            config,
            overrides,
            progress_queue=None,
            metrics_queue=metrics_q,
            data_dir=DATA_DIR,
        )
        snap = metrics_q.get_nowait()
        required = {
            "date",
            "alive",
            "deaths_today",
            "drift_count",
            "search_count",
            "hide_count",
            "other_count",
            "redd_count",
            "eggs_total",
            "emerged_cumulative",
        }
        assert required.issubset(snap.keys()), f"Missing keys: {required - snap.keys()}"

    def test_alive_is_dict_by_species(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-05"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(
            config,
            overrides,
            progress_queue=None,
            metrics_queue=metrics_q,
            data_dir=DATA_DIR,
        )
        snap = metrics_q.get_nowait()
        assert isinstance(snap["alive"], dict)
        assert all(isinstance(v, int) for v in snap["alive"].values())

    def test_deaths_today_non_negative(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-10"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(
            config,
            overrides,
            progress_queue=None,
            metrics_queue=metrics_q,
            data_dir=DATA_DIR,
        )
        while not metrics_q.empty():
            snap = metrics_q.get_nowait()
            assert snap["deaths_today"] >= 0

    def test_activity_counts_sum_to_alive(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-10"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(
            config,
            overrides,
            progress_queue=None,
            metrics_queue=metrics_q,
            data_dir=DATA_DIR,
        )
        while not metrics_q.empty():
            snap = metrics_q.get_nowait()
            alive_total = sum(snap["alive"].values())
            activity_total = (
                snap["drift_count"]
                + snap["search_count"]
                + snap["hide_count"]
                + snap["other_count"]
            )
            assert activity_total == alive_total

    def test_none_metrics_queue_still_works(self):
        from simulation import run_simulation

        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-05"},
            "performance": {"backend": "numpy"},
        }
        result = run_simulation(
            config,
            overrides,
            progress_queue=None,
            metrics_queue=None,
            data_dir=DATA_DIR,
        )
        assert result["summary"]["final_date"] != ""
