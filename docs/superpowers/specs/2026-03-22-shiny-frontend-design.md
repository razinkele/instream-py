# inSTREAM-py Shiny Frontend — Design Spec

## Goal

Build a Shiny for Python web application that lets researchers configure, run, and interactively explore inSTREAM individual-based salmonid simulations. Deploy to laguna.ku.lt Shiny Server.

## Architecture

Modular Shiny app with one module per panel. Simulation runs in a background thread via `@reactive.extended_task` (~80s for 912-day run), with progress bar updating in real time. When complete, all panels populate from a shared results dict.

### File Structure

```
app/
  app.py                      # Entry point, layout, sidebar, tab wiring
  simulation.py                # Model runner wrapper (runs in thread pool)
  modules/
    config_panel.py            # Config selector + parameter overrides
    population_panel.py        # Fish count timeline (plotly)
    spatial_panel.py           # Cell map (shiny_deckgl)
    environment_panel.py       # Temp/flow/turbidity timeseries (plotly)
    distribution_panel.py      # Length/weight histograms (plotly)
    redd_panel.py              # Redd tracking panel (plotly)
```

### Tech Stack

- **Shiny for Python 1.6.0** — UI framework
- **shiny_deckgl 1.9.1** — spatial cell map (optimized for Shiny; import as `shiny_deckgl`, PyPI name `shiny-deckgl`)
- **plotly 6.6.0** — interactive charts (population, environment, distribution, redds)
- **shinyswatch 0.9.0** — Bootstrap theme
- **geopandas** — cell polygon handling
- **instream** — simulation engine (imported directly)

## UI Layout

### Sidebar (always visible)

| Control | Type | YAML override key |
|---------|------|-------------------|
| Config file | Dropdown + upload | — (selects base config) |
| Start date | Date picker | `simulation.start_date` |
| End date | Date picker | `simulation.end_date` |
| Species | Checkboxes | — (filter display, not config) |
| Drift concentration | Slider (log scale) | `reaches[*].drift_conc` |
| Search productivity | Slider (log scale) | `reaches[*].search_prod` |
| Shading | Slider 0–1 | `reaches[*].shading` |
| Fish predation min | Slider 0–1 | `reaches[*].fish_pred_min` |
| Terrestrial pred min | Slider 0–1 | `reaches[*].terr_pred_min` |
| Backend | Dropdown | `performance.backend` |
| Run Simulation | Action button | — |
| Progress bar | Progress | Updated every 10 steps via extended_task |

### Main Area (5 tabs)

#### 1. Population

Plotly line chart: fish alive count by species over time. X = date, Y = count. One line per species. Shows total alive, plus optional cumulative mortality/outmigrant lines.

#### 2. Spatial

shiny_deckgl map rendering cell polygons from the shapefile. Dropdown selector for coloring variable:
- Depth (cm)
- Velocity (cm/s)
- Available drift food (`available_drift`)
- Available search food (`available_search`)
- Fish density (fish per cell, end-of-simulation count)
- Spawn fraction (`frac_spawn`, static from shapefile)

Hover tooltip shows: cell ID, reach, area, selected variable value. Color scale with legend.

Note: Cell polygons are not retained by `PolygonMesh` after init. The simulation wrapper must call `gpd.read_file()` on the shapefile path directly to obtain polygon geometries. Shapefile column names (e.g., `ID_TEXT`, `REACH_NAME`, `FRACSPWN`) must be renamed to canonical names using the `gis_properties` mapping from config:
```python
gis = raw_config["spatial"]["gis_properties"]
# Case-insensitive column resolution (matching PolygonMesh behavior)
col_map = {}
for key, shp_col in gis.items():
    for actual_col in cells_gdf.columns:
        if actual_col.upper() == shp_col.upper():
            canonical = {"cell_id": "cell_id", "reach_name": "reach",
                         "area": "area", "frac_spawn": "frac_spawn"}.get(key)
            if canonical:
                col_map[actual_col] = canonical
            break
cells_gdf = cells_gdf.rename(columns=col_map)
```
Dynamic fields (depth, velocity, available_drift, available_search, fish_count) are merged from `CellState` arrays at end-of-simulation. Since `PolygonMesh` retains `cell_ids` and `frac_spawn` as properties in the same row order as the shapefile, these can also be used for alignment if needed.

Note: Fish density shown is always the end-of-simulation state. A date selector for spatial fish density is deferred to v2.

#### 3. Environment

Plotly subplots (3 rows, shared x-axis = date):
- Temperature (°C)
- Flow (m³/s)
- Turbidity (NTU)

Data sourced from `model.time_manager._time_series` after model construction (avoids re-reading CSVs and replicating path resolution). Each reach's DataFrame has DatetimeIndex (named `"Date"`) and columns `temperature`, `flow`, `turbidity`. Reset index and rename: `.reset_index().rename(columns={"Date": "date"})`. Multi-reach: one trace per reach.

#### 4. Size Distribution

Plotly histograms of fish length (cm) and weight (g) at a user-selected date. Date slider spans simulation period. Histogram updates reactively on slider change. Colored by species.

For this, the simulation wrapper stores periodic snapshots (every 30 days + census days) of fish length/weight arrays rather than every-step data. ~30 snapshots × up to 2000 fish = ~60K rows total.

#### 5. Redds

Plotly line chart: active redd count over time, total eggs, cumulative emerged fry. Table below showing individual redd details at selected date (species, cell, eggs remaining, development fraction, mortality causes).

## Data Flow

### Threading Model

**Critical:** Shiny for Python is single-threaded (asyncio event loop). An 80-second synchronous simulation would freeze the UI entirely. The simulation must run in a background thread.

**Pattern:** Use `@reactive.extended_task` (available since Shiny 0.10+). The progress queue is a session-scoped closure variable, not a task argument:

```python
import asyncio
import queue
from shiny import reactive

# In server():
_progress_q: queue.Queue = queue.Queue()

@reactive.extended_task
async def run_sim_task(config_path, overrides):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, run_simulation, config_path, overrides, _progress_q
    )
```

Progress updates flow through the thread-safe `queue.Queue`. The UI polls the queue via `reactive.invalidate_later(1)` (1-second poll interval) to update the progress bar while the simulation thread runs. The `run_sim_task.status()` reactive property (`"initial" | "running" | "success" | "error"`) drives UI state transitions.

**Error handling:** If the simulation raises an exception (e.g., `FileNotFoundError`, `ValueError` for capacity exceeded), the extended_task catches it and sets status to `"error"`. The UI displays the error via `ui.notification_show()` and panels remain in their previous state.

### Simulation Wrapper (`simulation.py`)

```python
def run_simulation(config_path, overrides, progress_queue=None):
    """Run inSTREAM simulation and collect results.

    Runs synchronously in a worker thread (called via run_in_executor).

    Args:
        config_path: Path to YAML config file
        overrides: Dict of parameter overrides from UI
        progress_queue: Optional queue.Queue for progress updates

    Returns:
        dict with keys: daily, environment, cells, snapshots, redds, config, summary
    """
```

**Important implementation notes:**
- Must NOT use `model.run()` — it has no progress hook. Instead, implement a manual step loop: `while not model.time_manager.is_done(): model.step()`. (Note: `run()` also calls `write_outputs()`, but this is a no-op when `output_dir=None`, which is the wrapper's case. The missing progress hook is the sole blocking reason.)
- Total steps: derive from the configured date range (NOT from time-series row count, which covers a wider date span than the simulation). Only available after model construction:
  ```python
  import pandas as pd
  start = pd.Timestamp(model.config.simulation.start_date)
  end = pd.Timestamp(model.config.simulation.end_date)
  total_steps = int(((end - start).days + 1) * model.steps_per_day)  # +1: end date inclusive
  ```
- Per-species aggregation (alive count, mean length/weight) must be computed by the wrapper from `trout_state.alive` and `trout_state.species_idx` arrays — the model's built-in census does not break out by species
- Cell polygons must be loaded separately via `gpd.read_file(mesh_path)` since `PolygonMesh` discards geometry after init. Static fields (`frac_spawn`) should be read from the same GeoDataFrame to ensure row-order alignment.
- Environment time series: rather than pre-reading CSVs independently (which requires replicating the model's path resolution logic), read environment data from `model.time_manager._time_series` after model construction. This dict maps reach name → DataFrame with DatetimeIndex (named `"Date"`, capital D) and columns `temperature`, `flow`, `turbidity`. To build the results environment DataFrame: `env_df = df.reset_index().rename(columns={"Date": "date"})` for each reach.
- The output system (`io/output.py`) writes to files only — the wrapper builds results from live model state, not from output files
- Redd field mapping: `ReddState` uses `num_eggs` internally; the wrapper renames this to `eggs` in the results DataFrame for display clarity

**Collects per-step:**
- Fish alive count per species (from `trout_state.alive` + `trout_state.species_idx`)
- Mean length/weight per species
- Active redd count (`redd_state.alive.sum()`), total eggs (`redd_state.num_eggs[redd_state.alive].sum()`)
- Cumulative outmigrants, emerged fry

**Collects periodically (every 30 days + census days):**
- Fish length/weight snapshot for distribution panel

**Collects once (end of simulation):**
- Final cell state (depth, velocity, `available_drift`, `available_search` from `CellState`)
- Cell polygons + static fields (separate `gpd.read_file()` call)
- Per-cell fish count (from final `trout_state.cell_idx`)
- Redd details table

### Results Dict

```python
results = {
    "daily": pd.DataFrame,
    # Columns: date, species, alive, mean_length, mean_weight,
    #          redd_count, eggs_total, emerged_cumulative, outmigrants_cumulative

    "environment": pd.DataFrame,
    # Columns: date, reach, temperature, flow, turbidity
    # Sourced from model.time_manager._time_series after construction
    # Reset DatetimeIndex ("Date") to column, rename to "date"

    "cells": gpd.GeoDataFrame,
    # Columns: cell_id, reach, geometry, area, depth, velocity,
    #          available_drift, available_search, fish_count, frac_spawn
    # geometry + frac_spawn from gpd.read_file() with case-insensitive column rename
    # depth/velocity/available_drift/available_search from CellState at final step
    # area is in m² (raw from shapefile via gpd.read_file(); no conversion needed)
    # Note: CellState.area stores cm², but the cells GDF takes area from the raw GeoDataFrame
    # fish_count is end-of-simulation only

    "snapshots": dict,
    # Keys: date strings -> pd.DataFrame with columns:
    #   fish_idx, species, length, weight, cell_idx

    "redds": pd.DataFrame,
    # Columns: date, redd_idx, species, cell_idx, eggs, frac_developed,
    #          eggs_lo_temp, eggs_hi_temp, eggs_dewatering, eggs_scour
    # Note: 'eggs' is renamed from ReddState.num_eggs

    "config": dict,
    # Parsed YAML config for display/reference

    "summary": dict,
    # final_date, fish_alive, redds_alive, total_outmigrants
}
```

### Panel Reactivity

All panels share a single `reactive.Value` holding either the results dict or `None` (initial/error state). When simulation completes, the value is set, and all panels re-render independently. No cross-panel dependencies.

The spatial panel also has its own reactive for the selected coloring variable (dropdown), which triggers only a re-color, not a full re-render.

## Parameter Override Mechanism

The UI sidebar exposes ~10 key parameters. When "Run Simulation" is clicked:

1. Read the raw YAML file as a Python dict (via `yaml.safe_load`, NOT via Pydantic `load_config`)
2. Apply overrides on the raw dict before Pydantic parsing:
   ```python
   raw['simulation']['start_date'] = override_start
   raw['simulation']['end_date'] = override_end
   raw['performance']['backend'] = override_backend
   for reach_name in raw['reaches']:
       raw['reaches'][reach_name]['drift_conc'] = override_drift
       raw['reaches'][reach_name]['search_prod'] = override_search
       raw['reaches'][reach_name]['shading'] = override_shading
       raw['reaches'][reach_name]['fish_pred_min'] = override_fish_pred
       raw['reaches'][reach_name]['terr_pred_min'] = override_terr_pred
   ```
3. Write to a temporary file:
   ```python
   tmp = tempfile.NamedTemporaryFile(suffix='.yaml', mode='w', delete=False)
   yaml.dump(raw, tmp)
   tmp.flush()
   tmp.close()  # Must close before InSTREAMModel opens it (required on Windows)
   ```
4. Pass temp config path to `InSTREAMModel(config_path=tmp.name, data_dir=original_data_dir)`
   - `data_dir` must be passed explicitly as the original config file's parent directory, since data paths in config are relative to it and `tmp.name` is in `/tmp/`
   - On the server, `data_dir` must point to `/srv/shiny-server/inSTREAMPY/data/`
5. Clean up temp file in a `finally` block (the `try` must begin immediately after `tmp.close()` to guarantee cleanup even if `InSTREAMModel.__init__` raises):
   ```python
   try:
       model = InSTREAMModel(config_path=tmp.name, data_dir=original_data_dir)
       # ... run simulation ...
   finally:
       os.unlink(tmp.name)
   ```

## Deployment

### Target

- **Server:** laguna.ku.lt
- **User:** razinka (passwordless SSH)
- **Directory:** /srv/shiny-server/inSTREAMPY
- **Permissions:** writable by razinka, readable by shiny user

### What Gets Deployed

```
/srv/shiny-server/inSTREAMPY/
  app.py                    # Shiny entry point (Shiny Server looks for this)
  simulation.py
  modules/
    config_panel.py
    population_panel.py
    spatial_panel.py
    environment_panel.py
    distribution_panel.py
    redd_panel.py
  configs/                  # Example configs
  data/                     # Fixture data for examples (from tests/fixtures/)
```

Note: `instream` package is installed on the server via `pip install -e .` from a clone of the repo, NOT rsynced. This avoids `sys.path` hacks and ensures correct dependency resolution. The deploy skill runs `pip install` on the server if needed.

### Deploy Skill (`/deploy`)

```bash
# Sync app files (exclude configs/ and data/ from --delete)
rsync -avz --delete --exclude=configs --exclude=data \
  app/ razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/

# Sync configs and data (no --delete, additive)
rsync -avz configs/ razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/configs/
rsync -avz tests/fixtures/ razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/

# Ensure permissions and restart
ssh razinka@laguna.ku.lt "chmod -R g+r /srv/shiny-server/inSTREAMPY && sudo systemctl reload shiny-server"
```

Note: `systemctl reload shiny-server` is more reliable than `touch restart.txt` for Python Shiny apps. If razinka does not have passwordless sudo for this command, fall back to `touch restart.txt`.

### Server Prerequisites

- Python 3.11+ virtual environment with `instream` package installed (`pip install -e .` from repo clone)
- Additional Python packages in the same venv: `shiny`, `shiny-deckgl`, `plotly`, `shinyswatch`, `geopandas`
- Shiny Server configured for Python apps. Minimal `shiny-server.conf` stanza:
  ```
  server {
    listen 3838;
    location /inSTREAMPY {
      python /path/to/venv/bin/python3;
      app_dir /srv/shiny-server/inSTREAMPY;
    }
  }
  ```
  The `python` directive must point to the virtualenv's Python binary (not system Python). Shiny Server will look for `app.py` in the `app_dir`.

### Dependencies

Add the `frontend` key inside the **existing** `[project.optional-dependencies]` table in `pyproject.toml` (do NOT create a duplicate section header):

```toml
frontend = [
    "shiny>=1.0",
    "shiny-deckgl>=1.9",
    "plotly>=6.0",
    "shinyswatch>=0.9",
]
```

## Out of Scope (v2)

- Scenario comparison (side-by-side runs)
- Live stepping with real-time panel updates
- Full parameter editor (all 52+ species params)
- Date selector for spatial panel (fish density over time)
- User authentication
- Result persistence / database storage
- Multi-user concurrent simulations
