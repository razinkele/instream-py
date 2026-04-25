"""Marine sea-reach geometry helpers shared by Create Model UI and the
WGBAST batch generator.

Two functions:
  * `query_named_sea_polygon(bbox)` — Marine Regions WFS for IHO sea-area
    polygons (extracted from `create_model_panel.py::_query_marine_regions`).
  * `clip_sea_polygon_to_disk(...)` — clips a sea polygon to a true-meters
    disk around a river mouth.
"""
from __future__ import annotations

from typing import Optional

import geopandas as gpd
import requests
from shapely.geometry import MultiPolygon, Point, Polygon, box

MARINE_REGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"


def clip_sea_polygon_to_disk(
    sea_polygon: Polygon | MultiPolygon,
    mouth_lon_lat: tuple[float, float],
    *,
    radius_m: float,
    utm_epsg: int,
) -> Polygon | MultiPolygon:
    """Return `sea_polygon` clipped to a true-meters disk around the mouth.

    Algorithm (no land subtraction needed — sea_polygon is sea-only by
    definition):
      1. Reproject sea_polygon and mouth point to `utm_epsg`.
      2. Build a true-meters disk: mouth_pt.buffer(radius_m).
      3. Intersect: clipped = sea_polygon_utm.intersection(disk).
      4. Reproject the result back to EPSG:4326. Return.

    Raises:
      ValueError if the input sea_polygon is empty.
      ValueError if the intersection is empty (sea polygon does not
        cover the mouth at all).
    """
    if sea_polygon.is_empty:
        raise ValueError("sea_polygon is empty; nothing to clip")
    sea_gdf = gpd.GeoDataFrame(
        geometry=[sea_polygon], crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg)
    mouth_gdf = gpd.GeoDataFrame(
        geometry=[Point(mouth_lon_lat)], crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg)
    disk = mouth_gdf.geometry.iloc[0].buffer(radius_m)
    clipped = sea_gdf.geometry.iloc[0].intersection(disk)
    if clipped.is_empty:
        raise ValueError(
            f"sea polygon does not intersect a {radius_m}m disk at "
            f"mouth {mouth_lon_lat} — wrong waypoint?"
        )
    out = gpd.GeoDataFrame(
        geometry=[clipped], crs=f"EPSG:{utm_epsg}"
    ).to_crs("EPSG:4326")
    return out.geometry.iloc[0]


def query_named_sea_polygon(
    bbox_wgs84: tuple[float, float, float, float],
    timeout_s: int = 60,
) -> Optional[gpd.GeoDataFrame]:
    """Query Marine Regions WFS for IHO sea-area polygons within bbox.

    Returns a GeoDataFrame in EPSG:4326 with columns ['name', 'geometry'],
    post-filtered to features whose geometry actually intersects the bbox
    (Marine Regions returns global polygons that merely touch the bbox).
    Returns None on network/HTTP failure or empty result.
    """
    west, south, east, north = bbox_wgs84
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "MarineRegions:iho",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{west},{south},{east},{north},EPSG:4326",
    }
    try:
        # `with` ensures the connection-pool socket is returned to the
        # pool on every exit path (size-cap return, exception, success).
        # Without it, repeated retries on Windows can stall on socket
        # exhaustion until GC runs.
        with requests.get(MARINE_REGIONS_WFS, params=params, timeout=timeout_s) as resp:
            resp.raise_for_status()
            # Belt-and-suspenders: cap on payload size. The shiny
            # machine has 16 GB RAM and ~100 GB free disk per CLAUDE.md;
            # a 50 MB cap is comfortably above the expected ~1-5 MB for
            # an IHO sea-area query and below OOM risk.
            if int(resp.headers.get("Content-Length", 0) or 0) > 50_000_000:
                return None
            geoj = resp.json()
    except Exception as exc:
        # Log the exception class+message before swallowing so a CI
        # failure has a hint (DNS vs 503 vs malformed JSON vs timeout).
        import logging
        logging.warning(
            "Marine Regions WFS query failed (%s): %s",
            type(exc).__name__, exc,
        )
        return None
    if not geoj.get("features"):
        return None
    gdf = gpd.GeoDataFrame.from_features(geoj["features"], crs="EPSG:4326")
    # Drop null / invalid geometries before any spatial op. Marine
    # Regions WFS occasionally returns features with `"geometry": null`
    # on bbox-edge cases, which would NaN-propagate through the filter.
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid].copy()
    if gdf.empty:
        return None
    view_box = box(*bbox_wgs84)
    gdf = gdf[gdf.geometry.intersects(view_box)].copy()
    if len(gdf) > 1:
        centre = view_box.centroid
        covers = gdf[gdf.geometry.contains(centre)]
        if len(covers) > 0:
            gdf = covers.copy()
    if "name" not in gdf.columns:
        gdf["name"] = ""
    return gdf[["name", "geometry"]].reset_index(drop=True)
