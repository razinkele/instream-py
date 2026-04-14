"""Hexagonal and rectangular habitat cell generation from river reach segments."""

import math

import geopandas as gpd
import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from modules.create_model_utils import detect_utm_epsg, reproject_gdf


def _hexagon(cx: float, cy: float, size: float) -> Polygon:
    """Create a flat-top regular hexagon centered at (cx, cy)."""
    angles_deg = [0, 60, 120, 180, 240, 300]
    coords = [
        (cx + size * math.cos(math.radians(a)), cy + size * math.sin(math.radians(a)))
        for a in angles_deg
    ]
    return Polygon(coords)


def hexagonal_grid(bounds: tuple, cell_size: float) -> list[Polygon]:
    """Generate flat-top hexagonal grid covering *bounds* (minx, miny, maxx, maxy).

    ``cell_size`` is the circumradius (center to vertex).  For tight
    tessellation the column spacing is ``1.5 * R`` and the row spacing
    is ``sqrt(3) * R``, with odd columns offset by half a row.
    """
    minx, miny, maxx, maxy = bounds
    dx = cell_size * 1.5   # horizontal spacing between hex centres (flat-top)
    dy = cell_size * math.sqrt(3.0)  # vertical spacing

    hexagons = []
    col = 0
    x = minx
    while x <= maxx + cell_size:
        y_offset = (dy / 2.0) if col % 2 else 0.0
        y = miny + y_offset
        while y <= maxy + cell_size:
            hexagons.append(_hexagon(x, y, cell_size))
            y += dy
        x += dx
        col += 1
    return hexagons


def rectangular_grid(bounds: tuple, cell_size: float) -> list[Polygon]:
    """Generate rectangular grid covering *bounds* (minx, miny, maxx, maxy)."""
    minx, miny, maxx, maxy = bounds
    rects = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            rects.append(box(x, y, x + cell_size, y + cell_size))
            y += cell_size
        x += cell_size
    return rects


def generate_cells(
    reach_segments: dict,
    cell_size: float = 50.0,
    cell_shape: str = "hexagonal",
    buffer_factor: float = 2.0,
    min_overlap: float = 0.1,
) -> gpd.GeoDataFrame:
    """Generate habitat cells from river reach segments.

    Parameters
    ----------
    reach_segments : dict
        ``{reach_name: {"segments": [LineString in WGS84], "frac_spawn": float}}``
    cell_size : float
        Cell size in metres (hex radius or rect side length).
    cell_shape : str
        ``"hexagonal"`` or ``"rectangular"``.
    buffer_factor : float
        Buffer distance = ``cell_size * buffer_factor``.
    min_overlap : float
        Minimum fraction of cell area that must overlap the buffer to keep the cell.

    Returns
    -------
    gpd.GeoDataFrame
        Cells in UTM CRS with columns: cell_id, reach_name, area, dist_escape,
        num_hiding, frac_vel_shelter, frac_spawn, geometry.
    """
    # Collect all geometries and detect UTM zone from centroid
    all_geoms = []
    for info in reach_segments.values():
        all_geoms.extend(info["segments"])

    if not all_geoms:
        return gpd.GeoDataFrame(
            columns=["cell_id", "reach_name", "area", "dist_escape",
                      "num_hiding", "frac_vel_shelter", "frac_spawn", "geometry"],
        )

    geoms_gdf = gpd.GeoDataFrame(geometry=all_geoms, crs="EPSG:4326")
    centroid = unary_union(all_geoms).centroid
    utm_epsg = detect_utm_epsg(centroid.x, centroid.y)

    # Build per-reach buffers/regions and a combined area
    reach_buffers = {}
    reach_endpoints = {}
    buf_dist = cell_size * buffer_factor

    for name, info in reach_segments.items():
        seg_gdf = gpd.GeoDataFrame(geometry=info["segments"], crs="EPSG:4326")
        seg_utm = reproject_gdf(seg_gdf, utm_epsg)
        merged = unary_union(seg_utm.geometry)

        # For polygons (water bodies): use the polygon directly, no buffering
        reach_type = info.get("type", "river")
        if reach_type == "water" or merged.geom_type in ("Polygon", "MultiPolygon"):
            reach_buffers[name] = merged
        else:
            reach_buffers[name] = merged.buffer(buf_dist)

        # Collect endpoints (first/last coord of each line segment)
        eps = []
        for geom in seg_utm.geometry:
            if geom.geom_type in ("Polygon", "MultiPolygon"):
                # For polygons, use boundary points as "endpoints"
                boundary = geom.exterior if geom.geom_type == "Polygon" else geom.geoms[0].exterior
                coords = list(boundary.coords)
                eps.append(coords[0])
                eps.append(coords[len(coords) // 2])
            else:
                coords = list(geom.coords)
            eps.append(coords[0])
            eps.append(coords[-1])
        reach_endpoints[name] = eps

    combined_buffer = unary_union(list(reach_buffers.values()))

    # Generate grid
    bx = combined_buffer.bounds  # (minx, miny, maxx, maxy)
    if cell_shape == "hexagonal":
        raw_cells = hexagonal_grid(bx, cell_size)
    elif cell_shape == "rectangular":
        raw_cells = rectangular_grid(bx, cell_size)
    else:
        raise ValueError(f"Unknown cell_shape: {cell_shape!r}")

    # Clip cells to buffer and assign to reaches
    records = []
    cell_counter = 0

    for poly in raw_cells:
        if not combined_buffer.intersects(poly):
            continue
        clipped = combined_buffer.intersection(poly)
        if clipped.is_empty or clipped.area < poly.area * min_overlap:
            continue

        # Assign to reach with largest overlap
        best_reach = None
        best_overlap = 0.0
        for name, rbuf in reach_buffers.items():
            ov = rbuf.intersection(clipped).area
            if ov > best_overlap:
                best_overlap = ov
                best_reach = name

        if best_reach is None:
            continue

        cell_counter += 1
        ctr = clipped.centroid

        # Distance to nearest escape point (endpoint) in cm
        eps = reach_endpoints[best_reach]
        min_dist = min(ctr.distance(Point(ep[0], ep[1])) for ep in eps)
        dist_escape_cm = min_dist * 100.0

        # Edge detection: cells not fully inside buffer get more hiding
        is_edge = not combined_buffer.contains(poly)
        num_hiding = 5 if is_edge else 2

        # Velocity shelter fraction (edge cells have more shelter)
        frac_vel_shelter = 0.4 if is_edge else 0.15

        frac_spawn = reach_segments[best_reach].get("frac_spawn", 0.0)

        records.append(
            {
                "cell_id": f"C{cell_counter:04d}",
                "reach_name": best_reach,
                "area": clipped.area,
                "dist_escape": dist_escape_cm,
                "num_hiding": num_hiding,
                "frac_vel_shelter": frac_vel_shelter,
                "frac_spawn": frac_spawn,
                "geometry": clipped,
            }
        )

    gdf = gpd.GeoDataFrame(records, crs=f"EPSG:{utm_epsg}")
    # Reproject to WGS84 for map display (keep UTM area/distance values)
    gdf = gdf.to_crs("EPSG:4326")
    return gdf
