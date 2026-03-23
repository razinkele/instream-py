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


def run_simulation(config_path, overrides=None, progress_queue=None, data_dir=None):
    """Run inSTREAM simulation and collect results.

    Runs synchronously — designed to be called from a worker thread
    via asyncio.run_in_executor().

    Args:
        config_path: Path to YAML config file.
        overrides: Dict of parameter overrides (nested, matching YAML structure).
        progress_queue: Optional queue.Queue for (step, total) progress updates.
        data_dir: Optional path to data directory. Defaults to config file's parent.

    Returns:
        dict with keys: daily, environment, cells, snapshots, redds, config, summary
    """
    from instream.model import InSTREAMModel

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
        environment = (
            pd.concat(env_frames, ignore_index=True) if env_frames else pd.DataFrame()
        )

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
                            "redd_count": int(rs.alive.sum()),
                            "eggs_total": int(rs.num_eggs[rs.alive].sum())
                            if rs.alive.any()
                            else 0,
                            "emerged_cumulative": emerged_total,
                            "outmigrants_cumulative": len(
                                getattr(model, "_outmigrants", [])
                            ),
                        }
                    )

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

    # Fish count per cell at end of simulation
    ts = model.trout_state
    alive_cells = ts.cell_idx[ts.alive]
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
