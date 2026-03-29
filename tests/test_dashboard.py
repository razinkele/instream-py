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
        # Skip cells-init message
        first = metrics_q.get_nowait()
        assert first.get("type") == "cells"
        snap = metrics_q.get_nowait()
        required = {
            "type",
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
            "positions",
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
        # Skip cells-init message
        metrics_q.get_nowait()
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
            if snap.get("type") == "cells":
                continue
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
            if snap.get("type") == "cells":
                continue
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


class TestDashboardE2E:
    """End-to-end: run simulation, verify dashboard data collected and payload works."""

    def test_full_simulation_populates_queue(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-06-30"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(
            config,
            overrides,
            progress_queue=None,
            metrics_queue=metrics_q,
            data_dir=DATA_DIR,
        )

        all_messages = []
        while not metrics_q.empty():
            all_messages.append(metrics_q.get_nowait())

        # Filter out cells-init message
        snapshots = [m for m in all_messages if m.get("type") != "cells"]

        # ~91 days → ~91 snapshots
        assert len(snapshots) > 80
        # First and last dates should span the range
        assert snapshots[0]["date"] < snapshots[-1]["date"]
        # Population tracked throughout
        assert all(sum(s["alive"].values()) >= 0 for s in snapshots)

        # Payload builder works on the full dataset
        from modules.dashboard_panel import build_dashboard_payload

        payload = build_dashboard_payload(snapshots, 0, reset=True)
        assert payload is not None
        assert payload["reset"] is True
        assert "species" in payload
        assert len(payload["traces"]["population"]["x"][0]) == len(snapshots)
        assert len(payload["traces"]["mortality"]["y"][0]) == len(snapshots)
        assert len(payload["traces"]["feeding"]["y"]) == 4
        assert len(payload["traces"]["redds"]["y"][0]) == len(snapshots)


class TestMetricsSnapshotV2:
    """Verify cells-init message, type fields, and positions in metrics queue."""

    def _run_short_sim(self):
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
        messages = []
        while not metrics_q.empty():
            messages.append(metrics_q.get_nowait())
        return messages

    def test_snapshot_has_type_field(self):
        messages = self._run_short_sim()
        assert len(messages) >= 2, "Expected at least cells + 1 snapshot"
        assert messages[0]["type"] == "cells"
        for msg in messages[1:]:
            assert msg["type"] == "snapshot", (
                f"Expected type 'snapshot', got {msg.get('type')}"
            )

    def test_cells_init_has_geodataframe(self):
        import geopandas as gpd

        messages = self._run_short_sim()
        cells_msg = messages[0]
        assert cells_msg["type"] == "cells"
        gdf = cells_msg["cells_geojson"]
        assert isinstance(gdf, gpd.GeoDataFrame)
        # Should be in WGS84
        assert gdf.crs is None or gdf.crs.to_epsg() == 4326

    def test_snapshot_has_positions(self):
        messages = self._run_short_sim()
        snapshots = [m for m in messages if m["type"] == "snapshot"]
        assert len(snapshots) > 0
        snap = snapshots[0]
        assert "positions" in snap
        pos = snap["positions"]
        assert set(pos.keys()) == {"fish_idx", "cell_idx", "species_idx", "activity"}
        # All arrays should be the same length (parallel arrays)
        lengths = [len(pos[k]) for k in pos]
        assert len(set(lengths)) == 1, (
            f"Parallel arrays have different lengths: {lengths}"
        )

    def test_dashboard_payload_ignores_cells_message(self):
        from modules.dashboard_panel import build_dashboard_payload

        messages = self._run_short_sim()
        # Filter out cells messages (as dashboard_panel does)
        snapshot_data = [d for d in messages if d.get("type") != "cells"]
        assert all(d["type"] == "snapshot" for d in snapshot_data)
        payload = build_dashboard_payload(snapshot_data, 0, reset=True)
        assert payload is not None
        assert payload["reset"] is True
        assert "species" in payload
