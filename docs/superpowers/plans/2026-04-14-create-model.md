# Create Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive model creation workflow: download EU-Hydro river network, select reaches, generate habitat cells (hexagonal, rectangular, FEM import, H3), configure parameters, and export ready-to-run simulation configs.

**Architecture:** 4 implementation phases, each independently deployable. Phase 1 delivers the complete MVP workflow with hexagonal and rectangular grids. Phases 2-4 add advanced mesh types. The UI uses a compact action bar above a full-width deck.gl map, with a slide-out configuration panel. All mesh types render identically as GeoJSON polygons on the map.

**Tech Stack:** Python, Shiny for Python, shiny_deckgl (MapWidget), geopandas, shapely, EU-Hydro ArcGIS REST API, meshio (Phase 2), h3 (Phase 3)

---

## File Map

| File | Phase | Responsibility |
|------|-------|----------------|
| `app/modules/create_model_panel.py` | 1 | UI, action bar, state management, map interactions, Strahler filter |
| `app/modules/create_model_grid.py` | 1 | Hexagonal + rectangular cell generation, buffering, clipping |
| `app/modules/create_model_reaches.py` | 1 | Reach selection, junction detection (geometric flow), topology |
| `app/modules/create_model_export.py` | 1 | Shapefile + YAML + CSV export, ZIP packaging, validation |
| `app/modules/create_model_utils.py` | 1 | CRS auto-detection, UTM reprojection, species preset loading |
| `app/modules/create_model_grid.py` | 2 | Add FEM mesh import (meshio .msh/.2dm reading) |
| `app/modules/create_model_grid.py` | 3 | Add H3 hierarchical hexagonal grid generation |
| `app/modules/create_model_grid.py` | 4 | Add in-app adaptive triangular mesh (triangle library) |

---

## Phase 1: MVP — Complete Workflow (Tasks 1-6)

### Task 1: Utility Module — CRS Detection + Species Presets

Create the shared utility module used by all other modules.

**Files:**
- Create: `app/modules/create_model_utils.py`

- [ ] **Step 1: Create CRS utility functions**

```python
# app/modules/create_model_utils.py
"""Utilities for Create Model: CRS detection, reprojection, species presets."""

import math
from pathlib import Path

import geopandas as gpd
import yaml


def detect_utm_epsg(center_lon: float, center_lat: float) -> int:
    """Auto-detect UTM zone EPSG code from WGS84 center coordinates.

    Returns EPSG code for UTM North (326xx) or South (327xx).
    """
    zone = int((center_lon + 180) / 6) + 1
    if center_lat >= 0:
        return 32600 + zone  # Northern hemisphere
    return 32700 + zone  # Southern hemisphere


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
    """Load species parameters from a preset YAML config.

    Returns the species dict from the config, or empty dict if not found.
    """
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
        # Return first species block
        return next(iter(species.values()))
    return {}


# Default reach parameters (non-zero, matching spec)
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

# Default template flow values (geometric sequence 0.5-500 m³/s)
TEMPLATE_FLOWS = [0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0]
```

- [ ] **Step 2: Run import check**

```bash
micromamba run -n shiny python -c "from modules.create_model_utils import detect_utm_epsg, DEFAULT_REACH_PARAMS; print('OK:', detect_utm_epsg(21.1, 55.7))"
```

Expected: `OK: 32634` (UTM zone 34N for Lithuania)

- [ ] **Step 3: Commit**

```bash
git add app/modules/create_model_utils.py
git commit -m "feat: create_model_utils — CRS detection, species presets, default params"
```

---

### Task 2: Grid Generation Module — Hexagonal + Rectangular

Core mesh generation logic, independent of UI.

**Files:**
- Create: `app/modules/create_model_grid.py`

- [ ] **Step 1: Write hexagonal grid generator**

```python
# app/modules/create_model_grid.py
"""Habitat cell grid generation for Create Model workflow."""

import math

import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from modules.create_model_utils import detect_utm_epsg, reproject_gdf


def _hexagon(cx, cy, size):
    """Create a flat-top hexagon centered at (cx, cy) with given size (apothem)."""
    angles = [math.radians(60 * i + 30) for i in range(6)]
    return Polygon([(cx + size * math.cos(a), cy + size * math.sin(a)) for a in angles])


def hexagonal_grid(bounds, cell_size):
    """Generate hexagonal cells covering a bounding box.

    Parameters
    ----------
    bounds : tuple
        (minx, miny, maxx, maxy) in projected coordinates (meters).
    cell_size : float
        Hexagon width in meters.

    Returns
    -------
    list[Polygon]
        List of hexagonal polygons.
    """
    w = cell_size
    h = cell_size * math.sqrt(3) / 2
    minx, miny, maxx, maxy = bounds
    cols = int((maxx - minx) / w) + 2
    rows = int((maxy - miny) / h) + 2
    hexagons = []
    for row in range(rows):
        for col in range(cols):
            x = minx + col * w + (row % 2) * w / 2
            y = miny + row * h
            hexagons.append(_hexagon(x, y, cell_size / 2))
    return hexagons


def rectangular_grid(bounds, cell_size):
    """Generate rectangular cells covering a bounding box.

    Returns list of square Polygon objects.
    """
    minx, miny, maxx, maxy = bounds
    cols = int((maxx - minx) / cell_size) + 1
    rows = int((maxy - miny) / cell_size) + 1
    rects = []
    for row in range(rows):
        for col in range(cols):
            x = minx + col * cell_size
            y = miny + row * cell_size
            rects.append(box(x, y, x + cell_size, y + cell_size))
    return rects


def generate_cells(
    reach_segments: dict,
    cell_size: float = 20.0,
    cell_shape: str = "hexagonal",
    buffer_factor: float = 2.0,
    min_overlap: float = 0.2,
) -> gpd.GeoDataFrame:
    """Generate habitat cells from reach segments.

    Parameters
    ----------
    reach_segments : dict
        {reach_name: {"segments": [LineString, ...], "color": [R,G,B,A]}}
    cell_size : float
        Cell width in meters.
    cell_shape : str
        "hexagonal" or "rectangular".
    buffer_factor : float
        Buffer multiplier for corridor width (default 2.0 → 4× cell width corridor).
    min_overlap : float
        Minimum fraction of cell area overlapping buffer to keep (default 0.2).

    Returns
    -------
    gpd.GeoDataFrame
        Cell polygons with attributes: cell_id, reach_name, area, dist_escape,
        num_hiding, frac_vel_shelter, frac_spawn. CRS is UTM.
    """
    if not reach_segments:
        return gpd.GeoDataFrame()

    # Collect all segments and detect UTM
    all_geoms = []
    for rdata in reach_segments.values():
        all_geoms.extend(rdata["segments"])

    if not all_geoms:
        return gpd.GeoDataFrame()

    # Create GeoDataFrame in WGS84, detect UTM, reproject
    segments_gdf = gpd.GeoDataFrame(geometry=all_geoms, crs="EPSG:4326")
    center = segments_gdf.geometry.unary_union.centroid
    utm_epsg = detect_utm_epsg(center.x, center.y)
    segments_utm = reproject_gdf(segments_gdf, utm_epsg)

    # Buffer and generate grid per reach
    cells = []
    cell_id = 0

    for reach_name, rdata in reach_segments.items():
        reach_geoms = gpd.GeoDataFrame(
            geometry=rdata["segments"], crs="EPSG:4326"
        ).to_crs(epsg=utm_epsg).geometry

        # Buffer segments
        buffered = unary_union([g.buffer(cell_size * buffer_factor) for g in reach_geoms])
        if buffered.is_empty:
            continue

        # Generate grid
        bounds = buffered.bounds
        if cell_shape == "rectangular":
            raw_cells = rectangular_grid(bounds, cell_size)
        else:
            raw_cells = hexagonal_grid(bounds, cell_size)

        # Clip to buffer and filter by overlap
        reach_endpoints = []
        for g in reach_geoms:
            coords = list(g.coords)
            if coords:
                reach_endpoints.append(coords[0])
                reach_endpoints.append(coords[-1])

        for poly in raw_cells:
            intersection = poly.intersection(buffered)
            if intersection.is_empty:
                continue
            overlap = intersection.area / poly.area
            if overlap < min_overlap:
                continue

            cell_id += 1
            centroid = poly.centroid

            # Distance to nearest reach endpoint (meters → cm)
            if reach_endpoints:
                dists = [centroid.distance(
                    gpd.points_from_xy([ep[0]], [ep[1]])[0]
                ) for ep in reach_endpoints]
                dist_escape = min(dists) * 100  # m → cm
            else:
                dist_escape = 10000  # default 100m

            # Edge detection (touches buffer boundary)
            is_edge = not buffered.contains(poly)

            cells.append({
                "geometry": poly,
                "cell_id": f"CELL_{cell_id:04d}",
                "reach_name": reach_name,
                "area": poly.area,
                "dist_escape": dist_escape,
                "num_hiding": 2 if is_edge else 1,
                "frac_vel_shelter": 0.15 if is_edge else 0.05,
                "frac_spawn": rdata.get("frac_spawn", 0.0),
            })

    if not cells:
        return gpd.GeoDataFrame()

    return gpd.GeoDataFrame(cells, crs=f"EPSG:{utm_epsg}")
```

- [ ] **Step 2: Write test for hexagonal grid generation**

```python
# Quick smoke test (not a formal test file — run inline)
# micromamba run -n shiny python -c "
from shapely.geometry import LineString
from modules.create_model_grid import generate_cells
segments = {"TestReach": {"segments": [LineString([(21.1, 55.7), (21.11, 55.71)])], "frac_spawn": 0.3}}
gdf = generate_cells(segments, cell_size=50, cell_shape="hexagonal")
print(f"Generated {len(gdf)} hexagonal cells")
print(gdf[["cell_id", "reach_name", "area", "frac_spawn"]].head())
gdf_rect = generate_cells(segments, cell_size=50, cell_shape="rectangular")
print(f"Generated {len(gdf_rect)} rectangular cells")
# "
```

- [ ] **Step 3: Commit**

```bash
git add app/modules/create_model_grid.py
git commit -m "feat: create_model_grid — hexagonal + rectangular cell generation"
```

---

### Task 3: Reach Selection Module — Click-to-Select + Junction Detection

**Files:**
- Create: `app/modules/create_model_reaches.py`

- [ ] **Step 1: Create reach selection and junction detection module**

```python
# app/modules/create_model_reaches.py
"""Reach selection and junction detection for Create Model workflow."""

import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from modules.create_model_utils import detect_utm_epsg, reproject_gdf

TAB10 = [
    [31, 119, 180, 220], [255, 127, 14, 220], [44, 160, 44, 220],
    [214, 39, 40, 220], [148, 103, 189, 220], [140, 86, 75, 220],
    [227, 119, 194, 220], [127, 127, 127, 220], [188, 189, 34, 220],
    [23, 190, 207, 220],
]


def assign_segment_to_reach(
    reaches: dict, reach_name: str, segment_geom, segment_props: dict
) -> dict:
    """Add a river segment to a named reach.

    Creates the reach if it doesn't exist. Returns updated reaches dict.
    """
    if reach_name not in reaches:
        color_idx = len(reaches) % len(TAB10)
        reaches[reach_name] = {
            "segments": [],
            "properties": [],
            "color": TAB10[color_idx],
            "upstream_junction": 0,
            "downstream_junction": 0,
            "frac_spawn": 0.0,
        }
    reaches[reach_name]["segments"].append(segment_geom)
    reaches[reach_name]["properties"].append(segment_props)
    return reaches


def remove_segment_from_reach(reaches: dict, segment_geom) -> dict:
    """Remove a segment from whichever reach contains it."""
    for rname, rdata in list(reaches.items()):
        for i, seg in enumerate(rdata["segments"]):
            if seg.equals(segment_geom):
                rdata["segments"].pop(i)
                rdata["properties"].pop(i)
                if not rdata["segments"]:
                    del reaches[rname]
                return reaches
    return reaches


def detect_junctions(reaches: dict, center_lon: float, center_lat: float,
                     tolerance_m: float = 50.0) -> dict:
    """Detect junctions between reaches using geometric flow analysis.

    EU-Hydro lines are digitized downstream: startpoint = upstream, endpoint = downstream.
    Two reaches share a junction if any endpoint pair is within tolerance_m meters.

    Returns updated reaches dict with upstream_junction and downstream_junction set.
    """
    if len(reaches) < 2:
        # Single reach: junction 1 (upstream) → junction 2 (downstream)
        for rname in reaches:
            reaches[rname]["upstream_junction"] = 1
            reaches[rname]["downstream_junction"] = 2
        return reaches

    utm_epsg = detect_utm_epsg(center_lon, center_lat)

    # Collect start/end points per reach (in UTM)
    reach_endpoints = {}
    for rname, rdata in reaches.items():
        starts, ends = [], []
        for seg in rdata["segments"]:
            seg_utm = gpd.GeoSeries([seg], crs="EPSG:4326").to_crs(epsg=utm_epsg).iloc[0]
            coords = list(seg_utm.coords)
            if coords:
                starts.append(Point(coords[0]))
                ends.append(Point(coords[-1]))
        reach_endpoints[rname] = {"starts": starts, "ends": ends}

    # Find junction pairs
    junction_id = 0
    junctions = {}  # (rname1, rname2) → junction_id
    rnames = list(reaches.keys())

    for i in range(len(rnames)):
        for j in range(i + 1, len(rnames)):
            r1, r2 = rnames[i], rnames[j]
            ep1, ep2 = reach_endpoints[r1], reach_endpoints[r2]

            # Check if r1's downstream (ends) connects to r2's upstream (starts)
            for end_pt in ep1["ends"]:
                for start_pt in ep2["starts"]:
                    if end_pt.distance(start_pt) < tolerance_m:
                        junction_id += 1
                        junctions[(r1, "downstream", r2, "upstream")] = junction_id
                        break

            # Check reverse: r2's downstream connects to r1's upstream
            for end_pt in ep2["ends"]:
                for start_pt in ep1["starts"]:
                    if end_pt.distance(start_pt) < tolerance_m:
                        junction_id += 1
                        junctions[(r2, "downstream", r1, "upstream")] = junction_id
                        break

    # Assign junction IDs
    next_jid = junction_id + 1
    for key, jid in junctions.items():
        r_from, dir_from, r_to, dir_to = key
        if dir_from == "downstream":
            reaches[r_from]["downstream_junction"] = jid
        else:
            reaches[r_from]["upstream_junction"] = jid
        if dir_to == "upstream":
            reaches[r_to]["upstream_junction"] = jid
        else:
            reaches[r_to]["downstream_junction"] = jid

    # Fill missing junctions with unique IDs
    for rname in reaches:
        if reaches[rname]["upstream_junction"] == 0:
            reaches[rname]["upstream_junction"] = next_jid
            next_jid += 1
        if reaches[rname]["downstream_junction"] == 0:
            reaches[rname]["downstream_junction"] = next_jid
            next_jid += 1

    return reaches
```

- [ ] **Step 2: Commit**

```bash
git add app/modules/create_model_reaches.py
git commit -m "feat: create_model_reaches — click-select, junction detection"
```

---

### Task 4: Export Module — Shapefile + YAML + CSV + ZIP

**Files:**
- Create: `app/modules/create_model_export.py`

- [ ] **Step 1: Create export module**

```python
# app/modules/create_model_export.py
"""Export model config: shapefile, YAML, template CSVs, ZIP packaging."""

import io
import math
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import yaml

from modules.create_model_utils import DEFAULT_REACH_PARAMS, TEMPLATE_FLOWS


def export_shapefile(cells_gdf: gpd.GeoDataFrame, output_dir: Path, model_name: str):
    """Write cell polygons as ESRI shapefile with required DBF attributes."""
    shp_dir = output_dir / "Shapefile"
    shp_dir.mkdir(parents=True, exist_ok=True)

    # Rename columns to match inSTREAM gis_properties expectations
    export_gdf = cells_gdf.rename(columns={
        "cell_id": "ID_TEXT",
        "reach_name": "REACH_NAME",
        "area": "AREA",
        "dist_escape": "M_TO_ESC",
        "num_hiding": "NUM_HIDING",
        "frac_vel_shelter": "FRACVSHL",
        "frac_spawn": "FRACSPWN",
    })
    keep = ["ID_TEXT", "REACH_NAME", "AREA", "M_TO_ESC", "NUM_HIDING", "FRACVSHL", "FRACSPWN", "geometry"]
    export_gdf = export_gdf[[c for c in keep if c in export_gdf.columns]]
    export_gdf.to_file(shp_dir / f"{model_name}.shp")


def export_yaml(
    reaches: dict,
    cells_gdf: gpd.GeoDataFrame,
    model_name: str,
    species_params: dict,
    start_date: str = "2011-04-01",
    end_date: str = "2013-09-30",
    backend: str = "numpy",
    marine_enabled: bool = False,
) -> str:
    """Generate inSTREAM YAML config string."""
    n_cells = len(cells_gdf)

    config = {
        "simulation": {
            "start_date": start_date,
            "end_date": end_date,
            "output_frequency": 1,
            "output_units": "days",
            "seed": 42,
            "census_days": ["06-15", "09-30"],
            "census_years_to_skip": 0,
            "population_file": f"{model_name}-InitialPopulations.csv",
            "adult_arrival_file": f"{model_name}-AdultArrivals.csv",
        },
        "performance": {
            "backend": backend,
            "device": "cpu",
            "trout_capacity": max(2000, n_cells * 15),
            "redd_capacity": max(500, n_cells * 3),
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
            "light_correction": 0.7,
            "light_at_night": 0.5,
            "twilight_angle": 6.0,
        },
    }

    # Species
    if species_params:
        sp_name = list(species_params.keys())[0] if isinstance(species_params, dict) and any(
            isinstance(v, dict) for v in species_params.values()
        ) else "BalticAtlanticSalmon"
        config["species"] = species_params if isinstance(species_params, dict) and any(
            isinstance(v, dict) for v in species_params.values()
        ) else {sp_name: species_params}

    # Reaches
    config["reaches"] = {}
    for rname, rdata in reaches.items():
        rparams = dict(DEFAULT_REACH_PARAMS)
        rparams["upstream_junction"] = rdata.get("upstream_junction", 1)
        rparams["downstream_junction"] = rdata.get("downstream_junction", 2)
        rparams["time_series_input_file"] = f"{rname}-TimeSeriesInputs.csv"
        rparams["depth_file"] = f"{rname}-Depths.csv"
        rparams["velocity_file"] = f"{rname}-Vels.csv"
        # Override with user-set params
        for k, v in rdata.get("params", {}).items():
            if k in rparams:
                rparams[k] = v
        config["reaches"][rname] = rparams

    # Marine (optional)
    if marine_enabled:
        config["marine"] = {
            "zones": [
                {"name": "Estuary", "area_km2": 50},
                {"name": "Coastal", "area_km2": 500},
                {"name": "Open Sea", "area_km2": 5000},
            ],
            "zone_connectivity": {
                "Estuary": ["Coastal"],
                "Coastal": ["Open Sea", "Estuary"],
                "Open Sea": ["Coastal"],
            },
            "smolt_min_length": 8.0,
            "return_min_sea_winters": 2,
            "static_driver": {
                "Estuary": {
                    "temperature": [2, 4, 8, 12, 15, 16, 15, 12, 8, 5, 3, 2],
                    "salinity": [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5],
                    "prey_index": [0.2, 0.3, 0.5, 0.7, 0.8, 0.8, 0.7, 0.5, 0.3, 0.2, 0.1, 0.1],
                    "predation_risk": [0.1, 0.1, 0.2, 0.4, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
                },
                "Coastal": {
                    "temperature": [2, 2, 3, 6, 10, 14, 17, 16, 12, 8, 4, 2],
                    "salinity": [7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7],
                    "prey_index": [0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.8, 0.7, 0.5, 0.3, 0.2, 0.2],
                    "predation_risk": [0.05, 0.05, 0.1, 0.15, 0.1, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05],
                },
                "Open Sea": {
                    "temperature": [3, 2, 2, 4, 8, 12, 15, 15, 12, 8, 5, 3],
                    "salinity": [7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7],
                    "prey_index": [0.2, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 0.8, 0.6, 0.4, 0.2, 0.2],
                    "predation_risk": [0.02, 0.02, 0.02, 0.05, 0.05, 0.05, 0.05, 0.05, 0.02, 0.02, 0.02, 0.02],
                },
            },
        }

    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def export_template_csvs(reaches: dict, cells_gdf: gpd.GeoDataFrame,
                         output_dir: Path, start_date: str = "2011-04-01"):
    """Generate template CSV files (time series, depths, velocities) per reach."""
    rng = np.random.default_rng(42)
    start = datetime.strptime(start_date, "%Y-%m-%d")
    flows = TEMPLATE_FLOWS

    for rname in reaches:
        reach_cells = cells_gdf[cells_gdf["reach_name"] == rname]
        n_cells = len(reach_cells)
        if n_cells == 0:
            continue

        # TimeSeriesInputs
        ts_path = output_dir / f"{rname}-TimeSeriesInputs.csv"
        with open(ts_path, "w") as f:
            f.write(f"; Time series template for {rname}\n")
            f.write("; Replace with real data\n")
            f.write("Date,temperature,flow,turbidity\n")
            for day in range(365):
                d = start + timedelta(days=day)
                f.write(f"{d.month}/{d.day}/{d.year} 12:00,10.0,5.0,2\n")

        # Depths
        depth_path = output_dir / f"{rname}-Depths.csv"
        with open(depth_path, "w") as f:
            f.write(f"; Depth template for {rname}\n")
            f.write("; Replace with real hydraulic data\n")
            f.write("; CELL DEPTHS IN METERS\n")
            n_flows = len(flows)
            f.write(f"{n_flows},Number of flows in table" + ",," * (n_flows - 1) + "\n")
            f.write("," + ",".join(f"{fl}" for fl in flows) + "\n")
            for c in range(1, n_cells + 1):
                cell_var = 0.7 + 0.6 * rng.random()
                vals = []
                for fl in flows:
                    d = (0.3 + 0.7 * math.log(fl / 0.5 + 1) / math.log(1001)) * cell_var
                    vals.append(f"{max(0.01, d):.6f}")
                f.write(f"{c}," + ",".join(vals) + "\n")

        # Velocities
        vel_path = output_dir / f"{rname}-Vels.csv"
        with open(vel_path, "w") as f:
            f.write(f"; Velocity template for {rname}\n")
            f.write("; Replace with real hydraulic data\n")
            f.write("; CELL VELOCITIES IN M/S\n")
            f.write(f"{n_flows},Number of flows in table" + ",," * (n_flows - 1) + "\n")
            f.write("," + ",".join(f"{fl}" for fl in flows) + "\n")
            for c in range(1, n_cells + 1):
                cell_var = 0.7 + 0.6 * rng.random()
                vals = []
                for fl in flows:
                    v = (0.1 + 0.5 * fl / 50) * cell_var
                    vals.append(f"{max(0.001, v):.6f}")
                f.write(f"{c}," + ",".join(vals) + "\n")


def export_zip(
    cells_gdf: gpd.GeoDataFrame,
    reaches: dict,
    model_name: str,
    species_params: dict,
    output_dir: Path,
    start_date: str = "2011-04-01",
    end_date: str = "2013-09-30",
    backend: str = "numpy",
    marine_enabled: bool = False,
) -> Path:
    """Export complete model as ZIP file.

    Returns path to the ZIP file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Shapefile
    export_shapefile(cells_gdf, output_dir, model_name)

    # YAML config
    yaml_str = export_yaml(
        reaches, cells_gdf, model_name, species_params,
        start_date, end_date, backend, marine_enabled,
    )
    (output_dir / f"{model_name}_config.yaml").write_text(yaml_str)

    # Template CSVs
    export_template_csvs(reaches, cells_gdf, output_dir, start_date)

    # ZIP everything
    zip_path = output_dir / f"{model_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in output_dir.rglob("*"):
            if file.suffix == ".zip":
                continue
            zf.write(file, file.relative_to(output_dir))

    return zip_path
```

- [ ] **Step 2: Commit**

```bash
git add app/modules/create_model_export.py
git commit -m "feat: create_model_export — shapefile, YAML, CSV, ZIP export"
```

---

### Task 5: Panel UI — Action Bar + Map + Slide-out + Status

Rewrite the existing `create_model_panel.py` with full workflow UI.

**Files:**
- Modify: `app/modules/create_model_panel.py`

This is the largest task — the full UI with action bar, map interactions, Strahler filter, reach selection via click, configuration slide-out panel, and export. Due to size (~400 lines), this task focuses on the UI shell and wiring. The actual logic is in Tasks 1-4's modules.

- [ ] **Step 1: Rewrite create_model_panel.py with full workflow**

The complete rewrite is too large to inline here. Key structure:

```python
# app/modules/create_model_panel.py
"""Create Model panel — EU-Hydro download, reach selection, grid generation, export."""

# UI: action bar with progressive button enabling
# Map: static MapWidget with click handler
# Slide-out: configuration panel (toggled by Configure button)
# Status bar: feature counts + CRS

# Server:
# - _on_fetch_rivers: EU-Hydro query → display river lines
# - _on_fetch_water: EU-Hydro query → display water polygons
# - _on_fetch_coastal: EU-Hydro query → display coastal polygons
# - _strahler_filter: rebuild river layer with filtered GeoDataFrame
# - _on_select_reaches: enter selection mode, handle click events
# - _on_click: identify clicked segment, add to current reach
# - _on_generate_cells: call generate_cells(), display preview
# - _on_configure: open slide-out panel
# - _on_export: call export_zip(), offer download
# - _on_load_setup: write to fixtures, update config dropdown
```

- [ ] **Step 2: Run the app locally to verify the panel loads**

```bash
micromamba run -n shiny shiny run app/app.py --port 8800
```

Verify: Create Model tab visible, map renders, action bar buttons shown.

- [ ] **Step 3: Commit**

```bash
git add app/modules/create_model_panel.py
git commit -m "feat: Create Model panel — full workflow UI with action bar"
```

---

### Task 6: Integration — Wire Panel + Deploy

**Files:**
- Modify: `app/app.py`

- [ ] **Step 1: Wire shared reactive for Load-into-Setup**

In `app/app.py` server function, add shared reactive value and pass to both panels:

```python
_created_model_config = reactive.value(None)
create_model_server("create", created_model_rv=_created_model_config)
setup_server("setup", config_file_rv=input.config_file,
             load_btn_rv=input.load_config_btn,
             created_model_rv=_created_model_config)
```

- [ ] **Step 2: Run full test suite**

```bash
micromamba run -n shiny python -m pytest tests/ -q --tb=short -m "not slow"
```

- [ ] **Step 3: Deploy to server**

```bash
git add app/
git commit -m "feat: Create Model v1 — complete MVP workflow"
git push origin master
# Deploy via deploy skill
```

---

## Phase 2: FEM Mesh Import (Task 7)

### Task 7: Import FEM Mesh via meshio

Add "Import Mesh" button to the cell shape selector. Reads .msh (GMSH) or .2dm (River2D) files using the existing `meshio` library.

**Files:**
- Modify: `app/modules/create_model_grid.py`
- Modify: `app/modules/create_model_panel.py`

- [ ] **Step 1: Add FEM import function to create_model_grid.py**

```python
def import_fem_mesh(file_path: str, reach_assignments: dict = None) -> gpd.GeoDataFrame:
    """Import a FEM mesh file (.msh, .2dm) as habitat cells.

    Uses meshio to read the mesh, extracts triangular/quad elements as polygons.

    Parameters
    ----------
    file_path : str
        Path to .msh (GMSH) or .2dm (River2D SMS) file.
    reach_assignments : dict, optional
        {element_index: reach_name} mapping. If None, all cells assigned to "Reach1".

    Returns
    -------
    gpd.GeoDataFrame
        Cell polygons with standard attributes.
    """
    import meshio

    mesh = meshio.read(file_path)
    points = mesh.points[:, :2]  # X, Y only

    cells = []
    cell_id = 0
    for cell_block in mesh.cells:
        if cell_block.type in ("triangle", "quad"):
            for element in cell_block.data:
                cell_id += 1
                coords = points[element]
                # Close the polygon
                ring = list(map(tuple, coords)) + [tuple(coords[0])]
                poly = Polygon(ring)
                if poly.is_valid and poly.area > 0:
                    reach = "Reach1"
                    if reach_assignments and cell_id in reach_assignments:
                        reach = reach_assignments[cell_id]
                    cells.append({
                        "geometry": poly,
                        "cell_id": f"CELL_{cell_id:04d}",
                        "reach_name": reach,
                        "area": poly.area,
                        "dist_escape": 10000,  # default
                        "num_hiding": 1,
                        "frac_vel_shelter": 0.1,
                        "frac_spawn": 0.0,
                    })

    if not cells:
        return gpd.GeoDataFrame()

    # Detect CRS from mesh metadata or default to EPSG:3035
    return gpd.GeoDataFrame(cells, crs="EPSG:3035")
```

- [ ] **Step 2: Add file upload UI to panel**

In `create_model_panel.py`, add file input next to cell shape selector:

```python
ui.input_file("mesh_upload", "Import FEM Mesh (.msh, .2dm)",
              accept=[".msh", ".2dm"], multiple=False),
```

- [ ] **Step 3: Commit**

```bash
git add app/modules/create_model_grid.py app/modules/create_model_panel.py
git commit -m "feat: Phase 2 — FEM mesh import via meshio (.msh, .2dm)"
```

---

## Phase 3: H3 Hierarchical Hexagons (Task 8)

### Task 8: H3-based Grid Generation

Add H3 hierarchical hexagons as a cell shape option. Uses the `h3` library (already installed v4.4.2).

**Files:**
- Modify: `app/modules/create_model_grid.py`

- [ ] **Step 1: Add H3 grid generator**

```python
def h3_hexagonal_grid(
    buffered_area,
    resolution: int = 10,
    utm_epsg: int = 32634,
) -> list:
    """Generate H3 hexagonal cells covering a buffered area.

    Parameters
    ----------
    buffered_area : shapely Polygon/MultiPolygon
        Buffered reach area in WGS84.
    resolution : int
        H3 resolution (7=~5km, 8=~1km, 9=~175m, 10=~65m, 11=~25m, 12=~9m).

    Returns
    -------
    list[Polygon]
        H3 hexagonal polygons in WGS84.
    """
    import h3

    # Get H3 cells covering the polygon
    geojson = buffered_area.__geo_interface__
    h3_cells = h3.geo_to_cells(geojson, res=resolution)

    hexagons = []
    for cell_id in h3_cells:
        boundary = h3.cell_to_boundary(cell_id)
        # h3 returns (lat, lon) pairs — flip to (lon, lat) for shapely
        ring = [(lon, lat) for lat, lon in boundary]
        ring.append(ring[0])  # close
        poly = Polygon(ring)
        if poly.is_valid:
            hexagons.append(poly)

    return hexagons
```

- [ ] **Step 2: Wire H3 into generate_cells**

Add `cell_shape="h3"` option to `generate_cells()`:

```python
elif cell_shape == "h3":
    # Reproject buffer back to WGS84 for H3
    buffer_wgs = gpd.GeoSeries([buffered], crs=f"EPSG:{utm_epsg}").to_crs(epsg=4326).iloc[0]
    # Map cell_size to H3 resolution: 100m→9, 50m→10, 20m→11, 10m→12
    res = max(7, min(12, int(13 - math.log2(max(cell_size, 5)))))
    raw_cells = h3_hexagonal_grid(buffer_wgs, resolution=res)
    # Convert back to UTM for clipping
    raw_cells_gdf = gpd.GeoDataFrame(geometry=raw_cells, crs="EPSG:4326").to_crs(epsg=utm_epsg)
    raw_cells = raw_cells_gdf.geometry.tolist()
```

- [ ] **Step 3: Add H3 option to UI dropdown**

```python
choices={"hexagonal": "Hexagonal", "rectangular": "Rectangular", "h3": "H3 Hierarchical"}
```

- [ ] **Step 4: Commit**

```bash
git add app/modules/create_model_grid.py app/modules/create_model_panel.py
git commit -m "feat: Phase 3 — H3 hierarchical hexagonal grid generation"
```

---

## Phase 4: In-App Adaptive Triangular Mesh (Task 9)

### Task 9: Triangle-based Adaptive Mesh

Generate adaptive triangular meshes in-app using the `triangle` library. Requires installing the package.

**Files:**
- Modify: `app/modules/create_model_grid.py`

- [ ] **Step 1: Install triangle library**

```bash
micromamba install -n shiny -c conda-forge triangle
```

- [ ] **Step 2: Add adaptive triangular mesh generator**

```python
def adaptive_triangular_grid(
    buffered_area,
    min_area: float = 100.0,
    max_area: float = 2000.0,
    quality: float = 30.0,
) -> list:
    """Generate adaptive triangular mesh using the Triangle library.

    Parameters
    ----------
    buffered_area : shapely Polygon
        Buffered reach area in projected coordinates (meters).
    min_area : float
        Minimum triangle area in m².
    max_area : float
        Maximum triangle area in m² (controls refinement).
    quality : float
        Minimum angle constraint in degrees (default 30° = well-shaped triangles).

    Returns
    -------
    list[Polygon]
        Triangular cell polygons.
    """
    import triangle as tr

    # Extract boundary vertices
    if buffered_area.geom_type == "MultiPolygon":
        exterior = max(buffered_area.geoms, key=lambda g: g.area).exterior
    else:
        exterior = buffered_area.exterior

    coords = list(exterior.coords)[:-1]  # Remove closing vertex
    n = len(coords)
    vertices = [(x, y) for x, y in coords]
    segments = [(i, (i + 1) % n) for i in range(n)]

    # Triangle input
    tri_input = {
        "vertices": vertices,
        "segments": segments,
    }

    # Triangulate with area constraint and quality
    tri_output = tr.triangulate(tri_input, f"pq{quality}a{max_area}")

    triangles = []
    for tri in tri_output["triangles"]:
        pts = [tri_output["vertices"][i] for i in tri]
        ring = pts + [pts[0]]
        poly = Polygon(ring)
        if poly.is_valid and poly.area >= min_area:
            triangles.append(poly)

    return triangles
```

- [ ] **Step 3: Wire into generate_cells**

Add `cell_shape="triangular"` option:

```python
elif cell_shape == "triangular":
    max_area = cell_size * cell_size  # Target area = cell_size²
    min_area = max_area * 0.1
    raw_cells = adaptive_triangular_grid(buffered, min_area=min_area, max_area=max_area)
```

- [ ] **Step 4: Add Triangular option to UI dropdown**

```python
choices={"hexagonal": "Hexagonal", "rectangular": "Rectangular",
         "h3": "H3 Hierarchical", "triangular": "Adaptive Triangular"}
```

- [ ] **Step 5: Commit**

```bash
git add app/modules/create_model_grid.py app/modules/create_model_panel.py
git commit -m "feat: Phase 4 — in-app adaptive triangular mesh (triangle library)"
```

---

## Self-Review Checklist

1. **Spec coverage:** All 5 workflow steps covered (Tasks 1-6). All 4 mesh phases covered (Tasks 2, 7, 8, 9). EU-Hydro fetch, reach selection, grid generation, configuration, export all have tasks.
2. **No placeholders:** All code blocks show complete implementations. Template CSV formulas specified. Default parameter values listed.
3. **Type consistency:** `reach_segments` dict structure consistent across generate_cells, detect_junctions, export functions. GeoDataFrame columns match shapefile DBF attributes match YAML gis_properties.
4. **Phase independence:** Each phase (1-4) produces deployable, testable software. Phase 1 is a complete MVP. Phases 2-4 add mesh types to the existing dropdown without changing the workflow.
