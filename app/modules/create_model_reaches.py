"""Reach selection logic and junction auto-detection for Create Model."""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import matplotlib.colors as mcolors
from shapely.geometry import LineString, Point

from .create_model_utils import detect_utm_epsg

# Tab10 palette as RGBA float lists (matplotlib default qualitative palette)
_TAB10 = [list(mcolors.to_rgba(c)) for c in mcolors.TABLEAU_COLORS.values()]
def _next_color(index: int) -> list[float]:
    """Return Tab10 RGBA color for the given reach index."""
    return list(_TAB10[index % len(_TAB10)])


def _empty_reach(name: str, color: list[float]) -> dict[str, Any]:
    """Create an empty reach dict with defaults."""
    return {
        "segments": [],
        "properties": [],
        "color": color,
        "upstream_junction": None,
        "downstream_junction": None,
        "frac_spawn": 0.0,
    }


def assign_segment_to_reach(
    reaches: dict[str, dict],
    reach_name: str,
    segment_geom: LineString,
    segment_props: dict,
) -> dict[str, dict]:
    """Add a LineString segment to a named reach.

    Creates the reach if it doesn't exist yet, assigning the next Tab10 color.
    Returns the updated reaches dict.
    """
    if reach_name not in reaches:
        reaches[reach_name] = _empty_reach(reach_name, _next_color(len(reaches)))

    reach = reaches[reach_name]
    reach["segments"].append(segment_geom)
    reach["properties"].append(segment_props)
    return reaches


def remove_segment_from_reach(
    reaches: dict[str, dict],
    segment_geom: LineString,
) -> dict[str, dict]:
    """Remove a segment from whichever reach contains it.

    Uses ``seg.equals(segment_geom)`` for geometry matching.
    If the reach becomes empty after removal, it is deleted.
    Returns the updated reaches dict.
    """
    to_delete: str | None = None
    for name, reach in reaches.items():
        for i, seg in enumerate(reach["segments"]):
            if seg.equals(segment_geom):
                reach["segments"].pop(i)
                reach["properties"].pop(i)
                if not reach["segments"]:
                    to_delete = name
                break
        else:
            continue
        break

    if to_delete is not None:
        del reaches[to_delete]

    return reaches


def detect_junctions(
    reaches: dict[str, dict],
    center_lon: float,
    center_lat: float,
    tolerance_m: float = 50.0,
) -> dict[str, dict]:
    """Auto-detect upstream/downstream junctions between reaches.

    Batch-reprojects all reach segments to UTM, extracts start/end points,
    and matches endpoint pairs within *tolerance_m* metres.  OSM/EU-Hydro
    convention: startpoint = upstream, endpoint = downstream.

    Shared junctions get the same integer ID; unmatched endpoints get unique
    auto-incremented IDs.  Returns the updated reaches dict with
    ``upstream_junction`` and ``downstream_junction`` filled in.
    """
    if not reaches:
        return reaches

    utm_epsg = detect_utm_epsg(center_lon, center_lat)

    # --- collect UTM start/end points per reach ---
    reach_endpoints: dict[str, dict[str, Point]] = {}

    for name, reach in reaches.items():
        segs = reach["segments"]
        if not segs:
            continue

        # Skip polygon reaches — they have no meaningful upstream/downstream
        if any(s.geom_type in ("Polygon", "MultiPolygon") for s in segs):
            continue

        gdf = gpd.GeoDataFrame(geometry=segs, crs="EPSG:4326").to_crs(
            epsg=utm_epsg
        )

        # Upstream = first startpoint of the first segment
        first_coords = list(gdf.geometry.iloc[0].coords)
        upstream_pt = Point(first_coords[0])

        # Downstream = last endpoint of the last segment
        last_coords = list(gdf.geometry.iloc[-1].coords)
        downstream_pt = Point(last_coords[-1])

        reach_endpoints[name] = {
            "upstream": upstream_pt,
            "downstream": downstream_pt,
        }

    # --- match pairs: r1 downstream ↔ r2 upstream within tolerance ---
    names = list(reach_endpoints.keys())
    junction_id = 1
    # Track assigned junction IDs: (reach_name, "upstream"|"downstream") → id
    assigned: dict[tuple[str, str], int] = {}

    for i, n1 in enumerate(names):
        for j, n2 in enumerate(names):
            if i == j:
                continue
            ds_pt = reach_endpoints[n1]["downstream"]
            us_pt = reach_endpoints[n2]["upstream"]
            dist = ds_pt.distance(us_pt)
            if dist <= tolerance_m:
                key_ds = (n1, "downstream")
                key_us = (n2, "upstream")
                # Use existing ID if either side already assigned
                if key_ds in assigned:
                    jid = assigned[key_ds]
                elif key_us in assigned:
                    jid = assigned[key_us]
                else:
                    jid = junction_id
                    junction_id += 1
                assigned[key_ds] = jid
                assigned[key_us] = jid

    # --- fill unmatched endpoints with unique IDs ---
    for name in names:
        for end in ("upstream", "downstream"):
            key = (name, end)
            if key not in assigned:
                assigned[key] = junction_id
                junction_id += 1

    # --- write back to reaches dict ---
    for name in names:
        reaches[name]["upstream_junction"] = assigned[(name, "upstream")]
        reaches[name]["downstream_junction"] = assigned[(name, "downstream")]

    return reaches
