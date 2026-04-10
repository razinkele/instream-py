# Live Movement Map Tab — Design Spec

**Date:** 2026-03-28
**Status:** Approved (revised after architect + code review round 1)

## Overview

A dedicated "Movement" tab that shows fish positions growing in real-time on a deck.gl map during the simulation run. Uses the existing `metrics_queue` + `_dashboard_data` infrastructure. The TripsLayer rebuilds every 2 seconds with accumulated trajectory data.

## Architecture

### Data Flow

```
Simulation Thread                Shiny Main Thread              Browser
────────────────                 ────────────────                ───────
metrics_queue.put({              _poll_dashboard() [every 2s]
  type: "cells",                   drains into _dashboard_data
  cells_geojson: {...}             ↓
})  ← first message only         movement_server (async effect):
                                   reads dashboard_data_rv()
metrics_queue.put({                detects "cells" init message → build centroid LUT
  type: "snapshot",                detects "snapshot" messages → accumulate positions
  ...existing dashboard fields,    builds format_trips + trips_layer
  "positions": {                   await widget.update (cells once)
    fish_idx: [...],               await widget.partial_update (trips only)
    cell_idx: [...],                                            deck.gl map:
    species_idx: [...],                                         cell polygons (sent once)
    activity: [...]                                             TripsLayer (growing trails)
  }
})
```

### Key design decisions

- **Reuses `metrics_queue` and `_dashboard_data`** — no new queue or polling effect. The movement panel reads the same `dashboard_data_rv` as the dashboard panel.
- **Cells delivered as first queue message** — `run_simulation()` pushes a `{"type": "cells", "cells_geojson": gdf}` message into `metrics_queue` immediately after model construction, BEFORE the step loop. This provides the centroid LUT and cell polygon layer during the run, without waiting for `results_rv`.
- **Cells sent once via `widget.update()`, trips via `partial_update()`** — cell polygons are sent once when the cells init message is received. Subsequent 2-second updates use `widget.partial_update()` with only the trips layer, avoiding re-serializing cell geometry (~500KB+ for large meshes).
- **Trajectory accumulation happens in Python** — `movement_server` maintains a `_trajectory_history` dict (plain mutable, not reactive) mapping `fish_idx → list of [lon, lat, day_num]` waypoints. Each poll cycle, new positions from snapshots are appended to the history.
- **`format_trips()` from shiny_deckgl** handles path serialization. Paths are passed as 3-element `[lon, lat, day_num]` lists so `format_trips` uses the real timestamps (not auto-generated ones).
- **No `_tripsHeadIcons`** — the `_tripsHeadIcons` feature requires a `_tripsAnimation` RAF loop to interpolate head positions. Since we don't use `_tripsAnimation` (server drives updates), fish head sprites would never render. The growing-trail effect is the primary visual; head icons are available in the existing Spatial tab for post-hoc replay.
- **Tab-visibility gating** — `widget.update()` / `partial_update()` calls are skipped when the Movement tab is not active. When the user switches to the tab, one full rebuild is sent from accumulated `_trajectory_history`. This prevents a burst of 100+ deferred WebSocket messages replaying on tab open.

## Data Changes to simulation.py

### 1. Cells init message (new)

Push immediately after model construction, before the step loop:

```python
if metrics_queue is not None:
    # Build cells GeoDataFrame with GEOMETRY ONLY (static fields).
    # Dynamic fields (depth, velocity, fish_count) are at initial/zero
    # state before the step loop — we only need geometry + reach for
    # the polygon layer on the movement map.
    cells_gdf = _build_cells_gdf(model, raw)  # raw is the parsed YAML dict, already in scope
    # Strip dynamic columns that are meaningless at pre-loop time
    keep_cols = [c for c in ["cell_id", "reach", "area", "frac_spawn"] if c in cells_gdf.columns]
    cells_gdf = cells_gdf[keep_cols + ["geometry"]]
    if cells_gdf.crs is not None and cells_gdf.crs.to_epsg() != 4326:
        cells_gdf = cells_gdf.to_crs(epsg=4326)
    metrics_queue.put({
        "type": "cells",
        "cells_geojson": cells_gdf,
    })
```

### 2. Positions field (added to existing snapshot)

Add `"positions"` to the existing metrics snapshot dict. Use **vectorized** numpy slicing (not per-fish dict comprehension):

```python
alive_idx = np.where(ts.alive)[0]
metrics_queue.put({
    "type": "snapshot",
    ...existing fields...,
    "positions": {
        "fish_idx": alive_idx.tolist(),
        "cell_idx": ts.cell_idx[alive_idx].tolist(),
        "species_idx": ts.species_idx[alive_idx].tolist(),
        "activity": ts.activity[alive_idx].tolist(),
    },
})
```

Note: existing snapshot messages must also get `"type": "snapshot"` added. The dashboard panel's `build_dashboard_payload` must be updated to ignore `"type"` fields (or filter for `type == "snapshot"` only).

### 3. day_num derivation

Each snapshot has a `"date"` field (string). `movement_server` derives `day_num` as:

```python
day_num = snapshots.index(snapshot)  # 0-based index = day offset from start
```

Or more robustly, using the first snapshot's date as epoch:

```python
from datetime import datetime
start_date = datetime.strptime(snapshots[0]["date"], "%Y-%m-%d")
day_num = (datetime.strptime(snapshot["date"], "%Y-%m-%d") - start_date).days
```

## Components

### 1. `app/modules/movement_panel.py` (new)

**UI (`movement_ui()`):**
- `ui.card` with map container
- Color mode selector: species / activity
- Status text output (idle / running / complete)

**Server (`movement_server(input, output, session, dashboard_data_rv)`):**

Parameters:
- `dashboard_data_rv`: reactive.value holding accumulated metrics snapshots (includes cells init + position snapshots)

Internal state (plain mutable, NOT reactive — avoids self-triggering loops):
- `_trajectory_history`: `dict[int, list]` — `{fish_idx: [[lon, lat, day_num], ...]}` accumulated
- `_species_map`: `dict[int, int]` — `{fish_idx: species_idx}` for coloring
- `_last_processed_idx`: `[0]` — mutable list tracking processed snapshot count
- `_centroid_lut`: `np.ndarray | None` — `(n_cells, 2)` centroid lookup in WGS84
- `_cells_gdf`: `GeoDataFrame | None` — cells for polygon layer
- `_widget`: `MapWidget | None` — created when cells arrive
- `_cells_sent`: `[False]` — tracks if initial cell layer has been pushed

**Lifecycle:**

1. **Cells init message arrives** (type == "cells" in dashboard_data_rv): extract `cells_geojson`, build `_centroid_lut` from centroids, store `_cells_gdf`. Create `MapWidget`. Push cell polygon layer via `widget.update()`. Set `_cells_sent = True`.
2. **During simulation** (type == "snapshot" messages): async effect fires when `dashboard_data_rv()` changes. Process new snapshots since `_last_processed_idx`: for each position entry, look up centroid from `_centroid_lut[cell_idx]`, append `[lon, lat, day_num]` to `_trajectory_history[fish_idx]`. Build trips via `format_trips()` and push via `widget.partial_update()`.
3. **After completion**: no more dashboard_data_rv changes → map freezes with final trails. The `"success"` state's final flush in `_poll_progress` triggers one last update.
4. **New simulation**: detect `_dashboard_data` shrinkage (`len(data) < _last_processed_idx[0]`). Clear `_trajectory_history`, `_species_map`, reset `_last_processed_idx[0] = 0`, set `_centroid_lut = None`, `_cells_sent = False`.

**Tab-visibility gating:**

Use Shiny's `input._tab_selected()` or check if the widget div exists via a JS callback. If the Movement tab is not active, skip `widget.partial_update()` but continue accumulating trajectory data. When the tab becomes active, push one full `partial_update` with all accumulated trips.

Simpler approach: always push updates. deck.gl handles hidden-tab WebSocket messages by deferring. The concern about burst replay is mitigated because `widget.update()` is called only once (cells init) and `partial_update()` messages overwrite each other (only the last trips layer state matters). The deferred queue replays in order, but since each `partial_update` replaces the trips layer entirely, the final state is correct with a brief visual flash.

**Accepted trade-off:** Skip tab-visibility gating in v1 for simplicity. If burst replay proves problematic in practice, add gating in v2.

**Paths format for `format_trips()`:**

Paths must be 3-element lists `[lon, lat, day_num]` so `format_trips` takes the `has_3d` branch and uses real timestamps:

```python
paths = list(_trajectory_history.values())  # each value is [[lon, lat, day], ...]
props = [{"species": species_order[_species_map[fid]], "color": color}
         for fid in _trajectory_history.keys()]
trips_data = format_trips(paths, loop_length=max_day + 1, properties=props)
```

**Layer construction:**

```python
trip_lyr = trips_layer("fish_movement", trips_data,
    getColor="@@=d.color",
    currentTime=max_day,      # show all segments up to current day
    trailLength=max_day + 1,  # full trail visible
    fadeTrail=True,
    widthMinPixels=2,
    # NO _tripsAnimation — server drives updates
    # NO _tripsHeadIcons — requires RAF loop we don't run
)
await widget.partial_update(session, [trip_lyr])
```

**Color modes:**
- Species: use Tab10 colormap colors, keyed by species_idx
- Activity: use activity color dict (drift=blue, search=green, hide=grey, guard=red, hold=yellow), keyed by last recorded activity

### 2. Changes to `app/simulation.py`

- Add cells init message push before step loop (inside `if metrics_queue is not None`)
- Add `"type": "snapshot"` to existing snapshot dict
- Add `"positions"` field with vectorized numpy extraction
- Existing dashboard fields unchanged

### 3. Changes to `app/app.py`

- Import `movement_ui`, `movement_server` from `modules.movement_panel`
- Add `ui.nav_panel("Movement", movement_ui("movement"))` tab (after Dashboard)
- Wire `movement_server("movement", dashboard_data_rv=_dashboard_data)`

### 4. Changes to `app/modules/dashboard_panel.py`

**REPLACE** the current `_push_updates` implementation with the version below. This adds `type == "cells"` filtering that does not exist in the current code. Filter once in `_push_updates`, pass the filtered list to `build_dashboard_payload`. Do NOT add a second filter inside `build_dashboard_payload`.

```python
@reactive.effect
async def _push_updates():
    data = dashboard_data_rv()
    if not data:
        return

    # Filter to snapshot-only (skip cells init messages)
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

`build_dashboard_payload` receives only snapshot dicts — no internal filtering needed.

**IMPORTANT: Atomic deployment.** The `_push_updates` filtering change and the `simulation.py` cells init push MUST be committed together. If `simulation.py` emits `type: "cells"` messages but `_push_updates` hasn't been updated to filter them, `build_dashboard_payload` will crash with `KeyError: 'alive'` on the cells message.

## `_fit_bounds_zoom` Utility

Duplicate the 10-line `_fit_bounds_zoom()` function from `spatial_panel.py` into `movement_panel.py`. Avoids cross-module imports between panel modules.

## State Transitions

| State | Movement Map shows |
|---|---|
| **idle** (no sim run) | "Run a simulation to see fish movement" |
| **running, no cells yet** | "Waiting for simulation data..." |
| **running, cells available** | Map with cell polygons + growing fish trails |
| **success** | Map frozen with final trails (final flush from `_poll_progress` triggers one last update) |
| **error** | Map frozen at last update |

**Note:** The `"success"` transition in `_poll_progress` does a final drain of `_metrics_q` into `_dashboard_data`, which triggers `movement_server`'s async effect one final time. The movement server must NOT gate on `_sim_state == "running"` — it should always process new data regardless of sim state.

## Performance Considerations

- `_trajectory_history` grows throughout the run. `fish_idx` values are **slot indices** into fixed-size `trout_state` arrays — dead fish slots may be reused for newly emerged fry. When a `fish_idx` reappears after a gap (not seen in the previous snapshot), `movement_server` must **start a new path** for that index (clear the old trajectory for that `fish_idx`). Detection: track a `_last_seen_day` dict mapping `fish_idx → last day_num`. If a fish_idx appears with `day_num > _last_seen_day[fish_idx] + 1`, treat it as a new fish and reset its path. This prevents dead-then-reused slots from producing visually broken trails.
- Memory estimate: ~500 concurrent fish × 365 days × 3 floats = ~2MB for a 1-year run. Dead fish paths are cleared on slot reuse. Acceptable.
- `format_trips()` + `widget.partial_update()` every 2 seconds: serializes the trips dataset. For 500 fish × 100 days = ~50K waypoints × ~60 bytes JSON = ~3MB. Acceptable for 2-second intervals.
- Cell polygons sent once via `widget.update()` — NOT re-sent on each cycle.
- Positions field in snapshot: vectorized numpy extraction (~4 array slices + `.tolist()`) instead of per-fish dict comprehension. Fast for 500 fish.

## Testing

- Unit test: metrics snapshot has `"type"` and `"positions"` keys
- Unit test: positions field has parallel arrays (fish_idx, cell_idx, species_idx, activity) of equal length
- Unit test: cells init message has `"type": "cells"` and `"cells_geojson"` GeoDataFrame
- Unit test: trajectory accumulation from position snapshots → 3-element path lists
- Unit test: `_push_updates` filters out `type == "cells"` messages before calling `build_dashboard_payload`
- E2E test: run 14-day simulation with metrics_queue, verify cells init + position snapshots collected

## File Changes Summary

| File | Change |
|---|---|
| `app/modules/movement_panel.py` | **New** — UI + async server + trajectory accumulation |
| `app/simulation.py` | Add cells init message, add `"type"` to snapshots, add `"positions"` field |
| `app/app.py` | Add import, tab, wire movement_server |
| `app/modules/dashboard_panel.py` | Replace `_push_updates` with filtering version (filter `type == "cells"` before calling `build_dashboard_payload`) |
| `tests/test_dashboard.py` | Add tests for positions, cells init, type field |
