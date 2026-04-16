"""Local OSM PBF hydrology extraction for the Create Model panel.

Replaces Overpass API with offline pipeline:
  1. Download country .osm.pbf from Geofabrik (once, ~200 MB)
  2. Clip to bbox via ``osmium extract --bbox`` CLI (~10 s)
  3. Extract waterways + water bodies via pyosmium handlers (~13 s)
  4. Return GeoDataFrames with standard columns
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

import geopandas as gpd
import osmium
import shapely.wkb
from shapely.validation import make_valid

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OSM_DIR = Path(__file__).resolve().parent.parent / "data" / "osm"

_GEOFABRIK_BASE = "https://download.geofabrik.de/europe"

GEOFABRIK_COUNTRIES: set[str] = {
    "lithuania", "latvia", "estonia", "poland", "finland",
    "sweden", "norway", "denmark", "germany", "france",
    "spain", "italy", "netherlands", "belgium", "ireland",
}

WATERWAY_STRAHLER: dict[str, int] = {
    "river": 6,
    "canal": 4,
    "stream": 2,
    "ditch": 1,
    "drain": 1,
}

# Waterway types we extract as centerlines
_WATERWAY_TYPES = frozenset(WATERWAY_STRAHLER.keys())

# Water polygon tags that route to *waterways* GDF (river-like polygons)
_RIVER_WATER_TAGS = {"river", "stream", "canal", "oxbow"}

# ---------------------------------------------------------------------------
# URL / path helpers
# ---------------------------------------------------------------------------


def geofabrik_url(country: str) -> str:
    """Return the Geofabrik download URL for *country*."""
    c = country.lower().strip()
    return f"{_GEOFABRIK_BASE}/{c}-latest.osm.pbf"


def pbf_path(country: str) -> Path:
    """Return local cache path for the country PBF."""
    c = country.lower().strip()
    return _OSM_DIR / f"{c}-latest.osm.pbf"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def ensure_pbf(
    country: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Path:
    """Download the country PBF from Geofabrik if not already cached."""
    import urllib.request

    dst = pbf_path(country)
    if dst.exists():
        return dst

    url = geofabrik_url(country)
    if progress_cb:
        progress_cb(f"Downloading {url} …")

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".pbf.part")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "instream-py/1.0"})
        with urllib.request.urlopen(req) as resp, open(tmp, "wb") as fout:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(1 << 20)  # 1 MB
                if not chunk:
                    break
                fout.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    pct = downloaded * 100 // total
                    progress_cb(f"Downloading … {pct}%")
        tmp.rename(dst)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    return dst


# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------


def _clip_pbf(
    pbf_file: Path,
    bbox_wgs84: tuple[float, float, float, float],
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Path:
    """Clip *pbf_file* to *bbox_wgs84* (minx, miny, maxx, maxy).

    Results are cached by bbox MD5 hash inside ``_OSM_DIR``.
    """
    left, bottom, right, top = bbox_wgs84
    bbox_str = f"{left},{bottom},{right},{top}"
    bbox_hash = hashlib.md5(bbox_str.encode()).hexdigest()[:12]
    clipped = _OSM_DIR / f"clip_{bbox_hash}.osm.pbf"

    if clipped.exists():
        return clipped

    osmium_bin = shutil.which("osmium")
    if osmium_bin is None:
        raise RuntimeError(
            "osmium-tool not found on PATH. "
            "Install with: micromamba install -n shiny osmium-tool"
        )

    if progress_cb:
        progress_cb("Clipping PBF to bounding box …")

    clipped.parent.mkdir(parents=True, exist_ok=True)
    tmp = clipped.with_suffix(".pbf.part")

    try:
        subprocess.run(
            [
                osmium_bin, "extract",
                "--bbox", bbox_str,
                "--set-bounds",
                "--strategy", "complete_ways",
                "-o", str(tmp),
                "--overwrite",
                str(pbf_file),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        tmp.rename(clipped)
    except subprocess.CalledProcessError as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"osmium extract failed: {exc.stderr}") from exc

    return clipped


# ---------------------------------------------------------------------------
# pyosmium extraction
# ---------------------------------------------------------------------------


class _HydroHandler(osmium.SimpleHandler):
    """Collect waterway and water-body geometries from a PBF file."""

    def __init__(self) -> None:
        super().__init__()
        self._wkb = osmium.geom.WKBFactory()
        self.waterway_rows: list[tuple[str, str, str]] = []
        self.water_body_rows: list[tuple[str, str, str]] = []

    # -- polygon features (areas) ------------------------------------------

    def area(self, a: osmium.osm.Area) -> None:
        tags = a.tags

        # natural=water polygons
        natural = tags.get("natural", "")
        water = tags.get("water", "")
        waterway_tag = tags.get("waterway", "")

        is_river_polygon = False
        if natural == "water" and water in _RIVER_WATER_TAGS:
            is_river_polygon = True
        elif waterway_tag == "riverbank":
            is_river_polygon = True

        if is_river_polygon or (natural == "water" and not water in _RIVER_WATER_TAGS):
            try:
                wkb_hex = self._wkb.create_multipolygon(a)
            except Exception:
                return

            name = tags.get("name", "")
            type_tag = water or waterway_tag or natural

            if is_river_polygon:
                self.waterway_rows.append((wkb_hex, name, type_tag))
            else:
                self.water_body_rows.append((wkb_hex, name, type_tag))

    # -- linear features (ways) --------------------------------------------

    def way(self, w: osmium.osm.Way) -> None:
        ww = w.tags.get("waterway", "")
        if ww not in _WATERWAY_TYPES:
            return
        try:
            wkb_hex = self._wkb.create_linestring(w)
        except Exception:
            return
        name = w.tags.get("name", "")
        self.waterway_rows.append((wkb_hex, name, ww))


def _extract_hydro(
    pbf_file: Path,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Run pyosmium handler and return (waterway_rows, water_body_rows)."""
    if progress_cb:
        progress_cb("Extracting hydrology features …")

    handler = _HydroHandler()
    handler.apply_file(str(pbf_file), locations=True)

    return handler.waterway_rows, handler.water_body_rows


# ---------------------------------------------------------------------------
# GeoDataFrame conversion
# ---------------------------------------------------------------------------


def _rows_to_gdf(
    rows: list[tuple[str, str, str]],
    columns: list[str],
    wtype_key: str,
) -> gpd.GeoDataFrame:
    """Convert raw (wkb_hex, name, type_tag) rows into a GeoDataFrame."""
    if not rows:
        cols = ["geometry", "name", "nameText", wtype_key, "DFDD"]
        if wtype_key == "waterway":
            cols.append("STRAHLER")
        return gpd.GeoDataFrame(columns=cols, geometry="geometry", crs="EPSG:4326")

    geoms = []
    names = []
    types = []

    for wkb_hex, name, type_tag in rows:
        try:
            geom = shapely.wkb.loads(wkb_hex, hex=True)
        except Exception:
            continue
        if not geom.is_valid:
            geom = make_valid(geom)
        geoms.append(geom)
        names.append(name)
        types.append(type_tag)

    gdf = gpd.GeoDataFrame(
        {
            "name": names,
            wtype_key: types,
        },
        geometry=geoms,
        crs="EPSG:4326",
    )
    gdf["nameText"] = gdf["name"].where(gdf["name"] != "", None)
    gdf["DFDD"] = "BH" if wtype_key == "waterway" else "BH090"

    if wtype_key == "waterway":
        gdf["STRAHLER"] = gdf["waterway"].map(WATERWAY_STRAHLER).fillna(0).astype(int)

    return gdf


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_waterways(
    country: str,
    bbox_wgs84: tuple[float, float, float, float],
    progress_cb: Optional[Callable[[str], None]] = None,
) -> gpd.GeoDataFrame:
    """Return waterway centerlines + river polygons as a GeoDataFrame."""
    pbf = ensure_pbf(country, progress_cb)
    clipped = _clip_pbf(pbf, bbox_wgs84, progress_cb)
    ww_rows, _ = _extract_hydro(clipped, progress_cb)
    return _rows_to_gdf(ww_rows, ["geometry", "name", "nameText", "waterway", "STRAHLER", "DFDD"], "waterway")


def query_water_bodies(
    country: str,
    bbox_wgs84: tuple[float, float, float, float],
    progress_cb: Optional[Callable[[str], None]] = None,
) -> gpd.GeoDataFrame:
    """Return water-body polygons as a GeoDataFrame."""
    pbf = ensure_pbf(country, progress_cb)
    clipped = _clip_pbf(pbf, bbox_wgs84, progress_cb)
    _, wb_rows = _extract_hydro(clipped, progress_cb)
    return _rows_to_gdf(wb_rows, ["geometry", "name", "nameText", "water", "DFDD"], "water")
