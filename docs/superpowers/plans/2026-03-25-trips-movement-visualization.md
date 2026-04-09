# Trips Movement Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Spatial panel from matplotlib to an interactive deck.gl map with animated fish movement trails.

**Architecture:** The simulation loop in `app/simulation.py` collects per-fish, per-day position records. A helper function converts these to WGS84 coordinate paths for `format_trips()`. The spatial panel is rewritten to use `MapWidget` with `geojson_layer` (cell polygons) and `trips_layer` (fish trails), with color-by dropdowns and animation controls.

**Tech Stack:** shiny-deckgl (MapWidget, geojson_layer, trips_layer, format_trips, trips_animation_ui/server), GeoPandas (CRS reprojection), matplotlib (viridis colormap for cell colors), Shiny for Python (reactive UI).

**Spec:** `docs/superpowers/specs/2026-03-25-trips-movement-visualization-design.md`

---

## File Structure

| File | Role | Action |
|------|------|--------|
| `app/simulation.py` | Simulation runner + data collection | Edit: add trajectory collection + `_build_trajectories_data()` + `_value_to_rgba()` |
| `app/modules/spatial_panel.py` | Spatial visualization panel | Rewrite: MapWidget + geojson_layer + trips_layer |
| `app/app.py` | Main app wiring | Edit: minimal (verify import) |
| `tests/test_simulation_wrapper.py` | Integration tests for simulation results | Edit: add trajectory tests |
| `tests/test_spatial_panel.py` | Unit tests for spatial data helpers | Create: test `_build_trajectories_data()` and `_value_to_rgba()` |

---

## Task 1: Add trajectory collection to simulation loop

**Files:**
- Modify: `app/simulation.py:74-180`
- Test: `tests/test_simulation_wrapper.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_simulation_wrapper.py`:

```python
def test_trajectories_key_present(self):
    """run_simulation returns trajectories DataFrame."""
    results = run_simulation(
        self.CONFIG,
        overrides={"simulation": {"end_date": "2011-04-10"}},
        data_dir=self.DATA_DIR,
    )
    assert "trajectories" in results, "Missing 'trajectories' key"

def test_trajectories_columns(self):
    """trajectories DataFrame has required columns."""
    results = run_simulation(
        self.CONFIG,
        overrides={"simulation": {"end_date": "2011-04-10"}},
        data_dir=self.DATA_DIR,
    )
    traj = results["trajectories"]
    assert isinstance(traj, pd.DataFrame)
    for col in ("fish_idx", "cell_idx", "species_idx", "activity",
                "life_history", "day_num"):
        assert col in traj.columns, f"Missing column: {col}"

def test_trajectories_row_count(self):
    """trajectories has one row per alive fish per day."""
    results = run_simulation(
        self.CONFIG,
        overrides={"simulation": {"end_date": "2011-04-05"}},
        data_dir=self.DATA_DIR,
    )
    traj = results["trajectories"]
    # Should have rows for 5 days (Apr 1-5), each with ~360 fish
    assert len(traj) > 0
    days = traj["day_num"].nunique()
    assert days == 5, f"Expected 5 days, got {days}"

def test_trajectories_day_num_range(self):
    """day_num is 0-based and matches simulation duration."""
    results = run_simulation(
        self.CONFIG,
        overrides={"simulation": {"end_date": "2011-04-10"}},
        data_dir=self.DATA_DIR,
    )
    traj = results["trajectories"]
    assert traj["day_num"].min() == 0
    assert traj["day_num"].max() == 9  # 10 days, 0-indexed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n shiny python -m pytest tests/test_simulation_wrapper.py::TestRunSimulation::test_trajectories_key_present -v`
Expected: FAIL with `KeyError` or `AssertionError`

- [ ] **Step 3: Implement trajectory collection**

In `app/simulation.py`, add a `trajectory_records` list before the step loop (after line 77), and collect data inside the existing day-boundary block:

```python
# Before step loop (after line 77, "step_num = 0"):
trajectory_records = []

# Inside the existing "if model.time_manager.is_day_boundary or model.steps_per_day == 1:" block,
# after the daily_records.append() call (after line 126), add:
                # --- Trajectory collection ---
                day_num = (pd.Timestamp(current_date) - start).days
                alive_mask = ts.alive
                if alive_mask.any():
                    alive_idx = np.where(alive_mask)[0]
                    trajectory_records.append(
                        pd.DataFrame({
                            "fish_idx": alive_idx,
                            "cell_idx": ts.cell_idx[alive_mask],
                            "species_idx": ts.species_idx[alive_mask],
                            "activity": ts.activity[alive_mask],
                            "life_history": ts.life_history[alive_mask],
                            "day_num": day_num,
                        })
                    )
```

Note: the `day_num` variable is already computed at line 129 for snapshot logic. Move or reuse it before the snapshot block so both use it.

After the step loop (before `_build_cells_gdf` at line 156), concatenate:

```python
        # --- Build trajectories DataFrame ---
        trajectories = (
            pd.concat(trajectory_records, ignore_index=True)
            if trajectory_records
            else pd.DataFrame(
                columns=["fish_idx", "cell_idx", "species_idx",
                         "activity", "life_history", "day_num"]
            )
        )
```

Add `"trajectories": trajectories` to the return dict (line 172-180).

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n shiny python -m pytest tests/test_simulation_wrapper.py -k "trajectories" -v`
Expected: All 4 new tests PASS

- [ ] **Step 5: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add app/simulation.py tests/test_simulation_wrapper.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "feat: collect per-fish daily trajectories in simulation loop"
```

---

## Task 2: Add `_build_trajectories_data()` helper and `_value_to_rgba()`

**Files:**
- Modify: `app/simulation.py`
- Create: `tests/test_spatial_panel.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_spatial_panel.py`:

```python
"""Tests for spatial panel helper functions."""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "app"))

from simulation import _build_trajectories_data, _value_to_rgba


class TestBuildTrajectoriesData:
    """Unit tests for _build_trajectories_data()."""

    @staticmethod
    def _make_gdf():
        """3 cells in EPSG:4326 (already lon/lat)."""
        polys = [
            Polygon([(20.0, 55.0), (20.01, 55.0), (20.01, 55.01), (20.0, 55.01)]),
            Polygon([(20.01, 55.0), (20.02, 55.0), (20.02, 55.01), (20.01, 55.01)]),
            Polygon([(20.02, 55.0), (20.03, 55.0), (20.03, 55.01), (20.02, 55.01)]),
        ]
        return gpd.GeoDataFrame(
            {"cell_id": [0, 1, 2]},
            geometry=polys,
            crs="EPSG:4326",
        )

    @staticmethod
    def _make_traj():
        """5 fish, 3 days. Fish 4 dies on day 1 (absent day 2)."""
        rows = []
        for day in range(3):
            for fish in range(5):
                if fish == 4 and day == 2:
                    continue  # fish 4 dies
                rows.append({
                    "fish_idx": fish,
                    "cell_idx": fish % 3,
                    "species_idx": fish % 2,
                    "activity": 0,
                    "life_history": 0,
                    "day_num": day,
                })
        return pd.DataFrame(rows)

    def test_returns_two_lists(self):
        paths, props = _build_trajectories_data(
            self._make_traj(), self._make_gdf(), ["sp_a", "sp_b"],
        )
        assert isinstance(paths, list)
        assert isinstance(props, list)
        assert len(paths) == len(props)

    def test_paths_are_3d(self):
        paths, _ = _build_trajectories_data(
            self._make_traj(), self._make_gdf(), ["sp_a", "sp_b"],
        )
        for path in paths:
            for pt in path:
                assert len(pt) == 3, f"Expected [lon, lat, day_num], got {pt}"

    def test_correct_fish_count(self):
        """5 unique fish → 5 trips."""
        paths, props = _build_trajectories_data(
            self._make_traj(), self._make_gdf(), ["sp_a", "sp_b"],
        )
        assert len(paths) == 5

    def test_variable_length_paths(self):
        """Fish 4 has 2 days, others have 3."""
        paths, props = _build_trajectories_data(
            self._make_traj(), self._make_gdf(), ["sp_a", "sp_b"],
        )
        lengths = {p["fish_idx"]: len(path) for path, p in zip(paths, props)}
        assert lengths[4] == 2
        assert lengths[0] == 3

    def test_timestamps_are_actual_day_nums(self):
        """Third coordinate should be the actual day_num, not auto-generated."""
        paths, _ = _build_trajectories_data(
            self._make_traj(), self._make_gdf(), ["sp_a", "sp_b"],
        )
        # Fish 0 is present days 0, 1, 2
        fish0_path = paths[0]
        assert fish0_path[0][2] == 0
        assert fish0_path[1][2] == 1
        assert fish0_path[2][2] == 2

    def test_properties_contain_species(self):
        _, props = _build_trajectories_data(
            self._make_traj(), self._make_gdf(), ["sp_a", "sp_b"],
        )
        for p in props:
            assert "species" in p
            assert "color" in p
            assert "fish_idx" in p

    def test_coords_are_lon_lat(self):
        """Coordinates should be in WGS84 range."""
        paths, _ = _build_trajectories_data(
            self._make_traj(), self._make_gdf(), ["sp_a", "sp_b"],
        )
        for path in paths:
            for lon, lat, _ in path:
                assert -180 <= lon <= 180, f"lon out of range: {lon}"
                assert -90 <= lat <= 90, f"lat out of range: {lat}"


class TestValueToRgba:
    """Unit tests for _value_to_rgba()."""

    def test_returns_list_of_rgba(self):
        values = np.array([0.0, 0.5, 1.0])
        result = _value_to_rgba(values)
        assert len(result) == 3
        for rgba in result:
            assert len(rgba) == 4
            assert all(0 <= c <= 255 for c in rgba)

    def test_nan_is_transparent(self):
        values = np.array([1.0, np.nan, 2.0])
        result = _value_to_rgba(values)
        assert result[1] == [0, 0, 0, 0]

    def test_constant_values(self):
        """All same values should not crash (zero range)."""
        values = np.array([5.0, 5.0, 5.0])
        result = _value_to_rgba(values)
        assert len(result) == 3

    def test_custom_alpha(self):
        values = np.array([0.0, 1.0])
        result = _value_to_rgba(values, alpha=200)
        for rgba in result:
            assert rgba[3] == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n shiny python -m pytest tests/test_spatial_panel.py -v`
Expected: FAIL with `ImportError: cannot import name '_build_trajectories_data'`

- [ ] **Step 3: Implement `_value_to_rgba()`**

Add to `app/simulation.py` after the existing `_build_redds_df()` function:

```python
def _value_to_rgba(values, cmap="viridis", alpha=160):
    """Map numeric values to [R, G, B, A] lists via matplotlib colormap.

    NaN values → [0, 0, 0, 0] (transparent).
    """
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors

    values = np.asarray(values, dtype=float)
    mask = np.isfinite(values)
    result = [[0, 0, 0, 0]] * len(values)

    if not mask.any():
        return result

    valid = values[mask]
    vmin, vmax = valid.min(), valid.max()
    if vmin == vmax:
        normed = np.full_like(valid, 0.5)
    else:
        normed = (valid - vmin) / (vmax - vmin)

    colormap = cm.get_cmap(cmap)
    colors = colormap(normed)  # shape (n, 4) floats 0-1
    result = list(result)  # make mutable
    idx = 0
    for i in range(len(values)):
        if mask[i]:
            r, g, b, _ = colors[idx]
            result[i] = [int(r * 255), int(g * 255), int(b * 255), alpha]
            idx += 1
    return result
```

- [ ] **Step 4: Implement `_build_trajectories_data()`**

Add to `app/simulation.py` after `_value_to_rgba()`:

```python
# Color palettes for fish trail modes
_TAB10 = [
    [31, 119, 180], [255, 127, 14], [44, 160, 44], [214, 39, 40],
    [148, 103, 189], [140, 86, 75], [227, 119, 194], [127, 127, 127],
    [188, 189, 34], [23, 190, 207],
]
_ACTIVITY_COLORS = {
    0: [66, 133, 244],   # drift = blue
    1: [52, 168, 83],    # search = green
    2: [154, 160, 166],  # hide = gray
    3: [234, 67, 53],    # guard = red
    4: [251, 188, 4],    # hold = yellow
}
_LIFE_HISTORY_COLORS = {
    0: [0, 150, 136],    # resident = teal
    1: [0, 188, 212],    # anad_juve = cyan
    2: [255, 152, 0],    # anad_adult = orange
}
_SIZE_RAMP = [
    [189, 215, 231], [107, 174, 214], [49, 130, 189], [8, 81, 156],
]


def _build_trajectories_data(traj_df, cells_gdf, species_order, color_mode="species"):
    """Convert trajectory DataFrame + cells GeoDataFrame into format for format_trips().

    Parameters
    ----------
    traj_df : pd.DataFrame
        Columns: fish_idx, cell_idx, species_idx, activity, life_history, day_num.
    cells_gdf : gpd.GeoDataFrame
        Cell polygons with geometry (any CRS — will be reprojected to EPSG:4326).
    species_order : list[str]
        Species names in order of species_idx.
    color_mode : str
        One of "species", "activity", "life_history", "size_class".

    Returns
    -------
    (paths, properties) : tuple[list, list]
        paths: list of [[lon, lat, day_num], ...] per fish.
        properties: list of dicts with "species", "color", "fish_idx", etc.
    """
    if traj_df.empty:
        return [], []

    # Reproject to WGS84 and build centroid lookup
    gdf_wgs84 = cells_gdf.to_crs(epsg=4326) if cells_gdf.crs != "EPSG:4326" else cells_gdf
    centroids = gdf_wgs84.geometry.centroid
    centroid_lut = np.column_stack([centroids.x, centroids.y])  # (n_cells, 2)

    paths = []
    properties = []

    for fish_idx, group in traj_df.sort_values("day_num").groupby("fish_idx"):
        cell_indices = group["cell_idx"].values
        day_nums = group["day_num"].values

        # Build 3D path: [lon, lat, day_num]
        coords = centroid_lut[cell_indices]  # (n_days, 2)
        path = [[float(coords[i, 0]), float(coords[i, 1]), int(day_nums[i])]
                for i in range(len(coords))]

        # Get last recorded state for coloring
        last = group.iloc[-1]
        sp_idx = int(last["species_idx"])
        species_name = species_order[sp_idx] if sp_idx < len(species_order) else f"species_{sp_idx}"

        if color_mode == "activity":
            color = _ACTIVITY_COLORS.get(int(last["activity"]), [127, 127, 127])
        elif color_mode == "life_history":
            color = _LIFE_HISTORY_COLORS.get(int(last["life_history"]), [127, 127, 127])
        else:  # "species" (default and fallback)
            color = _TAB10[sp_idx % len(_TAB10)]

        props = {
            "fish_idx": int(fish_idx),
            "species": species_name,
            "activity": int(last["activity"]),
            "life_history": int(last["life_history"]),
            "color": color + [220],  # add alpha
        }

        paths.append(path)
        properties.append(props)

    return paths, properties
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `conda run -n shiny python -m pytest tests/test_spatial_panel.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add app/simulation.py tests/test_spatial_panel.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "feat: add _build_trajectories_data() and _value_to_rgba() helpers"
```

---

## Task 3: Rewrite spatial panel with MapWidget + GeoJsonLayer

**Files:**
- Rewrite: `app/modules/spatial_panel.py`
- Modify: `app/app.py` (verify imports)

- [ ] **Step 1: Rewrite `app/modules/spatial_panel.py`**

Replace the entire file content:

```python
"""Spatial panel — interactive deck.gl map with cell polygons and fish trips."""

from shiny import module, reactive, render, ui

from shiny_deckgl import (
    MapWidget,
    CARTO_DARK,
    geojson_layer,
)
from simulation import _build_trajectories_data, _value_to_rgba


COLORING_VARS = {
    "depth": "Depth (cm)",
    "velocity": "Velocity (cm/s)",
    "available_drift": "Drift Food Available",
    "available_search": "Search Food Available",
    "fish_count": "Fish Density",
}

TRIPS_COLOR_MODES = {
    "species": "Species",
    "activity": "Activity",
    "life_history": "Life History",
}


@module.ui
def spatial_ui():
    return ui.card(
        ui.card_header("Spatial View"),
        ui.layout_columns(
            ui.input_select("color_var", "Cells color:", choices=COLORING_VARS),
            ui.input_select("trips_color", "Trails color:", choices=TRIPS_COLOR_MODES),
            ui.input_checkbox("show_trips", "Show fish trails", value=False),
            col_widths=(4, 4, 4),
        ),
        ui.output_ui("map_container"),
    )


@module.server
def spatial_server(input, output, session, results_rv):
    # MapWidget will be created once results are available
    _widget_holder = reactive.value(None)
    _anim_holder = reactive.value(None)

    @output
    @render.ui
    def map_container():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")

        gdf = results["cells"]
        if gdf.empty:
            return ui.p("No spatial data available.")

        # Compute view state from GeoDataFrame bounds
        gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf
        bounds = gdf_wgs84.total_bounds  # [minx, miny, maxx, maxy]
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        # Rough zoom estimate from bounds extent
        extent = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
        zoom = max(1, min(18, int(11 - extent * 50)))

        widget = MapWidget(
            "spatial_map",
            view_state={
                "longitude": center_lon,
                "latitude": center_lat,
                "zoom": zoom,
            },
            style=CARTO_DARK,
            animate=True,
            tooltip={
                "html": "<b>{cell_id}</b><br/>{_tooltip_var}: {_tooltip_val}",
                "style": {"backgroundColor": "#222", "color": "#fff", "fontSize": "12px"},
            },
        )
        _widget_holder.set(widget)

        # Wire animation controls if trips are available
        if "trajectories" in results and not results["trajectories"].empty:
            from shiny_deckgl.ibm import trips_animation_ui, trips_animation_server
            anim = trips_animation_server("fish_anim", widget=widget, session=session)
            _anim_holder.set(anim)
            return ui.TagList(
                ui.panel_conditional(
                    "input['spatial-show_trips']",
                    trips_animation_ui("fish_anim"),
                ),
                widget.ui(height="600px"),
            )

        return widget.ui(height="600px")

    @reactive.effect
    async def _update_layers():
        widget = _widget_holder()
        results = results_rv()
        if widget is None or results is None:
            return

        gdf = results["cells"]
        if gdf.empty:
            return

        layers = []

        # --- Cell polygon layer ---
        color_var = input.color_var()
        gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf
        if color_var in gdf_wgs84.columns:
            colors = _value_to_rgba(gdf_wgs84[color_var].values)
            gdf_colored = gdf_wgs84.copy()
            gdf_colored["color"] = colors
            gdf_colored["_tooltip_var"] = COLORING_VARS.get(color_var, color_var)
            gdf_colored["_tooltip_val"] = gdf_colored[color_var].round(2).astype(str)
        else:
            gdf_colored = gdf_wgs84.copy()
            gdf_colored["color"] = [[100, 100, 100, 100]] * len(gdf_colored)
            gdf_colored["_tooltip_var"] = ""
            gdf_colored["_tooltip_val"] = ""

        cells_layer = geojson_layer(
            "cells",
            gdf_colored,
            getFillColor="@@=d.properties.color",
            getLineColor=[60, 60, 60, 100],
            lineWidthMinPixels=1,
        )
        layers.append(cells_layer)

        # --- Trips layer ---
        if input.show_trips():
            traj_df = results.get("trajectories")
            if traj_df is not None and not traj_df.empty:
                from shiny_deckgl import trips_layer
                from shiny_deckgl.ibm import format_trips

                species_order = results["config"].get("species", {}).keys()
                species_order = list(species_order) if species_order else ["unknown"]

                trips_color = input.trips_color()
                paths, props = _build_trajectories_data(
                    traj_df, gdf, species_order, color_mode=trips_color,
                )

                if paths:
                    total_days = int(traj_df["day_num"].max()) + 1
                    trips_data = format_trips(
                        paths, loop_length=total_days, properties=props,
                    )

                    anim = _anim_holder()
                    speed = anim.speed() if anim else 8.0
                    trail = anim.trail() if anim else 180

                    trip_layer = trips_layer(
                        "fish_trips",
                        trips_data,
                        getColor="@@=d.color",
                        trailLength=trail,
                        fadeTrail=True,
                        widthMinPixels=3,
                        _tripsAnimation={
                            "loopLength": total_days,
                            "speed": speed,
                        },
                    )
                    layers.append(trip_layer)

        await widget.update(session, layers, animate=True)
```

- [ ] **Step 2: Verify `app/app.py` needs no changes**

Read `app/app.py` — the spatial panel is already imported and wired via:
```python
from modules.spatial_panel import spatial_ui, spatial_server
```
and:
```python
spatial_server("spatial", results_rv=results_rv)
```

The `spatial_server` signature remains `(input, output, session, results_rv)` — no changes needed.

- [ ] **Step 3: Run existing tests to check no regressions**

Run: `conda run -n shiny python -m pytest tests/ -v --tb=short -x`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add app/modules/spatial_panel.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "feat: rewrite spatial panel with deck.gl MapWidget + geojson + trips layers"
```

---

## Task 4: Verify pyproject.toml dependency and run integration test

**Files:**
- Verify: `pyproject.toml`
- Manual test: run app

- [ ] **Step 1: Verify shiny-deckgl version in pyproject.toml**

Read `pyproject.toml` and check that `[project.optional-dependencies.frontend]` includes `shiny-deckgl>=1.9`. If the version is lower, update it.

- [ ] **Step 2: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v --tb=short`
Expected: All tests PASS (including new trajectory + spatial helper tests)

- [ ] **Step 3: Smoke test the app**

Run the Shiny app locally:
```bash
cd "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" && conda run -n shiny shiny run app/app.py --port 8080
```

Manually verify:
1. App loads without errors
2. Select Example A config, set end date to 2011-05-01 (30 days), click Run
3. After simulation completes, click Spatial tab
4. Cell polygons render on dark map, colored by depth
5. Change color dropdown to velocity — polygons recolor
6. Check "Show fish trails" — animation controls appear
7. Click Play — fish trails animate over the map
8. Change trails color dropdown — trail colors update
9. Hover over cell polygon — tooltip shows cell_id + variable value

- [ ] **Step 4: Commit any fixes from smoke test**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add -A
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "fix: address issues from integration smoke test"
```

(Only commit if fixes were needed.)

- [ ] **Step 5: Final commit — update pyproject.toml if needed**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add pyproject.toml
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "chore: verify shiny-deckgl>=1.9 dependency"
```
