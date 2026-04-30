"""Fetch OSM polylines + polygons for Minija basin tributaries (v0.55.0+).

Companion to `_extend_minija_with_tributaries.py` which generates hex cells
from the cached features. Mirrors `_fetch_wgbast_osm_polylines.py` for the
Baltic-state context.

v0.55.2: also fetches water POLYGONS (natural=water + waterway=riverbank)
within the basin bbox so the extender can clip cells to real river shapes
instead of buffering centerlines blindly. Without polygons, the v0.55.0/.1
fixture generated tributaries 5-10× wider than reality (caught by
test_geographic_conformance: RIVER_TOO_WIDE).

Caches:
  tests/fixtures/_osm_cache/minija_tributaries.json          (polylines)
  tests/fixtures/_osm_cache/minija_tributaries_polygons.json (water polygons)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from shapely.geometry import LineString, mapping, shape

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "tests" / "fixtures" / "_osm_cache"
CACHE_FILE = CACHE_DIR / "minija_tributaries.json"
POLY_CACHE_FILE = CACHE_DIR / "minija_tributaries_polygons.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]


@dataclass
class TributaryQuery:
    name: str            # ASCII identifier ("Babrungas")
    name_regex: str      # OSM name match (with diacritics)
    # Confluence with Minija — for orientation / sanity check
    confluence_lon_lat: tuple[float, float]


# Minija basin bounding box: NW Lithuania, ~21-22°E × 55.3-56.1°N
MINIJA_BBOX = (55.3, 20.9, 56.1, 22.2)  # (S, W, N, E)


TRIBUTARIES: list[TributaryQuery] = [
    TributaryQuery(
        name="Babrungas",
        name_regex="^(Babrungas)$",
        confluence_lon_lat=(21.85, 55.92),  # near Plungė
    ),
    TributaryQuery(
        # OSM tags this river as "Veiviržas" (Lithuanian masculine form,
        # cross-checked via wikidata=Q3500757 / wikipedia=lt:Veiviržas).
        # The original v0.55.0 regex used "Veiviržė" — the feminine form
        # which is a common typo / declension confusion. Probed via
        # `_probe_veivirze_osm.py` and confirmed.
        name="Veivirzas",
        name_regex="^(Veiviržas|Veivirzas)$",
        confluence_lon_lat=(21.40, 55.55),  # near Lankupiai
    ),
    TributaryQuery(
        name="Salantas",
        name_regex="^(Salantas)$",
        confluence_lon_lat=(21.62, 55.99),  # near Salantai
    ),
    TributaryQuery(
        name="Salpe",
        name_regex="^(Šalpė|Salpe)$",
        confluence_lon_lat=(21.50, 55.70),  # mid-river estimate
    ),
]


def _build_query(t: TributaryQuery) -> str:
    s, w, n, e = MINIJA_BBOX
    return (
        f'[out:json][timeout:180];\n'
        f'way["waterway"~"^(river|stream)$"]["name"~"{t.name_regex}"]'
        f'({s:.4f},{w:.4f},{n:.4f},{e:.4f});\n'
        f'out geom;'
    )


def _build_polygon_query() -> str:
    """v0.55.2: water polygons (natural=water + waterway=riverbank +
    multipolygon relations) within the Minija basin bbox. NOT name-filtered
    — within the bbox, water polygons mostly belong to the river system.
    Extender code clips them to per-tributary buffers.

    Same query shape as `_fetch_wgbast_osm_polylines._build_polygon_query`.
    """
    s, w, n, e = MINIJA_BBOX
    return (
        f'[out:json][timeout:180];\n'
        f'(\n'
        f'  way["natural"="water"]({s:.4f},{w:.4f},{n:.4f},{e:.4f});\n'
        f'  way["waterway"="riverbank"]({s:.4f},{w:.4f},{n:.4f},{e:.4f});\n'
        f'  relation["natural"="water"]({s:.4f},{w:.4f},{n:.4f},{e:.4f});\n'
        f');\n'
        f'out geom;'
    )


def fetch_overpass(t: TributaryQuery, query: str | None = None) -> dict:
    if query is None:
        query = _build_query(t)
    label = t.name if t else "polygons"
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            log.info("[%s] querying %s", label, endpoint)
            resp = requests.post(endpoint, data={"data": query}, timeout=200)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("[%s] endpoint failed: %s (%s)", label, endpoint, exc)
            last_err = exc
    raise RuntimeError(f"All Overpass endpoints failed for {label}: {last_err}")


def fetch_polygons() -> dict:
    """Fetch all water polygons in the Minija basin bbox."""
    query = _build_polygon_query()
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            log.info("[polygons] querying %s", endpoint)
            resp = requests.post(endpoint, data={"data": query}, timeout=200)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("[polygons] endpoint failed: %s (%s)", endpoint, exc)
            last_err = exc
    raise RuntimeError(f"All Overpass endpoints failed for polygons: {last_err}")


def parse_ways(data: dict) -> list[dict]:
    """Convert Overpass elements to GeoJSON-like records (LineStrings)."""
    out = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        coords = [(n["lon"], n["lat"]) for n in el.get("geometry", [])]
        if len(coords) < 2:
            continue
        out.append({
            "id": el["id"],
            "tags": el.get("tags", {}),
            "geometry": mapping(LineString(coords)),
        })
    return out


def parse_polygons(data: dict) -> list[dict]:
    """Convert Overpass elements to GeoJSON-like records (Polygons).

    Closed-ring ways become Polygons. Relations are skipped (would need
    multipolygon assembly; simpler ways usually cover what we need).
    """
    from shapely.geometry import Polygon
    out = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        coords = [(n["lon"], n["lat"]) for n in el.get("geometry", [])]
        if len(coords) < 4:
            continue
        # Polygon needs first == last
        if coords[0] != coords[-1]:
            continue
        try:
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_valid or poly.area <= 0:
                continue
            out.append({
                "id": el["id"],
                "tags": el.get("tags", {}),
                "geometry": mapping(poly),
            })
        except Exception:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="Ignore cache; force re-download.")
    args = ap.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    have_lines = CACHE_FILE.exists() and not args.refresh
    have_polys = POLY_CACHE_FILE.exists() and not args.refresh
    if have_lines and have_polys:
        log.info("Both caches present — use --refresh to re-download.")
        with open(CACHE_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        for trib_name, ways in cached.items():
            log.info("  %s: %d polylines", trib_name, len(ways))
        with open(POLY_CACHE_FILE, encoding="utf-8") as f:
            polys = json.load(f)
        log.info("  polygons: %d", len(polys))
        return

    if not have_lines:
        all_ways: dict[str, list[dict]] = {}
        for t in TRIBUTARIES:
            log.info(f"=== Fetching {t.name} polylines ===")
            try:
                data = fetch_overpass(t)
                ways = parse_ways(data)
                log.info("  %s: %d polylines extracted", t.name, len(ways))
                all_ways[t.name] = ways
            except Exception as exc:
                log.error("  %s: FAILED — %s", t.name, exc)
                all_ways[t.name] = []
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(all_ways, f, ensure_ascii=False, indent=1)
        log.info("Wrote %s", CACHE_FILE.relative_to(ROOT))

    if not have_polys:
        log.info("=== Fetching water polygons (basin-wide bbox) ===")
        try:
            data = fetch_polygons()
            polys = parse_polygons(data)
            log.info("Extracted %d water polygons in basin bbox", len(polys))
            with open(POLY_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(polys, f, ensure_ascii=False, indent=1)
            log.info("Wrote %s", POLY_CACHE_FILE.relative_to(ROOT))
        except Exception as exc:
            log.error("Polygon fetch FAILED — %s", exc)
            log.error("Extender will fall back to tight-buffer mode for "
                      "centerline-only tributaries.")


if __name__ == "__main__":
    main()
