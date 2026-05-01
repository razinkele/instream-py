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


def run_simulation(
    config_path, overrides=None, progress_queue=None, metrics_queue=None, data_dir=None
):
    """Run inSTREAM simulation and collect results.

    Runs synchronously — designed to be called from a worker thread
    via asyncio.run_in_executor().

    Args:
        config_path: Path to YAML config file.
        overrides: Dict of parameter overrides (nested, matching YAML structure).
        progress_queue: Optional queue.Queue for (step, total) progress updates.
        metrics_queue: Optional queue.Queue for per-day dashboard snapshots.
        data_dir: Optional path to data directory. Defaults to config file's parent.

    Returns:
        dict with keys: daily, environment, cells, snapshots, redds, config, summary, trajectories
    """
    from salmopy.model import SalmopyModel

    config_path = Path(config_path)
    original_data_dir = Path(data_dir) if data_dir else config_path.parent

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
        model = SalmopyModel(config_path=tmp.name, data_dir=original_data_dir)

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
        environment = (
            pd.concat(env_frames, ignore_index=True) if env_frames else pd.DataFrame()
        )

        # --- Track emerged fry (model has no cumulative counter) ---
        prev_alive_redds = set(np.where(model.redd_state.alive)[0])
        emerged_total = 0
        prev_alive_total = int(model.trout_state.alive.sum())

        # --- Push cells init message for movement map ---
        if metrics_queue is not None:
            _init_cells = _build_cells_gdf(model, raw)
            keep = [
                c
                for c in ["cell_id", "reach", "area", "frac_spawn"]
                if c in _init_cells.columns
            ]
            _init_cells = _init_cells[keep + ["geometry"]]
            if _init_cells.crs is not None and _init_cells.crs.to_epsg() != 4326:
                _init_cells = _init_cells.to_crs(epsg=4326)
            metrics_queue.put({"type": "cells", "cells_geojson": _init_cells})

        # --- Census day parsing for snapshot collection ---
        census_specs = model.config.simulation.census_days  # list of "MM-dd" strings

        # --- Step loop with data collection ---
        daily_records = []
        trajectory_records = []
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

            # Progress update every 10 steps (sleep(0) releases the GIL so
            # the Shiny async event loop can process reactive updates)
            if progress_queue is not None and step_num % 10 == 0:
                progress_queue.put((step_num, total_steps))
                import time

                time.sleep(0)

            # Per-step metrics (only at day boundaries to avoid sub-daily noise)
            if model.time_manager.is_day_boundary or model.steps_per_day == 1:
                current_date = model.time_manager.formatted_time()
                ts = model.trout_state
                rs = model.redd_state

                # Shared redd/egg values (used by both daily_records and metrics)
                _redd_count = int(rs.alive.sum())
                _eggs_total = int(rs.num_eggs[rs.alive].sum()) if rs.alive.any() else 0

                for sp_idx, sp_name in enumerate(model.species_order):
                    mask = ts.alive & (ts.species_idx == sp_idx)
                    count = int(mask.sum())
                    daily_records.append(
                        {
                            "date": current_date,
                            "species": sp_name,
                            "alive": count,
                            "mean_length": float(ts.length[mask].mean())
                            if count > 0
                            else 0.0,
                            "mean_weight": float(ts.weight[mask].mean())
                            if count > 0
                            else 0.0,
                            "redd_count": _redd_count,
                            "eggs_total": _eggs_total,
                            "emerged_cumulative": emerged_total,
                            "outmigrants_cumulative": len(
                                getattr(model, "_outmigrants", [])
                            ),
                        }
                    )

                # --- Dashboard metrics snapshot ---
                if metrics_queue is not None:
                    alive_now = int(ts.alive.sum())
                    activity = ts.activity[ts.alive]
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
                    prev_alive_total = alive_now

                # --- Shared day index and alive mask ---
                # day_num is 1-based (first boundary fires after first step)
                day_num = (pd.Timestamp(current_date) - start).days
                alive_mask = ts.alive

                # --- Trajectory collection (0-based for animation timeline) ---
                if alive_mask.any():
                    alive_idx = np.where(alive_mask)[0]
                    trajectory_records.append(
                        pd.DataFrame(
                            {
                                "fish_idx": alive_idx,
                                "cell_idx": ts.cell_idx[alive_mask],
                                "species_idx": ts.species_idx[alive_mask],
                                "activity": ts.activity[alive_mask],
                                "life_history": ts.life_history[alive_mask],
                                "day_num": max(day_num - 1, 0),
                            }
                        )
                    )

                # Periodic snapshot (every 30 days + census days)
                dt = pd.Timestamp(current_date)
                is_census = any(
                    dt.month == int(s.split("-")[0]) and dt.day == int(s.split("-")[1])
                    for s in census_specs
                )
                if day_num % 30 == 0 or is_census:
                    if alive_mask.any():
                        snapshots[current_date] = pd.DataFrame(
                            {
                                "fish_idx": np.where(alive_mask)[0],
                                "species": [
                                    model.species_order[i]
                                    for i in ts.species_idx[alive_mask]
                                ],
                                "length": ts.length[alive_mask],
                                "weight": ts.weight[alive_mask],
                                "cell_idx": ts.cell_idx[alive_mask],
                            }
                        )

        # Final progress
        if progress_queue is not None:
            progress_queue.put((total_steps, total_steps))

        # --- Concatenate trajectory records ---
        trajectories = (
            pd.concat(trajectory_records, ignore_index=True)
            if trajectory_records
            else pd.DataFrame(
                columns=[
                    "fish_idx",
                    "cell_idx",
                    "species_idx",
                    "activity",
                    "life_history",
                    "day_num",
                ]
            )
        )

        # --- Build cells GeoDataFrame ---
        cells = _build_cells_gdf(model, raw)

        # --- Build redds DataFrame ---
        redds = _build_redds_df(model)

        # --- Daily DataFrame ---
        daily = pd.DataFrame(daily_records) if daily_records else pd.DataFrame()

        # --- Summary ---
        summary = {
            "final_date": model.time_manager.formatted_time(),
            "fish_alive": int(model.trout_state.alive.sum()),
            "redds_alive": int(model.redd_state.alive.sum()),
            "total_outmigrants": len(getattr(model, "_outmigrants", [])),
        }

        return {
            "daily": daily,
            "environment": environment,
            "cells": cells,
            "snapshots": snapshots,
            "trajectories": trajectories,
            "redds": redds,
            "config": raw,
            "summary": summary,
            "osm_sidecars": _load_osm_sidecars(model, raw),
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
        alt = (
            Path(model.data_dir)
            / "Shapefile"
            / Path(raw_config["spatial"]["mesh_file"]).name
        )
        if alt.exists():
            mesh_path = alt
    gdf = gpd.read_file(mesh_path)

    # Case-insensitive column rename using gis_properties
    gis = raw_config["spatial"]["gis_properties"]
    col_map = {}
    canonical_map = {
        "cell_id": "cell_id",
        "reach_name": "reach",
        "area": "area",
        "frac_spawn": "frac_spawn",
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

    # Fish count per cell at end of simulation (exclude marine fish with cell_idx=-1)
    ts = model.trout_state
    alive_cells = ts.cell_idx[ts.alive]
    alive_cells = alive_cells[alive_cells >= 0]
    fish_counts = np.bincount(alive_cells, minlength=n)[:n]
    gdf["fish_count"] = fish_counts

    # Keep only needed columns + geometry
    keep = [
        "cell_id",
        "reach",
        "geometry",
        "area",
        "depth",
        "velocity",
        "available_drift",
        "available_search",
        "fish_count",
        "frac_spawn",
    ]
    return gdf[[c for c in keep if c in gdf.columns]]


def _load_osm_sidecars(model, raw_config) -> dict:
    """Discover OSM-input sidecar shapefiles next to the mesh shapefile.

    v0.56.4 began emitting `<fixture>-<extender>-osm-{polygons,centerlines}.shp`
    files alongside the cell shapefile to preserve the original OSM input
    geometry used during fixture generation. This helper finds them and
    returns a mapping of layer-name → WGS84 GeoDataFrame for the spatial
    panel's optional overlay.

    Returns an empty dict when no sidecars exist (older fixtures).
    Glob is restricted to siblings of the mesh path so unrelated OSM
    shapefiles in nearby directories are not picked up.
    """
    mesh_path = Path(model.data_dir) / raw_config["spatial"]["mesh_file"]
    if not mesh_path.exists():
        alt = Path(model.data_dir) / "Shapefile" / Path(raw_config["spatial"]["mesh_file"]).name
        if alt.exists():
            mesh_path = alt
    sidecar_dir = mesh_path.parent
    sidecars: dict = {}
    for sidecar in sorted(sidecar_dir.glob("*-osm-*.shp")):
        try:
            gdf = gpd.read_file(sidecar)
        except Exception:
            continue
        if gdf.empty:
            continue
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        sidecars[sidecar.stem] = gdf
    return sidecars


def _value_to_rgba(values, cmap="viridis", alpha=160):
    """Map numeric values to [R, G, B, A] lists via matplotlib colormap."""
    import matplotlib

    values = np.asarray(values, dtype=float)
    mask = np.isfinite(values)
    result = [[0, 0, 0, 0] for _ in range(len(values))]

    if not mask.any():
        return result

    valid = values[mask]
    vmin, vmax = valid.min(), valid.max()
    if vmin == vmax:
        normed = np.full_like(valid, 0.5)
    else:
        normed = (valid - vmin) / (vmax - vmin)

    colormap = matplotlib.colormaps[cmap]
    colors = colormap(normed)
    result = list(result)
    idx = 0
    for i in range(len(values)):
        if mask[i]:
            r, g, b, _ = colors[idx]
            result[i] = [int(r * 255), int(g * 255), int(b * 255), alpha]
            idx += 1
    return result


_TAB10 = [
    [31, 119, 180],
    [255, 127, 14],
    [44, 160, 44],
    [214, 39, 40],
    [148, 103, 189],
    [140, 86, 75],
    [227, 119, 194],
    [127, 127, 127],
    [188, 189, 34],
    [23, 190, 207],
]
_ACTIVITY_COLORS = {
    0: [66, 133, 244],  # drift = blue
    1: [52, 168, 83],  # search = green
    2: [154, 160, 166],  # hide = gray
    3: [234, 67, 53],  # guard = red
    4: [251, 188, 4],  # hold = yellow
}
_LIFE_HISTORY_COLORS = {
    0: [0, 150, 136],  # resident = teal
    1: [0, 188, 212],  # anad_juve = cyan
    2: [255, 152, 0],  # anad_adult = orange
}


def _build_trajectories_data(traj_df, cells_gdf, species_order, color_mode="species"):
    """Convert trajectory DataFrame + cells GeoDataFrame into format for format_trips().

    Returns (paths, properties) — two parallel lists for format_trips().
    """
    if traj_df.empty:
        return [], []

    if cells_gdf.crs is not None and cells_gdf.crs.to_epsg() != 4326:
        gdf_wgs84 = cells_gdf.to_crs(epsg=4326)
    else:
        gdf_wgs84 = cells_gdf
    centroids = gdf_wgs84.geometry.centroid
    centroid_lut = np.column_stack([centroids.x, centroids.y])

    paths = []
    properties = []

    for fish_idx, group in traj_df.sort_values("day_num").groupby(
        "fish_idx", sort=False
    ):
        cell_indices = group["cell_idx"].values
        day_nums = group["day_num"].values

        if cell_indices.max() >= len(centroid_lut):
            raise ValueError(
                f"cell_idx {cell_indices.max()} out of range for centroid_lut "
                f"(size {len(centroid_lut)})"
            )
        coords = centroid_lut[cell_indices]
        path = [
            [float(coords[i, 0]), float(coords[i, 1]), int(day_nums[i])]
            for i in range(len(coords))
        ]

        last = group.iloc[-1]
        sp_idx = int(last["species_idx"])
        species_name = (
            species_order[sp_idx]
            if sp_idx < len(species_order)
            else f"species_{sp_idx}"
        )

        if color_mode == "activity":
            color = _ACTIVITY_COLORS.get(int(last["activity"]), [127, 127, 127])
        elif color_mode == "life_history":
            color = _LIFE_HISTORY_COLORS.get(int(last["life_history"]), [127, 127, 127])
        else:
            color = _TAB10[sp_idx % len(_TAB10)]

        props = {
            "fish_idx": int(fish_idx),
            "species": species_name,
            "activity": int(last["activity"]),
            "life_history": int(last["life_history"]),
            "color": [*color, 220],
        }

        paths.append(path)
        properties.append(props)

    return paths, properties


def _build_redds_df(model):
    """Build redds DataFrame from final ReddState."""
    rs = model.redd_state
    alive = rs.alive
    if not alive.any():
        return pd.DataFrame(
            columns=[
                "redd_idx",
                "species",
                "cell_idx",
                "eggs",
                "frac_developed",
                "eggs_lo_temp",
                "eggs_hi_temp",
                "eggs_dewatering",
                "eggs_scour",
            ]
        )
    indices = np.where(alive)[0]
    return pd.DataFrame(
        {
            "redd_idx": indices,
            "species": [model.species_order[i] for i in rs.species_idx[alive]],
            "cell_idx": rs.cell_idx[alive],
            "eggs": rs.num_eggs[alive],
            "frac_developed": rs.frac_developed[alive],
            "eggs_lo_temp": rs.eggs_lo_temp[alive],
            "eggs_hi_temp": rs.eggs_hi_temp[alive],
            "eggs_dewatering": rs.eggs_dewatering[alive],
            "eggs_scour": rs.eggs_scour[alive],
        }
    )
