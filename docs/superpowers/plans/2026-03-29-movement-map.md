# Live Movement Map — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Movement" tab showing fish trails growing in real-time on a deck.gl map during the simulation run, using the existing metrics_queue infrastructure.

**Architecture:** Simulation thread pushes a cells-init message + per-day position snapshots into `metrics_queue`. The movement panel accumulates positions into trajectory paths and rebuilds the TripsLayer via `partial_update()` every 2 seconds. Cells are sent once; trips grow as data arrives.

**Tech Stack:** Shiny for Python, shiny_deckgl (MapWidget, geojson_layer, trips_layer, format_trips), GeoDataFrame, NumPy

**Spec:** `docs/superpowers/specs/2026-03-28-movement-map-design.md`

**Run tests:** `conda run -n shiny python -m pytest tests/ -v`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/simulation.py` | Modify | Add cells-init message, add `"type"` + `"positions"` to snapshots |
| `app/modules/dashboard_panel.py` | Modify | Filter `type == "cells"` in `_push_updates` (atomic with simulation.py change) |
| `app/modules/movement_panel.py` | Create | Movement map UI + async server + trajectory accumulation |
| `app/app.py` | Modify | Import, add tab, wire movement_server |
| `tests/test_dashboard.py` | Modify | Add tests for type field, positions, cells-init message |

---

### Task 1: Add cells-init message + type/positions to simulation.py, update dashboard_panel filtering (ATOMIC)

These two changes MUST be committed together — emitting `type: "cells"` without the dashboard filter causes a `KeyError: 'alive'` crash.

**Files:**
- Modify: `app/simulation.py:73` (insert cells init AFTER this line), `app/simulation.py:139-162` (add type + positions to snapshot)
- Modify: `app/modules/dashboard_panel.py:200-219` (replace `_push_updates` with filtering version)
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests for type field, positions, and cells init**

Append to `tests/test_dashboard.py`:

```python
class TestMetricsSnapshotV2:
    """Tests for v2 snapshot fields: type, positions, cells init."""

    def test_snapshot_has_type_field(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-05"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(config, overrides, progress_queue=None,
                       metrics_queue=metrics_q, data_dir=DATA_DIR)

        messages = []
        while not metrics_q.empty():
            messages.append(metrics_q.get_nowait())

        # First message should be cells init
        assert messages[0]["type"] == "cells"
        # Remaining should be snapshots
        for msg in messages[1:]:
            assert msg["type"] == "snapshot"

    def test_cells_init_has_geodataframe(self):
        import geopandas as gpd
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-05"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(config, overrides, progress_queue=None,
                       metrics_queue=metrics_q, data_dir=DATA_DIR)

        cells_msg = metrics_q.get_nowait()
        assert cells_msg["type"] == "cells"
        assert isinstance(cells_msg["cells_geojson"], gpd.GeoDataFrame)
        gdf = cells_msg["cells_geojson"]
        assert "geometry" in gdf.columns
        # Should be in WGS84
        assert gdf.crs is None or gdf.crs.to_epsg() == 4326

    def test_snapshot_has_positions(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-05"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(config, overrides, progress_queue=None,
                       metrics_queue=metrics_q, data_dir=DATA_DIR)

        # Skip cells init
        metrics_q.get_nowait()
        snap = metrics_q.get_nowait()
        pos = snap["positions"]
        assert "fish_idx" in pos
        assert "cell_idx" in pos
        assert "species_idx" in pos
        assert "activity" in pos
        # Parallel arrays of equal length
        n = len(pos["fish_idx"])
        assert len(pos["cell_idx"]) == n
        assert len(pos["species_idx"]) == n
        assert len(pos["activity"]) == n
        assert n > 0  # should have alive fish

    def test_dashboard_payload_ignores_cells_message(self):
        from modules.dashboard_panel import build_dashboard_payload

        mixed = [
            {"type": "cells", "cells_geojson": "dummy"},
            {"type": "snapshot", "date": "2011-04-02",
             "alive": {"sp": 100}, "deaths_today": 5,
             "drift_count": 60, "search_count": 30,
             "hide_count": 8, "other_count": 2,
             "redd_count": 3, "eggs_total": 1500,
             "emerged_cumulative": 0,
             "positions": {"fish_idx": [], "cell_idx": [],
                           "species_idx": [], "activity": []}},
        ]
        # Filter as _push_updates would
        snapshot_data = [d for d in mixed if d.get("type") != "cells"]
        payload = build_dashboard_payload(snapshot_data, 0, reset=True)
        assert payload is not None
        assert payload["kpi"]["alive"] == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n shiny python -m pytest tests/test_dashboard.py::TestMetricsSnapshotV2 -v --tb=short`
Expected: FAIL — no `"type"` key in snapshot

- [ ] **Step 3: Update simulation.py — add cells init + type + positions**

In `app/simulation.py`, after line 73 (`prev_alive_total = ...`), before the census day parsing, add:

```python
        # --- Push cells init message for movement map ---
        if metrics_queue is not None:
            _init_cells = _build_cells_gdf(model, raw)
            keep = [c for c in ["cell_id", "reach", "area", "frac_spawn"]
                    if c in _init_cells.columns]
            _init_cells = _init_cells[keep + ["geometry"]]
            if _init_cells.crs is not None and _init_cells.crs.to_epsg() != 4326:
                _init_cells = _init_cells.to_crs(epsg=4326)
            metrics_queue.put({"type": "cells", "cells_geojson": _init_cells})
```

In the existing metrics snapshot push (line 143), add `"type": "snapshot"` and `"positions"`:

Change the `metrics_queue.put({...})` block to:

```python
                    alive_idx = np.where(ts.alive)[0]
                    metrics_queue.put(
                        {
                            "type": "snapshot",
                            "date": current_date,
                            "alive": {
                                sp: int((ts.alive & (ts.species_idx == si)).sum())
                                for si, sp in enumerate(model.species_order)
                            },
                            "deaths_today": max(prev_alive_total - alive_now, 0),
                            "drift_count": int((activity == 0).sum()),
                            "search_count": int((activity == 1).sum()),
                            "hide_count": int((activity == 2).sum()),
                            "other_count": int(
                                ((activity == 3) | (activity == 4)).sum()
                            ),
                            "redd_count": _redd_count,
                            "eggs_total": _eggs_total,
                            "emerged_cumulative": emerged_total,
                            "positions": {
                                "fish_idx": alive_idx.tolist(),
                                "cell_idx": ts.cell_idx[alive_idx].tolist(),
                                "species_idx": ts.species_idx[alive_idx].tolist(),
                                "activity": ts.activity[alive_idx].tolist(),
                            },
                        }
                    )
```

- [ ] **Step 4: Update dashboard_panel.py — filter cells messages in _push_updates**

In `app/modules/dashboard_panel.py`, replace lines 200-219 (the `_push_updates` effect) with:

```python
    @reactive.effect
    async def _push_updates():
        data = dashboard_data_rv()
        if not data:
            return

        snapshot_data = [d for d in data if d.get("type") != "cells"]
        current_len = len(snapshot_data)

        if current_len < _last_sent_idx[0]:
            reset = True
            start = 0
        elif current_len > _last_sent_idx[0]:
            reset = _last_sent_idx[0] == 0
            start = _last_sent_idx[0]
        else:
            return

        payload = build_dashboard_payload(snapshot_data, start, reset=reset)
        if payload is not None:
            await session.send_custom_message("dashboard_update", payload)
        _last_sent_idx[0] = current_len
```

- [ ] **Step 5: Run tests**

Run: `conda run -n shiny python -m pytest tests/test_dashboard.py -v --tb=short`
Expected: All tests pass (existing 11 + 4 new = 15)

- [ ] **Step 6: Run full suite**

Run: `conda run -n shiny python -m pytest tests/ -q --tb=line`
Expected: 630+ passed, 0 failed

- [ ] **Step 7: Commit (atomic — both files together)**

```bash
git add app/simulation.py app/modules/dashboard_panel.py tests/test_dashboard.py
git commit -m "feat: add cells-init message + positions to metrics queue, filter in dashboard"
```

---

### Task 2: Create movement_panel.py

**Files:**
- Create: `app/modules/movement_panel.py`

- [ ] **Step 1: Create the movement panel module**

Create `app/modules/movement_panel.py`:

```python
"""Movement panel — live fish movement map during simulation."""

import math
import logging
from datetime import datetime

import numpy as np
from shiny import module, reactive, render, ui

from shiny_deckgl import MapWidget, geojson_layer, trips_layer
from shiny_deckgl.ibm import format_trips

logger = logging.getLogger(__name__)

BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

_TAB10 = [
    [31, 119, 180, 220], [255, 127, 14, 220], [44, 160, 44, 220],
    [214, 39, 40, 220], [148, 103, 189, 220], [140, 86, 75, 220],
    [227, 119, 194, 220], [127, 127, 127, 220], [188, 189, 34, 220],
    [23, 190, 207, 220],
]
_ACTIVITY_COLORS = {
    0: [66, 133, 244, 220],   # drift
    1: [52, 168, 83, 220],    # search
    2: [154, 160, 166, 220],  # hide
    3: [234, 67, 53, 220],    # guard
    4: [251, 188, 4, 220],    # hold
}


def _fit_bounds_zoom(bounds, map_width_px=800, map_height_px=600):
    """Compute zoom level fitting [minx, miny, maxx, maxy] bounds."""
    minx, miny, maxx, maxy = bounds
    lng_span = max(maxx - minx, 1e-6)
    lat_span = max(maxy - miny, 1e-6)
    zoom_lng = math.log2(map_width_px * 360 / (256 * lng_span)) if lng_span > 0 else 20
    lat_rad = math.radians((miny + maxy) / 2)
    zoom_lat = (
        math.log2(map_height_px * 360 / (256 * lat_span / math.cos(lat_rad)))
        if lat_span > 0 else 20
    )
    zoom = min(zoom_lng, zoom_lat) - 0.5
    return max(8, min(20, zoom))


@module.ui
def movement_ui():
    return ui.card(
        ui.card_header("Live Movement Map"),
        ui.layout_columns(
            ui.input_select("color_mode", "Color by:",
                            choices={"species": "Species", "activity": "Activity"}),
            col_widths=(4,),
        ),
        ui.output_ui("map_container"),
        ui.output_ui("status_text"),
        full_screen=True,
        height="100%",
        style="min-height: 600px;",
    )


@module.server
def movement_server(input, output, session, dashboard_data_rv):
    # ALL state is plain mutable — NOT reactive (avoids self-triggering loops)
    _trajectory_history = {}   # {fish_idx: [[lon, lat, day], ...]}
    _species_map = {}          # {fish_idx: species_idx}
    _activity_map = {}         # {fish_idx: last_activity_code} for activity coloring
    _last_seen_day = {}        # {fish_idx: last day_num} for slot-reuse detection
    _last_processed_idx = [0]
    _centroid_lut = [None]     # mutable container for np.ndarray
    _cells_gdf = [None]
    _widget = [None]           # plain mutable — NOT reactive.value
    _cells_sent = [False]
    _species_order = [[]]
    _start_date = [None]

    # Use a reactive.value to signal map_container to re-render when widget is ready
    _widget_version = reactive.value(0)

    @output
    @render.ui
    def map_container():
        """Reactively render map widget or placeholder."""
        _widget_version()  # take dependency — re-renders when widget is created
        if _widget[0] is not None:
            return _widget[0].ui(height="100%")
        data = dashboard_data_rv()
        if not data:
            return ui.p("Run a simulation to see fish movement.",
                        style="text-align:center;color:#888;padding:60px;")
        return ui.p("Waiting for simulation data...",
                    style="text-align:center;color:#888;padding:40px;")

    @output
    @render.ui
    def status_text():
        data = dashboard_data_rv()
        if not data:
            return ui.p("Idle", style="color:#888;text-align:center;")
        snapshots = [d for d in data if d.get("type") == "snapshot"]
        if not snapshots:
            return ui.p("Waiting for data...", style="color:#888;text-align:center;")
        return ui.p(
            "Day {} — {} fish tracked".format(
                snapshots[-1]["date"],
                len(_trajectory_history),
            ),
            style="color:#555;text-align:center;",
        )

    @reactive.effect
    async def _process_data():
        data = dashboard_data_rv()
        if not data:
            return

        # Reset detection: data shrank (new simulation started)
        total_len = len(data)
        if total_len < _last_processed_idx[0]:
            _trajectory_history.clear()
            _species_map.clear()
            _activity_map.clear()
            _last_seen_day.clear()
            _last_processed_idx[0] = 0
            _centroid_lut[0] = None
            _cells_gdf[0] = None
            _cells_sent[0] = False
            _start_date[0] = None
            _widget[0] = None

        # Process new messages since last index
        new_messages = data[_last_processed_idx[0]:]
        if not new_messages:
            return
        _last_processed_idx[0] = total_len

        try:
            for msg in new_messages:
                if msg.get("type") == "cells":
                    _cells_gdf[0] = msg["cells_geojson"]
                    centroids = _cells_gdf[0].geometry.centroid
                    _centroid_lut[0] = np.column_stack([centroids.x, centroids.y])
                    _species_order[0] = []
                    # Create widget now (inside _process_data, not map_container)
                    gdf = _cells_gdf[0]
                    bounds = gdf.total_bounds
                    center_lon = (bounds[0] + bounds[2]) / 2
                    center_lat = (bounds[1] + bounds[3]) / 2
                    zoom = _fit_bounds_zoom(bounds)
                    _widget[0] = MapWidget(
                        "movement_map",
                        view_state={
                            "longitude": center_lon,
                            "latitude": center_lat,
                            "zoom": zoom,
                        },
                        style=BASEMAP_LIGHT,
                        tooltip={
                            "html": "<b>{cell_id}</b>",
                            "style": {"backgroundColor": "#fff", "color": "#333",
                                      "fontSize": "12px", "border": "1px solid #ccc"},
                        },
                    )
                    _cells_sent[0] = False
                    _widget_version.set(_widget_version() + 1)  # trigger map_container re-render

                elif msg.get("type") == "snapshot" and _centroid_lut[0] is not None:
                    pos = msg["positions"]
                    date_str = msg["date"]

                    if _start_date[0] is None:
                        _start_date[0] = date_str
                    dt_start = datetime.strptime(_start_date[0], "%Y-%m-%d")
                    dt_now = datetime.strptime(date_str, "%Y-%m-%d")
                    day_num = (dt_now - dt_start).days

                    if not _species_order[0]:
                        _species_order[0] = list(msg["alive"].keys())

                    for i in range(len(pos["fish_idx"])):
                        fid = pos["fish_idx"][i]
                        cid = pos["cell_idx"][i]
                        sid = pos["species_idx"][i]
                        act = pos["activity"][i]

                        if cid >= len(_centroid_lut[0]):
                            continue

                        # Slot-reuse detection: gap > 1 day means slot was recycled
                        if fid in _last_seen_day and day_num > _last_seen_day[fid] + 1:
                            _trajectory_history[fid] = []

                        lon, lat = _centroid_lut[0][cid]
                        if fid not in _trajectory_history:
                            _trajectory_history[fid] = []
                        _trajectory_history[fid].append([float(lon), float(lat), day_num])
                        _species_map[fid] = sid
                        _activity_map[fid] = act
                        _last_seen_day[fid] = day_num

            # Send layers if widget exists and we have trajectory data
            widget = _widget[0]
            if widget is not None and _trajectory_history:
                # Send cells once
                if not _cells_sent[0] and _cells_gdf[0] is not None:
                    cells_layer = geojson_layer(
                        "movement_cells", _cells_gdf[0],
                        getFillColor=[200, 200, 200, 80],
                        getLineColor=[120, 120, 120, 150],
                        lineWidthMinPixels=1,
                        pickable=True,
                    )
                    await widget.update(session, [cells_layer])
                    _cells_sent[0] = True

                # Build trips from accumulated history
                color_mode = "species"
                try:
                    color_mode = input.color_mode()
                except Exception:
                    pass

                paths = []
                props = []
                for fid, path in _trajectory_history.items():
                    if len(path) < 2:
                        continue
                    paths.append(path)  # 3-element [lon, lat, day_num] lists
                    sid = _species_map.get(fid, 0)
                    if color_mode == "activity":
                        act = _activity_map.get(fid, 0)
                        color = _ACTIVITY_COLORS.get(act, [127, 127, 127, 220])
                    else:
                        color = _TAB10[sid % len(_TAB10)]
                    sp_name = (_species_order[0][sid]
                               if sid < len(_species_order[0])
                               else "species_{}".format(sid))
                    props.append({"species": sp_name, "color": color})

                if paths:
                    max_day = max(p[-1][2] for p in paths)
                    trips_data = format_trips(
                        paths, loop_length=max_day + 1, properties=props
                    )
                    trip_lyr = trips_layer(
                        "fish_movement", trips_data,
                        getColor="@@=d.color",
                        currentTime=max_day,
                        trailLength=max_day + 1,
                        fadeTrail=True,
                        widthMinPixels=2,
                    )
                    await widget.partial_update(session, [trip_lyr])

        except Exception as e:
            if "SilentException" in type(e).__name__:
                return
            logger.exception("Error processing movement data")
```

- [ ] **Step 2: Verify module imports**

Run: `cd app && conda run -n shiny python -c "from modules.movement_panel import movement_ui, movement_server; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/modules/movement_panel.py
git commit -m "feat: add movement panel module with live trajectory map"
```

---

### Task 3: Wire movement panel into app.py

**Files:**
- Modify: `app/app.py:23` (imports)
- Modify: `app/app.py:123-131` (add tab)
- Modify: `app/app.py:308` (wire server)

- [ ] **Step 1: Add import**

In `app/app.py`, after line 23 (dashboard import), add:

```python
from modules.movement_panel import movement_ui, movement_server
```

- [ ] **Step 2: Add Movement tab**

In `app/app.py`, in the `ui.navset_tab(...)` block (line 123-131), add after the Dashboard tab:

```python
        ui.nav_panel("Movement", movement_ui("movement")),
```

- [ ] **Step 3: Wire movement_server**

After the `dashboard_server("dash", ...)` line (around line 308), add:

```python
    movement_server("movement", dashboard_data_rv=_dashboard_data)
```

- [ ] **Step 4: Verify app loads**

Run: `cd app && conda run -n shiny python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -q --tb=line`
Expected: 635+ passed, 0 failed

- [ ] **Step 6: Commit**

```bash
git add app/app.py
git commit -m "feat: wire movement map tab into app"
```

---

### Task 4: Manual verification

- [ ] **Step 1: Start app**

```bash
cd app && conda run -n shiny python -m shiny run app.py --port 18910 --host 127.0.0.1
```

- [ ] **Step 2: Test in browser**

Open `http://127.0.0.1:18910`:
1. Click "Movement" tab — should show "Run a simulation to see fish movement"
2. Set dates 2011-04-01 → 2011-06-30, click "Run Simulation"
3. Switch to Movement tab — should show cell polygons appearing, then trails growing
4. Switch between Dashboard and Movement tabs — both should update
5. Wait for completion — trails freeze with final state
6. Run again — trails reset and start growing fresh

- [ ] **Step 3: Stop app**

Kill the server process.

---

### Task 5: Add movement-specific E2E test

**Files:**
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add trajectory accumulation test**

Append to `tests/test_dashboard.py`:

```python
class TestMovementData:
    """Test that movement panel data pipeline works end-to-end."""

    def test_cells_init_plus_positions_collected(self):
        from simulation import run_simulation

        metrics_q = queue.Queue()
        config = str(CONFIGS_DIR / "example_a.yaml")
        overrides = {
            "simulation": {"start_date": "2011-04-01", "end_date": "2011-04-15"},
            "performance": {"backend": "numpy"},
        }
        run_simulation(config, overrides, progress_queue=None,
                       metrics_queue=metrics_q, data_dir=DATA_DIR)

        messages = []
        while not metrics_q.empty():
            messages.append(metrics_q.get_nowait())

        # First message is cells init
        cells_msg = messages[0]
        assert cells_msg["type"] == "cells"
        assert len(cells_msg["cells_geojson"]) > 0

        # Build centroid LUT from cells
        import numpy as np
        gdf = cells_msg["cells_geojson"]
        centroids = gdf.geometry.centroid
        centroid_lut = np.column_stack([centroids.x, centroids.y])

        # Accumulate trajectories from snapshots
        snapshots = [m for m in messages[1:] if m["type"] == "snapshot"]
        assert len(snapshots) > 10  # ~14 days

        trajectory_history = {}
        for day_idx, snap in enumerate(snapshots):
            pos = snap["positions"]
            for i in range(len(pos["fish_idx"])):
                fid = pos["fish_idx"][i]
                cid = pos["cell_idx"][i]
                if cid < len(centroid_lut):
                    lon, lat = centroid_lut[cid]
                    if fid not in trajectory_history:
                        trajectory_history[fid] = []
                    trajectory_history[fid].append([float(lon), float(lat), day_idx])

        # Should have trajectories for multiple fish
        assert len(trajectory_history) > 10
        # Each fish should have multiple waypoints
        for fid, path in trajectory_history.items():
            assert len(path) >= 1
        # Paths should have valid WGS84 coordinates
        for path in trajectory_history.values():
            for lon, lat, _ in path:
                assert -180 <= lon <= 180
                assert -90 <= lat <= 90
```

- [ ] **Step 2: Run the test**

Run: `conda run -n shiny python -m pytest tests/test_dashboard.py::TestMovementData -v --tb=short`
Expected: PASS

- [ ] **Step 3: Run full suite**

Run: `conda run -n shiny python -m pytest tests/ -q --tb=line`
Expected: 636+ passed, 0 failed

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard.py
git commit -m "test: add movement data pipeline E2E test"
```
