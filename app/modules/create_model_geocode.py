"""Nominatim place-lookup helper for the Create Model panel.

Wraps Nominatim's free geocoding API to return a Geofabrik-compatible
country name plus a WGS84 bounding box for a place name. Used by the
🔍 Find by name button in create_model_panel.py to set the Region
dropdown and zoom the map to a user-typed location.

Pattern mirrors `query_named_sea_polygon` in create_model_marine.py:
  * timeout-bounded `requests.get` inside a `with` block (Windows
    socket-pool hygiene).
  * Content-Length cap to short-circuit on giant responses.
  * Exception logging via `logging.warning(class, message)` before
    swallowing — failure modes go to logs, not the user.
"""
from __future__ import annotations

import logging
import os

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# ISO 3166-1 alpha-2 → Geofabrik country name (subset of GEOFABRIK_COUNTRIES
# in create_model_osm.py). Initial coverage: WGBAST + Baltic countries.
_ISO_TO_GEOFABRIK: dict[str, str] = {
    "lt": "lithuania",
    "lv": "latvia",
    "ee": "estonia",
    "pl": "poland",
    "de": "germany",
    "se": "sweden",
    "fi": "finland",
    "no": "norway",
    "dk": "denmark",
}
# Note: ISO "ru" intentionally NOT mapped — `GEOFABRIK_REGIONS` only has
# "kaliningrad" for Russia (see create_model_osm.py:54). A user typing a
# place in Russia outside Kaliningrad gets the (None, bbox) "no Geofabrik
# extract" fallback path.

# Sanity: every ISO mapping resolves to a known Geofabrik country at import
# time so a future bad addition fails loudly here, not silently in
# ui.update_select.
try:
    from modules.create_model_osm import GEOFABRIK_COUNTRIES as _GFC
    _bad = [v for v in _ISO_TO_GEOFABRIK.values() if v not in _GFC]
    assert not _bad, f"_ISO_TO_GEOFABRIK contains unknown Geofabrik names: {_bad}"
except ImportError:
    pass  # tests may import this module without the panel siblings

try:
    from salmopy import __version__
except ImportError:
    __version__ = "dev"

_CONTACT = os.environ.get(
    "INSTREAM_NOMINATIM_CONTACT",
    "arturas.razinkovas-baziukas@ku.lt",
)
_USER_AGENT = f"inSTREAM-py/{__version__} ({_CONTACT})"


def lookup_place_bbox(
    name: str,
    timeout_s: int = 10,
) -> tuple[str | None, tuple[float, float, float, float]] | None:
    """Geocode `name` via Nominatim → (geofabrik_country, bbox_wgs84).

    Returns:
      (geofabrik_name, (lon_w, lat_s, lon_e, lat_n)) — happy path.
      (None, bbox) — country recognized but not in GEOFABRIK_COUNTRIES.
      None — empty input, 0 results, parse failure, or network error.
    """
    if not name or not name.strip():
        return None

    params = {
        "q": name.strip(),
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }
    headers = {"User-Agent": _USER_AGENT}

    try:
        with requests.get(
            NOMINATIM_URL, params=params, headers=headers, timeout=timeout_s,
        ) as resp:
            resp.raise_for_status()
            if int(resp.headers.get("Content-Length", 0) or 0) > 5_000_000:
                return None
            results = resp.json()
    except Exception as exc:
        logging.warning(
            "Nominatim lookup failed (%s): %s",
            type(exc).__name__, exc,
        )
        return None

    if not results:
        return None

    item = results[0]
    bb = item.get("boundingbox") or []
    if len(bb) != 4:
        return None
    try:
        lat_s, lat_n, lon_w, lon_e = (float(x) for x in bb)
    except (TypeError, ValueError):
        return None
    bbox_wgs84 = (lon_w, lat_s, lon_e, lat_n)

    iso2 = (item.get("address", {}).get("country_code") or "").lower()
    geofabrik = _ISO_TO_GEOFABRIK.get(iso2)
    return (geofabrik, bbox_wgs84)
