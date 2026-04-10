# Live Simulation Dashboard — Design Spec

**Date:** 2026-03-28
**Status:** Approved (revised after architect + code review)

## Overview

A dedicated "Dashboard" tab in the inSTREAM Shiny app that displays live simulation metrics during the model run. Four key indicators — Population, Mortality, Feeding, and Redds — update every 2 seconds via Plotly's `extendTraces()` API for flicker-free chart growth. The tab remains visible after completion as a run summary.

## Architecture

### Data Flow

```
Simulation Thread              Shiny Main Thread              Browser
──────────────────             ──────────────────             ────────
model.step()
  ↓ (day boundary)
  metrics_queue.put({          _poll_dashboard() [every 2s]
    date, alive_by_species,      drain metrics_queue
    deaths_today,                accumulate into _dashboard_data
    activity_counts,             call _dashboard_data.set(new_list)
    redd_count, eggs, emerged     ↓
  })                           dashboard_server (async effect):
                                 reads dashboard_data_rv()
                                 builds payload
                                 await session.send_custom_message(
                                   "dashboard_update", payload)
                                                              JS handler:
                                                              → update KPI text
                                                              → Plotly.react() or
                                                                Plotly.extendTraces()
```

**Key separation:** `_poll_dashboard` in `app.py` only drains the queue into `_dashboard_data` (a `reactive.value`). `dashboard_server` in `dashboard_panel.py` watches `dashboard_data_rv()` and sends the WebSocket message via an `async def` reactive effect (required for `await session.send_custom_message()`).

### Threading Model

- `metrics_queue`: a `queue.Queue()` created in `app.py server()`, passed as keyword argument `metrics_queue=` to `run_simulation()`.
- The simulation thread calls `metrics_queue.put(snapshot_dict)` at every day boundary — lightweight, no GIL contention.
- The Shiny main thread drains `metrics_queue` via `get_nowait()` inside a `reactive.effect` with `reactive.invalidate_later(2)`.
- The drain reads `_dashboard_data` under `reactive.isolate()` to prevent a self-invalidation loop, then calls `_dashboard_data.set(current + new_items)` to trigger dependents.
- The 2-second polling interval decouples chart updates from simulation speed, preventing flicker.

### Reactive Isolation Pattern

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

## Data Collected Per Day Boundary

Collected inside `run_simulation()` at each `is_day_boundary` checkpoint, pushed to `metrics_queue`:

| Field | Source | Type |
|---|---|---|
| `date` | `time_manager.formatted_time()` | str |
| `alive` | `{species: count}` per species | dict[str, int] |
| `deaths_today` | `prev_alive_total - alive_now` (total, all causes) | int |
| `drift_count` | fish with activity == 0 | int |
| `search_count` | fish with activity == 1 | int |
| `hide_count` | fish with activity == 2 | int |
| `other_count` | fish with activity in {3, 4} (guard, hold) | int |
| `redd_count` | `int(rs.alive.sum())` | int |
| `eggs_total` | `int(rs.num_eggs[rs.alive].sum())` | int |
| `emerged_cumulative` | running total of emerged fry (already tracked). Collected for future use; not sent in v1 payload. | int |

### Mortality Tracking

**v1 approach:** Track total deaths per day as `pre_alive_total - alive_now`. Show as a single "deaths" line. Per-cause breakdown requires the model to expose mortality counters — deferred to a future iteration.

**Note on sub-daily steps:** When `steps_per_day > 1`, mortality fires on every sub-step. `deaths_today` counts cumulative deaths across all sub-steps within a calendar day, which is the correct semantic.

### Activity Accounting

Activity codes: 0=drift, 1=search, 2=hide, 3=guard, 4=hold. All five are counted so `drift_count + search_count + hide_count + other_count == alive_now`. The KPI card shows drift/search percentages; guard/hold are grouped as "other" and shown as sub-text when non-zero.

### `prev_alive_total` Initialization

`prev_alive_total` must be initialized **before the step loop**, mirroring the existing `prev_alive_redds` pattern:

```python
prev_alive_total = int(model.trout_state.alive.sum())
```

## `run_simulation()` Signature Change

Current signature:
```python
def run_simulation(config_path, overrides=None, progress_queue=None, data_dir=None):
```

New signature:
```python
def run_simulation(config_path, overrides=None, progress_queue=None, metrics_queue=None, data_dir=None):
```

**Call site updates required:**

Note: `_launch()` does NOT contain the executor call — it calls `run_sim_task(config_path, overrides)`. The executor call is INSIDE the `@reactive.extended_task` bodies. Update these:

- `run_sim_task` body (the `@reactive.extended_task`): replace the `run_in_executor` call to pass `_metrics_q`:
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
- `run_test_task` body (the other `@reactive.extended_task`): pass `None` for both queues:
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
- `_launch()` only needs: drain `_metrics_q`, call `_dashboard_data.set([])`, then `run_sim_task(config_path, overrides)` as before.

## Components

### 1. `app/modules/dashboard_panel.py`

New Shiny module.

**UI (`dashboard_ui()`):**
- KPI strip: 4 value boxes in a row (Alive, Deaths Today, Feeding Split, Redds)
- 3 chart containers: `<div id="dash-pop-chart">`, `<div id="dash-mort-chart">`, `<div id="dash-feed-chart">`
- A 4th chart container for redds: `<div id="dash-redd-chart">`
- JS handler registered in `ui.tags.head()` (NOT inside module-rendered UI) to survive Shiny WebSocket reconnection

**Server (`dashboard_server(input, output, session, dashboard_data_rv)`):**
- `async def` reactive effect watching `dashboard_data_rv()`
- Tracks `_last_sent_idx = [0]` (plain mutable list, NOT reactive.value — avoids self-triggering loop since reading it does not register a reactive dependency). When `len(dashboard_data_rv()) < _last_sent_idx[0]`, a reset occurred — send `reset=True` and set `_last_sent_idx[0] = 0`
- On change, builds payload and calls `await session.send_custom_message("dashboard_update", payload)`

**Payload field mapping (snapshot → KPI):**
The snapshot dict uses `deaths_today` but the KPI payload uses `deaths`. The builder must map:
- `snapshot["deaths_today"]` → `payload["kpi"]["deaths"]`
- `snapshot["drift_count"] / max(alive_now, 1) * 100` → `payload["kpi"]["drift_pct"]` (guard div-by-zero when all fish dead)
- `snapshot["search_count"] / max(alive_now, 1) * 100` → `payload["kpi"]["search_pct"]`
- `snapshot["other_count"] / max(alive_now, 1) * 100` → `payload["kpi"]["other_pct"]`
- `sum(snapshot["alive"].values())` → `payload["kpi"]["alive"]`
- `snapshot["redd_count"]` → `payload["kpi"]["redds"]`
- `snapshot["eggs_total"]` → `payload["kpi"]["eggs"]`

**Payload structure:**
```python
payload = {
    "kpi": {
        "alive": 847,
        "deaths": 23,
        "drift_pct": 62,
        "search_pct": 35,
        "other_pct": 3,
        "redds": 12,
        "eggs": 4200,
    },
    "reset": True,  # or False
    "species": ["Chinook-Spring"],  # only on reset, for trace initialization
    "traces": {
        "population": {
            "x": [["2011-04-15"], ["2011-04-15"]],  # one inner list per species
            "y": [[420], [427]],                      # one inner list per species
        },
        "mortality": {
            "x": [["2011-04-15"]],
            "y": [[23]],
        },
        "feeding": {
            "x": [["2011-04-15"], ["2011-04-15"], ["2011-04-15"], ["2011-04-15"]],
            "y": [[drift_count], [search_count], [hide_count], [other_count]],
        },
        "redds": {
            "x": [["2011-04-15"]],
            "y": [[12]],
        },
    },
}
```

### 2. Changes to `app/simulation.py`

Add `metrics_queue=None` parameter. At each day boundary:

```python
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

### 3. Changes to `app/app.py`

- **Declaration order matters:** declare these BEFORE any `@reactive.effect` that references them:
  - `_metrics_q = queue.Queue()` (alongside existing `_progress_q`)
  - `_dashboard_data = reactive.value([])`
- In `_launch()`: drain `_metrics_q` and reset `_dashboard_data.set([])` before starting
- Pass `_metrics_q` to `run_simulation()` via lambda in executor call
- Add `_poll_dashboard()` with `reactive.isolate()` guard (see pattern above)
- Gate on `_active_task() == "sim"` to avoid polling during test runs
- In `_poll_progress` success path: drain remaining `_metrics_q` items into `_dashboard_data` before setting `_sim_state = "success"`. Must use `reactive.isolate()` on the `_dashboard_data.get()` read to prevent adding unwanted reactive dependency:
  ```python
  with reactive.isolate():
      current = _dashboard_data.get()
  remaining = []
  try:
      while True:
          remaining.append(_metrics_q.get_nowait())
  except queue.Empty:
      pass
  if remaining:
      _dashboard_data.set(current + remaining)
  ```
- Wire `dashboard_server("dash", dashboard_data_rv=_dashboard_data)`
- Add "Dashboard" tab to `ui.navset_tab()`

### 4. JS Handler

Registered in `app_ui` via `ui.tags.head(ui.tags.script(...))` to survive reconnection.

```javascript
Shiny.addCustomMessageHandler('dashboard_update', function(msg) {
    // Update KPI numbers
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
        // New simulation — create traces from species list
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
        // Append new points — use safeExtend to guard against uninitialized divs
        var popIdx = msg.traces.population.x.map(function(_, i) { return i; });
        safeExtend('dash-pop-chart', msg.traces.population, popIdx);
        safeExtend('dash-mort-chart', msg.traces.mortality, [0]);
        safeExtend('dash-feed-chart', msg.traces.feeding, [0, 1, 2, 3]);
        safeExtend('dash-redd-chart', msg.traces.redds, [0]);
    }
});
```

**Reconnection & uninitialized-div guard:** `Plotly.extendTraces` throws on an uninitialized div. The JS handler must check whether the chart is initialized before calling `extendTraces`. **`safeExtend` must be defined in the same `<script>` block (or same `.js` file) as the `addCustomMessageHandler` call.** Do not split them across separate tags or files. The guard pattern:
```javascript
function safeExtend(divId, update, indices) {
    var div = document.getElementById(divId);
    if (!div || !div.data || div.data.length === 0) return;  // not initialized yet
    Plotly.extendTraces(divId, update, indices);
}
```
On first tab visit after a running simulation, `dashboard_server` detects the tab render and sends a `reset=True` message with all accumulated data, which uses `Plotly.react` to initialize from scratch.

## UI Layout

### KPI Strip (top)

```
┌──────────┐ ┌──────────┐ ┌──────────────────┐ ┌──────────────┐
│  ALIVE   │ │  DEATHS  │ │     FEEDING      │ │    REDDS     │
│   847    │ │ 23 today │ │ drift 62%/srch 35%│ │ 12 (4200 eggs)│
└──────────┘ └──────────┘ └──────────────────┘ └──────────────┘
```

### Charts (stacked below)

4 full-width charts (not 3 — splitting feeding and redds avoids dual-axis complexity):

1. **Population Over Time** — line chart, one trace per species (~200px)
2. **Daily Mortality** — single line, deaths per day (~150px)
3. **Feeding Activity** — stacked area: drift/search/other counts (~150px)
4. **Redds** — single line, active redd count (~150px)

All charts: `plotly_white` template, compact margins, responsive width.

## State Transitions

| State | Dashboard shows |
|---|---|
| **idle** (no sim run) | "Run a simulation to see live metrics" placeholder |
| **running** | KPIs update every 2s, charts grow with new points |
| **success** | Charts frozen with final data, KPIs show final values, "Complete" badge |
| **error** | Charts frozen at last update, error badge |

### Reset / Drain Protocol

1. **New sim starts** (`_launch`): drain `_metrics_q`, call `_dashboard_data.set([])`
2. **During run** (`_poll_dashboard`): drain queue every 2s, `_dashboard_data.set(current + new)`
3. **Sim completes** (`_poll_progress` success path): drain remaining `_metrics_q` into `_dashboard_data` before setting `_sim_state = "success"`
4. **Dashboard server** detects reset via `_last_sent_idx[0]` (plain int in mutable list): if `len(data) < _last_sent_idx[0]`, a reset occurred — send `reset=True` and set `_last_sent_idx[0] = 0`; otherwise send only new items since `_last_sent_idx[0]`

## Testing

- Unit test: metrics snapshot contains all required keys with correct types
- Unit test: `_poll_dashboard` pattern — drain queue, isolate read, set new list
- Unit test: payload builder produces correct `extendTraces` shape (`{x: [[...]], y: [[...]]}`)
- Unit test: `prev_alive_total` initialized correctly, deaths_today >= 0
- Unit test: activity counts sum to alive_now (drift + search + hide + other)
- JS test: `safeExtend` on uninitialized div (no `.data` property) returns without throwing
- E2E test: run 14-day simulation, verify dashboard KPIs show non-zero values

## File Changes Summary

| File | Change |
|---|---|
| `app/modules/dashboard_panel.py` | **New** — UI + async server + KPI layout |
| `app/static/dashboard.js` | **New** — JS handler for `dashboard_update` messages (or inline in `app_ui`) |
| `app/simulation.py` | Add `metrics_queue` parameter, init `prev_alive_total`, push snapshots at day boundary |
| `app/app.py` | Add `_metrics_q`, `_dashboard_data`, `_poll_dashboard`, drain protocol, wire module, add tab |
| `tests/test_dashboard.py` | **New** — unit tests for metrics collection, payload format, reactive pattern |
