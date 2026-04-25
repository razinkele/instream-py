"""Centerline-driven river-polygon analysis helpers.

Extracted from `scripts/_generate_wgbast_physical_domains.py` so both
the WGBAST batch generator AND a future Create Model UI button can
share the algorithms.
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
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
