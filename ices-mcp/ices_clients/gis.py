"""
ICES GIS (GeoServer WFS) client.

Provides access to ICES spatial reference layers:
  - ICES Statistical Areas
  - ICES Statistical Rectangles
  - ICES Ecoregions
  - HELCOM subbasins

All layers served via WFS from gis.ices.dk/geoserver/wfs.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

WFS_URL = "https://gis.ices.dk/geoserver/wfs"

# Key layer names discovered from GetCapabilities
KNOWN_LAYERS = {
    "ices_areas": "ices_eg:ICES_AREAS_VISA_SIMPLE_5KM",
    "helcom_subbasins": "ices_ref:HELCOM_subbasins_2013_WGS",
    "helcom_au": "HHAT:HELCOM_AU_L3_2018",
    "countries": "ne:countries",
    "coastlines": "ne:coastlines",
}

# Property name for ICES area filtering (discovered from schema)
_AREA_FILTER_PROP = "Area_Full"

_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def get_features(
    layer_name: str,
    *,
    max_features: int = 1000,
    cql_filter: Optional[str] = None,
    bbox: Optional[tuple[float, float, float, float]] = None,
    output_format: str = "application/json",
) -> dict[str, Any]:
    """
    Fetch features from an ICES GeoServer WFS layer.

    Parameters
    ----------
    layer_name : str
        Full layer name (e.g. 'ices_ref:ICES_Areas') or a short alias
        from KNOWN_LAYERS.
    max_features : int
        Maximum features to return.
    cql_filter : str or None
        CQL filter expression (e.g. "Area_27 LIKE '27.3.d%'").
    bbox : tuple or None
        Bounding box as (minx, miny, maxx, maxy) in EPSG:4326.
    output_format : str
        WFS output format. Default is GeoJSON.

    Returns
    -------
    dict
        GeoJSON FeatureCollection.
    """
    resolved = KNOWN_LAYERS.get(layer_name, layer_name)

    params: dict[str, Any] = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": resolved,
        "outputFormat": output_format,
        "count": max_features,
    }

    if cql_filter:
        params["CQL_FILTER"] = cql_filter
    if bbox:
        params["bbox"] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:4326"

    resp = _get_session().get(WFS_URL, params=params, timeout=120)
    resp.raise_for_status()
    return resp.json()


def list_available_layers() -> list[dict[str, str]]:
    """Return the known layer aliases and their full WFS names."""
    return [
        {"alias": alias, "wfs_name": name, "description": alias.replace("_", " ").title()}
        for alias, name in KNOWN_LAYERS.items()
    ]


def get_ices_areas(area_filter: Optional[str] = None, max_features: int = 500) -> dict:
    """Get ICES statistical areas, optionally filtered by Area_Full property."""
    cql = None
    if area_filter:
        cql = f"{_AREA_FILTER_PROP} LIKE '%{area_filter}%'"
    return get_features("ices_areas", max_features=max_features, cql_filter=cql)


def get_ices_areas_by_bbox(
    bbox: tuple[float, float, float, float],
    max_features: int = 500,
) -> dict:
    """Get ICES statistical areas within a bounding box."""
    return get_features("ices_areas", max_features=max_features, bbox=bbox)
