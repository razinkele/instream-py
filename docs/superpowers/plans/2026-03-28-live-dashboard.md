# Live Simulation Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Dashboard" tab that displays live Population, Mortality, Feeding, and Redds metrics during a simulation run, updating every 2 seconds via flicker-free Plotly.extendTraces().

**Architecture:** Simulation thread pushes daily snapshots to a `metrics_queue`. Shiny main thread drains it every 2s into a `reactive.value` list. A dashboard module watches that list and sends incremental updates to the browser via `session.send_custom_message()`. JS handler calls `Plotly.react()` on reset or `Plotly.extendTraces()` to append points.

**Tech Stack:** Shiny for Python, Plotly.js (CDN already loaded), queue.Queue for thread-safe messaging.

**Spec:** `docs/superpowers/specs/2026-03-28-live-dashboard-design.md`

**Run tests:** `conda run -n shiny python -m pytest tests/ -v`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/simulation.py` | Modify | Add `metrics_queue` param, init `prev_alive_total`, push snapshots |
| `app/modules/dashboard_panel.py` | Create | Dashboard UI (KPIs + chart divs) + async server (payload builder + send) |
| `app/app.py` | Modify | Add `_metrics_q`, `_dashboard_data`, `_poll_dashboard`, drain protocol, wire module |
| `tests/test_dashboard.py` | Create | Unit tests for metrics snapshot, payload builder, activity accounting |

---

### Task 1: Add metrics_queue to simulation.py

**Files:**
- Modify: `app/simulation.py:17` (signature)
- Modify: `app/simulation.py:69` (init prev_alive_total)
- Modify: `app/simulation.py:103-131` (push snapshot at day boundary)
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing test for metrics snapshot**

Create `tests/test_dashboard.py`:

```python
"""Tests for live dashboard metrics collection and payload building."""

import queue
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "app"))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = PROJECT_ROOT / "configs"


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
        run_simulation(config, overrides, progress_queue=None,
                       metrics_queue=metrics_q)

        snapshots = []
        while not metrics_q.empty():
            snapshots.append(metrics_q.get_nowait())

        assert len(snapshots) > 0, "metrics_queue should have snapshots"

    def test_snapshot_has_required_keys(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-05"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(config, overrides, progress_queue=None,
                       metrics_queue=metrics_q)

        snap = metrics_q.get_nowait()
        required = {"date", "alive", "deaths_today", "drift_count",
                    "search_count", "hide_count", "other_count",
                    "redd_count", "eggs_total", "emerged_cumulative"}
        assert required.issubset(snap.keys()), f"Missing keys: {required - snap.keys()}"

    def test_alive_is_dict_by_species(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-05"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(config, overrides, progress_queue=None,
                       metrics_queue=metrics_q)

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
        run_simulation(config, overrides, progress_queue=None,
                       metrics_queue=metrics_q)

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
        run_simulation(config, overrides, progress_queue=None,
                       metrics_queue=metrics_q)

        while not metrics_q.empty():
            snap = metrics_q.get_nowait()
            alive_total = sum(snap["alive"].values())
            activity_total = (snap["drift_count"] + snap["search_count"]
                              + snap["hide_count"] + snap["other_count"])
            assert activity_total == alive_total, (
                f"Activity {activity_total} != alive {alive_total} on {snap['date']}"
            )

    def test_none_metrics_queue_still_works(self):
        """Simulation should work without metrics_queue (backward compat)."""
        from simulation import run_simulation

        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-05"},
            "performance": {"backend": "numpy"},
        }
        result = run_simulation(config, overrides, progress_queue=None,
                                metrics_queue=None)
        assert result["summary"]["final_date"] != ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_dashboard.py -v --tb=short`
Expected: FAIL — `run_simulation() got an unexpected keyword argument 'metrics_queue'`

- [ ] **Step 3: Update run_simulation signature and add metrics collection**

In `app/simulation.py`, change the signature at line 17:

```python
def run_simulation(config_path, overrides=None, progress_queue=None, metrics_queue=None, data_dir=None):
```

Add `prev_alive_total` init after line 69 (after `emerged_total = 0`):

```python
        prev_alive_total = int(model.trout_state.alive.sum())
```

Add metrics snapshot push inside the day-boundary block (after the `for sp_idx, sp_name` loop that builds `daily_records`, around line 131), still inside the `if model.time_manager.is_day_boundary` block:

```python
                # --- Dashboard metrics snapshot ---
                if metrics_queue is not None:
                    alive_now = int(ts.alive.sum())
                    activity = ts.activity[ts.alive]
                    metrics_queue.put({
                        "date": current_date,
                        "alive": {sp: int((ts.alive & (ts.species_idx == si)).sum())
                                  for si, sp in enumerate(model.species_order)},
                        "deaths_today": max(prev_alive_total - alive_now, 0),
                        "drift_count": int((activity == 0).sum()),
                        "search_count": int((activity == 1).sum()),
                        "hide_count": int((activity == 2).sum()),
                        "other_count": int(((activity == 3) | (activity == 4)).sum()),
                        "redd_count": int(rs.alive.sum()),
                        "eggs_total": int(rs.num_eggs[rs.alive].sum()) if rs.alive.any() else 0,
                        "emerged_cumulative": emerged_total,
                    })
                    prev_alive_total = alive_now
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n shiny python -m pytest tests/test_dashboard.py -v --tb=short`
Expected: All 6 tests PASS

- [ ] **Step 5: Run full test suite to verify no regression**

Run: `conda run -n shiny python -m pytest tests/ -q --tb=line`
Expected: 617+ passed, 0 failed

- [ ] **Step 6: Commit**

```bash
git add app/simulation.py tests/test_dashboard.py
git commit -m "feat: add metrics_queue to simulation for live dashboard data"
```

---

### Task 2: Create dashboard_panel.py (UI + server)

**Files:**
- Create: `app/modules/dashboard_panel.py`
- Test: `tests/test_dashboard.py` (add payload builder tests)

- [ ] **Step 1: Write failing test for payload builder**

Append to `tests/test_dashboard.py`:

```python
class TestPayloadBuilder:
    """Verify dashboard payload structure for Plotly.extendTraces."""

    def test_build_payload_reset(self):
        from modules.dashboard_panel import build_dashboard_payload

        snapshots = [{
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
        }]
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
            {"date": "2011-04-02", "alive": {"sp": 100}, "deaths_today": 5,
             "drift_count": 60, "search_count": 30, "hide_count": 8,
             "other_count": 2, "redd_count": 3, "eggs_total": 1500,
             "emerged_cumulative": 0},
            {"date": "2011-04-03", "alive": {"sp": 95}, "deaths_today": 3,
             "drift_count": 55, "search_count": 35, "hide_count": 4,
             "other_count": 1, "redd_count": 4, "eggs_total": 2000,
             "emerged_cumulative": 0},
        ]
        payload = build_dashboard_payload(snapshots, 1, reset=False)

        assert payload["reset"] is False
        # Only the new snapshot (index 1) should be in traces
        assert len(payload["traces"]["population"]["x"][0]) == 1
        assert payload["traces"]["population"]["x"][0][0] == "2011-04-03"
        assert payload["traces"]["mortality"]["y"][0][0] == 3

    def test_build_payload_zero_alive_no_crash(self):
        from modules.dashboard_panel import build_dashboard_payload

        snapshots = [{
            "date": "2011-04-02",
            "alive": {"sp": 0},
            "deaths_today": 10,
            "drift_count": 0, "search_count": 0, "hide_count": 0,
            "other_count": 0, "redd_count": 0, "eggs_total": 0,
            "emerged_cumulative": 0,
        }]
        payload = build_dashboard_payload(snapshots, 0, reset=True)
        assert payload["kpi"]["drift_pct"] == 0
        assert payload["kpi"]["alive"] == 0

    def test_traces_shape_for_extend(self):
        """extendTraces needs {x: [[...]], y: [[...]]} with inner lists."""
        from modules.dashboard_panel import build_dashboard_payload

        snapshots = [
            {"date": "2011-04-02", "alive": {"a": 50, "b": 50},
             "deaths_today": 2, "drift_count": 40, "search_count": 30,
             "hide_count": 15, "other_count": 15, "redd_count": 1,
             "eggs_total": 500, "emerged_cumulative": 0},
        ]
        payload = build_dashboard_payload(snapshots, 0, reset=False)

        pop = payload["traces"]["population"]
        # 2 species → 2 inner lists for x and y
        assert len(pop["x"]) == 2
        assert len(pop["y"]) == 2
        # Each inner list has 1 data point
        assert len(pop["x"][0]) == 1
        assert len(pop["y"][0]) == 1

        # Feeding has 4 traces (drift, search, hide, other)
        feed = payload["traces"]["feeding"]
        assert len(feed["y"]) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_dashboard.py::TestPayloadBuilder -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.dashboard_panel'`

- [ ] **Step 3: Create dashboard_panel.py**

Create `app/modules/dashboard_panel.py`:

```python
"""Dashboard panel — live simulation metrics with KPI cards and Plotly charts."""

from shiny import module, reactive, render, ui


def build_dashboard_payload(snapshots, start_idx, reset=False):
    """Build a payload dict for the JS dashboard_update handler.

    Parameters
    ----------
    snapshots : list[dict]
        Accumulated metrics snapshots from the simulation.
    start_idx : int
        Index of the first new snapshot to include in traces.
    reset : bool
        If True, include species list and all data from start_idx for Plotly.react().
        If False, include only new data since start_idx for Plotly.extendTraces().
    """
    if not snapshots:
        return None

    new = snapshots[start_idx:]
    if not new:
        return None

    latest = new[-1]
    alive_total = sum(latest["alive"].values())
    denom = max(alive_total, 1)

    species = list(snapshots[0]["alive"].keys())
    n_species = len(species)

    # Build trace data arrays: {x: [[...], [...]], y: [[...], [...]]}
    dates = [s["date"] for s in new]

    pop_x = [list(dates) for _ in range(n_species)]
    pop_y = [[s["alive"].get(sp, 0) for s in new] for sp in species]

    mort_x = [list(dates)]
    mort_y = [[s["deaths_today"] for s in new]]

    feed_x = [list(dates) for _ in range(4)]
    feed_y = [
        [s["drift_count"] for s in new],
        [s["search_count"] for s in new],
        [s["hide_count"] for s in new],
        [s["other_count"] for s in new],
    ]

    redd_x = [list(dates)]
    redd_y = [[s["redd_count"] for s in new]]

    payload = {
        "kpi": {
            "alive": alive_total,
            "deaths": latest["deaths_today"],
            "drift_pct": int(latest["drift_count"] / denom * 100),
            "search_pct": int(latest["search_count"] / denom * 100),
            "other_pct": int(latest["other_count"] / denom * 100),
            "redds": latest["redd_count"],
            "eggs": latest["eggs_total"],
        },
        "reset": reset,
        "traces": {
            "population": {"x": pop_x, "y": pop_y},
            "mortality": {"x": mort_x, "y": mort_y},
            "feeding": {"x": feed_x, "y": feed_y},
            "redds": {"x": redd_x, "y": redd_y},
        },
    }
    if reset:
        payload["species"] = species

    return payload


# ---- JS handler (inline script for ui.tags.head) ----

DASHBOARD_JS = """
function safeExtend(divId, update, indices) {
    var div = document.getElementById(divId);
    if (!div || !div.data || div.data.length === 0) return;
    Plotly.extendTraces(divId, update, indices);
}

Shiny.addCustomMessageHandler('dashboard_update', function(msg) {
    var el;
    el = document.getElementById('kpi-alive');
    if (el) el.textContent = msg.kpi.alive;
    el = document.getElementById('kpi-deaths');
    if (el) el.textContent = msg.kpi.deaths;
    el = document.getElementById('kpi-feeding');
    if (el) el.textContent = 'drift ' + msg.kpi.drift_pct + '% / search ' + msg.kpi.search_pct + '%';
    el = document.getElementById('kpi-redds');
    if (el) el.textContent = msg.kpi.redds + ' (' + msg.kpi.eggs + ' eggs)';

    if (msg.reset) {
        var popTraces = msg.species.map(function(sp, i) {
            return {x: msg.traces.population.x[i], y: msg.traces.population.y[i],
                    name: sp, mode: 'lines'};
        });
        Plotly.react('dash-pop-chart', popTraces, {
            title: 'Population', template: 'plotly_white',
            margin: {t:30, b:30, l:50, r:20}, hovermode: 'x unified'
        });
        Plotly.react('dash-mort-chart',
            [{x: msg.traces.mortality.x[0], y: msg.traces.mortality.y[0],
              name: 'Deaths', mode: 'lines', line: {color: '#c64'}}],
            {title: 'Daily Mortality', template: 'plotly_white',
             margin: {t:30, b:30, l:50, r:20}});
        var feedNames = ['Drift', 'Search', 'Hide', 'Other'];
        var feedColors = ['#48c', '#8c4', '#999', '#888'];
        var feedTraces = feedNames.map(function(n, i) {
            return {x: msg.traces.feeding.x[i], y: msg.traces.feeding.y[i],
                    name: n, stackgroup: 'feed', line: {color: feedColors[i]}};
        });
        Plotly.react('dash-feed-chart', feedTraces, {
            title: 'Feeding Activity', template: 'plotly_white',
            margin: {t:30, b:30, l:50, r:20}});
        Plotly.react('dash-redd-chart',
            [{x: msg.traces.redds.x[0], y: msg.traces.redds.y[0],
              name: 'Active Redds', mode: 'lines', line: {color: '#a48'}}],
            {title: 'Redds', template: 'plotly_white',
             margin: {t:30, b:30, l:50, r:20}});
    } else {
        var popIdx = msg.traces.population.x.map(function(_, i) { return i; });
        safeExtend('dash-pop-chart', msg.traces.population, popIdx);
        safeExtend('dash-mort-chart', msg.traces.mortality, [0]);
        safeExtend('dash-feed-chart', msg.traces.feeding, [0, 1, 2, 3]);
        safeExtend('dash-redd-chart', msg.traces.redds, [0]);
    }
});
"""


@module.ui
def dashboard_ui():
    return ui.card(
        ui.card_header("Live Dashboard"),
        ui.layout_columns(
            ui.div(
                ui.tags.div("ALIVE", style="font-size:11px;color:#666;text-transform:uppercase;"),
                ui.tags.div("—", id="kpi-alive", style="font-size:24px;font-weight:bold;color:#2a6;"),
                style="background:#e8f4e8;border-radius:6px;padding:12px;text-align:center;",
            ),
            ui.div(
                ui.tags.div("DEATHS TODAY", style="font-size:11px;color:#666;text-transform:uppercase;"),
                ui.tags.div("—", id="kpi-deaths", style="font-size:24px;font-weight:bold;color:#c64;"),
                style="background:#fef3e0;border-radius:6px;padding:12px;text-align:center;",
            ),
            ui.div(
                ui.tags.div("FEEDING", style="font-size:11px;color:#666;text-transform:uppercase;"),
                ui.tags.div("—", id="kpi-feeding", style="font-size:24px;font-weight:bold;color:#36a;"),
                style="background:#e8eef8;border-radius:6px;padding:12px;text-align:center;",
            ),
            ui.div(
                ui.tags.div("REDDS", style="font-size:11px;color:#666;text-transform:uppercase;"),
                ui.tags.div("—", id="kpi-redds", style="font-size:24px;font-weight:bold;color:#a48;"),
                style="background:#f8e8f0;border-radius:6px;padding:12px;text-align:center;",
            ),
            col_widths=(3, 3, 3, 3),
        ),
        ui.tags.div(id="dash-pop-chart", style="width:100%;height:200px;"),
        ui.tags.div(id="dash-mort-chart", style="width:100%;height:150px;"),
        ui.tags.div(id="dash-feed-chart", style="width:100%;height:150px;"),
        ui.tags.div(id="dash-redd-chart", style="width:100%;height:150px;"),
        ui.output_ui("dash_status"),
    )


@module.server
def dashboard_server(input, output, session, dashboard_data_rv):
    _last_sent_idx = [0]

    @reactive.effect
    async def _push_updates():
        data = dashboard_data_rv()
        if not data:
            return

        current_len = len(data)
        if current_len < _last_sent_idx[0]:
            # Reset detected (new simulation started, list was cleared and refilled)
            reset = True
            start = 0
        elif current_len > _last_sent_idx[0]:
            reset = _last_sent_idx[0] == 0
            start = _last_sent_idx[0]
        else:
            return  # No new data

        payload = build_dashboard_payload(data, start, reset=reset)
        if payload is not None:
            await session.send_custom_message("dashboard_update", payload)
        _last_sent_idx[0] = current_len

    @output
    @render.ui
    def dash_status():
        data = dashboard_data_rv()
        if not data:
            return ui.p("Run a simulation to see live metrics.",
                        style="text-align:center;color:#888;padding:40px;")
        return ui.TagList()
```

- [ ] **Step 4: Run payload builder tests**

Run: `conda run -n shiny python -m pytest tests/test_dashboard.py::TestPayloadBuilder -v --tb=short`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/dashboard_panel.py tests/test_dashboard.py
git commit -m "feat: add dashboard panel module with KPI cards and Plotly charts"
```

---

### Task 3: Wire dashboard into app.py

**Files:**
- Modify: `app/app.py:15-22` (imports)
- Modify: `app/app.py:120-130` (add tab + JS head)
- Modify: `app/app.py:134-146` (add queues, update run_sim_task)
- Modify: `app/app.py:185-194` (drain in _launch)
- Modify: `app/app.py:229-232` (drain in _poll_progress success)
- Modify: `app/app.py:270-276` (update run_test_task)
- Add: `_poll_dashboard` effect
- Add: wire `dashboard_server`

- [ ] **Step 1: Add imports**

In `app/app.py`, after the existing module imports (line 22), add:

```python
from modules.dashboard_panel import dashboard_ui, dashboard_server, DASHBOARD_JS
```

- [ ] **Step 2: Add Dashboard tab and JS handler to UI**

In `app/app.py`, add the JS handler to `ui.tags.head()` (around line 114):

```python
    ui.tags.head(
        ui.tags.script(
            src="https://cdn.plot.ly/plotly-2.35.2.min.js",
            charset="utf-8",
        ),
        ui.tags.script(DASHBOARD_JS),
    ),
```

Add the Dashboard tab to `ui.navset_tab()` (around line 120):

```python
        ui.nav_panel("Dashboard", dashboard_ui("dash")),
```

- [ ] **Step 3: Add reactive state and update run_sim_task**

In `app/app.py server()`, after `_progress_q` declaration (line 136), add:

```python
    _metrics_q = queue.Queue()
    _dashboard_data = reactive.value([])
```

Update `run_sim_task` body to use lambda (line 140-146):

```python
    @reactive.extended_task
    async def run_sim_task(config_path, overrides):
        data_dir = _resolve_data_dir(config_path)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: run_simulation(
                config_path, overrides, _progress_q, _metrics_q, data_dir
            )
        )
```

- [ ] **Step 4: Add drain to _launch**

In `_launch()`, after draining `_progress_q` (line 190), add:

```python
            while not _metrics_q.empty():
                try:
                    _metrics_q.get_nowait()
                except Exception:
                    break
            _dashboard_data.set([])
```

- [ ] **Step 5: Add final drain to _poll_progress success path**

In `_poll_progress`, before `_sim_state.set("success")` (line 229), add:

```python
            # Drain remaining dashboard metrics before closing
            with reactive.isolate():
                _dash_current = _dashboard_data.get()
            _dash_remaining = []
            try:
                while True:
                    _dash_remaining.append(_metrics_q.get_nowait())
            except Exception:
                pass
            if _dash_remaining:
                _dashboard_data.set(_dash_current + _dash_remaining)
```

- [ ] **Step 6: Add _poll_dashboard effect**

After `_poll_progress`, add:

```python
    @reactive.effect
    def _poll_dashboard():
        if _sim_state.get() != "running":
            return
        if _active_task() != "sim":
            return
        reactive.invalidate_later(2)
        with reactive.isolate():
            current = _dashboard_data.get()
        new_items = []
        try:
            while True:
                new_items.append(_metrics_q.get_nowait())
        except queue.Empty:
            pass
        if new_items:
            _dashboard_data.set(current + new_items)
```

- [ ] **Step 7: Update run_test_task to use lambda**

Update `run_test_task` body (around line 270):

```python
    @reactive.extended_task
    async def run_test_task(config_path, overrides):
        data_dir = _resolve_data_dir(config_path)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: run_simulation(
                config_path, overrides, None, None, data_dir
            )
        )
```

- [ ] **Step 8: Wire dashboard_server**

After `spatial_server("spatial", ...)` (line 262), add:

```python
    dashboard_server("dash", dashboard_data_rv=_dashboard_data)
```

- [ ] **Step 9: Verify app loads**

Run: `cd app && conda run -n shiny python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 10: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -q --tb=line`
Expected: 620+ passed, 0 failed

- [ ] **Step 11: Commit**

```bash
git add app/app.py
git commit -m "feat: wire live dashboard into app — poll, drain, tab"
```

---

### Task 4: E2E manual verification

**Files:** None (manual test)

- [ ] **Step 1: Start the app**

```bash
cd app && conda run -n shiny python -m shiny run app.py --port 18905 --host 127.0.0.1 --reload
```

- [ ] **Step 2: Verify in browser**

Open `http://127.0.0.1:18905`:
1. Click "Dashboard" tab — should show "Run a simulation to see live metrics"
2. Set dates to 2011-04-01 → 2011-06-30, click "Run Simulation"
3. Switch to Dashboard tab while running — KPIs should update every 2s, charts should grow
4. Wait for completion — charts should freeze, KPIs show final values
5. Run again — charts should reset and start fresh

- [ ] **Step 3: Stop the app**

Kill the server process.

---

### Task 5: Add E2E test

**Files:**
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add E2E test**

Append to `tests/test_dashboard.py`:

```python
class TestDashboardE2E:
    """End-to-end test: run simulation, verify dashboard data is collected."""

    def test_full_simulation_populates_queue(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-06-30"},
            "performance": {"backend": "numpy"},
        }
        result = run_simulation(config, overrides, progress_queue=None,
                                metrics_queue=metrics_q)

        snapshots = []
        while not metrics_q.empty():
            snapshots.append(metrics_q.get_nowait())

        # ~91 days → ~91 snapshots
        assert len(snapshots) > 80
        # First and last dates should span the range
        assert snapshots[0]["date"] < snapshots[-1]["date"]
        # Population should be tracked
        assert all(sum(s["alive"].values()) >= 0 for s in snapshots)
        # Payload builder should work on the full dataset
        from modules.dashboard_panel import build_dashboard_payload
        payload = build_dashboard_payload(snapshots, 0, reset=True)
        assert payload is not None
        assert len(payload["traces"]["population"]["x"][0]) == len(snapshots)
```

- [ ] **Step 2: Run the test**

Run: `conda run -n shiny python -m pytest tests/test_dashboard.py::TestDashboardE2E -v --tb=short`
Expected: PASS

- [ ] **Step 3: Run full suite one final time**

Run: `conda run -n shiny python -m pytest tests/ -q --tb=line`
Expected: 625+ passed, 0 failed

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard.py
git commit -m "test: add E2E test for dashboard metrics collection"
```
