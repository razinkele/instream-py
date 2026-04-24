"""Fetch OSM waterway polylines for the 4 WGBAST rivers via Overpass API.

Queries by (bbox, name pattern) for each river, downloads all ways tagged
`waterway=river`, and caches the raw GeoJSON-style response to
`tests/fixtures/_osm_cache/{river}.json` so subsequent runs are instant.

Companion to `scripts/_generate_wgbast_physical_domains.py`, which consumes
the cached polylines to build 4-reach hex-cell shapefiles.

Usage:
    micromamba run -n shiny python scripts/_fetch_wgbast_osm_polylines.py
    micromamba run -n shiny python scripts/_fetch_wgbast_osm_polylines.py --refresh  # ignore cache

The Overpass API is a shared public service. Default: fetch only when
cache is missing. Use --refresh to force re-download (e.g. to pick up
new OSM edits).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from shapely.geometry import LineString, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "tests" / "fixtures" / "_osm_cache"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]


@dataclass
class RiverQuery:
    short_name: str          # example_tornionjoki
    river_label: str         # "Tornionjoki"
    # bbox: (south, west, north, east) — Overpass uses S,W,N,E order
    bbox: tuple[float, float, float, float]
    # Regex of name values to match (Finnish, Swedish, English etc.)
    name_regex: str
    # Expected mouth location for orientation (lon, lat). Used later to
    # compute along-channel distance for reach splitting.
    mouth_lon_lat: tuple[float, float]


QUERIES: list[RiverQuery] = [
    RiverQuery(
        short_name="example_tornionjoki",
        river_label="Tornionjoki",
        # Covers mouth at Tornio up through Muonionjoki confluence and beyond.
        # The main stem becomes Muonionjoki then Könkämäeno going north.
        bbox=(65.5, 22.8, 68.6, 25.6),
        name_regex="^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne)$",
        mouth_lon_lat=(24.142, 65.881),
    ),
    RiverQuery(
        short_name="example_simojoki",
        river_label="Simojoki",
        bbox=(65.5, 24.5, 66.3, 27.2),
        name_regex="^(Simojoki)$",
        mouth_lon_lat=(25.063, 65.619),
    ),
    RiverQuery(
        short_name="example_byskealven",
        river_label="Byskeälven",
        bbox=(64.8, 18.3, 65.3, 21.5),
        name_regex="^(Byskeälven|Byske älv)$",
        mouth_lon_lat=(21.182, 64.945),
    ),
    RiverQuery(
        short_name="example_morrumsan",
        river_label="Mörrumsån",
        bbox=(56.0, 14.3, 56.75, 14.95),
        name_regex="^(Mörrumsån|Morrumsan)$",
        mouth_lon_lat=(14.745, 56.175),
    ),
]


def _build_query(q: RiverQuery) -> str:
    """Build Overpass QL for waterway=river ways within bbox matching the
    river's name regex."""
    s, w, n, e = q.bbox
    return (
        f'[out:json][timeout:180];\n'
        f'way["waterway"="river"]["name"~"{q.name_regex}"]'
        f'({s:.4f},{w:.4f},{n:.4f},{e:.4f});\n'
        f'out geom;'
    )


def fetch_overpass(q: RiverQuery) -> dict:
    """POST the query to Overpass and return the parsed JSON response."""
    query = _build_query(q)
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            log.info("[%s] querying %s", q.river_label, endpoint)
            resp = requests.post(endpoint, data={"data": query}, timeout=200)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("[%s] endpoint failed: %s (%s)", q.river_label, endpoint, exc)
            last_err = exc
            time.sleep(2)
    raise RuntimeError(f"All Overpass endpoints failed for {q.river_label}: {last_err}")


def parse_ways_to_linestrings(osm_json: dict) -> list[dict]:
    """Convert Overpass `out geom` response into per-way dicts containing
    a shapely LineString (in WGS84 lon/lat) plus metadata."""
    features = []
    for element in osm_json.get("elements", []):
        if element.get("type") != "way":
            continue
        geom = element.get("geometry")
        if not geom or len(geom) < 2:
            continue
        # OSM geometry is a list of {lat, lon} pairs. Shapely wants (lon, lat).
        coords = [(node["lon"], node["lat"]) for node in geom]
        try:
            line = LineString(coords)
        except Exception as exc:
            log.debug("skipping malformed way %s: %s", element.get("id"), exc)
            continue
        features.append({
            "id": element.get("id"),
            "name": element.get("tags", {}).get("name", ""),
            "geometry": mapping(line),
        })
    return features


def cache_path(short_name: str) -> Path:
    return CACHE_DIR / f"{short_name}.json"


def load_cached_ways(short_name: str) -> list[dict] | None:
    p = cache_path(short_name)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_cached_ways(short_name: str, features: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = cache_path(short_name)
    p.write_text(json.dumps(features, indent=2), encoding="utf-8")
    log.info("[%s] cached %d ways to %s", short_name, len(features), p.relative_to(ROOT))


def fetch_river(q: RiverQuery, refresh: bool = False) -> list[dict]:
    if not refresh:
        cached = load_cached_ways(q.short_name)
        if cached is not None:
            log.info("[%s] using cached %d ways", q.river_label, len(cached))
            return cached

    osm_json = fetch_overpass(q)
    features = parse_ways_to_linestrings(osm_json)
    if not features:
        raise RuntimeError(
            f"[{q.river_label}] Overpass returned 0 ways. Check bbox/name_regex."
        )
    log.info("[%s] parsed %d ways from Overpass response",
             q.river_label, len(features))
    save_cached_ways(q.short_name, features)
    return features


def features_to_linestrings(features: list[dict]) -> list[LineString]:
    return [shape(f["geometry"]) for f in features]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ignore cache, force re-download")
    args = ap.parse_args()

    total = 0
    for q in QUERIES:
        features = fetch_river(q, refresh=args.refresh)
        total += len(features)
        # Quick sanity report
        lines = features_to_linestrings(features)
        if lines:
            lens_m_approx = [  # degrees * 111 km approximate
                sum(
                    ((c2[0] - c1[0]) ** 2 + (c2[1] - c1[1]) ** 2) ** 0.5 * 111
                    for c1, c2 in zip(line.coords[:-1], line.coords[1:])
                )
                for line in lines
            ]
            total_km = sum(lens_m_approx)
            log.info("[%s] %d ways, ~%.1f km total polyline",
                     q.river_label, len(lines), total_km)

    log.info("=" * 60)
    log.info("All rivers: %d ways cached under %s", total, CACHE_DIR.relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main() or 0)
