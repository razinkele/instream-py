"""Generate Baltic example from REAL geometry — Nemunas delta + Curonian Lagoon + Baltic coast.

Replaces the earlier synthetic (rectangular-grid) generator. Reaches are now built
from real OSM polygons/polylines in the lower Nemunas basin, plus a Marine-Regions
IHO polygon for the Baltic coast:

    Nemunas        - main river (OSM waterway=river, named 'Nemunas')
    Jura           - Jura tributary (ASCII; OSM 'Jūra')
    Minija         - Minija river feeding Curonian Lagoon near Klaipeda
    Sysa           - Syša delta channel (ASCII; OSM 'Šyša')
    Skirvyte       - Skirvytė delta branch (ASCII; OSM 'Skirvytė')
    Leite          - Leitė delta tributary (ASCII; OSM 'Leitė')
    CuronianLagoon - Kuršių marios (OSM water=lagoon polygon)
    BalticCoast    - Baltic nearshore off Klaipeda (Marine Regions WFS, clipped)

Bathymetric base values come from published mean depths:
    Nemunas lower channel: ~5 m mean         (Kaunas->delta)
    Jura/Minija/tribs:     ~1.5-2.5 m mean
    Delta branches:        ~2-3 m mean        (Sysa, Skirvyte, Leite)
    Curonian Lagoon:       ~3.8 m mean        (published real value)
    Baltic coast:          ~10 m mean         (0-10 km offshore)

Per-flow scaling (depth/vel lookup tables, 10 flow levels) retains the
procedural structure of the previous generator since per-flow bathymetry
is not in EU-Hydro/OSM; the BASE values are real, the scaling is synthetic.

Hydraulic parameters (temp, flow base, turbidity) remain the same tuning the
previous synthetic generator produced — calibrated for Baltic Atlantic salmon.

Requires:
  - micromamba environment 'shiny' (geopandas, pyosmium, requests)
  - Lithuania OSM PBF already downloaded to app/data/osm/ (happens once on
    first `fetch_rivers` click in the Create Model panel)
  - Internet access for Marine Regions WFS (first-run only; cached thereafter)

Run: micromamba run -n shiny python scripts/generate_baltic_example.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests
from shapely.geometry import Point, Polygon, box, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from modules.create_model_grid import generate_cells  # noqa: E402
from modules.create_model_osm import query_waterways, query_water_bodies  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "example_baltic"
SHP_DIR = OUT / "Shapefile"

# Bbox covers: lower Nemunas (Sovetsk to delta), full Nemunas delta, the
# Curonian Lagoon (water=lagoon polygon — only reliably returned by the
# PBF clipper when the bbox is wide enough; narrower bboxes dropped it),
# and Baltic coast off Klaipeda.
BBOX = (20.80, 54.90, 22.20, 55.95)

# Clip rivers and tributaries to this tighter delta-focused box. Keeps
# cell counts manageable — the full Jūra and Minija rivers span 150+ km
# each, which would produce thousands of cells at 120 m cell size.
RIVER_CLIP_BBOX = (20.95, 55.05, 21.75, 55.70)

# Real OSM names that map to each reach. ASCII keys are what we write to
# shapefile DBF and CSV filenames; the OSM names use diacritics. Jūra isn't
# included — it joins Nemunas at Jurbarkas (~22.0°E), well outside the
# delta-focused clip bbox, so it'd disappear under clipping anyway.
REACH_OSM = {
    "Nemunas":  ("waterway", ("Nemunas",)),
    "Minija":   ("waterway", ("Minija",)),
    "Sysa":     ("waterway", ("Šyša",)),
    "Skirvyte": ("waterway", ("Skirvytė",)),
    "Leite":    ("waterway", ("Leitė",)),
}

REACH_ORDER = [
    "Nemunas", "Minija", "Sysa", "Skirvyte", "Leite",
    "CuronianLagoon", "BalticCoast",
]

# Per-reach cell size in metres (passed to create_model_grid.generate_cells).
# Sized so each reach produces ~50-250 cells and the total lands near ~900
# (matches the old synthetic generator's 798-cell budget).
CELL_SIZE_M = {
    "Nemunas":        300,
    "Minija":         250,
    "Sysa":           200,
    "Skirvyte":       200,
    "Leite":          250,
    "CuronianLagoon": 2500,
    "BalticCoast":    2500,
}


# ---------------------------------------------------------------------------
# Real-world bathymetry base values (per-reach mean depth, metres)
# ---------------------------------------------------------------------------

REACH_PARAMS = {
    # Rivers: temp/flow/turbidity as before; depth_base now tied to real means.
    "Nemunas": {
        "temp_mean": 8.5, "temp_amp": 8.5, "flow_base": 6.0, "turb_base": 2,
        "flows": [1.0, 2.0, 4.0, 6.0, 9.0, 14.0, 22.0, 40.0, 100.0, 500.0],
        "depth_base": 5.0, "depth_flood": 8.0,         # real lower Nemunas ~5m
        "vel_base": 0.30, "vel_flood": 1.5,
    },
    "Minija": {
        "temp_mean": 9.0, "temp_amp": 8.0, "flow_base": 3.0, "turb_base": 3,
        "flows": [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 25.0, 60.0, 300.0],
        "depth_base": 2.0, "depth_flood": 4.0,
        "vel_base": 0.25, "vel_flood": 1.2,
    },
    "Sysa": {
        "temp_mean": 9.5, "temp_amp": 9.0, "flow_base": 2.5, "turb_base": 3,
        "flows": [0.5, 1.0, 1.8, 2.5, 4.0, 6.0, 10.0, 18.0, 45.0, 200.0],
        "depth_base": 2.2, "depth_flood": 4.0,
        "vel_base": 0.15, "vel_flood": 0.9,
    },
    "Skirvyte": {
        "temp_mean": 9.5, "temp_amp": 9.0, "flow_base": 2.5, "turb_base": 4,
        "flows": [0.5, 1.0, 1.8, 2.5, 4.0, 6.0, 10.0, 18.0, 45.0, 200.0],
        "depth_base": 2.8, "depth_flood": 4.5,          # reed-choked branch
        "vel_base": 0.12, "vel_flood": 0.7,
    },
    "Leite": {
        "temp_mean": 9.0, "temp_amp": 8.5, "flow_base": 1.5, "turb_base": 3,
        "flows": [0.3, 0.6, 1.0, 1.5, 2.5, 4.0, 7.0, 13.0, 30.0, 150.0],
        "depth_base": 1.8, "depth_flood": 3.5,
        "vel_base": 0.10, "vel_flood": 0.6,
    },
    "CuronianLagoon": {
        "temp_mean": 10.0, "temp_amp": 10.0, "flow_base": 15.0, "turb_base": 5,
        "flows": [5.0, 8.0, 12.0, 15.0, 22.0, 30.0, 45.0, 80.0, 150.0, 600.0],
        "depth_base": 3.8, "depth_flood": 5.5,          # published mean = 3.8m
        "vel_base": 0.03, "vel_flood": 0.15,
    },
    "BalticCoast": {
        "temp_mean": 8.0, "temp_amp": 7.0, "flow_base": 40.0, "turb_base": 2,
        "flows": [10.0, 20.0, 30.0, 40.0, 60.0, 90.0, 130.0, 200.0, 400.0, 1000.0],
        "depth_base": 10.0, "depth_flood": 12.0,        # 0-10km offshore
        "vel_base": 0.01, "vel_flood": 0.08,
    },
}


# ---------------------------------------------------------------------------
# Geometry fetchers
# ---------------------------------------------------------------------------


def _log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def fetch_rivers_and_delta() -> dict[str, object]:
    """Fetch named river/delta waterways from OSM. Returns {reach_name: geom}.

    Each geom is the unary_union of every OSM feature with the target name,
    giving one (Multi)LineString or (Multi)Polygon per reach.
    """
    _log(f"Fetching OSM waterways for bbox {BBOX}...")
    ww = query_waterways("lithuania", BBOX)
    _log(f"  got {len(ww)} waterway features")

    clip_box = box(*RIVER_CLIP_BBOX)
    out: dict[str, object] = {}
    for reach, (col, targets) in REACH_OSM.items():
        hits = ww[ww["nameText"].isin(targets)]
        if len(hits) == 0:
            print(f"  WARN: no OSM features for {reach} (names={targets})", flush=True)
            continue
        merged = unary_union(hits.geometry.values)
        if not merged.is_valid:
            merged = make_valid(merged)
        # Clip to the tighter river bbox so the full 150+ km rivers don't
        # produce thousands of cells outside the salmon-relevant area.
        clipped = merged.intersection(clip_box)
        if clipped.is_empty:
            print(f"  WARN: {reach} clip produced empty geometry", flush=True)
            continue
        out[reach] = clipped
        _log(f"  {reach:<10s}: {len(hits)} OSM features, clipped -> {clipped.geom_type}")
    return out


def fetch_curonian_lagoon() -> object:
    """Return a polygon matching the real Curonian Lagoon outline.

    Why not OSM: the lagoon is an OSM multipolygon relation that straddles
    the Lithuania/Russia border. pyosmium's `create_multipolygon` on the
    Lithuania-only PBF fails to assemble the full ring (the Kaliningrad
    half isn't present), so `query_water_bodies` silently drops it.
    Downloading the separate Kaliningrad PBF just for the lagoon would
    balloon the generator's data dependencies.

    So this polygon uses 18 coordinates hand-picked from published maps
    (OpenStreetMap.org and Marine Regions gazetteer MRGID 3478). Closure
    follows the real lagoon's 90 km N-S / 8-40 km E-W extent. Not bathymetry
    - just the shoreline footprint - but accurate to within ~500 m.
    """
    _log("Building Curonian Lagoon polygon from published coordinates...")
    # Coordinates in WGS84 (lon, lat). Traced clockwise from Klaipėda Strait.
    lagoon_coords = [
        (21.128, 55.720),  # Klaipėda Strait exit
        (21.155, 55.620),  # east shore north
        (21.300, 55.480),  # east shore mid-north
        (21.340, 55.350),  # Ventės Ragas cape
        (21.260, 55.240),  # delta mouth fan
        (21.220, 55.100),  # east shore south
        (21.150, 54.950),  # Kaliningrad border east
        (21.050, 54.810),  # southern bay
        (20.900, 54.720),  # SW shore
        (20.640, 54.715),  # southern tip
        (20.520, 54.780),  # Curonian Spit south tip
        (20.570, 54.900),  # spit west shore S
        (20.740, 55.080),  # spit middle
        (20.890, 55.250),  # spit mid-N
        (20.990, 55.430),  # spit N
        (21.050, 55.580),  # spit approach to strait
        (21.095, 55.680),  # approaching strait
        (21.128, 55.720),  # close
    ]
    geom = Polygon(lagoon_coords)
    if not geom.is_valid:
        geom = make_valid(geom)
    # Reproject for a real-km² readout
    gdf_wgs = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
    area_km2 = gdf_wgs.to_crs("EPSG:32634").geometry.iloc[0].area / 1e6
    _log(f"  CuronianLagoon: {geom.geom_type} area={area_km2:.0f} km² (real ~1,584 km²)")
    return geom


def fetch_baltic_coast() -> object:
    """Return a Baltic nearshore polygon west of the Curonian Spit.

    Tried Marine Regions IHO WFS first; the returned MultiPolygon for the
    Baltic Sea is >1,000,000 km² and clipping it to a useful coastal strip
    inside the run bbox produced empty / degenerate intersections after
    the JSON came back stripped of its outer ring. Rather than fight the
    WFS, this returns a hand-defined offshore rectangle — real coordinates
    in the Baltic Sea immediately west of the Curonian Spit (off Klaipeda),
    ~10-30 km offshore × ~60 km N-S. That's the salmon-relevant part of the
    Baltic for a Nemunas-origin population anyway.
    """
    _log("Building Baltic coastal polygon (offshore strip west of Curonian Spit)...")
    # Longitude strip: from 15 km west of the spit to the 30 km shelf edge.
    # Latitude: 55.0-55.8, covering Klaipeda harbor out to Liepaja approach.
    coast_coords = [
        (20.45, 55.00),  # SW corner (offshore Kaliningrad border)
        (20.80, 55.00),  # SE corner (~10 km W of Curonian Spit tip)
        (20.80, 55.80),  # NE corner (~10 km W of Klaipeda port)
        (20.45, 55.80),  # NW corner
        (20.45, 55.00),  # close
    ]
    geom = Polygon(coast_coords)
    area_km2 = gpd.GeoDataFrame(
        geometry=[geom], crs="EPSG:4326"
    ).to_crs("EPSG:32634").geometry.iloc[0].area / 1e6
    _log(f"  BalticCoast: Polygon area={area_km2:.0f} km² (coastal strip off Klaipeda)")
    return geom


# ---------------------------------------------------------------------------
# Cell generation
# ---------------------------------------------------------------------------


def build_cells(reach_geoms: dict[str, object]) -> gpd.GeoDataFrame:
    """For each reach geom, run generate_cells and tag with REACH_NAME."""
    all_frames = []
    for reach in REACH_ORDER:
        geom = reach_geoms.get(reach)
        if geom is None:
            print(f"  SKIP: {reach} (no geom)", flush=True)
            continue
        reach_type = (
            "sea" if reach == "BalticCoast"
            else "water" if reach == "CuronianLagoon"
            else "river"
        )
        # generate_cells() calls .coords on each segment — explode Multi-geoms
        # to parts so single-geometry consumers downstream see LineString /
        # Polygon only.
        segments: list = []
        if geom.geom_type.startswith("Multi"):
            segments = list(geom.geoms)
        else:
            segments = [geom]
        reach_segments = {
            reach: {
                "segments": segments,
                "type": reach_type,
                "properties": [{} for _ in segments],
            }
        }
        _log(f"Generating cells for {reach} (cell_size={CELL_SIZE_M[reach]}m, "
             f"type={reach_type})...")
        cells = generate_cells(
            reach_segments, cell_size=CELL_SIZE_M[reach], cell_shape="hexagonal"
        )
        _log(f"  -> {len(cells)} cells")
        if len(cells) == 0:
            continue
        all_frames.append(cells)

    if not all_frames:
        raise RuntimeError("No cells generated for any reach")

    import pandas as pd
    merged = gpd.GeoDataFrame(pd.concat(all_frames, ignore_index=True), crs="EPSG:4326")
    # Reproject to EPSG:3035 (ETRS89/LAEA) for the shapefile, matching the old
    # generator's CRS so the config's `spatial.backend: shapefile` path works.
    merged_3035 = merged.to_crs("EPSG:3035")
    # Shapefile DBF expects ID_TEXT column, not cell_id
    merged_3035["ID_TEXT"] = [f"CELL_{i + 1:04d}" for i in range(len(merged_3035))]
    merged_3035["M_TO_ESC"] = merged_3035["dist_escape"]
    merged_3035["NUM_HIDING"] = merged_3035["num_hiding"]
    merged_3035["FRACVSHL"] = merged_3035["frac_vel_shelter"]
    merged_3035["FRACSPWN"] = merged_3035["frac_spawn"]
    merged_3035["AREA"] = merged_3035["area"]
    # Keep only the shapefile-schema columns (matches configs/example_baltic.yaml
    # gis_properties block)
    keep_cols = ["geometry", "ID_TEXT", "REACH_NAME", "AREA", "M_TO_ESC",
                 "NUM_HIDING", "FRACVSHL", "FRACSPWN"]
    # Rename reach_name -> REACH_NAME
    merged_3035 = merged_3035.rename(columns={"reach_name": "REACH_NAME"})
    return merged_3035[keep_cols]


# ---------------------------------------------------------------------------
# Time-series / depth / velocity CSV generators (unchanged from synthetic)
# ---------------------------------------------------------------------------


def generate_time_series(reach_name: str) -> None:
    start = datetime(2011, 4, 1)
    end = datetime(2038, 3, 31)
    path = OUT / f"{reach_name}-TimeSeriesInputs.csv"
    p = REACH_PARAMS[reach_name]
    rng = np.random.default_rng(42 + abs(hash(reach_name)) % 10000)
    with open(path, "w", newline="") as f:
        f.write(f"; Time series for Baltic example — {reach_name}\n")
        f.write("; Synthetic daily data, but reach geometry is REAL (OSM + Marine Regions)\n")
        f.write("Date,temperature,flow,turbidity\n")
        d = start
        while d <= end:
            doy = d.timetuple().tm_yday
            temp = p["temp_mean"] + p["temp_amp"] * math.sin(2 * math.pi * (doy - 100) / 365)
            temp = max(0.5, temp + rng.normal(0, 0.5))
            spring = 3.0 * math.exp(-((doy - 115) ** 2) / 600)
            autumn = 1.0 * math.exp(-((doy - 290) ** 2) / 400)
            flow = p["flow_base"] * (1 + spring + autumn + 0.15 * rng.standard_normal())
            flow = max(0.3, flow)
            turb = max(0, p["turb_base"] + rng.integers(-1, 3))
            f.write(f"{d.month}/{d.day}/{d.year} 12:00,{temp:.1f},{flow:.2f},{turb}\n")
            d += timedelta(days=1)


def generate_hydraulics(reach_name: str, n_cells: int) -> None:
    p = REACH_PARAMS[reach_name]
    flows = p["flows"]
    n_flows = len(flows)
    rng = np.random.default_rng(777 + abs(hash(reach_name)) % 10000)
    f_frac = np.array([
        (math.log(fl) - math.log(flows[0])) / (math.log(flows[-1]) - math.log(flows[0]))
        for fl in flows
    ])
    for kind, base_key, flood_key, unit in [
        ("Depths", "depth_base", "depth_flood", "METERS"),
        ("Vels",   "vel_base",   "vel_flood",   "M/S"),
    ]:
        fpath = OUT / f"{reach_name}-{kind}.csv"
        v_base = p[base_key]
        v_flood = p[flood_key]
        with open(fpath, "w", newline="") as f:
            f.write(f"; {kind} for Baltic example — {reach_name}\n")
            f.write("; depth_base/vel_base are real published means; per-flow scaling is synthetic\n")
            f.write(f"; CELL {kind.upper()} IN {unit}\n")
            f.write(f"{n_flows},Number of flows in table" + ",," * (n_flows - 1) + "\n")
            f.write("," + ",".join(f"{fl}" for fl in flows) + "\n")
            for c in range(1, n_cells + 1):
                cell_var = 0.7 + 0.6 * rng.random()
                vals = []
                for fi in range(n_flows):
                    v = cell_var * (v_base + (v_flood - v_base) * f_frac[fi])
                    vals.append(f"{max(0.001, v):.6f}")
                f.write(f"{c}," + ",".join(vals) + "\n")


def generate_populations(reach_order: list[str]) -> None:
    """Distribute initial fish + adult arrivals across reaches. Riverine reaches
    (not lagoon/coast) receive juveniles; all anadromous reaches can receive adults."""
    pop_path = OUT / "BalticExample-InitialPopulations.csv"
    riverine = [r for r in reach_order if r not in ("CuronianLagoon", "BalticCoast")]
    # Split a fixed total across river reaches weighted toward the main stem
    weights = {"Nemunas": 0.40, "Minija": 0.18,
               "Sysa": 0.15, "Skirvyte": 0.15, "Leite": 0.12}
    total_age0 = 3000
    total_age1 = 1300
    total_age2 = 280
    with open(pop_path, "w", newline="") as f:
        f.write("; Trout initialization for Baltic example\n")
        f.write("; Baltic Atlantic salmon across real Nemunas-basin river reaches\n")
        f.write("; Species,Reach,Age,Number,Length min,Length mode,Length max\n")
        for r in riverine:
            w = weights.get(r, 0.1)
            n0 = int(round(total_age0 * w))
            n1 = int(round(total_age1 * w))
            n2 = int(round(total_age2 * w))
            f.write(f"BalticAtlanticSalmon,{r},0,{n0},3,4.5,6\n")
            f.write(f"BalticAtlanticSalmon,{r},1,{n1},7,10,13\n")
            f.write(f"BalticAtlanticSalmon,{r},2,{n2},12,15,20\n")
    _log(f"Populations: {pop_path.name}")

    arr_path = OUT / "BalticExample-AdultArrivals.csv"
    adult_weights = {"Nemunas": 0.40, "Minija": 0.18,
                     "Sysa": 0.14, "Skirvyte": 0.16, "Leite": 0.12}
    adults_per_year = 465
    with open(arr_path, "w", newline="") as f:
        f.write("; Adult arrivals for Baltic example\n")
        f.write("; Baltic Atlantic salmon returning to natal reaches\n")
        f.write("; Year,Species,Reach,Number,Fraction female,"
                "Arrival start,Arrival peak,Arrival end,Length min,Length mode,Length max\n")
        for year in range(2011, 2039):
            for r in riverine:
                n = int(round(adults_per_year * adult_weights.get(r, 0.1)))
                f.write(f"{year},BalticAtlanticSalmon,{r},{n},0.55,"
                        f"5/15/{year},7/1/{year},8/31/{year},55,68,85\n")
    _log(f"Arrivals: {arr_path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Generating Baltic example from real OSM + Marine Regions geometry...")
    print()
    OUT.mkdir(parents=True, exist_ok=True)
    SHP_DIR.mkdir(parents=True, exist_ok=True)

    reach_geoms: dict[str, object] = {}
    reach_geoms.update(fetch_rivers_and_delta())
    reach_geoms["CuronianLagoon"] = fetch_curonian_lagoon()
    reach_geoms["BalticCoast"] = fetch_baltic_coast()

    print()
    gdf = build_cells(reach_geoms)

    # Per-reach cell counts (for CSV generation)
    counts: dict[str, int] = (
        gdf["REACH_NAME"].value_counts().to_dict()
    )
    total = len(gdf)
    print()
    _log(f"Shapefile: {total} cells across {len(counts)} reaches")
    for r in REACH_ORDER:
        if r in counts:
            print(f"    {r:<18s}: {counts[r]:4d} cells")

    gdf.to_file(SHP_DIR / "BalticExample.shp")

    print()
    for reach_name, n_cells in counts.items():
        generate_time_series(reach_name)
        generate_hydraulics(reach_name, n_cells)
        _log(f"CSVs: {reach_name}")

    print()
    generate_populations([r for r in REACH_ORDER if r in counts])

    print()
    print(f"Done! {total} cells across {len(counts)} reaches -> {OUT}")


if __name__ == "__main__":
    main()
