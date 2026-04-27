"""Centerline-driven river-polygon analysis helpers.

Extracted from `scripts/_generate_wgbast_physical_domains.py` so both
the WGBAST batch generator AND a future Create Model UI button can
share the algorithms.
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

log = logging.getLogger(__name__)


def filter_polygons_by_centerline_connectivity(
    centerline: Sequence[LineString] | LineString | MultiLineString,
    polygons: Sequence[Polygon | MultiPolygon],
    *,
    tolerance_deg: float = 0.0005,
    max_polys: int = 2000,
    label: Optional[str] = None,
) -> list[Polygon | MultiPolygon]:
    """Return only the polygons in the connected component touching the centerline.

    Algorithm (graph flood-fill):
      1. Buffer each polygon by `tolerance_deg` (small bridge over OSM
         tagging gaps).
      2. Build an STRtree spatial index for fast neighbor lookup.
      3. Seed the visited-set with polygons whose buffered envelope
         intersects the buffered centerline.
      4. BFS: for each visited polygon, find polygons whose buffered
         envelope intersects → add to visited.
      5. Return only visited polygons (capped at `max_polys`).
    """
    if not polygons:
        return []

    # Normalize centerline to a single geometry
    if isinstance(centerline, (LineString, MultiLineString)):
        centerline_union = centerline
    else:
        centerline_union = unary_union(list(centerline))

    polys = list(polygons)
    buffered = [p.buffer(tolerance_deg) for p in polys]
    tree = STRtree(buffered)
    n = len(polys)
    visited = [False] * n
    from collections import deque
    queue: deque[int] = deque()

    seed_buffered_line = centerline_union.buffer(tolerance_deg)
    visited_count = 0
    # Sort tree.query() output so visit order is deterministic across
    # shapely builds (STRtree internal iteration order is not guaranteed
    # stable across versions). Without this, the `max_polys` cap could
    # surface a different polygon set on different machines / shapely
    # versions, producing non-byte-identical fixtures.
    # `predicate="intersects"` (shapely ≥2.0) pushes the intersect
    # check into GEOS's spatial index — returns only true-intersect
    # hits, not bbox-envelope-overlap. Drops the redundant Python-side
    # .intersects() check below and is materially faster on dense
    # polygon networks (Tornionjoki ~9000 polygons). Without this,
    # the max_polys cap could fire on bbox-overlap noise rather than
    # real adjacency.
    # .tolist() converts the np.ndarray to plain list[int] so
    # indexing buffered[i]/polys[i] doesn't see np.int64.
    for i in sorted(tree.query(seed_buffered_line, predicate="intersects").tolist()):
        if visited_count >= max_polys:
            # Cap also enforced during seeding — production case where
            # a long centerline touches more than max_polys polygons
            # directly (e.g., a dense lake-and-river network).
            break
        if not visited[i]:
            visited[i] = True
            visited_count += 1
            queue.append(i)

    if not queue:
        log.warning(
            "[%s] no polygons touch the centerline within %.4f deg",
            label or "<unlabeled>", tolerance_deg,
        )
        return []

    # Track visited_count incrementally instead of `sum(visited)` per
    # iteration — sum() is O(n) per call, making the BFS O(n²). For
    # Tornionjoki at ~9000 polygons, that's ~80M boolean sums per
    # regenerate. Incremental counter restores O(n log n + E).
    #
    # Use FIFO popleft (deque, declared above) for true BFS order —
    # a list.pop() from the end would visit polygons in DFS order
    # which interacts badly with the max_polys cap (different
    # polygons could survive depending on traversal direction).
    # Combined with the sorted() above, the traversal is now a pure
    # function of input polygon order.
    while queue and visited_count < max_polys:
        i = queue.popleft()
        # Same predicate="intersects" optimization as the seed loop.
        for j in sorted(tree.query(buffered[i], predicate="intersects").tolist()):
            if visited[j]:
                continue
            visited[j] = True
            visited_count += 1
            queue.append(j)

    # Reorder kept output by sorted index so the result is also
    # order-deterministic regardless of BFS visit order.
    kept = [polys[i] for i, v in enumerate(visited) if v]
    log.info(
        "[%s] connectivity filter: %d/%d polygons in the centerline-connected component",
        label or "<unlabeled>", len(kept), n,
    )
    return kept


def partition_polygons_along_channel(
    centerline: Sequence[LineString] | LineString | MultiLineString,
    polygons: Sequence[Polygon | MultiPolygon],
    *,
    mouth_lon_lat: tuple[float, float],
    n_reaches: int,
) -> list[list[Polygon | MultiPolygon]]:
    """Partition polygons into N groups by ALONG-channel distance from mouth.

    Each polygon's centroid is projected onto the centerline; polygons are
    sorted by along-line distance from the mouth point and split into N
    equal-count groups (the last group absorbs any rounding remainder).

    Returns a list of N lists. Caller assigns reach names + frac_spawn
    afterwards. For len(polygons) < n_reaches, returns mostly-empty
    lists with the polygons distributed across the first slots.
    """
    from shapely.geometry import Point

    if n_reaches < 1:
        raise ValueError(f"n_reaches must be >= 1, got {n_reaches}")
    if not polygons:
        return [[] for _ in range(n_reaches)]

    if isinstance(centerline, (LineString, MultiLineString)):
        centerline_union = centerline
    else:
        centerline_union = unary_union(list(centerline))

    mouth = Point(mouth_lon_lat)
    oriented = _orient_centerline_mouth_to_source(centerline_union, mouth)

    polys = list(polygons)
    scored = sorted(
        ((oriented.project(p.centroid), p) for p in polys),
        key=lambda t: t[0],
    )

    n = len(scored)
    q = n / float(n_reaches)
    slices = [(int(q * i), int(q * (i + 1))) for i in range(n_reaches)]
    if slices:
        slices[-1] = (slices[-1][0], n)

    return [
        [p for _, p in scored[lo:hi]]
        for lo, hi in slices
    ]


def _orient_centerline_mouth_to_source(
    centerline_union: LineString | MultiLineString,
    mouth: "Point",
) -> LineString | MultiLineString:
    """Return centerline oriented mouth → source so that .project()
    returns 0 at mouth and increases upstream.

    For a LineString: flip if mouth is closer to the end than the start.
    For a MultiLineString: try shapely.ops.linemerge first — if all
    sub-lines connect end-to-end the result is a single LineString and
    we orient it the same way. Otherwise (genuinely disjoint segments,
    common for OSM way collections like Tornionjoki+Muonio), fall back
    to a coordinate-based proxy: build a single LineString from the
    sequence of all sub-line coordinates concatenated, sorted by
    distance from the mouth. This is approximate but produces a
    monotone .project() that respects mouth → source ordering for
    ALL the common WGBAST cases.

    Returning a raw MultiLineString here is a BUG: shapely's
    MultiLineString.project() returns 0.0 for every input regardless
    of geometry, which silently scrambles the partition.
    """
    from shapely.ops import linemerge

    if centerline_union.geom_type == "LineString":
        coords = list(centerline_union.coords)
        d_start = mouth.distance(Point(coords[0]))
        d_end = mouth.distance(Point(coords[-1]))
        if d_start > d_end:
            coords = list(reversed(coords))
        return LineString(coords)

    # MultiLineString: try linemerge first
    merged = linemerge(centerline_union)
    if merged.geom_type == "LineString":
        coords = list(merged.coords)
        d_start = mouth.distance(Point(coords[0]))
        d_end = mouth.distance(Point(coords[-1]))
        if d_start > d_end:
            coords = list(reversed(coords))
        return LineString(coords)

    # Disconnected: concatenate sub-line coordinates sorted by distance
    # from the mouth. Approximate but produces a monotone .project().
    all_coords: list[tuple[float, float]] = []
    for sub in merged.geoms:
        all_coords.extend(list(sub.coords))
    # Deduplicate while preserving order
    seen: set[tuple[float, float]] = set()
    unique: list[tuple[float, float]] = []
    for c in all_coords:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    # Sort by distance from mouth
    unique.sort(key=lambda c: mouth.distance(Point(c)))
    if len(unique) < 2:
        return merged  # fall through; downstream will detect a degenerate input
    return LineString(unique)


def filter_centerlines_by_name(
    centerlines: Sequence[LineString | MultiLineString],
    names: Sequence[Optional[str]],
    name_query: str,
) -> list[LineString | MultiLineString]:
    """Return centerlines whose name contains ``name_query`` (case-insensitive
    substring, casefolded so 'dane' matches 'Danė').

    Empty / whitespace ``name_query`` short-circuits to passthrough — that's
    how callers signal "no filter". With a non-empty query, ways whose
    paired name is None or "" are dropped (OSM unnamed tributaries would
    otherwise leak through and defeat single-river selection).

    Motivated by v0.51.0's Klaipėda pivot: the BFS in
    ``filter_polygons_by_centerline_connectivity`` over-collects polygons
    when the centerline contains every river in a connected water network
    (port + strait + lagoon + delta). Pre-filtering centerlines by river
    name narrows the BFS seed set so only the named river's polygons are
    visited.
    """
    if len(names) != len(centerlines):
        raise ValueError(
            f"length mismatch: {len(centerlines)} centerlines vs {len(names)} names"
        )

    q = (name_query or "").strip()
    if not q:
        return list(centerlines)

    needle = q.casefold()
    return [
        cl for cl, nm in zip(centerlines, names)
        if nm and needle in nm.casefold()
    ]


def default_reach_names(n_reaches: int) -> list[str]:
    """Smart default for reach names produced by Auto-split.

    For the WGBAST convention N=4 → ["Mouth", "Lower", "Middle", "Upper"].
    For any other N → ["Reach1", "Reach2", ..., "ReachN"]. Users can
    rename via the Edit Model panel after the split runs.
    """
    if n_reaches == 4:
        return ["Mouth", "Lower", "Middle", "Upper"]
    return [f"Reach{i}" for i in range(1, n_reaches + 1)]
