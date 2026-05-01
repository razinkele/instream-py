"""Append per-reach channel-envelope polygons to the OSM-input sidecars.

v0.56.4 wrote `*-osm-polygons.shp` sidecars containing only the raw OSM
`natural=water` polygons that were near each centerline. For Lithuanian
small rivers OSM polygon coverage is very sparse (Salpe: 0, Salantas:
1, Babrungas: 6, Veivirzas: 10), so the Spatial-panel overlay has no
visible "area" feature for several rivers.

v0.56.7 fix: for each reach in the centerlines sidecar, compute a
buffered envelope (union(centerlines).buffer(VIZ_BUFFER_M)) and append
it to the polygons sidecar with the reach's name. The envelope reflects
the channel buffer used by `generate_cells` (CELL_SIZE_M *
BUFFER_FACTOR = 10 m total) widened to ``VIZ_BUFFER_M`` for visibility
on the map. Each reach now has at least one polygon row in the sidecar.

Idempotent: re-runs detect existing envelope rows (REACH_NAME suffixed
with `-channel`) and replace them.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "example_minija_basin" / "Shapefile"

# Visualization buffer (metres). Wider than the cell-buffer (10 m) so the
# envelope shows up as a recognisable channel shape on a basemap. 25 m
# each side gives a 50 m wide ribbon — visible at zoom 13+ without
# overstating real river width too much (real channels here are 5-30 m).
VIZ_BUFFER_M = 25.0

# UTM zone for Lithuanian Minija basin (matches the extenders).
UTM_EPSG = 32634

CHANNEL_SUFFIX = "-channel"

SIDECAR_PAIRS = [
    (
        FIXTURE_DIR / "MinijaBasinExample-tributaries-osm-centerlines.shp",
        FIXTURE_DIR / "MinijaBasinExample-tributaries-osm-polygons.shp",
    ),
    (
        FIXTURE_DIR / "MinijaBasinExample-mainstem-osm-centerlines.shp",
        FIXTURE_DIR / "MinijaBasinExample-mainstem-osm-polygons.shp",
    ),
]


def add_envelopes(centerline_path: Path, polygon_path: Path) -> None:
    if not centerline_path.exists():
        log.warning("missing centerlines sidecar: %s — skipping", centerline_path.name)
        return

    centerlines = gpd.read_file(centerline_path)
    if centerlines.empty:
        log.info("[%s] empty centerlines — skipping", centerline_path.name)
        return

    target_crs = centerlines.crs
    cl_utm = centerlines.to_crs(epsg=UTM_EPSG)

    envelope_rows: list = []
    for reach_name, group in cl_utm.groupby("REACH_NAME"):
        envelope = group.geometry.union_all().buffer(VIZ_BUFFER_M)
        if envelope.is_empty or not envelope.is_valid:
            log.warning("[%s] invalid envelope — skipping", reach_name)
            continue
        envelope_rows.append({
            "REACH_NAME": f"{reach_name}{CHANNEL_SUFFIX}",
            "geometry": envelope,
        })

    if not envelope_rows:
        log.warning("[%s] no envelopes built", centerline_path.name)
        return

    envelopes_utm = gpd.GeoDataFrame(envelope_rows, geometry="geometry",
                                    crs=f"EPSG:{UTM_EPSG}")
    envelopes = envelopes_utm.to_crs(target_crs)

    if polygon_path.exists():
        existing = gpd.read_file(polygon_path)
        # Drop any prior envelope rows so re-runs are idempotent.
        existing = existing[
            ~existing["REACH_NAME"].astype(str).str.endswith(CHANNEL_SUFFIX)
        ].copy()
        log.info("[%s] keeping %d existing OSM water polygons", polygon_path.name, len(existing))
        merged = gpd.GeoDataFrame(
            pd.concat([existing, envelopes], ignore_index=True),
            geometry="geometry",
            crs=target_crs,
        )
    else:
        log.info("[%s] no existing polygons sidecar — writing fresh", polygon_path.name)
        merged = envelopes

    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        stale = polygon_path.with_suffix(ext)
        if stale.exists():
            stale.unlink()
    merged.to_file(polygon_path, driver="ESRI Shapefile")

    n_envelopes = int(
        merged["REACH_NAME"].astype(str).str.endswith(CHANNEL_SUFFIX).sum()
    )
    log.info(
        "[%s] wrote %d total polygons (%d OSM water + %d channel envelopes)",
        polygon_path.name, len(merged), len(merged) - n_envelopes, n_envelopes,
    )


def main() -> None:
    for cl_path, poly_path in SIDECAR_PAIRS:
        add_envelopes(cl_path, poly_path)
    log.info("OK: channel envelopes added to all sidecars.")


if __name__ == "__main__":
    main()
