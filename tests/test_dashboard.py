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


class TestPayloadBuilder:
    """Verify dashboard payload structure for Plotly.extendTraces."""

    def test_build_payload_reset(self):
        sys.path.insert(0, str(PROJECT_ROOT / "app"))
        from modules.dashboard_panel import build_dashboard_payload

        snapshots = [
            {
                "date": "2011-04-02",
                "alive": {"Chinook-Spring": 100},
                "deaths_today": 5,
                "drift_count": 60,
                "search_count": 30,
                "hide_count": 8,
                "other_count": 2,
                "redd_count": 3,
                "eggs_total": 1500,
                "emerged_cumulative": 0,
            }
        ]
        payload = build_dashboard_payload(snapshots, 0, reset=True)

        assert payload["reset"] is True
        assert payload["species"] == ["Chinook-Spring"]
        assert payload["kpi"]["alive"] == 100
        assert payload["kpi"]["deaths"] == 5
        assert payload["kpi"]["redds"] == 3
        assert payload["kpi"]["eggs"] == 1500
        assert payload["kpi"]["drift_pct"] == 60
        assert payload["kpi"]["search_pct"] == 30

    def test_build_payload_extend(self):
        from modules.dashboard_panel import build_dashboard_payload

        snapshots = [
            {
                "date": "2011-04-02",
                "alive": {"sp": 100},
                "deaths_today": 5,
                "drift_count": 60,
                "search_count": 30,
                "hide_count": 8,
                "other_count": 2,
                "redd_count": 3,
                "eggs_total": 1500,
                "emerged_cumulative": 0,
            },
            {
                "date": "2011-04-03",
                "alive": {"sp": 95},
                "deaths_today": 3,
                "drift_count": 55,
                "search_count": 35,
                "hide_count": 4,
                "other_count": 1,
                "redd_count": 4,
                "eggs_total": 2000,
                "emerged_cumulative": 0,
            },
        ]
        payload = build_dashboard_payload(snapshots, 1, reset=False)

        assert payload["reset"] is False
        assert len(payload["traces"]["population"]["x"][0]) == 1
        assert payload["traces"]["population"]["x"][0][0] == "2011-04-03"
        assert payload["traces"]["mortality"]["y"][0][0] == 3

    def test_build_payload_zero_alive_no_crash(self):
        from modules.dashboard_panel import build_dashboard_payload

        snapshots = [
            {
                "date": "2011-04-02",
                "alive": {"sp": 0},
                "deaths_today": 10,
                "drift_count": 0,
                "search_count": 0,
                "hide_count": 0,
                "other_count": 0,
                "redd_count": 0,
                "eggs_total": 0,
                "emerged_cumulative": 0,
            }
        ]
        payload = build_dashboard_payload(snapshots, 0, reset=True)
        assert payload["kpi"]["drift_pct"] == 0
        assert payload["kpi"]["alive"] == 0

    def test_traces_shape_for_extend(self):
        from modules.dashboard_panel import build_dashboard_payload

        snapshots = [
            {
                "date": "2011-04-02",
                "alive": {"a": 50, "b": 50},
                "deaths_today": 2,
                "drift_count": 40,
                "search_count": 30,
                "hide_count": 15,
                "other_count": 15,
                "redd_count": 1,
                "eggs_total": 500,
                "emerged_cumulative": 0,
            },
        ]
        payload = build_dashboard_payload(snapshots, 0, reset=False)

        pop = payload["traces"]["population"]
        assert len(pop["x"]) == 2
        assert len(pop["y"]) == 2
        assert len(pop["x"][0]) == 1
        assert len(pop["y"][0]) == 1

        feed = payload["traces"]["feeding"]
        assert len(feed["y"]) == 4
