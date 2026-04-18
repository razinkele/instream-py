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
from modules.bathymetry import fetch_emodnet_dtm, sample_depth  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "example_baltic"
SHP_DIR = OUT / "Shapefile"

# Bbox covers: lower Nemunas (Sovetsk to delta), full Nemunas delta, the
# Curonian Lagoon (water=lagoon polygon — only reliably returned by the
# PBF clipper when the bbox is wide enough; narrower bboxes dropped it),
# and Baltic coast off Klaipeda.
BBOX = (20.80, 54.90, 22.20, 55.95)

# River clip bbox — match the fetch bbox so we don't truncate reaches.
# Previous tighter clip (20.95, 55.05, 21.75, 55.70) cut off Gilija's southern
# half (Kaliningrad, south of 55.05°N) and Nemunas's upper section (east of
# 21.75°E). With our current cell sizes (200-300 m for rivers, 2500 m for
# marine), the full bbox stays under ~2500 cells so the tight clip is no
# longer needed.
RIVER_CLIP_BBOX = BBOX

# Marine Regions authoritative polygon cache + metadata.
# MRGID 3642 is the Curonian Lagoon (Kuršių marios). Per 2026-04-18 probing,
# no Marine Regions WFS layer returns MRGID 3642 via cql_filter — the polygon
# is in the gazetteer but not exposed as WFS-queryable content. The fetcher
# tries anyway (future-proof), falls back to hand-traced polygon on miss.
CURONIAN_CACHE_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "data" / "marineregions" / "curonian_lagoon.geojson"
)
CURONIAN_MRGID = 3642
MARINEREGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"
# Most plausible future home for the polygon — if/when Marine Regions adds
# MRGID 3642 to a WFS-exposed layer, gazetteer_polygon is the likely target.
MARINEREGIONS_TYPENAME = "MarineRegions:gazetteer_polygon"

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
    # Gilija is the Lithuanian name; the feature is only in the Kaliningrad PBF
    # and OSM tags it with the Russian name Матросовка (Matrosovka).
    "Gilija":   ("waterway", ("Матросовка", "Matrosovka", "Gilija")),
}

REACH_ORDER = [
    "Nemunas", "Minija", "Sysa", "Skirvyte", "Leite", "Gilija",
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
    "Gilija":         250,   # southern delta branch from Kaliningrad PBF
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
    "Gilija": {
        # Southern Nemunas delta branch (Матросовка / Matrosovka on the Kaliningrad
        # side). Warmer, flatter than the northern delta arms. Hydraulic params
        # modelled on Leite with slightly higher depth/flow (longer effective reach).
        "temp_mean": 10.0, "temp_amp": 9.5, "flow_base": 3.0, "turb_base": 4,
        "flows": [0.6, 1.2, 2.0, 3.0, 5.0, 7.0, 12.0, 22.0, 55.0, 250.0],
        "depth_base": 2.5, "depth_flood": 4.0,
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
    # Merge Lithuania + Kaliningrad PBFs so the Kaliningrad-side delta branch
    # Матросовка (Gilija) is reachable.
    ww = query_waterways(("lithuania", "kaliningrad"), BBOX)
    _log(f"  got {len(ww)} waterway features")

    clip_box = box(*RIVER_CLIP_BBOX)
    # Per-reach tighter bboxes for rivers that naturally extend far beyond the
    # salmon-relevant Nemunas / Curonian Lagoon / Baltic coast system. Keyed
    # on ASCII reach name; absent keys fall back to RIVER_CLIP_BBOX.
    per_reach_clip = {
        # Minija's full basin reaches Plateliai lake (~22.0°E, ~56.0°N),
        # 90+ km from the lagoon. Anadromous salmon rarely ascend past
        # the lower-Minija confluence with the lagoon. Keep only the lower
        # ~35 km of the river between the lagoon and the first major inland
        # bend. Real geography: Minija enters Curonian Lagoon at Ventės Ragas
        # (~21.20°E, 55.34°N) via Klaipėda; lower Minija runs through
        # Gargždai (~21.4°E, 55.7°N). Clip to lon [21.20, 21.55], lat
        # [55.30, 55.75].
        "Minija": (21.20, 55.30, 21.55, 55.75),
    }
    out: dict[str, object] = {}
    for reach, (col, targets) in REACH_OSM.items():
        hits = ww[ww["nameText"].isin(targets)]
        if len(hits) == 0:
            print(f"  WARN: no OSM features for {reach} (names={targets})", flush=True)
            continue
        merged = unary_union(hits.geometry.values)
        if not merged.is_valid:
            merged = make_valid(merged)
        # Clip to this reach's specific bbox (or the default river clip).
        this_clip = box(*per_reach_clip.get(reach, RIVER_CLIP_BBOX))
        clipped = merged.intersection(this_clip)
        if clipped.is_empty:
            print(f"  WARN: {reach} clip produced empty geometry", flush=True)
            continue
        out[reach] = clipped
        _log(f"  {reach:<10s}: {len(hits)} OSM features, clipped -> {clipped.geom_type}")
    return out


def _fetch_curonian_from_marineregions() -> object | None:
    """Try to fetch the Curonian Lagoon polygon from Marine Regions WFS.
    Returns None on any failure so the caller can fall back.

    As of 2026-04-18, no WFS typeName exposes MRGID 3642 via cql_filter —
    this function is future-proofing. If Marine Regions adds the polygon to
    gazetteer_polygon (or similar) later, the fetcher picks it up automatically.
    """
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": MARINEREGIONS_TYPENAME,
        "cql_filter": f"MRGID={CURONIAN_MRGID}",
        "outputFormat": "application/json",
    }
    try:
        resp = requests.get(MARINEREGIONS_WFS, params=params, timeout=60)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  WARN: Marine Regions fetch failed ({exc}); using fallback", flush=True)
        return None

    try:
        data = resp.json()
    except Exception as exc:
        print(f"  WARN: Marine Regions response not JSON ({exc}); using fallback", flush=True)
        return None

    feats = data.get("features", [])
    geoms: list = []
    for f in feats:
        g = f.get("geometry")
        if g is None:
            continue
        geom = shape(g)
        if not geom.is_valid:
            geom = make_valid(geom)
        geoms.append(geom)
    if not geoms:
        print(f"  WARN: Marine Regions returned 0 features for MRGID={CURONIAN_MRGID}; "
              "using fallback", flush=True)
        return None
    return unary_union(geoms)


def _write_curonian_cache(geom) -> None:
    CURONIAN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326").to_file(
        CURONIAN_CACHE_PATH, driver="GeoJSON"
    )


def _fallback_curonian_polygon() -> object:
    """18-coord hand-traced polygon (pre-2026-04-18 implementation, kept as fallback).

    Traced clockwise from Klaipėda Strait. Accurate to ~500 m along the shoreline.
    Real lagoon: 1,584 km². This polygon computes to ~2,585 km² (63% too large),
    but that's the best static fallback available without Marine Regions WFS data.
    """
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
    return Polygon(lagoon_coords)


def fetch_curonian_lagoon() -> object:
    """Return the Curonian Lagoon polygon. Priority:
      1. Cached GeoJSON at app/data/marineregions/curonian_lagoon.geojson
      2. Marine Regions WFS (MRGID 3642) — currently a no-op, future-proof
      3. 18-coord hand-traced fallback
    """
    if CURONIAN_CACHE_PATH.exists():
        _log(f"Loading cached Curonian Lagoon polygon from {CURONIAN_CACHE_PATH.name}...")
        gdf = gpd.read_file(CURONIAN_CACHE_PATH)
        return gdf.geometry.iloc[0]

    _log(f"Fetching Curonian Lagoon from Marine Regions WFS (MRGID {CURONIAN_MRGID})...")
    geom = _fetch_curonian_from_marineregions()
    if geom is None:
        _log("Using hand-traced fallback polygon...")
        geom = _fallback_curonian_polygon()
    else:
        _write_curonian_cache(geom)
        _log(f"  Cached to {CURONIAN_CACHE_PATH}")

    area_km2 = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326").to_crs(
        "EPSG:32634"
    ).geometry.iloc[0].area / 1e6
    _log(f"  CuronianLagoon: {geom.geom_type} area={area_km2:.0f} km² (real ~1,584 km²)")
    return geom


SPIT_CACHE_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "data" / "marineregions" / "curonian_spit.geojson"
)


def fetch_baltic_coast() -> object:
    """Return a Baltic nearshore polygon IN FRONT OF the Klaipėda channel,
    clipped by the Curonian Spit so no cells fall on land.

    Salmon leaving the Nemunas exit through the Klaipėda strait (~55.70°N,
    21.10°E) and head north into the Baltic Proper. This reach captures
    that transit corridor: a ~18 × 28 km rectangle immediately north of
    the strait, east of the offshore shelf, west of the Lithuanian
    mainland coast (Klaipėda–Palanga coastline sits at lon ~21.06-21.13°E
    between lat 55.70 and 55.95). The east edge is pinned at 21.05°E so
    the rectangle never crosses the mainland coast.

    Previous iteration placed a rectangle WEST of the Curonian Spit
    (wrong side — that's Kaliningrad offshore, not a salmon transit
    corridor). The spit polygon (cached from OSM relation 309762) is
    subtracted to handle any southern overlap with the spit tip.
    """
    _log("Building Baltic coastal polygon (offshore N of Klaipėda strait)...")
    # Longitude: 20.80-21.05 (stays offshore of the Lithuanian mainland at
    # Klaipėda–Palanga, which hugs ~21.06-21.13°E).
    # Latitude: 55.70 (north shore of the strait) → 55.95 (Palanga area).
    coast_rect = Polygon([
        (20.80, 55.70),   # SW corner, immediately N of the strait
        (21.05, 55.70),   # SE corner, just W of Klaipėda port
        (21.05, 55.95),   # NE corner, just W of Palanga
        (20.80, 55.95),   # NW corner, ~15 km offshore
        (20.80, 55.70),
    ])

    # Clip by the Curonian Spit polygon so any cells that would fall on
    # land (the spit tip near Smiltynė reaches up to ~55.73°N) are removed.
    geom = coast_rect
    if SPIT_CACHE_PATH.exists():
        spit = gpd.read_file(SPIT_CACHE_PATH).geometry.iloc[0]
        geom = coast_rect.difference(spit)
        if not geom.is_valid:
            geom = make_valid(geom)
        _log("  Clipped BalticCoast by Curonian Spit polygon (OSM 309762).")
    else:
        _log("  WARN: curonian_spit.geojson missing — BalticCoast not spit-clipped. "
             "Run scripts/_fetch_curonian_spit_osm.py to generate it.")

    area_km2 = gpd.GeoDataFrame(
        geometry=[geom], crs="EPSG:4326"
    ).to_crs("EPSG:32634").geometry.iloc[0].area / 1e6
    _log(f"  BalticCoast: {geom.geom_type} area={area_km2:.0f} km² "
         f"(offshore transit zone N of Klaipėda strait)")
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
        # AND GeometryCollections to parts so single-geometry consumers
        # downstream see LineString / Polygon only. GeometryCollections arise
        # when a reach's OSM features mix line and polygon types (Gilija does).
        segments: list = []
        if geom.geom_type == "GeometryCollection":
            # Keep only line/polygon members; skip Point or nested GeometryCollections.
            for sub in geom.geoms:
                if sub.geom_type.startswith("Multi"):
                    segments.extend(sub.geoms)
                elif sub.geom_type in ("LineString", "Polygon"):
                    segments.append(sub)
        elif geom.geom_type.startswith("Multi"):
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


def generate_hydraulics(
    reach_name: str,
    n_cells: int,
    depths_by_cell: "np.ndarray | None" = None,
) -> None:
    """Write -Depths.csv and -Vels.csv for *reach_name*.

    If *depths_by_cell* is provided (from EMODnet sampling for marine reaches),
    the Depths CSV uses per-cell real base depths with the reach's published
    flood:base ratio for per-flow scaling. Otherwise (river reaches, or when
    EMODnet is unavailable), per-cell values are synthesized with a ±30 %
    jitter around the reach's published mean depth.
    """
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
        real_bathy = kind == "Depths" and depths_by_cell is not None
        with open(fpath, "w", newline="") as f:
            f.write(f"; {kind} for Baltic example — {reach_name}\n")
            if real_bathy:
                f.write("; per-cell depth_base sampled from EMODnet DTM "
                        "(1/16 arc-min, https://emodnet.ec.europa.eu/en/bathymetry); "
                        "per-flow scaling synthetic\n")
            else:
                f.write("; depth_base/vel_base are real published means; "
                        "per-flow scaling is synthetic\n")
            f.write(f"; CELL {kind.upper()} IN {unit}\n")
            f.write(f"{n_flows},Number of flows in table" + ",," * (n_flows - 1) + "\n")
            f.write("," + ",".join(f"{fl}" for fl in flows) + "\n")
            flood_base_ratio = p["depth_flood"] / p["depth_base"] if p["depth_base"] else 1.0
            for c in range(1, n_cells + 1):
                if real_bathy:
                    # Per-cell real base depth; scale flood by same ratio as the
                    # reach's published (base, flood) pair to keep per-flow curves
                    # sensible even for land-adjacent cells (clamped to 0.1 m).
                    cell_base = float(depths_by_cell[c - 1])
                    cell_flood = cell_base * flood_base_ratio
                    vals = []
                    for fi in range(n_flows):
                        v = cell_base + (cell_flood - cell_base) * f_frac[fi]
                        vals.append(f"{max(0.001, v):.6f}")
                    f.write(f"{c}," + ",".join(vals) + "\n")
                else:
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
    weights = {"Nemunas": 0.35, "Minija": 0.16, "Sysa": 0.13,
               "Skirvyte": 0.13, "Leite": 0.11, "Gilija": 0.12}
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
    adult_weights = {"Nemunas": 0.35, "Minija": 0.16, "Sysa": 0.12,
                     "Skirvyte": 0.14, "Leite": 0.11, "Gilija": 0.12}
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

    # Fetch EMODnet DTM once and sample per-cell real depths for marine reaches.
    # River reaches retain the published-mean-depth scaling (EMODnet coverage
    # is marine-only). Failures are non-fatal — fall back to synthetic scaling.
    depths_by_reach: dict[str, np.ndarray] = {}
    dtm_bbox = (BBOX[0] - 0.1, BBOX[1] - 0.1, BBOX[2] + 0.1, BBOX[3] + 0.1)
    try:
        _log(f"Fetching EMODnet DTM for marine reaches (bbox {dtm_bbox})...")
        dtm_path = fetch_emodnet_dtm(dtm_bbox)
        _log(f"  DTM cached at {dtm_path.name}")
        gdf_wgs = gdf.to_crs("EPSG:4326")
        for reach in ("CuronianLagoon", "BalticCoast"):
            mask = gdf_wgs["REACH_NAME"] == reach
            if mask.any():
                depths = sample_depth(gdf_wgs[mask], dtm_path)
                depths_by_reach[reach] = depths
                _log(f"  {reach}: sampled {len(depths)} depths "
                     f"(min {depths.min():.1f} m, max {depths.max():.1f} m, "
                     f"mean {depths.mean():.1f} m)")
    except Exception as exc:
        print(f"  WARN: EMODnet fetch/sample failed ({exc}); "
              "marine reaches fall back to synthetic depth scaling", flush=True)

    print()
    for reach_name, n_cells in counts.items():
        generate_time_series(reach_name)
        generate_hydraulics(reach_name, n_cells, depths_by_reach.get(reach_name))
        _log(f"CSVs: {reach_name}")

    print()
    generate_populations([r for r in REACH_ORDER if r in counts])

    print()
    print(f"Done! {total} cells across {len(counts)} reaches -> {OUT}")


if __name__ == "__main__":
    main()
