"""Extend example_minija_basin with tributary reaches (v0.55.0).

Reads the cached tributary OSM polylines (from
`_fetch_minija_tributaries_osm.py`), buffers them into polygons, generates
hex cells via `create_model_grid.generate_cells`, and appends them to the
existing example_minija_basin shapefile (Minija + Atmata + CuronianLagoon
+ BalticCoast from v0.54.4).

Tributaries added (right bank, north to south):
  Babrungas   ~22 km, Lake Plateliai → Plungė → Minija main stem
  Salantas    ~52 km, north Lithuania → Salantai → Minija
  Šalpė       smaller stream, mid-river area

Veiviržė was queried but returned 0 ways (OSM regex mismatch — likely a
diacritic/spelling issue). Deferred to v0.55.x patch.

Each tributary becomes a new reach with:
  * unique REACH_NAME in the shapefile DBF
  * hex cells generated at 50m circumradius (small-channel scale)
  * per-cell Depths/Vels CSVs cloned from Minija (calibration deferred)
  * reach-level TimeSeriesInputs cloned from Minija (deferred)
  * upstream_junction = unique (7/8/9), downstream_junction = 3 (joins
    Minija's upstream end). Topologically a star — geographically the
    tributaries join at different points along Minija, but with Minija
    as a single reach we converge them all at the same junction.

Side effects: rewrites
  tests/fixtures/example_minija_basin/Shapefile/MinijaBasinExample.{shp,dbf,prj,shx,cpg}
  tests/fixtures/example_minija_basin/{Babrungas,Salantas,Salpe}-{Depths,Vels,TimeSeriesInputs}.csv

Re-running is idempotent — wipes prior tributary CSVs first.
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

from modules.create_model_grid import generate_cells  # noqa: E402
from modules.create_model_utils import detect_utm_epsg  # noqa: E402


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "example_minija_basin"
SHP_PATH = FIXTURE_DIR / "Shapefile" / "MinijaBasinExample.shp"
OSM_CACHE = ROOT / "tests" / "fixtures" / "_osm_cache" / "minija_tributaries.json"

# Tributaries to add (must have data in OSM cache).
# v0.55.1: added Veivirzas (was deferred in v0.55.0 due to OSM name
# regex mismatch — actual tag is "Veiviržas", not "Veiviržė").
TRIBUTARIES = ["Babrungas", "Salantas", "Salpe", "Veivirzas"]

# Generation parameters — small streams, smaller cells than Minija main stem
CELL_SIZE_M = 50.0
BUFFER_FACTOR = 2.0   # 100 m buffer either side
FRAC_SPAWN_TRIBUTARY = 0.30  # tributaries are typically high-quality spawning habitat

# Match the COLUMN_RENAME from _generate_wgbast_physical_domains.py so the
# output shapefile follows the same DBF schema as Minija/Atmata/etc.
COLUMN_RENAME = {
    "cell_id": "ID_TEXT",
    "reach_name": "REACH_NAME",
    "area": "AREA",
    "dist_escape": "M_TO_ESC",
    "num_hiding": "NUM_HIDING",
    "frac_vel_shelter": "FRACVSHL",
    "frac_spawn": "FRACSPWN",
}


def load_osm_lines(trib_name: str) -> list[LineString]:
    data = json.loads(OSM_CACHE.read_text(encoding="utf-8"))
    ways = data.get(trib_name, [])
    lines = []
    for w in ways:
        try:
            geom = shape(w["geometry"])
            if isinstance(geom, LineString) and len(geom.coords) >= 2:
                lines.append(geom)
        except Exception as exc:
            log.warning("[%s] skipping malformed way %s: %s",
                        trib_name, w.get("id"), exc)
    return lines


def main() -> None:
    if not SHP_PATH.exists():
        raise SystemExit(
            f"missing base shapefile: {SHP_PATH}. Run "
            "_extract_minija_from_baltic.py first."
        )
    if not OSM_CACHE.exists():
        raise SystemExit(
            f"missing OSM cache: {OSM_CACHE}. Run "
            "_fetch_minija_tributaries_osm.py first."
        )

    base = gpd.read_file(SHP_PATH)
    # If a previous run left tributary cells in the shapefile, drop them
    # so we don't double-up on re-run (v0.55.1 idempotency).
    pre_tribs = [r for r in base["REACH_NAME"].unique() if r in TRIBUTARIES]
    if pre_tribs:
        log.info("Removing pre-existing tributary cells: %s", pre_tribs)
        base = base[~base["REACH_NAME"].isin(TRIBUTARIES)].copy()
    log.info("Base fixture: %d cells, reaches=%s",
             len(base), sorted(base["REACH_NAME"].unique()))
    target_crs = base.crs
    log.info("Target CRS: %s", target_crs)

    # Determine UTM zone from base bounds (for cell generation)
    base_wgs = base.to_crs("EPSG:4326")
    bw, bs, be, bn = base_wgs.total_bounds
    utm_epsg = detect_utm_epsg(center_lon=(bw + be) / 2, center_lat=(bs + bn) / 2)
    log.info("Detected UTM EPSG: %s for cell generation", utm_epsg)

    # Build reach_segments dict: one entry per tributary
    reach_segments = {}
    for trib in TRIBUTARIES:
        lines = load_osm_lines(trib)
        if not lines:
            log.warning("[%s] no OSM lines — skipping", trib)
            continue
        log.info("[%s] %d OSM line segments", trib, len(lines))
        reach_segments[trib] = {
            "segments": lines,
            "frac_spawn": FRAC_SPAWN_TRIBUTARY,
        }

    if not reach_segments:
        raise SystemExit("no tributary data — aborting.")

    # Generate cells for tributaries
    log.info("Generating hex cells for %d tributaries (cell_size=%s m, buffer=%sx)...",
             len(reach_segments), CELL_SIZE_M, BUFFER_FACTOR)
    new_cells = generate_cells(
        reach_segments=reach_segments,
        cell_size=CELL_SIZE_M,
        cell_shape="hexagonal",
        buffer_factor=BUFFER_FACTOR,
    )
    log.info("Generated %d new cells across %d tributaries",
             len(new_cells), new_cells["reach_name"].nunique())
    for r, n in new_cells["reach_name"].value_counts().sort_index().items():
        log.info("  %s: %d cells", r, n)

    # Reproject to base CRS (EPSG:3035)
    new_cells = new_cells.to_crs(target_crs)

    # Rename columns to match the shapefile schema (UPPERCASE)
    new_cells = new_cells.rename(columns=COLUMN_RENAME)
    new_cells["ID_TEXT"] = new_cells["ID_TEXT"].astype(str)

    # Drop columns base doesn't have (defensive)
    keep_cols = [c for c in base.columns if c in new_cells.columns]
    new_cells = new_cells[keep_cols + ["geometry"]] if "geometry" not in keep_cols else new_cells[keep_cols]

    # Concatenate base + tributaries
    combined = pd.concat([base, new_cells], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=target_crs)
    log.info("Combined: %d cells, reaches=%s",
             len(combined), sorted(combined["REACH_NAME"].unique()))

    # Wipe & rewrite shapefile
    shp_dir = SHP_PATH.parent
    for pat in ("*.shp", "*.shx", "*.dbf", "*.prj", "*.cpg"):
        for stale in shp_dir.glob(pat):
            stale.unlink()
    combined.to_file(SHP_PATH, driver="ESRI Shapefile")
    log.info("Wrote %s", SHP_PATH.relative_to(ROOT))

    # Clone hydraulic CSVs for each tributary from Minija
    log.info("Cloning hydraulic CSVs from Minija for each tributary...")
    for trib in TRIBUTARIES:
        if trib not in reach_segments:
            continue
        n_cells = int((combined["REACH_NAME"] == trib).sum())
        # TimeSeriesInputs: reach-scoped, copy verbatim
        src_ts = FIXTURE_DIR / "Minija-TimeSeriesInputs.csv"
        dst_ts = FIXTURE_DIR / f"{trib}-TimeSeriesInputs.csv"
        shutil.copy2(src_ts, dst_ts)
        # Depths/Vels: per-cell — need n_cells rows. Borrow the
        # _expand_per_cell_csv helper from _wire_wgbast_physical_configs.
        sys.path.insert(0, str(ROOT / "scripts"))
        from _wire_wgbast_physical_configs import _expand_per_cell_csv
        for suffix in ("Depths", "Vels"):
            src = FIXTURE_DIR / f"Minija-{suffix}.csv"
            dst = FIXTURE_DIR / f"{trib}-{suffix}.csv"
            _expand_per_cell_csv(src, dst, n_cells)
        log.info("  %s: TimeSeriesInputs + Depths(%d rows) + Vels(%d rows)",
                 trib, n_cells, n_cells)

    log.info("OK: example_minija_basin extended with %d tributaries.",
             len(reach_segments))


if __name__ == "__main__":
    main()
