"""Fetch OSM polylines for Minija basin tributaries (v0.55.0).

Companion to `_extend_minija_with_tributaries.py` which generates hex cells
from the cached polylines. Mirrors `_fetch_wgbast_osm_polylines.py` for the
Baltic-state context.

Tributaries fetched (right bank, north to south):
  Salantas    — joins Minija near Salantai (~55.99°N, 21.62°E)
  Babrungas   — Lake Plateliai → Plungė → joins Minija (~55.92°N, 21.85°E)
  Veiviržė    — joins Minija near Lankupiai (~55.55°N, 21.40°E)
  Šalpė       — small tributary in mid-river area

OSM tagging — Lithuanian rivers commonly use:
  * Native name (Lithuanian, with diacritics): "Salantas", "Babrungas",
    "Veiviržė", "Šalpė"
  * ASCII alternates sometimes appear as `name:en` or `alt_name`

Cache: tests/fixtures/_osm_cache/minija_tributaries.json
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


def fetch_overpass(t: TributaryQuery) -> dict:
    query = _build_query(t)
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            log.info("[%s] querying %s", t.name, endpoint)
            resp = requests.post(endpoint, data={"data": query}, timeout=200)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("[%s] endpoint failed: %s (%s)", t.name, endpoint, exc)
            last_err = exc
    raise RuntimeError(f"All Overpass endpoints failed for {t.name}: {last_err}")


def parse_ways(data: dict) -> list[dict]:
    """Convert Overpass elements to GeoJSON-like records."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="Ignore cache; force re-download.")
    args = ap.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if CACHE_FILE.exists() and not args.refresh:
        log.info("Cache hit: %s — skipping fetch (use --refresh to re-download)",
                 CACHE_FILE.relative_to(ROOT))
        with open(CACHE_FILE) as f:
            cached = json.load(f)
        for trib_name, ways in cached.items():
            log.info("  %s: %d ways", trib_name, len(ways))
        return

    all_ways: dict[str, list[dict]] = {}
    for t in TRIBUTARIES:
        log.info(f"=== Fetching {t.name} ===")
        try:
            data = fetch_overpass(t)
            ways = parse_ways(data)
            log.info("  %s: %d ways extracted", t.name, len(ways))
            all_ways[t.name] = ways
        except Exception as exc:
            log.error("  %s: FAILED — %s", t.name, exc)
            all_ways[t.name] = []

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(all_ways, f, ensure_ascii=False, indent=1)
    log.info("Wrote %s", CACHE_FILE.relative_to(ROOT))
    for trib_name, ways in all_ways.items():
        log.info("  %s: %d ways cached", trib_name, len(ways))


if __name__ == "__main__":
    main()
