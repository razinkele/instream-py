"""Geographic-conformance checks for habitat-cell fixtures.

Pure (no Shiny) helpers used by ``tests/test_geographic_conformance.py``
and by the developer probe at ``scripts/check_fixture_geography.py``.

Motivation (v0.51.2): the v0.51.0 Danė fixture and the WGBAST Simojoki +
Tornionjoki fixtures use buffered-centerline cell generation that
inflates river widths by 5-15× the real OSM polygon. The v0.51.0
KlaipedaStrait reach is a single 11.3 km² hand-traced blob (CELL_2357).
This module defines the per-reach metrics and the threshold rules that
catch both classes of artefact:

- RIVER reaches: ``effective_width = area / mrr_length`` should not
  exceed a narrow-river threshold (default 350 m). Real Lithuanian /
  Swedish / Finnish salmon rivers are 25-200 m wide in their middle
  reaches; the threshold sits 6× above the gold-standard Mörrumsån
  fixture's worst reach (55 m) and well below the broken Danė fixture's
  best reach (376 m).
- MARINE/lagoon reaches: should have at least ``min_marine_cells``
  cells (default 5). A single mega-cell (the v0.51.0 KlaipedaStrait
  hand-trace) is geographically irrelevant.

Both rules are tunable. Both can be overridden per-reach when a fixture
legitimately violates the default (e.g. a nearshore Baltic strip with
deliberately coarse 4 km cells).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import geopandas as gpd

ReachClass = Literal["river", "marine"]

# Reach-name keywords that route to the MARINE classification. Match is
# case-insensitive substring; longer keywords win (so "BalticCoast"
# routes to marine even though it doesn't end in "Coast" alone).
_MARINE_KEYWORDS = (
    "Coast", "Lagoon", "Strait", "Bay", "Sea",
    "Bothnia", "Estuary", "Harbor", "Harbour",
)

# Defaults. Set per the v0.51.2 calibration scan:
#   Mörrumsån worst reach (Lower) = 49 m   ← gold standard
#   Nemunas delta worst (Skirvyte) = 275 m ← real distributary, kept under
#   Danė best reach (Middle)       = 376 m ← broken, fails by design
DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M = 350.0

# Single-cell hand-traced reaches (KlaipedaStrait) need to fail; v0.45.2-
# style polygon-fill marine reaches have 60-300 cells comfortably.
DEFAULT_MIN_MARINE_CELLS = 5


@dataclass(frozen=True)
class ReachMetrics:
    """Per-reach geometric summary."""
    cells: int
    area_m2: float
    mrr_width_m: float       # min-rotated-rect width (channel-cross-axis proxy)
    mrr_length_m: float      # min-rotated-rect length (along-channel proxy)
    effective_width_m: float  # area / mrr_length — robust channel-width proxy

    @property
    def is_single_mega_cell(self) -> bool:
        """A reach that consists of one cell whose area dominates: a
        hand-traced lagoon/strait blob rather than a real habitat tile.
        """
        return self.cells == 1 and self.area_m2 > 100_000.0


# v0.51.4: when cell_area/polygon_area exceeds this, the cells overshoot
# the real OSM water polygon by 50%+ — buffer-inflation regardless of
# the absolute width. The v0.51.0 Danė fixture had ratio ~50× before
# regen; the v0.45.x WGBAST fixtures sit at 1.02-1.03 (faithful).
DEFAULT_MAX_CELL_TO_POLYGON_AREA_RATIO = 1.5

# v0.56.0: inter-reach connectivity defaults. A reach must have cells
# within DEFAULT_CONNECTIVITY_THRESHOLD_M of at least one other reach
# reachable within DEFAULT_CONNECTIVITY_HOPS steps in the YAML junction
# graph. See docs/superpowers/plans/2026-04-30-inter-reach-connectivity-check.md.
#
# k=2 hops handle star-graph abstractions (Minija basin: 4 tributaries
# all converge on junction 3) and cross-basin abstractions (Minija →
# Atmata is geographically separated by ~50 km but logically connected
# via junction 4 → 5; the 2-hop walk reaches Lagoon which IS adjacent).
#
# 500 m is roughly 6-17× the cell circumradius across existing fixtures
# (Minija basin uses 30 m cells, WGBAST uses 60-150 m cells). A reach
# 6+ cells away from any 2-hop neighbor is almost certainly mis-located.
DEFAULT_CONNECTIVITY_THRESHOLD_M = 500.0
# Marine reaches naturally sit far from their 1-hop junction neighbor.
# In WGBAST topology, BalticCoast's 1-hop neighbor is Upper (sharing
# the chain-end junction 5), not Mouth — Mouth is 4 hops away through
# the chain Mouth → Lower → Middle → Upper → BalticCoast. The
# physically-adjacent reach is at the FAR end of the BFS walk, not
# the near end. Marine reaches therefore use a large k to traverse
# the whole connected component and find the closest river reach
# geographically (typically Mouth).
DEFAULT_MARINE_CONNECTIVITY_THRESHOLD_M = 5_000.0
DEFAULT_CONNECTIVITY_HOPS = 2
DEFAULT_MARINE_CONNECTIVITY_HOPS = 10  # effectively traverse component


@dataclass(frozen=True)
class ReachIssue:
    """One violation produced by ``check_reach_plausibility``."""
    severity: Literal["error", "warning"]
    code: str
    message: str


def classify_reach(reach_name: str) -> ReachClass:
    """River unless the name contains a marine keyword.

    Substring match (so ``BalticCoast`` is marine via ``Coast``,
    ``KlaipedaStrait`` via ``Strait``, ``CuronianLagoon`` via ``Lagoon``,
    ``GulfOfBothnia`` via ``Bothnia``).
    """
    if not reach_name:
        return "river"
    lower = reach_name.lower()
    return "marine" if any(kw.lower() in lower for kw in _MARINE_KEYWORDS) else "river"


def compute_reach_metrics(reach_gdf: gpd.GeoDataFrame) -> ReachMetrics:
    """Compute geometric summary for a single reach's cell collection.

    Reprojects to EPSG:3857 (Web Mercator, meters) if the input is in
    geographic CRS or has no CRS. Already-projected EPSG codes (e.g.
    EPSG:3035 LAEA Europe) are kept as-is — their units are already
    meters and reprojection would lose precision.
    """
    if len(reach_gdf) == 0:
        return ReachMetrics(0, 0.0, 0.0, 0.0, 0.0)

    epsg = reach_gdf.crs.to_epsg() if reach_gdf.crs else None
    if epsg is None or epsg == 4326:
        gdf_m = reach_gdf.to_crs("EPSG:3857")
    else:
        gdf_m = reach_gdf

    union = gdf_m.geometry.union_all()
    area = float(union.area)

    mrr = union.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)
    side1 = ((coords[0][0]-coords[1][0])**2 + (coords[0][1]-coords[1][1])**2) ** 0.5
    side2 = ((coords[1][0]-coords[2][0])**2 + (coords[1][1]-coords[2][1])**2) ** 0.5
    mrr_width = min(side1, side2)
    mrr_length = max(side1, side2)
    effective_width = area / mrr_length if mrr_length > 0 else 0.0

    return ReachMetrics(
        cells=len(reach_gdf),
        area_m2=area,
        mrr_width_m=mrr_width,
        mrr_length_m=mrr_length,
        effective_width_m=effective_width,
    )


def compute_polygon_coverage_ratio(
    reach_cells_gdf: gpd.GeoDataFrame,
    reference_polygons: list,
) -> Optional[float]:
    """Return ``cells_total_area / reference_polygons_total_area``.

    Reference polygons are real OSM water polygons (loaded from
    ``_osm_cache/{fixture}_polygons.json``). Both areas are computed in
    the cells' projected CRS so the ratio is dimensionless and comparable.

    A ratio ≈ 1.0 means cells faithfully tile real water; ratio > 1.5
    means cells overshoot the real polygons (buffer inflation). Ratio
    < 0.5 means cells under-cover (sparse polygon-fill failures).

    Returns None when either input is empty or unprojectable; callers
    should treat None as "no signal".
    """
    if reach_cells_gdf.empty or not reference_polygons:
        return None

    target_crs = reach_cells_gdf.crs
    if target_crs is None:
        return None

    epsg = target_crs.to_epsg()
    if epsg is None or epsg == 4326:
        cells_m = reach_cells_gdf.to_crs("EPSG:3857")
    else:
        cells_m = reach_cells_gdf

    cells_area = cells_m.geometry.union_all().area
    if cells_area <= 0:
        return None

    ref_gdf = gpd.GeoDataFrame(
        geometry=list(reference_polygons), crs="EPSG:4326"
    ).to_crs(cells_m.crs)
    ref_area = ref_gdf.geometry.union_all().area
    if ref_area <= 0:
        return None

    return cells_area / ref_area


def check_reach_plausibility(
    metrics: ReachMetrics,
    classification: ReachClass,
    *,
    max_river_effective_width_m: float = DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M,
    min_marine_cells: int = DEFAULT_MIN_MARINE_CELLS,
    polygon_coverage_ratio: Optional[float] = None,
    max_cell_to_polygon_area_ratio: float = DEFAULT_MAX_CELL_TO_POLYGON_AREA_RATIO,
    nearest_neighbor_distance_m: Optional[float] = None,
    connectivity_threshold_m: float = DEFAULT_CONNECTIVITY_THRESHOLD_M,
    marine_connectivity_threshold_m: float = DEFAULT_MARINE_CONNECTIVITY_THRESHOLD_M,
) -> list[ReachIssue]:
    """Apply the rules to one reach. Empty list = clean.

    When ``polygon_coverage_ratio`` is provided (computed externally
    from a real OSM polygon cache), the polygon-coverage rule is the
    AUTHORITATIVE check for buffer inflation: a ratio > 1.5 fails
    regardless of the absolute effective width. The effective_width
    rule is then a soft pre-check that's bypassed for legitimately
    wide rivers (large Finnish/Swedish/braided systems).
    """
    issues: list[ReachIssue] = []
    if metrics.cells == 0:
        issues.append(ReachIssue(
            severity="error",
            code="EMPTY_REACH",
            message="reach has 0 cells",
        ))
        return issues

    if classification == "river":
        if polygon_coverage_ratio is not None:
            # Polygon-overlap mode: AUTHORITATIVE. Wide-but-faithful
            # rivers (Tornionjoki/Simojoki) pass on ratio ≈ 1.0 even if
            # they exceed the legacy width threshold.
            if polygon_coverage_ratio > max_cell_to_polygon_area_ratio:
                issues.append(ReachIssue(
                    severity="error",
                    code="CELLS_OVERSHOOT_REAL_POLYGONS",
                    message=(
                        f"cells cover {polygon_coverage_ratio:.2f}× the area of "
                        f"real OSM water polygons (max {max_cell_to_polygon_area_ratio}× allowed) — "
                        f"buffer-inflation regression"
                    ),
                ))
        elif metrics.effective_width_m > max_river_effective_width_m:
            # No polygon reference available — fall back to width
            # heuristic. Catches Danė-style buffer inflation when
            # OSM polygon coverage doesn't exist for cross-checking.
            issues.append(ReachIssue(
                severity="error",
                code="RIVER_TOO_WIDE",
                message=(
                    f"effective width {metrics.effective_width_m:.0f} m exceeds "
                    f"river threshold {max_river_effective_width_m:.0f} m and no "
                    f"OSM polygon reference available — cells likely buffered "
                    f"against centerline rather than clipped to real water"
                ),
            ))
    elif classification == "marine":
        if metrics.is_single_mega_cell:
            issues.append(ReachIssue(
                severity="error",
                code="MARINE_SINGLE_MEGA_CELL",
                message=(
                    f"single {metrics.area_m2 / 1e6:.1f} km² cell — "
                    f"hand-traced blob, not real habitat tiling. "
                    f"Use polygon-fill grid generation."
                ),
            ))
        elif metrics.cells < min_marine_cells:
            issues.append(ReachIssue(
                severity="error",
                code="MARINE_TOO_FEW_CELLS",
                message=(
                    f"marine/lagoon reach has only {metrics.cells} cells "
                    f"(min {min_marine_cells}); habitat tiling is too coarse"
                ),
            ))

    # v0.56.0: connectivity check — fires when caller has computed
    # neighbor proximity from the YAML junction graph. None signals
    # "no junction config available" (single-reach fixtures, missing
    # config); the check is then skipped. 0.0 (cells overlap) is
    # distinct from None and passes the threshold.
    # Class-aware threshold: marine reaches use a much larger value
    # because offshore zones (Marine Regions WFS-derived BalticCoast
    # disks) can naturally sit tens of km from their river mouth.
    if nearest_neighbor_distance_m is not None:
        active_threshold = (
            marine_connectivity_threshold_m if classification == "marine"
            else connectivity_threshold_m
        )
        if nearest_neighbor_distance_m > active_threshold:
            issues.append(ReachIssue(
                severity="error",
                code="REACH_DISCONNECTED",
                message=(
                    f"nearest configured-neighbor reach (within "
                    f"{DEFAULT_CONNECTIVITY_HOPS} junction hops) is "
                    f"{nearest_neighbor_distance_m:.0f} m away "
                    f"(threshold {active_threshold:.0f} m for "
                    f"{classification}); cells likely generated at "
                    f"wrong coordinates relative to the basin"
                ),
            ))
    return issues


def discover_fixture_shapefile(fixture_dir: Path) -> Optional[Path]:
    """Locate the cells shapefile inside a fixture directory.

    Returns the first ``*.shp`` under ``Shapefile/``, or None if none
    exists. Used by ``check_fixture_geography`` and the CLI probe.
    """
    shp_dir = fixture_dir / "Shapefile"
    if not shp_dir.exists():
        return None
    shps = sorted(shp_dir.glob("*.shp"))
    return shps[0] if shps else None


def find_reach_column(gdf: gpd.GeoDataFrame) -> Optional[str]:
    """Reach-classification column varies between fixture vintages
    (REACH_NAME on the v0.45.x WGBAST set, Reach on the v0.30.x baseline).
    """
    for cand in ("REACH_NAME", "Reach", "reach", "reach_name"):
        if cand in gdf.columns:
            return cand
    return None


def load_fixture_polygon_cache(fixture_dir: Path) -> Optional[list]:
    """Load the OSM polygon cache for a fixture if one exists.

    Convention: ``tests/fixtures/_osm_cache/{fixture_name}_polygons.json``
    or ``..._osm_cache/{stem}_polygons.json`` where ``stem`` strips the
    ``example_`` prefix (Mörrumsån convention from v0.45.2).

    Returns a list of shapely geometries or None if no cache exists.
    """
    fixtures_root = fixture_dir.parent
    cache_dir = fixtures_root / "_osm_cache"
    if not cache_dir.exists():
        return None

    candidates = [
        cache_dir / f"{fixture_dir.name}_polygons.json",
        cache_dir / f"{fixture_dir.name.removeprefix('example_')}_polygons.json",
    ]
    cache_path: Optional[Path] = next((p for p in candidates if p.exists()), None)
    if cache_path is None:
        return None

    try:
        import json
        from shapely.geometry import shape
        from shapely.errors import GEOSException
    except ImportError:
        return None

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return None

    polys = []
    for item in data:
        try:
            poly = shape(item["geometry"])
        except (GEOSException, ValueError, TypeError, KeyError):
            continue
        if not poly.is_valid or poly.is_empty:
            continue
        if poly.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        polys.append(poly)
    return polys


def build_junction_graph(reaches) -> dict[str, set[str]]:
    """Adjacency from reach A → reach B if they share any junction.

    Two reaches share a junction when A's `upstream_junction` or
    `downstream_junction` equals B's `upstream_junction` or
    `downstream_junction`. Symmetric.

    Reaches whose junction fields are unset / None contribute no edges
    (this is a graceful degradation, not an error — `ReachConfig` is
    Pydantic `extra='allow'` and legacy fixtures may have reaches
    without junction config).

    Parameters
    ----------
    reaches : Mapping[str, Any]
        ``ModelConfig.reaches``-style mapping. Each value must expose
        ``upstream_junction`` and ``downstream_junction`` attributes
        (Pydantic models or duck-typed objects).
    """
    graph: dict[str, set[str]] = {name: set() for name in reaches}
    # Map junction_id -> list of reach names that touch it
    junction_to_reaches: dict[int, list[str]] = {}
    for reach_name, cfg in reaches.items():
        for attr in ("upstream_junction", "downstream_junction"):
            j = getattr(cfg, attr, None)
            if j is None:
                continue
            junction_to_reaches.setdefault(j, []).append(reach_name)
    # Connect every pair of reaches sharing a junction
    for sharing in junction_to_reaches.values():
        for a in sharing:
            for b in sharing:
                if a != b:
                    graph[a].add(b)
    return graph


def find_neighbor_reaches(
    graph: dict[str, set[str]],
    target_reach: str,
    max_hops: int = DEFAULT_CONNECTIVITY_HOPS,
) -> set[str]:
    """BFS to depth `max_hops` over the junction graph.

    Excludes `target_reach` itself from the result. Returns an empty set
    if `target_reach` is not in the graph or has no neighbors.
    """
    if target_reach not in graph:
        return set()
    visited = {target_reach}
    frontier = {target_reach}
    for _ in range(max_hops):
        next_frontier: set[str] = set()
        for node in frontier:
            for neighbor in graph.get(node, ()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    visited.discard(target_reach)
    return visited


def compute_min_reach_distance(
    target_cells_gdf: gpd.GeoDataFrame,
    neighbor_cells_gdf: gpd.GeoDataFrame,
) -> float:
    """Minimum cell-to-cell distance in meters between two reach cell sets.

    Both inputs must share a CRS. Geographic CRS (EPSG:4326) inputs are
    reprojected to EPSG:3857 for meter-accurate distances, mirroring
    ``compute_reach_metrics``. Already-projected EPSG codes (e.g.
    EPSG:3035 LAEA Europe) are kept as-is.

    Implementation: ``gpd.sjoin_nearest`` uses an R-tree spatial index,
    yielding O((N+M) log(N+M)) rather than naive O(N×M).

    Returns 0.0 when ANY cells touch / overlap (intersection has zero
    distance). Returns ``inf`` if either input is empty.
    """
    if target_cells_gdf.empty or neighbor_cells_gdf.empty:
        return float("inf")

    # Reproject to a meter-based CRS if needed
    epsg = target_cells_gdf.crs.to_epsg() if target_cells_gdf.crs else None
    if epsg is None or epsg == 4326:
        target_m = target_cells_gdf.to_crs("EPSG:3857")
        neighbor_m = neighbor_cells_gdf.to_crs("EPSG:3857")
    else:
        target_m = target_cells_gdf
        neighbor_m = neighbor_cells_gdf.to_crs(target_cells_gdf.crs)

    joined = gpd.sjoin_nearest(
        target_m, neighbor_m, how="left", distance_col="dist_m"
    )
    if joined.empty or "dist_m" not in joined.columns:
        return float("inf")
    distances = joined["dist_m"].dropna()
    if distances.empty:
        return float("inf")
    return float(distances.min())


def _load_fixture_config(fixture_dir: Path):
    """Auto-discover the YAML config for a fixture by name convention.

    Looks for ``<repo_root>/configs/{fixture_dir.name}.yaml`` (the standard
    convention used across all WGBAST and Baltic fixtures). Returns the
    loaded ``ModelConfig`` or None if the config is missing OR loading
    fails (in which case a warning is logged).

    Callers treat None as "skip connectivity check for this fixture" —
    it's a soft signal, not an error. Existing per-reach checks continue
    to fire regardless.
    """
    # tests/fixtures/X → repo_root is parents[2]
    try:
        repo_root = fixture_dir.resolve().parents[2]
    except IndexError:
        return None
    cfg_path = repo_root / "configs" / f"{fixture_dir.name}.yaml"
    if not cfg_path.exists():
        return None
    try:
        # Late import — keeps geographic_conformance importable in
        # contexts that don't have salmopy on the path (e.g. some
        # CI lints).
        from salmopy.io.config import load_config
        return load_config(cfg_path)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "geographic_conformance: could not load %s for connectivity "
            "check: %s", cfg_path, exc,
        )
        return None


def check_fixture_geography(
    fixture_dir: Path,
    *,
    max_river_effective_width_m: float = DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M,
    min_marine_cells: int = DEFAULT_MIN_MARINE_CELLS,
    max_cell_to_polygon_area_ratio: float = DEFAULT_MAX_CELL_TO_POLYGON_AREA_RATIO,
    connectivity_threshold_m: float = DEFAULT_CONNECTIVITY_THRESHOLD_M,
    marine_connectivity_threshold_m: float = DEFAULT_MARINE_CONNECTIVITY_THRESHOLD_M,
    connectivity_hops: int = DEFAULT_CONNECTIVITY_HOPS,
    marine_connectivity_hops: int = DEFAULT_MARINE_CONNECTIVITY_HOPS,
) -> dict[str, tuple[ReachMetrics, ReachClass, list[ReachIssue]]]:
    """Run the rules against every reach in one fixture.

    When ``_osm_cache/{fixture}_polygons.json`` exists, the polygon-
    coverage ratio becomes the authoritative river-buffer-inflation
    check (see ``check_reach_plausibility``). When no cache exists,
    the effective_width heuristic is used.

    Returns a mapping ``{reach_name: (metrics, classification, issues)}``.
    """
    shp = discover_fixture_shapefile(fixture_dir)
    if shp is None:
        return {}

    gdf = gpd.read_file(shp)
    reach_col = find_reach_column(gdf)
    if reach_col is None:
        return {}

    polygon_cache = load_fixture_polygon_cache(fixture_dir)

    # v0.56.0: load YAML config (best-effort) for the connectivity check.
    # When None, individual reaches' nearest_neighbor_distance_m stays
    # None and the connectivity check is skipped per-reach.
    config = _load_fixture_config(fixture_dir)
    junction_graph: dict[str, set[str]] = {}
    if config is not None and getattr(config, "reaches", None):
        junction_graph = build_junction_graph(config.reaches)
    shapefile_reaches = set(str(r) for r in gdf[reach_col].unique())

    out: dict[str, tuple[ReachMetrics, ReachClass, list[ReachIssue]]] = {}
    for reach in sorted(gdf[reach_col].unique()):
        sub = gdf[gdf[reach_col] == reach]
        metrics = compute_reach_metrics(sub)
        classification = classify_reach(str(reach))

        # Polygon-coverage ratio is computed at the FIXTURE level (sum
        # of all river cells / sum of all polygons) rather than per-
        # reach because the polygon cache has no reach metadata. We
        # apply that fixture-level ratio to each river reach. Marine
        # reaches don't need it.
        ratio = None
        if classification == "river" and polygon_cache:
            river_cells = gdf[gdf[reach_col].apply(
                lambda r: classify_reach(str(r)) == "river"
            )]
            ratio = compute_polygon_coverage_ratio(river_cells, polygon_cache)

        # v0.56.0: connectivity — find k-hop neighbors via the junction
        # graph, restrict to reaches actually present in the shapefile
        # (orphan YAML entries are skipped), and compute minimum cell-
        # cell distance via gpd.sjoin_nearest.
        # Class-aware k: marine reaches use a large hop count because
        # WGBAST topology connects BalticCoast to Upper (chain-end) not
        # Mouth (mouth-end), so the geographically-adjacent neighbor is
        # at the FAR end of the BFS walk through the chain.
        nearest_neighbor_distance_m: Optional[float] = None
        if junction_graph:
            active_hops = (
                marine_connectivity_hops if classification == "marine"
                else connectivity_hops
            )
            neighbors = find_neighbor_reaches(
                junction_graph, str(reach), max_hops=active_hops,
            ) & shapefile_reaches
            if neighbors:
                neighbor_cells = gdf[gdf[reach_col].astype(str).isin(neighbors)]
                if not neighbor_cells.empty:
                    nearest_neighbor_distance_m = compute_min_reach_distance(
                        sub, neighbor_cells,
                    )

        issues = check_reach_plausibility(
            metrics, classification,
            max_river_effective_width_m=max_river_effective_width_m,
            min_marine_cells=min_marine_cells,
            polygon_coverage_ratio=ratio,
            max_cell_to_polygon_area_ratio=max_cell_to_polygon_area_ratio,
            nearest_neighbor_distance_m=nearest_neighbor_distance_m,
            connectivity_threshold_m=connectivity_threshold_m,
            marine_connectivity_threshold_m=marine_connectivity_threshold_m,
        )
        out[str(reach)] = (metrics, classification, issues)
    return out
