"""Generate physical (geographically real) domain fixtures for the 4 WGBAST rivers.

Replaces the Nemunas-template-copy fixtures with shapefiles whose cells sit at
real lat/lon locations for each river, using curated waypoints from public
geographic data (mouth + source + intermediate tributary confluences).

Rivers covered (north to south):
  Tornionjoki   — Torne river, FI/SE border; mouth Tornio-Haparanda
  Simojoki      — Simo river, Finland; mouth Simo
  Byskealven    — Byske river, Sweden; mouth Byske
  Morrumsan     — Mörrum river, Sweden; mouth Mörrum

For each river, builds a 4-reach topology (Mouth → Lower → Middle → Upper)
along a simplified polyline. Hex cells are generated via the existing
`app/modules/create_model_grid.generate_cells` used by the Create-Model UI.
Output shapefiles match the `spatial.gis_properties` contract of the configs
(ID_TEXT, REACH_NAME, AREA, M_TO_ESC, NUM_HIDING, FRACVSHL, FRACSPWN).

Usage:
    micromamba run -n shiny python scripts/_generate_wgbast_physical_domains.py

This is idempotent — re-running overwrites existing shapefiles.
"""
from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

# Borrow the Create-Model hex-cell infrastructure so the output is schema-
# compatible with what the Shiny UI produces and what SalmopyModel loads.
from modules.create_model_grid import generate_cells  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# River waypoints (WGS84, lon/lat). Curated from:
#   - OpenStreetMap (main channel + major tributary confluences)
#   - SMHI (Sweden) and SYKE (Finland) public river metadata
#   - Wikipedia gazetteer entries (cross-referenced)
# Each river lists waypoints from mouth (index 0) to source (last index).
# We split the polyline into 4 reaches at roughly equal along-channel
# distances so every fixture has Mouth / Lower / Middle / Upper reaches.
# ---------------------------------------------------------------------------


@dataclass
class River:
    short_name: str           # example_tornionjoki
    stem: str                 # TornionjokiExample (for CSV/Shapefile naming)
    river_name: str           # "Tornionjoki" (for config river_name field)
    latitude: float           # river-mouth latitude (config.light.latitude)
    # Waypoints: list of (lon, lat) pairs, MOUTH first, SOURCE last.
    # Must be in geographic (EPSG:4326) coordinates.
    waypoints: list[tuple[float, float]]
    # Cell size in metres (hex circumradius). Larger rivers → bigger cells.
    cell_size_m: float
    # Buffer factor × cell_size_m defines the cross-channel extent.
    # ~half channel width in cell units. 30-50 m channels -> factor 3-4.
    buffer_factor: float


RIVERS: list[River] = [
    # --- Tornionjoki (Torne River) — Finnish-Swedish border ---
    # Mouth Tornio/Haparanda (~65.88°N). Flows south from Lake Kilpisjärvi
    # region; the Finnish-Swedish border follows the main stem.
    # Source waypoint: Muonionjoki confluence at Pajala/Kolari.
    River(
        short_name="example_tornionjoki",
        stem="TornionjokiExample",
        river_name="Tornionjoki",
        latitude=65.85,
        waypoints=[
            (24.142, 65.881),   # 0: Tornio/Haparanda (mouth into Gulf of Bothnia)
            (23.910, 66.260),   # 1: Karunki area (lower)
            (23.665, 66.820),   # 2: Ylitornio (middle)
            (23.640, 67.180),   # 3: Pello (upper-middle)
            (23.530, 67.600),   # 4: Kolari / Muonionjoki confluence (upper)
        ],
        cell_size_m=150.0,      # ~100m channel width, 150m cells
        buffer_factor=3.0,
    ),
    # --- Simojoki (Simo River) — small Finnish Baltic salmon river ---
    # Mouth at Simo (~65.62°N). Flows SW from Lake Simojärvi.
    River(
        short_name="example_simojoki",
        stem="SimojokiExample",
        river_name="Simojoki",
        latitude=65.62,
        waypoints=[
            (25.063, 65.619),   # 0: Simo (mouth into Gulf of Bothnia)
            (25.400, 65.780),   # 1: Simonkylä (lower)
            (25.950, 65.900),   # 2: Ranua area (middle)
            (26.600, 66.000),   # 3: Tainijärvi area
            (26.916, 66.091),   # 4: Simojärvi outflow (upper/source)
        ],
        cell_size_m=80.0,       # ~30m channel width, smaller cells
        buffer_factor=3.0,
    ),
    # --- Byskealven (Byske River) — Swedish Baltic salmon river ---
    # Mouth at Byske (~64.94°N). Flows SE from Västerbotten highlands.
    River(
        short_name="example_byskealven",
        stem="ByskealvenExample",
        river_name="Byskealven",
        latitude=64.94,
        waypoints=[
            (21.182, 64.945),   # 0: Byske (mouth into Gulf of Bothnia)
            (20.700, 65.000),   # 1: Fällfors
            (20.100, 65.070),   # 2: Jörn area
            (19.400, 65.120),   # 3: Kåtaviken area
            (18.850, 65.160),   # 4: Arvidsjaur area (upper)
        ],
        cell_size_m=80.0,
        buffer_factor=3.0,
    ),
    # --- Mörrumsån (Mörrum River) — southern Swedish Baltic salmon river ---
    # Mouth at Mörrum (~56.17°N). Short river (~186 km); flows S from
    # Lake Möckeln. Famous salmon-angling river.
    River(
        short_name="example_morrumsan",
        stem="MorrumsanExample",
        river_name="Morrumsan",
        latitude=56.17,
        waypoints=[
            (14.745, 56.175),   # 0: Mörrum (mouth into Hanöbukten/Baltic)
            (14.702, 56.300),   # 1: Svängsta
            (14.636, 56.450),   # 2: Asarum / mid-course
            (14.595, 56.570),   # 3: Ubbaboda area
            (14.580, 56.671),   # 4: Lake Möckeln outflow (upper/source)
        ],
        cell_size_m=60.0,       # ~20m channel width, small cells
        buffer_factor=4.0,
    ),
]


# Property naming from configs/example_baltic.yaml spatial.gis_properties.
# The loader reads these exact column names from the shapefile.
COLUMN_RENAME = {
    "cell_id": "ID_TEXT",
    "reach_name": "REACH_NAME",
    "area": "AREA",
    "dist_escape": "M_TO_ESC",
    "num_hiding": "NUM_HIDING",
    "frac_vel_shelter": "FRACVSHL",
    "frac_spawn": "FRACSPWN",
}


def build_reach_segments(river: River) -> dict:
    """Split river waypoints into 4 reaches (Mouth/Lower/Middle/Upper).

    With 5 waypoints we get 4 segments; each segment becomes one reach.
    The most-downstream reach (0→1) is the Mouth; it receives
    frac_spawn=0 because Atlantic salmon spawn upstream, not at the mouth.
    Upstream reaches get progressively higher frac_spawn.
    """
    wps = river.waypoints
    reach_names = ["Mouth", "Lower", "Middle", "Upper"]
    # Salmon prefer fast-water riffles in mid-upper reaches for redd digging.
    frac_spawn = [0.0, 0.15, 0.35, 0.30]

    segments = {}
    for i, name in enumerate(reach_names):
        line = LineString([wps[i], wps[i + 1]])
        segments[name] = {
            "segments": [line],
            "frac_spawn": frac_spawn[i],
            "type": "river",
        }
    return segments


def write_river_shapefile(river: River) -> Path:
    """Generate hex cells for `river` and write {RiverStem}Example.shp."""
    fixture_dir = ROOT / "tests" / "fixtures" / river.short_name
    shp_dir = fixture_dir / "Shapefile"
    shp_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("River: %s  (%s)", river.river_name, river.short_name)
    log.info("Latitude: %.3f  |  cell_size=%s m, buffer=%s×",
             river.latitude, river.cell_size_m, river.buffer_factor)

    reach_segments = build_reach_segments(river)
    total_len = sum(
        r["segments"][0].length for r in reach_segments.values()
    )
    log.info("Main channel length (degrees): %.4f  [~%s km at this lat]",
             total_len, int(total_len * 111))

    cells = generate_cells(
        reach_segments=reach_segments,
        cell_size=river.cell_size_m,
        cell_shape="hexagonal",
        buffer_factor=river.buffer_factor,
        min_overlap=0.1,
    )

    if cells.empty:
        raise RuntimeError(
            f"{river.short_name}: generate_cells returned 0 cells. "
            f"Increase buffer_factor or cell_size and re-run."
        )

    log.info("Generated %d cells", len(cells))
    log.info("Per-reach distribution:")
    for reach, count in cells["reach_name"].value_counts().sort_index().items():
        log.info("  %-8s %d cells", reach, count)

    # Rename columns to match the shapefile-loader contract
    cells = cells.rename(columns=COLUMN_RENAME)

    # Coerce to str for the ID column (loader expects string IDs)
    cells["ID_TEXT"] = cells["ID_TEXT"].astype(str)

    # Clear any stale Shapefile/* from a prior run (Nemunas leftover)
    for pat in ("*.shp", "*.shx", "*.dbf", "*.prj", "*.cpg"):
        for stale in shp_dir.glob(pat):
            stale.unlink()

    out_path = shp_dir / f"{river.stem}.shp"
    cells.to_file(out_path, driver="ESRI Shapefile")
    log.info("Wrote %s (%d cells, EPSG:4326)", out_path.relative_to(ROOT), len(cells))
    return out_path


def main():
    for river in RIVERS:
        write_river_shapefile(river)
    log.info("=" * 60)
    log.info("All 4 WGBAST river shapefiles regenerated with real geography.")


if __name__ == "__main__":
    main()
