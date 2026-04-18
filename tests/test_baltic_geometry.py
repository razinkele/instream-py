"""Fast geometry invariants for the Baltic fixture shapefile.

Reads `tests/fixtures/example_baltic/Shapefile/BalticExample.shp` directly
(no simulation, no OSM queries) and asserts properties that must hold for
the case study to be valid:

  - All 9 named reaches are present (no silent drop)
  - Cell count is inside the expected band (generator-tuned baseline)
  - Direct-adjacency pairs touch on the cell grid (salmon migration path)
  - Documented indirect gaps don't regress to disconnection

If a future clip or BUFFER_FACTOR tweak breaks direct connectivity (as
happened twice during the v0.30 → v0.30.1 cycle), these tests fail in CI
instead of only surfacing as a visual defect on the laguna map.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.strtree import STRtree


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures" / "example_baltic" / "Shapefile" / "BalticExample.shp"
)

EXPECTED_REACHES = {
    "Nemunas", "Atmata", "Minija", "Sysa", "Skirvyte", "Leite",
    "Gilija", "CuronianLagoon", "BalticCoast",
}

# Cell-count band (updated by the generator if CELL_SIZE_M / BUFFER_FACTOR
# / per_reach_clip are retuned). Current baseline: 1,591 cells at v0.30.1.
CELL_COUNT_MIN = 1300
CELL_COUNT_MAX = 2200

# Pairs that MUST be connected on the cell grid (< 0.5 km apart) for the
# salmon migration path to be continuous. A failure here means a clip bug.
DIRECT_ADJACENCY_PAIRS = [
    # Baltic → strait → lagoon
    ("BalticCoast", "CuronianLagoon"),
    # Lagoon → delta branches with real estuarine mouths
    ("CuronianLagoon", "Atmata"),
    ("CuronianLagoon", "Gilija"),
    ("CuronianLagoon", "Skirvyte"),
    # Delta bifurcation at Rusnė
    ("Atmata", "Nemunas"),
    ("Skirvyte", "Nemunas"),
    ("Leite", "Nemunas"),
    ("Gilija", "Nemunas"),
    # Šyša joins Atmata at Šilutė
    ("Atmata", "Sysa"),
]

# Pairs that are ALLOWED to be disconnected because real geography or OSM
# tagging puts them > 0.5 km apart. Each entry documents the indirect
# migration path so the gap is understood, not ignored.
DOCUMENTED_GAPS = {
    # OSM Minija tagging stops ~6 km east of the real Ventės Ragas mouth;
    # salmon reach Minija via the lagoon's Kintai bay shore (neighbouring
    # Minija's southernmost cells).
    ("CuronianLagoon", "Minija"): 3.0,
    # Leitė joins Nemunas at Rusnė; salmon route: Leite → Nemunas → Atmata
    # → lagoon. Direct distance to the lagoon shore is ~8 km of delta.
    ("CuronianLagoon", "Leite"): 10.0,
    # Šyša joins Atmata at Šilutė, not Nemunas; salmon route:
    # Sysa → Atmata → Nemunas.
    ("Sysa", "Nemunas"): 5.0,
}


@pytest.fixture(scope="module")
def baltic_gdf() -> gpd.GeoDataFrame:
    """Load the Baltic fixture shapefile reprojected to UTM 34N for
    metre-accurate distance calculations."""
    if not FIXTURE.exists():
        pytest.skip(f"Baltic fixture not present at {FIXTURE}")
    return gpd.read_file(str(FIXTURE)).to_crs("EPSG:32634")


@pytest.fixture(scope="module")
def reach_cells(baltic_gdf: gpd.GeoDataFrame) -> dict[str, list]:
    """Dict mapping reach name → list of cell polygons (UTM 34N)."""
    return {
        r: list(baltic_gdf.loc[baltic_gdf["REACH_NAME"] == r].geometry.values)
        for r in baltic_gdf["REACH_NAME"].unique()
    }


def _nearest_km(a_geoms, b_geoms) -> float:
    """Minimum distance in km between any geom in a_geoms and b_geoms
    using an STRtree for speed. Inputs are UTM (metres)."""
    tree = STRtree(b_geoms)
    best = float("inf")
    for g in a_geoms:
        idx = tree.nearest(g)
        d = g.distance(b_geoms[idx])
        if d < best:
            best = d
    return best / 1000.0


# ---------------------------------------------------------------------------
# Invariant: all 9 named reaches are present
# ---------------------------------------------------------------------------


def test_all_reaches_present(baltic_gdf: gpd.GeoDataFrame) -> None:
    present = set(baltic_gdf["REACH_NAME"].unique())
    missing = EXPECTED_REACHES - present
    extra = present - EXPECTED_REACHES
    assert not missing, (
        f"Missing reaches in BalticExample.shp: {sorted(missing)}. "
        f"If a reach was intentionally removed, update EXPECTED_REACHES."
    )
    assert not extra, (
        f"Unexpected reaches in BalticExample.shp: {sorted(extra)}. "
        f"If a new reach was intentionally added, update EXPECTED_REACHES."
    )


# ---------------------------------------------------------------------------
# Invariant: cell count stays inside the generator-tuned band
# ---------------------------------------------------------------------------


def test_cell_count_in_band(baltic_gdf: gpd.GeoDataFrame) -> None:
    n = len(baltic_gdf)
    assert CELL_COUNT_MIN <= n <= CELL_COUNT_MAX, (
        f"Baltic fixture has {n} cells, outside band "
        f"{CELL_COUNT_MIN}-{CELL_COUNT_MAX}. If you retuned CELL_SIZE_M, "
        f"BUFFER_FACTOR, or per_reach_clip in "
        f"scripts/generate_baltic_example.py, update the band."
    )


# ---------------------------------------------------------------------------
# Invariant: direct-adjacency pairs are CONNECTED on the cell grid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("reach_a", "reach_b"), DIRECT_ADJACENCY_PAIRS)
def test_direct_adjacency_pair_connected(
    reach_cells: dict[str, list], reach_a: str, reach_b: str
) -> None:
    """Each (a, b) pair must have nearest-cell distance < 0.5 km so the
    salmon migration path is continuous. Failure = clip regression."""
    d_km = _nearest_km(reach_cells[reach_a], reach_cells[reach_b])
    assert d_km < 0.5, (
        f"Direct-adjacency pair {reach_a} ↔ {reach_b} is {d_km:.3f} km "
        f"apart on the cell grid. This breaks the salmon migration path. "
        f"Likely cause: a per-reach clip in scripts/generate_baltic_example.py "
        f"was changed and the reaches no longer overlap at their confluence. "
        f"Run scripts/_probe_connectivity.py for endpoint coordinates."
    )


# ---------------------------------------------------------------------------
# Invariant: documented gaps don't regress further
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reach_a", "reach_b", "max_km"),
    [(a, b, km) for (a, b), km in DOCUMENTED_GAPS.items()],
)
def test_documented_gap_under_budget(
    reach_cells: dict[str, list], reach_a: str, reach_b: str, max_km: float
) -> None:
    """These reaches are intentionally not directly adjacent (real
    geography or OSM-tagging limit), but the distance shouldn't grow
    beyond what was documented at v0.30.1. If it does, something in the
    upstream geometry fetcher changed."""
    d_km = _nearest_km(reach_cells[reach_a], reach_cells[reach_b])
    assert d_km <= max_km, (
        f"Documented gap {reach_a} ↔ {reach_b} grew from its v0.30.1 "
        f"budget of {max_km} km to {d_km:.3f} km. This is an acceptable "
        f"gap (see DOCUMENTED_GAPS comments) but the blow-up suggests a "
        f"regression — investigate the OSM fetch or per-reach clip."
    )


# ---------------------------------------------------------------------------
# Invariant: spawning reaches have frac_spawn > 0
# ---------------------------------------------------------------------------

# Tributaries where real-world salmon spawning occurs. If any of these drop
# to frac_spawn = 0 in the DBF, the whole spawning pipeline silently fails —
# spawn_suitability score = 0 for every candidate cell, no redds are ever
# created, and the population can't reproduce. This exact bug shipped in
# v0.30.0 → v0.30.1 because the real-OSM generator never populated the
# `frac_spawn` key in reach_segments (default 0.0 in create_model_grid).
SPAWNING_REACHES = ["Nemunas", "Atmata", "Minija", "Sysa", "Skirvyte",
                    "Leite", "Gilija"]


def test_spawning_reaches_have_nonzero_frac_spawn(
    baltic_gdf: gpd.GeoDataFrame,
) -> None:
    """Every river reach must have at least one cell with FRACSPWN > 0.
    Zero-everywhere means `create_model_grid.generate_cells()` was called
    without `frac_spawn` in the reach_segments dict — a generator bug that
    silently kills reproduction."""
    failures: list[str] = []
    for r in SPAWNING_REACHES:
        mask = baltic_gdf["REACH_NAME"] == r
        if mask.sum() == 0:
            failures.append(f"{r}: no cells (reach missing)")
            continue
        n_nonzero = int((baltic_gdf.loc[mask, "FRACSPWN"] > 0).sum())
        if n_nonzero == 0:
            failures.append(f"{r}: 0/{int(mask.sum())} cells have FRACSPWN > 0")
    assert not failures, (
        "Reaches with no spawning habitat at all:\n  " + "\n  ".join(failures) + "\n\n"
        "Likely cause: scripts/generate_baltic_example.py doesn't pass "
        "'frac_spawn' in the reach_segments dict to "
        "create_model_grid.generate_cells(), so it defaults to 0.0. Check "
        "REACH_PARAMS and build_cells()."
    )


def test_non_spawning_reaches_have_zero_frac_spawn(
    baltic_gdf: gpd.GeoDataFrame,
) -> None:
    """Marine / lagoon cells must have FRACSPWN = 0. If they're > 0, fish
    might spawn in the ocean, which never happens for Atlantic salmon."""
    for r in ("CuronianLagoon", "BalticCoast"):
        mask = baltic_gdf["REACH_NAME"] == r
        if mask.sum() == 0:
            continue
        max_fs = float(baltic_gdf.loc[mask, "FRACSPWN"].max())
        assert max_fs == 0.0, (
            f"Reach {r} has FRACSPWN max = {max_fs}; must be 0 for "
            f"non-freshwater habitat."
        )
