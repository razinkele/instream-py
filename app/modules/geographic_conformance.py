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


def check_reach_plausibility(
    metrics: ReachMetrics,
    classification: ReachClass,
    *,
    max_river_effective_width_m: float = DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M,
    min_marine_cells: int = DEFAULT_MIN_MARINE_CELLS,
) -> list[ReachIssue]:
    """Apply the v0.51.2 rules to one reach. Empty list = clean."""
    issues: list[ReachIssue] = []
    if metrics.cells == 0:
        issues.append(ReachIssue(
            severity="error",
            code="EMPTY_REACH",
            message="reach has 0 cells",
        ))
        return issues

    if classification == "river":
        if metrics.effective_width_m > max_river_effective_width_m:
            issues.append(ReachIssue(
                severity="error",
                code="RIVER_TOO_WIDE",
                message=(
                    f"effective width {metrics.effective_width_m:.0f} m exceeds "
                    f"river threshold {max_river_effective_width_m:.0f} m — "
                    f"cells likely buffered against centerline rather than "
                    f"clipped to real OSM water polygon"
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


def check_fixture_geography(
    fixture_dir: Path,
    *,
    max_river_effective_width_m: float = DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M,
    min_marine_cells: int = DEFAULT_MIN_MARINE_CELLS,
) -> dict[str, tuple[ReachMetrics, ReachClass, list[ReachIssue]]]:
    """Run the rules against every reach in one fixture.

    Returns a mapping ``{reach_name: (metrics, classification, issues)}``.
    Empty issues list means the reach is clean.
    """
    shp = discover_fixture_shapefile(fixture_dir)
    if shp is None:
        return {}

    gdf = gpd.read_file(shp)
    reach_col = find_reach_column(gdf)
    if reach_col is None:
        return {}

    out: dict[str, tuple[ReachMetrics, ReachClass, list[ReachIssue]]] = {}
    for reach in sorted(gdf[reach_col].unique()):
        sub = gdf[gdf[reach_col] == reach]
        metrics = compute_reach_metrics(sub)
        classification = classify_reach(str(reach))
        issues = check_reach_plausibility(
            metrics, classification,
            max_river_effective_width_m=max_river_effective_width_m,
            min_marine_cells=min_marine_cells,
        )
        out[str(reach)] = (metrics, classification, issues)
    return out
