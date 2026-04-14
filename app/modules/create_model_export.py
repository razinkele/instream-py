"""Export Create Model output: shapefile, YAML config, template CSVs, ZIP."""

import math
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from modules.create_model_utils import DEFAULT_REACH_PARAMS, TEMPLATE_FLOWS

# DBF column mapping (shapefile 10-char limit)
_COL_MAP = {
    "cell_id": "ID_TEXT",
    "reach_name": "REACH_NAME",
    "area": "AREA",
    "dist_escape": "M_TO_ESC",
    "num_hiding": "NUM_HIDING",
    "frac_vel_shelter": "FRACVSHL",
    "frac_spawn": "FRACSPWN",
}


def export_shapefile(
    cells_gdf: gpd.GeoDataFrame,
    output_dir: Path,
    model_name: str,
) -> Path:
    """Write cells GeoDataFrame as shapefile with DBF-safe column names.

    Returns path to the .shp file.
    """
    output_dir = Path(output_dir)
    shp_dir = output_dir / "Shapefile"
    shp_dir.mkdir(parents=True, exist_ok=True)

    gdf = cells_gdf[list(_COL_MAP.keys()) + ["geometry"]].copy()
    gdf = gdf.rename(columns=_COL_MAP)

    shp_path = shp_dir / f"{model_name}.shp"
    gdf.to_file(shp_path)
    return shp_path


def export_yaml(
    reaches: dict,
    cells_gdf: gpd.GeoDataFrame,
    model_name: str,
    species_params: dict,
    start_date: str,
    end_date: str,
    backend: str = "numpy",
    marine_enabled: bool = False,
) -> str:
    """Build YAML config string for an inSTREAM model.

    Parameters
    ----------
    reaches : dict
        ``{reach_name: {param_name: value, ...}}``.  User-set params override
        DEFAULT_REACH_PARAMS; unset params fall back to defaults.
    cells_gdf : gpd.GeoDataFrame
        Cells with ``reach_name`` column (used to count cells per reach).
    model_name : str
        Model name used in file references.
    species_params : dict
        Full species parameter dict (e.g. from ``load_species_preset``).
    start_date, end_date : str
        ISO date strings (YYYY-MM-DD).
    backend : str
        Performance backend (``"numpy"`` or ``"jax"``).
    marine_enabled : bool
        Whether to include a stub marine section.

    Returns
    -------
    str
        YAML text ready to write to file.
    """
    n_cells = len(cells_gdf)
    trout_cap = max(2000, n_cells * 15)

    config: dict = {
        "simulation": {
            "start_date": start_date,
            "end_date": end_date,
            "output_frequency": 1,
            "output_units": "days",
            "seed": 42,
            "census_days": ["06-15", "09-30"],
            "census_years_to_skip": 0,
        },
        "performance": {
            "backend": backend,
            "device": "cpu",
            "trout_capacity": trout_cap,
            "redd_capacity": max(500, n_cells * 4),
            "jit_warmup": False,
        },
        "spatial": {
            "backend": "shapefile",
            "mesh_file": f"Shapefile/{model_name}.shp",
            "gis_properties": {
                "cell_id": "ID_TEXT",
                "reach_name": "REACH_NAME",
                "area": "AREA",
                "dist_escape": "M_TO_ESC",
                "num_hiding_places": "NUM_HIDING",
                "frac_vel_shelter": "FRACVSHL",
                "frac_spawn": "FRACSPWN",
            },
        },
        "light": {
            "latitude": 55.7,
            "light_correction": 0.65,
            "light_at_night": 0.5,
            "twilight_angle": 6.0,
        },
    }

    # Species section
    if species_params:
        species_name = species_params.pop("_name", "Species1")
        config["species"] = {species_name: species_params}

    # Reaches section — merge user overrides onto defaults
    reaches_cfg: dict = {}
    junction_counter = 1
    reach_names = sorted(reaches.keys())
    for i, rname in enumerate(reach_names):
        user_params = reaches[rname]
        merged = dict(DEFAULT_REACH_PARAMS)
        for k, v in user_params.items():
            if k in merged:
                merged[k] = v
        merged["upstream_junction"] = junction_counter + i
        merged["downstream_junction"] = junction_counter + i + 1
        merged["time_series_input_file"] = f"{rname}-TimeSeriesInputs.csv"
        merged["depth_file"] = f"{rname}-Depths.csv"
        merged["velocity_file"] = f"{rname}-Vels.csv"
        reaches_cfg[rname] = merged

    config["reaches"] = reaches_cfg

    # Optional marine stub
    if marine_enabled:
        config["marine"] = {
            "zones": [
                {"name": "Estuary", "area_km2": 80},
                {"name": "Coastal", "area_km2": 800},
            ],
            "zone_connectivity": {
                "Estuary": ["Coastal"],
                "Coastal": ["Estuary"],
            },
            "smolt_min_length": 8.0,
            "return_min_sea_winters": 2,
        }

    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def _date_range_365(start_date: str) -> list[str]:
    """Return 365 ISO date strings starting from *start_date*."""
    d0 = date.fromisoformat(start_date)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(365)]


def export_template_csvs(
    reaches: dict,
    cells_gdf: gpd.GeoDataFrame,
    output_dir: Path,
    start_date: str,
) -> list[Path]:
    """Generate template CSV files (time-series, depths, velocities) per reach.

    Returns list of paths to created CSV files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    dates_365 = _date_range_365(start_date)
    flows = TEMPLATE_FLOWS

    for rname in sorted(reaches.keys()):
        reach_cells = cells_gdf[cells_gdf["reach_name"] == rname]
        cell_ids = list(reach_cells["cell_id"])
        n_cells = len(cell_ids)
        if n_cells == 0:
            continue

        # --- TimeSeriesInputs (365 rows) ---
        ts_path = output_dir / f"{rname}-TimeSeriesInputs.csv"
        ts_df = pd.DataFrame(
            {
                "date": dates_365,
                "flow": [5.0] * 365,
                "temperature": [10.0] * 365,
                "turbidity": [1.0] * 365,
            }
        )
        ts_df.to_csv(ts_path, index=False)
        created.append(ts_path)

        # --- Depths (10 flows x n_cells) ---
        depth_path = output_dir / f"{rname}-Depths.csv"
        depth_rows = []
        for flow in flows:
            row = {"flow": flow}
            for cid in cell_ids:
                cell_var = 0.8 + 0.4 * (hash(cid) % 100) / 100.0
                depth = (
                    0.3 + 0.7 * math.log(flow / 0.5 + 1) / math.log(1001)
                ) * cell_var
                row[cid] = round(depth, 4)
            depth_rows.append(row)
        pd.DataFrame(depth_rows).to_csv(depth_path, index=False)
        created.append(depth_path)

        # --- Velocities (10 flows x n_cells) ---
        vel_path = output_dir / f"{rname}-Vels.csv"
        vel_rows = []
        for flow in flows:
            row = {"flow": flow}
            for cid in cell_ids:
                cell_var = 0.8 + 0.4 * (hash(cid) % 100) / 100.0
                vel = (0.1 + 0.5 * flow / 50) * cell_var
                row[cid] = round(vel, 4)
            vel_rows.append(row)
        pd.DataFrame(vel_rows).to_csv(vel_path, index=False)
        created.append(vel_path)

    return created


def export_zip(
    cells_gdf: gpd.GeoDataFrame,
    reaches: dict,
    model_name: str,
    species_params: dict,
    output_dir: Path,
    start_date: str = "2020-01-01",
    end_date: str = "2025-12-31",
    backend: str = "numpy",
    marine_enabled: bool = False,
) -> Path:
    """Bundle shapefile + YAML + template CSVs into a ZIP archive.

    Returns path to the created ZIP file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / model_name
        tmp.mkdir()

        # 1. Shapefile
        export_shapefile(cells_gdf, tmp, model_name)

        # 2. YAML config
        yaml_text = export_yaml(
            reaches=reaches,
            cells_gdf=cells_gdf,
            model_name=model_name,
            species_params=dict(species_params),  # copy to avoid mutation
            start_date=start_date,
            end_date=end_date,
            backend=backend,
            marine_enabled=marine_enabled,
        )
        yaml_path = tmp / f"{model_name}.yaml"
        yaml_path.write_text(yaml_text, encoding="utf-8")

        # 3. Template CSVs
        export_template_csvs(reaches, cells_gdf, tmp, start_date)

        # 4. Create ZIP
        zip_stem = output_dir / model_name
        zip_path = Path(
            shutil.make_archive(str(zip_stem), "zip", root_dir=tmpdir, base_dir=model_name)
        )

    return zip_path
