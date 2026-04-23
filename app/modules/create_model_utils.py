"""Utilities for Create Model: CRS detection, reprojection, species presets."""

from pathlib import Path

import geopandas as gpd
import yaml


def detect_utm_epsg(center_lon: float, center_lat: float) -> int:
    """Auto-detect UTM zone EPSG code from WGS84 center coordinates."""
    zone = int((center_lon + 180) / 6) + 1
    if center_lat >= 0:
        return 32600 + zone
    return 32700 + zone


def reproject_gdf(gdf: gpd.GeoDataFrame, target_epsg: int) -> gpd.GeoDataFrame:
    """Reproject a GeoDataFrame to a target CRS."""
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    return gdf.to_crs(epsg=target_epsg)


SPECIES_PRESETS = {
    "Baltic Atlantic Salmon": "baltic_salmon_species.yaml",
    "Chinook Spring": "example_a.yaml",
}


def load_species_preset(preset_name: str, configs_dir: Path) -> dict:
    """Load species parameters from a preset YAML config."""
    filename = SPECIES_PRESETS.get(preset_name)
    if not filename:
        return {}
    path = configs_dir / filename
    if not path.exists():
        return {}
    with open(path) as f:
        raw = yaml.safe_load(f)
    species = raw.get("species", {})
    if species:
        return next(iter(species.values()))
    return {}


DEFAULT_REACH_PARAMS = {
    "drift_conc": 5.0e-9,
    "search_prod": 8.0e-7,
    "shelter_speed_frac": 0.3,
    "prey_energy_density": 4500,
    "drift_regen_distance": 1000,
    "shading": 0.8,
    "fish_pred_min": 0.97,
    "terr_pred_min": 0.94,
    "light_turbid_coef": 0.002,
    "light_turbid_const": 0.0,
    "max_spawn_flow": 20,
    "shear_A": 0.013,
    "shear_B": 0.40,
}

TEMPLATE_FLOWS = [0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0]
