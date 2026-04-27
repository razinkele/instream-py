"""Generate `tests/fixtures/_dane_temp/` for v0.51.0 — script-based pivot.

The original v0.51.0 plan called for using the v0.50.0 Find/Auto-extract/Auto-split
buttons end-to-end via the Create Model panel. In practice, Klaipėda's
geography defeats the connectivity-based Auto-extract: the Danė is connected
via the strait + lagoon to the entire Lithuanian water network, so BFS
visits every river. This script bypasses the UI by querying Overpass
directly for the Danė centerline and using the v0.50.0 helpers
(generate_cells, partition_polygons_along_channel) programmatically.

Output: `tests/fixtures/_dane_temp/Dane_*-{Depths,Vels,TimeSeriesInputs}.csv`
plus `tests/fixtures/_dane_temp/Shapefile/dane.shp` — same format as
Create Model 📦 Export, so the merge tasks in the v0.51.0 plan (Task 2+)
work unchanged.

Usage:
    micromamba run -n shiny python scripts/_generate_dane_temp_fixture.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString, MultiLineString, Point, mapping, shape
from shapely.ops import linemerge, unary_union, substring

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from modules.create_model_grid import generate_cells
from modules.create_model_export import _write_hydraulic_csv
from modules.create_model_utils import TEMPLATE_FLOWS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

OUT_DIR = ROOT / "tests" / "fixtures" / "_dane_temp"
SHAPEFILE_DIR = OUT_DIR / "Shapefile"
CACHE = ROOT / "tests" / "fixtures" / "_osm_cache" / "dane.json"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    # NOTE: overpass.osm.ch dropped — currently returns empty 200 responses
    # with bogus timestamp_osm_base. Reinstate when fixed.
]

# Danė watershed bbox (S, W, N, E) — Overpass uses S,W,N,E order.
# Covers Klaipėda mouth (lat 55.71) up to Plungė area (~lat 56.0).
DANE_BBOX = (55.65, 21.00, 56.05, 21.55)
# Match Danė + alt spelling Dangė + Akmena (the upper Danė is also called Akmena)
DANE_NAME_REGEX = "^(Danė|Dange|Dangė|Dane|Akmena|Akmena-Danė|Akmena-Dange)$"
# Mouth at Klaipėda port — used for along-channel orientation
DANE_MOUTH_LON_LAT = (21.135, 55.713)


def _build_query() -> str:
    """Fetch waterway=river ways named Dan* in bbox.

    Use the prefix regex `^Dan` (no Unicode in the regex itself, no
    anchors that some servers reject). Verified working: curl test
    against overpass-api.de returns 12 Danė ways with this query.
    """
    s, w, n, e = DANE_BBOX
    return (
        f'[out:json][timeout:180];\n'
        f'way["waterway"="river"]["name"~"^Dan"]'
        f'({s:.4f},{w:.4f},{n:.4f},{e:.4f});\n'
        f'out geom;'
    )


# Names accepted as "this is Danė or its upper-stretch alias"
DANE_NAME_TOKENS = {"Danė", "Dange", "Dangė", "Dane", "Akmena", "Akmena-Danė", "Akmena-Dange"}


def fetch_dane_centerline(refresh: bool = False) -> list[LineString]:
    """Fetch Danė waterway=river ways from Overpass; cache to JSON."""
    if CACHE.exists() and not refresh:
        log.info("using cached %s", CACHE)
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    else:
        query = _build_query()
        log.info("Overpass query:\n%s", query)
        data = None
        for url in OVERPASS_ENDPOINTS:
            try:
                log.info("trying %s ...", url)
                resp = requests.post(
                    url,
                    data={"data": query},
                    timeout=240,
                    headers={"User-Agent": "inSTREAM-py/0.51.0 (research; arturas.razinkovas-baziukas@ku.lt)"},
                )
                if resp.status_code != 200:
                    log.warning("%s returned HTTP %d: %s", url, resp.status_code, resp.text[:200])
                    time.sleep(5)
                    continue
                data = resp.json()
                if not data.get("elements"):
                    log.warning("%s returned 200 but 0 elements (likely degraded server)", url)
                    data = None
                    time.sleep(5)
                    continue
                break
            except Exception as exc:
                log.warning("%s failed: %s: %s", url, type(exc).__name__, exc)
                time.sleep(5)
        if data is None:
            raise RuntimeError("All Overpass endpoints failed or returned empty")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        log.info("cached → %s", CACHE)

    elements = data.get("elements", [])
    log.info("Overpass returned %d elements (will filter by name)", len(elements))

    # Log distinct names for debugging
    name_counts: dict[str, int] = {}
    for elem in elements:
        n = elem.get("tags", {}).get("name", "<unnamed>")
        name_counts[n] = name_counts.get(n, 0) + 1
    log.info("Names found: %s", sorted(name_counts.items(), key=lambda kv: -kv[1])[:10])

    lines: list[LineString] = []
    for elem in elements:
        name = elem.get("tags", {}).get("name", "")
        if name not in DANE_NAME_TOKENS:
            continue
        geom = elem.get("geometry") or []
        if len(geom) < 2:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in geom]
        ls = LineString(coords)
        if ls.is_valid and not ls.is_empty:
            lines.append(ls)
    log.info("parsed %d valid Danė LineStrings (filtered by name)", len(lines))
    return lines


def split_centerline_into_n(
    lines: list[LineString], mouth: tuple[float, float], n_reaches: int = 4
) -> dict[str, list[LineString]]:
    """Split the Danė centerline into N along-channel segments.

    Strategy: union → linemerge → orient mouth-to-source → take N equal-length
    sub-LineStrings via shapely.ops.substring. Each becomes one reach.
    """
    union = unary_union(lines)
    if union.geom_type == "MultiLineString":
        merged = linemerge(union)
    else:
        merged = union

    if merged.geom_type == "MultiLineString":
        # Disjoint segments — linemerge couldn't fully merge. Take the longest
        # connected component as the main stem.
        longest = max(merged.geoms, key=lambda g: g.length)
        log.warning(
            "Centerline is MultiLineString; using longest component (%d/%d, %.3f deg)",
            list(merged.geoms).index(longest) + 1, len(list(merged.geoms)), longest.length,
        )
        merged = longest

    if merged.geom_type != "LineString":
        raise RuntimeError(f"Cannot split: merged is {merged.geom_type}")

    # Orient mouth-to-source so substring(0, fraction) starts at the mouth
    mouth_pt = Point(mouth)
    coords = list(merged.coords)
    d_start = mouth_pt.distance(Point(coords[0]))
    d_end = mouth_pt.distance(Point(coords[-1]))
    if d_start > d_end:
        coords = list(reversed(coords))
        merged = LineString(coords)
    log.info(
        "Oriented centerline: total length = %.4f deg (start near mouth at %.3f, end at %.3f)",
        merged.length, mouth_pt.distance(Point(coords[0])), mouth_pt.distance(Point(coords[-1])),
    )

    names = ["Mouth", "Lower", "Middle", "Upper"]
    groups: dict[str, list[LineString]] = {}
    for i in range(n_reaches):
        sub = substring(
            merged,
            start_dist=i / n_reaches,
            end_dist=(i + 1) / n_reaches,
            normalized=True,
        )
        # Rename: Mouth→Dane_Mouth etc to skip the Edit Model rename step
        groups[f"Dane_{names[i]}"] = [sub]
        log.info("Dane_%s: %.4f deg of centerline", names[i], sub.length)

    return groups


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHAPEFILE_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: fetch centerline
    lines = fetch_dane_centerline()
    if not lines:
        raise RuntimeError("No Danė centerline lines found from OSM")

    # Step 2: split into 4 reaches by along-channel distance
    reach_lines = split_centerline_into_n(lines, DANE_MOUTH_LON_LAT, n_reaches=4)

    # Step 3: build reach_segments dict for generate_cells
    reach_segments = {
        name: {
            "segments": segs,
            "frac_spawn": 0.0 if name == "Dane_Mouth" else 0.05,  # Mouth=brackish, no spawn
        }
        for name, segs in reach_lines.items()
    }

    # Step 4: generate hex cells. cell_size=75m, buffer_factor=2.0 → 150m
    # buffer width. Targets ~100-200 cells per reach (~600 total new cells)
    # to keep example_baltic fixture growth modest (1591 → ~2200 cells).
    cells_gdf = generate_cells(
        reach_segments,
        cell_size=75.0,
        cell_shape="hexagonal",
        buffer_factor=2.0,
        min_overlap=0.1,
    )
    log.info("generate_cells produced %d cells", len(cells_gdf))
    if len(cells_gdf) == 0:
        raise RuntimeError("generate_cells returned 0 cells — check buffer_factor")

    # Per-reach cell counts
    for name in reach_lines:
        n = int((cells_gdf["reach_name"] == name).sum())
        log.info("  %s: %d cells", name, n)

    # Step 5: write per-cell CSVs (one per reach × {Depths, Vels, TimeSeriesInputs})
    flow_template = list(TEMPLATE_FLOWS)  # 10 flow values
    n_flows = len(flow_template)

    for name in reach_lines:
        reach_cells = cells_gdf[cells_gdf["reach_name"] == name].reset_index(drop=True)
        if len(reach_cells) == 0:
            log.warning("Reach %s has 0 cells; skipping CSVs", name)
            continue
        cell_ids = [f"CELL_{i+1:04d}" for i in range(len(reach_cells))]

        # Depths: cloned from Minija pattern — increase modestly with flow
        # Use a base depth of 0.5m at flow 10, scaling to 1.5m at flow 1000
        # for each cell — adds slight variation per cell (1-5cm)
        depths = []
        for i, _row in reach_cells.iterrows():
            base = 0.5 + 0.01 * i  # slight per-cell variation (1cm/cell)
            depths.append([
                round(base * (1.0 + 0.20 * (j / max(1, n_flows - 1))), 3)
                for j in range(n_flows)
            ])
        _write_hydraulic_csv(
            OUT_DIR / f"{name}-Depths.csv",
            reach_name=name, kind="Depths", units="m",
            flows=flow_template, cell_ids=cell_ids, values=depths,
        )

        # Vels: similar scaling, base 0.3 m/s
        vels = []
        for i, _row in reach_cells.iterrows():
            base = 0.30 + 0.005 * i
            vels.append([
                round(base * (1.0 + 0.30 * (j / max(1, n_flows - 1))), 3)
                for j in range(n_flows)
            ])
        _write_hydraulic_csv(
            OUT_DIR / f"{name}-Vels.csv",
            reach_name=name, kind="Vels", units="m/s",
            flows=flow_template, cell_ids=cell_ids, values=vels,
        )

        # TimeSeriesInputs: copy Minija's daily schedule format (header + 365 rows)
        # Use a stub schedule — flow 50, temp varies seasonally 2-18°C
        with (OUT_DIR / f"{name}-TimeSeriesInputs.csv").open("w", encoding="utf-8") as f:
            f.write(f"; Daily time-series inputs for {name}\n")
            f.write("; Stub schedule generated by _generate_dane_temp_fixture.py\n")
            f.write("Date,flow,temperature,turbidity,light\n")
            import datetime, math
            d = datetime.date(2011, 1, 1)
            for day in range(365):
                doy = day + 1
                temp = 2.0 + 8.0 * (1.0 + math.sin(2 * math.pi * (doy - 90) / 365.0))
                f.write(f"{d.isoformat()},50.0,{temp:.2f},5.0,500\n")
                d += datetime.timedelta(days=1)
        log.info("wrote %s-{Depths,Vels,TimeSeriesInputs}.csv", name)

    # Step 6: write the shapefile
    shp = SHAPEFILE_DIR / "dane.shp"
    cells_gdf_for_shp = cells_gdf.rename(columns={
        "cell_id": "ID_TEXT",
        "reach_name": "REACH_NAME",
        "area": "AREA",
        "dist_escape": "M_TO_ESC",
        "num_hiding": "NUM_HIDING",
        "frac_vel_shelter": "FRACVSHL",
        "frac_spawn": "FRACSPWN",
    })
    cells_gdf_for_shp.to_file(shp)
    log.info("wrote shapefile → %s (%d features, CRS=%s)",
             shp, len(cells_gdf_for_shp), cells_gdf_for_shp.crs)

    print()
    print("=" * 60)
    print(f"Output: {OUT_DIR}")
    print(f"  Shapefile: {shp.name} ({len(cells_gdf_for_shp)} cells, {cells_gdf_for_shp.crs})")
    for name in reach_lines:
        n = int((cells_gdf["reach_name"] == name).sum())
        print(f"  {name}: {n} cells, 3 CSVs")


if __name__ == "__main__":
    main()
