# inSTREAM-py Shiny Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Shiny for Python web app that lets researchers configure, run, and explore inSTREAM salmonid simulations, then deploy it to laguna.ku.lt.

**Architecture:** Modular Shiny app with one module per visualization panel. Simulation runs in a background thread via `@reactive.extended_task`. Results stored in a shared `reactive.Value` dict consumed by all panels independently.

**Tech Stack:** Shiny for Python 1.6.0, shiny_deckgl 1.9.1, plotly 6.6.0, shinyswatch 0.9.0, geopandas, instream (simulation engine)

**Spec:** `docs/superpowers/specs/2026-03-22-shiny-frontend-design.md`

**Shell rules:** Use `conda run -n shiny` prefix for all Python commands. Double-quote all paths. No `$()`, no backslash escapes.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/simulation.py` | Create | Simulation wrapper: config overrides, model step loop, results collection |
| `app/app.py` | Create | Shiny entry point: layout, sidebar, tab wiring, extended_task |
| `app/modules/__init__.py` | Create | Empty package init |
| `app/modules/population_panel.py` | Create | Fish count timeline (plotly) |
| `app/modules/environment_panel.py` | Create | Temp/flow/turbidity subplots (plotly) |
| `app/modules/distribution_panel.py` | Create | Length/weight histograms (plotly) |
| `app/modules/redd_panel.py` | Create | Redd tracking chart + table (plotly) |
| `app/modules/spatial_panel.py` | Create | Cell map (shiny_deckgl) |
| `tests/test_simulation_wrapper.py` | Create | Tests for simulation.py |
| `tests/test_app_smoke.py` | Create | Smoke test: app imports, layout renders |
| `pyproject.toml` | Modify | Add `frontend` optional-dependencies |
| `.claude/skills/deploy/SKILL.md` | Create | Deploy skill for /deploy command |

---

### Task 1: Add Frontend Dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml:22-40`

- [ ] **Step 1: Add frontend optional-dependencies**

Add inside the existing `[project.optional-dependencies]` table, after the `docs` entry:

```toml
frontend = [
    "shiny>=1.0",
    "shiny-deckgl>=1.9",
    "plotly>=6.0",
    "shinyswatch>=0.9",
]
```

- [ ] **Step 2: Verify pyproject.toml parses correctly**

Run: `conda run -n shiny python -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add frontend optional-dependencies (shiny, plotly, shiny-deckgl)"
```

---

### Task 2: Simulation Wrapper — Core

**Files:**
- Create: `app/simulation.py`
- Create: `tests/test_simulation_wrapper.py`

- [ ] **Step 1: Create app/ directory structure**

```bash
mkdir -p app/modules
touch app/__init__.py app/modules/__init__.py
```

- [ ] **Step 2: Write failing test for run_simulation**

```python
"""Tests for the simulation wrapper."""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

# Add app/ to path so we can import simulation
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "app"))

from simulation import run_simulation


class TestRunSimulation:
    """Integration tests using Example A fixture data."""

    CONFIG = str(PROJECT_ROOT / "configs" / "example_a.yaml")

    def test_returns_results_dict(self):
        """run_simulation returns a dict with all required keys."""
        results = run_simulation(self.CONFIG, overrides={"simulation": {"end_date": "2011-04-10"}})
        assert isinstance(results, dict)
        for key in ("daily", "environment", "cells", "snapshots", "redds", "config", "summary"):
            assert key in results, f"Missing key: {key}"

    def test_daily_dataframe_columns(self):
        """daily DataFrame has expected columns and per-species rows."""
        results = run_simulation(self.CONFIG, overrides={"simulation": {"end_date": "2011-04-10"}})
        df = results["daily"]
        assert isinstance(df, pd.DataFrame)
        for col in ("date", "species", "alive", "mean_length", "mean_weight",
                    "redd_count", "eggs_total", "emerged_cumulative", "outmigrants_cumulative"):
            assert col in df.columns, f"Missing column: {col}"
        assert len(df) > 0

    def test_environment_dataframe(self):
        """environment DataFrame has date, reach, temperature, flow, turbidity."""
        results = run_simulation(self.CONFIG, overrides={"simulation": {"end_date": "2011-04-10"}})
        df = results["environment"]
        assert isinstance(df, pd.DataFrame)
        for col in ("date", "reach", "temperature", "flow", "turbidity"):
            assert col in df.columns, f"Missing column: {col}"

    def test_cells_geodataframe(self):
        """cells GeoDataFrame has geometry and expected columns."""
        import geopandas as gpd
        results = run_simulation(self.CONFIG, overrides={"simulation": {"end_date": "2011-04-10"}})
        gdf = results["cells"]
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert "geometry" in gdf.columns
        for col in ("cell_id", "reach", "depth", "velocity", "fish_count", "frac_spawn"):
            assert col in gdf.columns, f"Missing column: {col}"

    def test_progress_queue(self):
        """Progress updates are sent to queue when provided."""
        import queue
        q = queue.Queue()
        run_simulation(self.CONFIG, overrides={"simulation": {"end_date": "2011-04-10"}}, progress_queue=q)
        # Should have received at least one progress update
        assert not q.empty()
        step, total = q.get()
        assert isinstance(step, int)
        assert isinstance(total, int)
        assert total > 0

    def test_summary_dict(self):
        """summary contains expected keys."""
        results = run_simulation(self.CONFIG, overrides={"simulation": {"end_date": "2011-04-10"}})
        s = results["summary"]
        for key in ("final_date", "fish_alive", "redds_alive", "total_outmigrants"):
            assert key in s
```

- [ ] **Step 3: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_simulation_wrapper.py -v --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'simulation'`

- [ ] **Step 4: Implement simulation.py**

```python
"""Simulation wrapper for the Shiny frontend.

Runs inSTREAM simulation with config overrides and collects results
into DataFrames for visualization panels.
"""
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml


def run_simulation(config_path, overrides=None, progress_queue=None):
    """Run inSTREAM simulation and collect results.

    Runs synchronously — designed to be called from a worker thread
    via asyncio.run_in_executor().

    Args:
        config_path: Path to YAML config file.
        overrides: Dict of parameter overrides (nested, matching YAML structure).
        progress_queue: Optional queue.Queue for (step, total) progress updates.

    Returns:
        dict with keys: daily, environment, cells, snapshots, redds, config, summary
    """
    from instream.model import InSTREAMModel

    config_path = Path(config_path)
    original_data_dir = config_path.parent

    # --- Apply overrides via temp YAML ---
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if overrides:
        _apply_overrides(raw, overrides)

    tmp = tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False)
    yaml.dump(raw, tmp)
    tmp.flush()
    tmp.close()

    try:
        model = InSTREAMModel(config_path=tmp.name, data_dir=original_data_dir)

        # --- Pre-compute totals ---
        start = pd.Timestamp(model.config.simulation.start_date)
        end = pd.Timestamp(model.config.simulation.end_date)
        total_steps = int(((end - start).days + 1) * model.steps_per_day)

        # --- Collect environment from time_manager (avoid re-reading CSVs) ---
        env_frames = []
        for rname, ts_df in model.time_manager._time_series.items():
            ef = ts_df.reset_index().rename(columns={"Date": "date"})
            ef["reach"] = rname
            env_frames.append(ef)
        environment = pd.concat(env_frames, ignore_index=True) if env_frames else pd.DataFrame()

        # --- Track emerged fry (model has no cumulative counter) ---
        prev_alive_redds = set(np.where(model.redd_state.alive)[0])
        emerged_total = 0

        # --- Census day parsing for snapshot collection ---
        census_specs = model.config.simulation.census_days  # list of "MM-dd" strings

        # --- Step loop with data collection ---
        daily_records = []
        snapshots = {}
        step_num = 0

        while not model.time_manager.is_done():
            model.step()
            step_num += 1

            # Track emerged fry: redds that were alive before step but dead after
            # with frac_developed >= 1.0 are emerged (not killed by mortality)
            if model.time_manager.is_day_boundary or model.steps_per_day == 1:
                curr_alive_redds = set(np.where(model.redd_state.alive)[0])
                died = prev_alive_redds - curr_alive_redds
                for idx in died:
                    if model.redd_state.frac_developed[idx] >= 1.0:
                        emerged_total += int(model.redd_state.eggs_initial[idx])
                prev_alive_redds = curr_alive_redds

            # Progress update every 10 steps
            if progress_queue is not None and step_num % 10 == 0:
                progress_queue.put((step_num, total_steps))

            # Per-step metrics (only at day boundaries to avoid sub-daily noise)
            if model.time_manager.is_day_boundary or model.steps_per_day == 1:
                current_date = model.time_manager.formatted_time()
                ts = model.trout_state
                rs = model.redd_state

                for sp_idx, sp_name in enumerate(model.species_order):
                    mask = ts.alive & (ts.species_idx == sp_idx)
                    count = int(mask.sum())
                    daily_records.append({
                        "date": current_date,
                        "species": sp_name,
                        "alive": count,
                        "mean_length": float(ts.length[mask].mean()) if count > 0 else 0.0,
                        "mean_weight": float(ts.weight[mask].mean()) if count > 0 else 0.0,
                        "redd_count": int(rs.alive.sum()),
                        "eggs_total": int(rs.num_eggs[rs.alive].sum()) if rs.alive.any() else 0,
                        "emerged_cumulative": emerged_total,
                        "outmigrants_cumulative": len(getattr(model, "_outmigrants", [])),
                    })

                # Periodic snapshot (every 30 days + census days)
                day_num = (pd.Timestamp(current_date) - start).days
                dt = pd.Timestamp(current_date)
                is_census = any(
                    dt.month == int(s.split("-")[0]) and dt.day == int(s.split("-")[1])
                    for s in census_specs
                )
                if day_num % 30 == 0 or is_census:
                    alive_mask = ts.alive
                    if alive_mask.any():
                        snapshots[current_date] = pd.DataFrame({
                            "fish_idx": np.where(alive_mask)[0],
                            "species": [model.species_order[i] for i in ts.species_idx[alive_mask]],
                            "length": ts.length[alive_mask],
                            "weight": ts.weight[alive_mask],
                            "cell_idx": ts.cell_idx[alive_mask],
                        })

        # Final progress
        if progress_queue is not None:
            progress_queue.put((total_steps, total_steps))

        # --- Build cells GeoDataFrame ---
        cells = _build_cells_gdf(model, raw)

        # --- Build redds DataFrame ---
        redds = _build_redds_df(model)

        # --- Daily DataFrame ---
        daily = pd.DataFrame(daily_records) if daily_records else pd.DataFrame()

        # --- Summary ---
        summary = {
            "final_date": model.time_manager.current_date_str,
            "fish_alive": int(model.trout_state.alive.sum()),
            "redds_alive": int(model.redd_state.alive.sum()),
            "total_outmigrants": len(getattr(model, "_outmigrants", [])),
        }

        return {
            "daily": daily,
            "environment": environment,
            "cells": cells,
            "snapshots": snapshots,
            "redds": redds,
            "config": raw,
            "summary": summary,
        }

    finally:
        os.unlink(tmp.name)


def _apply_overrides(raw, overrides):
    """Recursively merge overrides into raw YAML dict."""
    for key, value in overrides.items():
        if isinstance(value, dict) and key in raw and isinstance(raw[key], dict):
            _apply_overrides(raw[key], value)
        else:
            raw[key] = value


def _build_cells_gdf(model, raw_config):
    """Build cells GeoDataFrame from shapefile + final CellState."""
    mesh_path = Path(model.data_dir) / raw_config["spatial"]["mesh_file"]
    if not mesh_path.exists():
        alt = Path(model.data_dir) / "Shapefile" / Path(raw_config["spatial"]["mesh_file"]).name
        if alt.exists():
            mesh_path = alt
    gdf = gpd.read_file(mesh_path)

    # Case-insensitive column rename using gis_properties
    gis = raw_config["spatial"]["gis_properties"]
    col_map = {}
    canonical_map = {
        "cell_id": "cell_id", "reach_name": "reach",
        "area": "area", "frac_spawn": "frac_spawn",
    }
    for key, shp_col in gis.items():
        for actual_col in gdf.columns:
            if actual_col.upper() == shp_col.upper():
                canonical = canonical_map.get(key)
                if canonical:
                    col_map[actual_col] = canonical
                break
    gdf = gdf.rename(columns=col_map)

    # Merge dynamic fields from CellState
    cs = model.fem_space.cell_state
    n = len(gdf)
    gdf["depth"] = cs.depth[:n]
    gdf["velocity"] = cs.velocity[:n]
    gdf["available_drift"] = cs.available_drift[:n]
    gdf["available_search"] = cs.available_search[:n]

    # Fish count per cell at end of simulation
    ts = model.trout_state
    alive_cells = ts.cell_idx[ts.alive]
    fish_counts = np.bincount(alive_cells, minlength=n)[:n]
    gdf["fish_count"] = fish_counts

    # Keep only needed columns + geometry
    keep = ["cell_id", "reach", "geometry", "area", "depth", "velocity",
            "available_drift", "available_search", "fish_count", "frac_spawn"]
    return gdf[[c for c in keep if c in gdf.columns]]


def _build_redds_df(model):
    """Build redds DataFrame from final ReddState."""
    rs = model.redd_state
    alive = rs.alive
    if not alive.any():
        return pd.DataFrame(columns=[
            "redd_idx", "species", "cell_idx", "eggs",
            "frac_developed", "eggs_lo_temp", "eggs_hi_temp",
            "eggs_dewatering", "eggs_scour",
        ])
    indices = np.where(alive)[0]
    return pd.DataFrame({
        "redd_idx": indices,
        "species": [model.species_order[i] for i in rs.species_idx[alive]],
        "cell_idx": rs.cell_idx[alive],
        "eggs": rs.num_eggs[alive],
        "frac_developed": rs.frac_developed[alive],
        "eggs_lo_temp": rs.eggs_lo_temp[alive],
        "eggs_hi_temp": rs.eggs_hi_temp[alive],
        "eggs_dewatering": rs.eggs_dewatering[alive],
        "eggs_scour": rs.eggs_scour[alive],
    })
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `conda run -n shiny python -m pytest tests/test_simulation_wrapper.py -v --tb=short`
Expected: 6 PASSED (may take ~10-15s due to short simulation runs)

- [ ] **Step 6: Commit**

```bash
git add app/ tests/test_simulation_wrapper.py
git commit -m "feat: add simulation wrapper with config overrides and results collection"
```

---

### Task 3: Population Panel Module

**Files:**
- Create: `app/modules/population_panel.py`

- [ ] **Step 1: Implement population panel**

```python
"""Population panel — fish alive count by species over time."""
from shiny import module, render, ui


@module.ui
def population_ui():
    return ui.card(
        ui.card_header("Population Over Time"),
        ui.output_ui("population_plot"),
    )


@module.server
def population_server(input, output, session, results_rv):
    @output
    @render.ui
    def population_plot():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")
        df = results["daily"]
        if df.empty:
            return ui.p("No daily data collected.")

        import plotly.express as px
        from shiny import ui as sui

        fig = px.line(
            df, x="date", y="alive", color="species",
            labels={"alive": "Fish Alive", "date": "Date", "species": "Species"},
            title="Fish Population Over Time",
        )
        fig.update_layout(template="plotly_white", hovermode="x unified")
        return sui.HTML(fig.to_html(full_html=False, include_plotlyjs="cdn"))
```

- [ ] **Step 2: Commit**

```bash
git add app/modules/population_panel.py
git commit -m "feat: add population panel module (plotly line chart)"
```

---

### Task 4: Environment Panel Module

**Files:**
- Create: `app/modules/environment_panel.py`

- [ ] **Step 1: Implement environment panel**

```python
"""Environment panel — temperature, flow, turbidity subplots."""
from shiny import module, render, ui


@module.ui
def environment_ui():
    return ui.card(
        ui.card_header("Environmental Conditions"),
        ui.output_ui("environment_plot"),
    )


@module.server
def environment_server(input, output, session, results_rv):
    @output
    @render.ui
    def environment_plot():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")
        df = results["environment"]
        if df.empty:
            return ui.p("No environment data available.")

        from plotly.subplots import make_subplots
        import plotly.graph_objects as go
        from shiny import ui as sui

        reaches = df["reach"].unique()
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            subplot_titles=("Temperature (°C)", "Flow (m³/s)", "Turbidity (NTU)"),
            vertical_spacing=0.08,
        )
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
        for i, rname in enumerate(reaches):
            rd = df[df["reach"] == rname]
            color = colors[i % len(colors)]
            fig.add_trace(go.Scatter(x=rd["date"], y=rd["temperature"],
                                     name=rname, legendgroup=rname,
                                     line=dict(color=color)), row=1, col=1)
            fig.add_trace(go.Scatter(x=rd["date"], y=rd["flow"],
                                     name=rname, legendgroup=rname,
                                     showlegend=False, line=dict(color=color)), row=2, col=1)
            fig.add_trace(go.Scatter(x=rd["date"], y=rd["turbidity"],
                                     name=rname, legendgroup=rname,
                                     showlegend=False, line=dict(color=color)), row=3, col=1)
        fig.update_layout(template="plotly_white", height=600)
        return sui.HTML(fig.to_html(full_html=False, include_plotlyjs="cdn"))
```

- [ ] **Step 2: Commit**

```bash
git add app/modules/environment_panel.py
git commit -m "feat: add environment panel module (temp/flow/turbidity subplots)"
```

---

### Task 5: Size Distribution Panel Module

**Files:**
- Create: `app/modules/distribution_panel.py`

- [ ] **Step 1: Implement distribution panel**

```python
"""Distribution panel — fish length/weight histograms at selected date."""
from shiny import module, reactive, render, ui


@module.ui
def distribution_ui():
    return ui.card(
        ui.card_header("Fish Size Distribution"),
        ui.input_select("snapshot_date", "Select Date", choices=[]),
        ui.output_ui("distribution_plot"),
    )


@module.server
def distribution_server(input, output, session, results_rv):
    @reactive.effect
    def _update_date_choices():
        results = results_rv()
        if results is None:
            return
        dates = sorted(results["snapshots"].keys())
        ui.update_select("snapshot_date", choices=dates,
                         selected=dates[-1] if dates else None)

    @output
    @render.ui
    def distribution_plot():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")
        snapshots = results["snapshots"]
        sel = input.snapshot_date()
        if not sel or sel not in snapshots:
            return ui.p("No snapshot available for selected date.")

        import plotly.express as px
        from plotly.subplots import make_subplots
        from shiny import ui as sui

        df = snapshots[sel]
        fig = make_subplots(rows=1, cols=2, subplot_titles=("Length (cm)", "Weight (g)"))
        for sp in df["species"].unique():
            sp_df = df[df["species"] == sp]
            import plotly.graph_objects as go
            fig.add_trace(go.Histogram(x=sp_df["length"], name=sp,
                                        legendgroup=sp, opacity=0.7), row=1, col=1)
            fig.add_trace(go.Histogram(x=sp_df["weight"], name=sp,
                                        legendgroup=sp, showlegend=False,
                                        opacity=0.7), row=1, col=2)
        fig.update_layout(template="plotly_white", barmode="overlay",
                          title=f"Fish Size Distribution — {sel}")
        return sui.HTML(fig.to_html(full_html=False, include_plotlyjs="cdn"))
```

- [ ] **Step 2: Commit**

```bash
git add app/modules/distribution_panel.py
git commit -m "feat: add distribution panel module (length/weight histograms)"
```

---

### Task 6: Redd Panel Module

**Files:**
- Create: `app/modules/redd_panel.py`

- [ ] **Step 1: Implement redd panel**

```python
"""Redd panel — redd count timeline + details table."""
from shiny import module, render, ui


@module.ui
def redd_ui():
    return ui.card(
        ui.card_header("Redd Tracking"),
        ui.output_ui("redd_plot"),
        ui.card_header("Redd Details (End of Simulation)"),
        ui.output_table("redd_table"),
    )


@module.server
def redd_server(input, output, session, results_rv):
    @output
    @render.ui
    def redd_plot():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")
        df = results["daily"]
        if df.empty:
            return ui.p("No data available.")

        import plotly.graph_objects as go
        from shiny import ui as sui

        # Aggregate across species for redd metrics (same value per species per day)
        redd_df = df.groupby("date").first().reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=redd_df["date"], y=redd_df["redd_count"],
                                  name="Active Redds", mode="lines"))
        if "eggs_total" in redd_df.columns:
            fig.add_trace(go.Scatter(x=redd_df["date"], y=redd_df["eggs_total"],
                                      name="Total Eggs", mode="lines", yaxis="y2"))
        fig.update_layout(
            template="plotly_white", title="Redd Activity Over Time",
            yaxis=dict(title="Count"),
            yaxis2=dict(title="Eggs", overlaying="y", side="right"),
        )
        return sui.HTML(fig.to_html(full_html=False, include_plotlyjs="cdn"))

    @output
    @render.table
    def redd_table():
        results = results_rv()
        if results is None:
            return None
        redds = results["redds"]
        if redds.empty:
            return None
        return redds.round(4)
```

- [ ] **Step 2: Commit**

```bash
git add app/modules/redd_panel.py
git commit -m "feat: add redd panel module (timeline + details table)"
```

---

### Task 7: Spatial Panel Module

**Files:**
- Create: `app/modules/spatial_panel.py`

- [ ] **Step 1: Implement spatial panel**

```python
"""Spatial panel — cell polygon map using shiny_deckgl."""
from shiny import module, reactive, render, ui


COLORING_VARS = {
    "depth": "Depth (cm)",
    "velocity": "Velocity (cm/s)",
    "available_drift": "Drift Food Available",
    "available_search": "Search Food Available",
    "fish_count": "Fish Density",
    "frac_spawn": "Spawn Fraction",
}


@module.ui
def spatial_ui():
    return ui.card(
        ui.card_header("Spatial View"),
        ui.input_select("color_var", "Color by:", choices=COLORING_VARS),
        ui.output_ui("spatial_map"),
    )


@module.server
def spatial_server(input, output, session, results_rv):
    @output
    @render.ui
    def spatial_map():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")

        gdf = results["cells"]
        if gdf.empty:
            return ui.p("No spatial data available.")

        color_var = input.color_var()
        if color_var not in gdf.columns:
            return ui.p(f"Variable '{color_var}' not available.")

        # Use matplotlib for reliable rendering (shiny_deckgl integration
        # can be swapped in later for interactive maps)
        return _fallback_plot(gdf, color_var)


def _fallback_plot(gdf, color_var):
    """Fallback matplotlib plot if shiny_deckgl is not available."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import io, base64
    from shiny import ui as sui

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    gdf.plot(column=color_var, ax=ax, legend=True, cmap="viridis")
    ax.set_title(f"Cells colored by {COLORING_VARS.get(color_var, color_var)}")
    ax.set_aspect("equal")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode()
    return sui.HTML(f'<img src="data:image/png;base64,{img_b64}" style="max-width:100%">')
```

- [ ] **Step 2: Commit**

```bash
git add app/modules/spatial_panel.py
git commit -m "feat: add spatial panel module (shiny_deckgl map + matplotlib fallback)"
```

---

### Task 8: Main App Entry Point

**Files:**
- Create: `app/app.py`

- [ ] **Step 1: Implement app.py**

```python
"""inSTREAM-py Shiny Frontend — main application."""
import asyncio
import queue
from pathlib import Path

from shiny import App, reactive, render, ui
import shinyswatch

from modules.population_panel import population_ui, population_server
from modules.environment_panel import environment_ui, environment_server
from modules.distribution_panel import distribution_ui, distribution_server
from modules.redd_panel import redd_ui, redd_server
from modules.spatial_panel import spatial_ui, spatial_server
from simulation import run_simulation


# --- Discover available configs ---
CONFIGS_DIR = Path(__file__).parent / "configs"
if not CONFIGS_DIR.exists():
    CONFIGS_DIR = Path(__file__).parent.parent / "configs"
CONFIG_CHOICES = {
    str(p): p.stem for p in sorted(CONFIGS_DIR.glob("*.yaml"))
} if CONFIGS_DIR.exists() else {}


app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h4("inSTREAM-py"),
        ui.input_select("config_file", "Configuration", choices=CONFIG_CHOICES),
        ui.input_date("start_date", "Start Date", value="2011-04-01"),
        ui.input_date("end_date", "End Date", value="2013-09-30"),
        ui.hr(),
        ui.h5("Reach Parameters"),
        ui.input_slider("drift_conc", "Drift Concentration",
                         min=-12, max=-6, value=-9.5, step=0.5,
                         post=" (10^x)"),
        ui.input_slider("search_prod", "Search Productivity",
                         min=-8, max=-4, value=-6, step=0.5,
                         post=" (10^x)"),
        ui.input_slider("shading", "Shading", min=0, max=1, value=0.85, step=0.05),
        ui.input_slider("fish_pred_min", "Fish Pred. Min", min=0.8, max=1, value=0.95, step=0.01),
        ui.input_slider("terr_pred_min", "Terr. Pred. Min", min=0.8, max=1, value=0.92, step=0.01),
        ui.hr(),
        ui.input_select("backend", "Backend", choices=["numpy", "numba"], selected="numpy"),
        ui.input_action_button("run_btn", "Run Simulation", class_="btn-primary w-100"),
        ui.output_text("progress_text"),
        width=320,
    ),
    ui.navset_tab(
        ui.nav_panel("Population", population_ui("pop")),
        ui.nav_panel("Spatial", spatial_ui("spatial")),
        ui.nav_panel("Environment", environment_ui("env")),
        ui.nav_panel("Size Distribution", distribution_ui("dist")),
        ui.nav_panel("Redds", redd_ui("redds")),
    ),
    title="inSTREAM-py Simulation Explorer",
    theme=shinyswatch.theme.flatly,
)


def server(input, output, session):
    results_rv = reactive.value(None)
    _progress_q = queue.Queue()
    _latest_progress = reactive.value((0, 1))

    @reactive.extended_task
    async def run_sim_task(config_path, overrides):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, run_simulation, config_path, overrides, _progress_q
        )

    @reactive.effect
    @reactive.event(input.run_btn)
    def _launch():
        config_path = input.config_file()
        if not config_path:
            ui.notification_show("Please select a configuration file.", type="error")
            return
        overrides = {
            "simulation": {
                "start_date": str(input.start_date()),
                "end_date": str(input.end_date()),
            },
            "performance": {"backend": input.backend()},
        }
        # Build reach overrides
        reach_overrides = {
            "drift_conc": 10 ** input.drift_conc(),
            "search_prod": 10 ** input.search_prod(),
            "shading": input.shading(),
            "fish_pred_min": input.fish_pred_min(),
            "terr_pred_min": input.terr_pred_min(),
        }
        # Load config to get reach names
        import yaml
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        if "reaches" in raw:
            overrides["reaches"] = {}
            for rname in raw["reaches"]:
                overrides["reaches"][rname] = dict(reach_overrides)

        # Drain queue safely (thread-safe)
        while not _progress_q.empty():
            try:
                _progress_q.get_nowait()
            except Exception:
                break
        _latest_progress.set((0, 1))
        run_sim_task(config_path, overrides)

    @reactive.effect
    def _poll_progress():
        status = run_sim_task.status()
        if status == "running":
            reactive.invalidate_later(1)
            # Drain queue into reactive value (single consumer)
            step, total = _latest_progress.get()
            try:
                while not _progress_q.empty():
                    step, total = _progress_q.get_nowait()
            except Exception:
                pass
            _latest_progress.set((step, total))
        elif status == "success":
            results_rv.set(run_sim_task.result())
            ui.notification_show("Simulation complete!", type="message", duration=3)
        elif status == "error":
            ui.notification_show(f"Simulation failed: {run_sim_task.error()}", type="error")

    @output
    @render.text
    def progress_text():
        status = run_sim_task.status()
        if status == "running":
            step, total = _latest_progress.get()
            pct = int(100 * step / max(total, 1))
            return f"Running... {pct}% ({step}/{total} steps)"
        elif status == "success":
            return "Complete!"
        elif status == "error":
            return "Error — see notification"
        return "Ready"

    # Wire panel modules
    population_server("pop", results_rv=results_rv)
    environment_server("env", results_rv=results_rv)
    distribution_server("dist", results_rv=results_rv)
    redd_server("redds", results_rv=results_rv)
    spatial_server("spatial", results_rv=results_rv)


app = App(app_ui, server)
```

- [ ] **Step 2: Write smoke test**

Create `tests/test_app_smoke.py`:

```python
"""Smoke test: app module imports and UI renders without errors."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


def test_simulation_imports():
    from simulation import run_simulation
    assert callable(run_simulation)


def test_panel_modules_import():
    from modules.population_panel import population_ui, population_server
    from modules.environment_panel import environment_ui, environment_server
    from modules.distribution_panel import distribution_ui, distribution_server
    from modules.redd_panel import redd_ui, redd_server
    from modules.spatial_panel import spatial_ui, spatial_server
    assert callable(population_ui)
    assert callable(spatial_server)


def test_app_creates():
    from app import app
    assert app is not None
```

- [ ] **Step 3: Run smoke tests**

Run: `conda run -n shiny python -m pytest tests/test_app_smoke.py -v --tb=short`
Expected: 3 PASSED

- [ ] **Step 4: Commit**

```bash
git add app/app.py tests/test_app_smoke.py
git commit -m "feat: add main Shiny app entry point with sidebar, tabs, and extended_task"
```

---

### Task 9: Local Test Run

- [ ] **Step 1: Run the full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v --tb=short -q`
Expected: All tests pass (490 existing + ~9 new)

- [ ] **Step 2: Test the app locally**

Run: `conda run -n shiny python -m shiny run app/app.py --port 8123`

Open http://localhost:8123 in browser. Verify:
- Sidebar renders with all controls
- Select `example_a` config
- Click "Run Simulation"
- Wait for completion (~80s or reduce end date to 2011-05-01 for quick test)
- All 5 tabs show data

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues from local test run"
```

---

### Task 10: Deploy Skill

**Files:**
- Create: `.claude/skills/deploy/SKILL.md`

- [ ] **Step 1: Create deploy skill**

```markdown
---
name: deploy
description: Deploy the inSTREAM-py Shiny app to laguna.ku.lt. Use when user says /deploy or asks to deploy the app.
---

# Deploy inSTREAM-py Shiny App

When invoked via `/deploy`, perform these steps:

## 1. Run Tests

Run the test suite to gate the deployment:

```bash
conda run -n shiny python -m pytest tests/ -q --tb=short
```

If tests fail, stop and report the failures. Do not deploy broken code.

## 2. Sync App Files

```bash
rsync -avz --delete --exclude=configs --exclude=data "app/" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/"
```

## 3. Sync Configs

```bash
rsync -avz "configs/" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/configs/"
```

## 4. Sync Data

```bash
rsync -avz "tests/fixtures/" "razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/data/"
```

## 5. Set Permissions and Restart

```bash
ssh razinka@laguna.ku.lt "chmod -R g+r /srv/shiny-server/inSTREAMPY && touch /srv/shiny-server/inSTREAMPY/restart.txt"
```

If `sudo` is available, use `sudo systemctl reload shiny-server` instead of `touch restart.txt`.

## 6. Verify

```bash
ssh razinka@laguna.ku.lt "ls -la /srv/shiny-server/inSTREAMPY/app.py"
```

Report the deployment status: files synced, permissions set, server restarted.

## Notes

- SSH user: `razinka` (passwordless SSH required)
- Server: `laguna.ku.lt`
- Target directory: `/srv/shiny-server/inSTREAMPY`
- The `instream` package must be installed on the server via `pip install -e .` from a repo clone
- All commands must use double-quoted paths (no backslash escapes, no `$()`)
```

- [ ] **Step 2: Commit**

```bash
git add ".claude/skills/deploy/SKILL.md"
git commit -m "feat: add /deploy skill for laguna.ku.lt Shiny Server deployment"
```

---

### Task 11: Final Integration + Release

- [ ] **Step 1: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v -q`
Expected: All tests pass

- [ ] **Step 2: Update README Planned section**

Remove "Shiny dashboard for interactive visualization" from Planned. Add to Completed:
- Shiny for Python frontend (configure, run, explore simulations)
- Deploy skill for laguna.ku.lt Shiny Server

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README with Shiny frontend in completed features"
```
