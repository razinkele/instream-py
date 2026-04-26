"""Fixture-shape regression tests for the 4 WGBAST rivers.

Asserts post-regeneration invariants:
  - Each fixture has exactly 5 reaches: {Mouth, Lower, Middle, Upper, BalticCoast}
  - BalticCoast cell count is in [100, 5000]
  - BalticCoast cells are spatially adjacent to Mouth cells
  - YAML reaches: section has exactly 5 entries (no orphans)
  - Tornionjoki has more cells than Simojoki (PR-1 acceptance)
  - YAML BalticCoast.upstream_junction == Upper.downstream_junction (topology)
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
# Hoisted from test-function-local scope so it runs once per session,
# not on every parametrized invocation. Required for `from modules.X`
# imports below (matches existing test-suite pattern in
# tests/test_create_model_grid.py).
sys.path.insert(0, str(ROOT / "app"))

from modules.create_model_utils import detect_utm_epsg  # noqa: E402

WGBAST = ["example_tornionjoki", "example_simojoki", "example_byskealven", "example_morrumsan"]
EXPECTED_REACHES = {"Mouth", "Lower", "Middle", "Upper", "BalticCoast"}

# BalticCoast cell-count bounds. Sized so all 4 rivers' clipped disks
# fit comfortably:
#   Mörrumsån (240m × factor 8 = 480m hex, open Hanöbukten): ~1500
#   Tornionjoki/Simojoki (320m): ~1500
#   Byskeälven (320m): ~1500
# A future-river-with-different-radius might bump these.
BALTICCOAST_MIN_CELLS = 100
BALTICCOAST_MAX_CELLS = 5000


# Module-scope cache so the 4 shapefiles are read once across all 22
# parametrized test cases (was: 20 redundant reads at ~3000-4000 cells
# each + pyogrio + yaml.safe_load overhead).
_LOAD_CACHE: dict[str, tuple] = {}


def _load(short_name: str) -> tuple[gpd.GeoDataFrame, dict, str]:
    if short_name in _LOAD_CACHE:
        return _LOAD_CACHE[short_name]
    fix = ROOT / "tests" / "fixtures" / short_name
    shp = next((fix / "Shapefile").glob("*.shp"))
    gdf = gpd.read_file(shp)
    cfg = yaml.safe_load((ROOT / "configs" / f"{short_name}.yaml").read_text(encoding="utf-8"))
    reach_col = "REACH_NAME" if "REACH_NAME" in gdf.columns else "reach_name"
    result = (gdf, cfg, reach_col)
    _LOAD_CACHE[short_name] = result
    return result


@pytest.mark.parametrize("short_name", WGBAST)
def test_reach_name_set(short_name: str):
    gdf, _cfg, reach_col = _load(short_name)
    assert set(gdf[reach_col].unique()) == EXPECTED_REACHES, (
        f"{short_name}: reach set wrong"
    )


@pytest.mark.parametrize("short_name", WGBAST)
def test_balticcoast_cell_count_in_range(short_name: str):
    gdf, _cfg, reach_col = _load(short_name)
    n_bc = int((gdf[reach_col] == "BalticCoast").sum())
    assert BALTICCOAST_MIN_CELLS <= n_bc <= BALTICCOAST_MAX_CELLS, (
        f"{short_name}: BalticCoast cell count {n_bc} outside "
        f"[{BALTICCOAST_MIN_CELLS}, {BALTICCOAST_MAX_CELLS}]"
    )


@pytest.mark.parametrize("short_name", WGBAST)
def test_balticcoast_geometric_adjacency_to_mouth(short_name: str):
    gdf, _cfg, reach_col = _load(short_name)
    mouth = gdf[gdf[reach_col] == "Mouth"]
    bc = gdf[gdf[reach_col] == "BalticCoast"]
    assert not mouth.empty
    assert not bc.empty
    # Project to UTM for a true-meters adjacency check, matching the
    # generator's tolerance (5 m). A WGS84-degree buffer here would be
    # anisotropic at Bothnian Bay latitudes and could spuriously fail.
    # (`detect_utm_epsg` is imported once at module top — see header.)
    mouth_centroid = mouth.geometry.union_all().centroid
    utm_epsg = detect_utm_epsg(mouth_centroid.x, mouth_centroid.y)
    mouth_utm = mouth.to_crs(epsg=utm_epsg)
    bc_utm = bc.to_crs(epsg=utm_epsg)
    bc_union_utm = bc_utm.geometry.union_all()
    hits = mouth_utm.geometry.buffer(5.0).intersects(bc_union_utm).sum()
    assert hits >= 1, (
        f"{short_name}: no Mouth↔BalticCoast geometric adjacency "
        f"(within 5 m UTM tolerance)"
    )


@pytest.mark.parametrize("short_name", WGBAST)
def test_yaml_no_orphan_reaches(short_name: str):
    _gdf, cfg, _reach_col = _load(short_name)
    yaml_reaches = set(cfg["reaches"].keys())
    assert yaml_reaches == EXPECTED_REACHES, (
        f"{short_name}: YAML reaches set {yaml_reaches} != expected {EXPECTED_REACHES}"
    )


@pytest.mark.parametrize("short_name", WGBAST)
def test_yaml_junction_topology(short_name: str):
    _gdf, cfg, _reach_col = _load(short_name)
    upper_dn = cfg["reaches"]["Upper"]["downstream_junction"]
    bc_up = cfg["reaches"]["BalticCoast"]["upstream_junction"]
    assert upper_dn == bc_up, (
        f"{short_name}: junction graph broken — Upper.downstream={upper_dn} "
        f"!= BalticCoast.upstream={bc_up}"
    )


def test_tornionjoki_larger_than_simojoki():
    """PR-1 acceptance: Tornionjoki regex extension restored its size."""
    torn, _, _ = _load("example_tornionjoki")
    simo, _, _ = _load("example_simojoki")
    assert len(torn) > len(simo), (
        f"Tornionjoki ({len(torn)} cells) should exceed Simojoki ({len(simo)})"
    )


@pytest.mark.parametrize("short_name", WGBAST)
def test_balticcoast_offset_from_mouth(short_name: str):
    """Sanity: BalticCoast centroid is at least 1 km away from Mouth
    centroid. The 0.01° threshold (~1 km) detects "BalticCoast disk
    centred ON the mouth" or "disk spuriously inland" — both bug
    modes that would slip past geometric-adjacency checks.

    NOTE: a strict "BalticCoast south of Mouth" assertion was tried in
    an earlier draft, but Byskeälven's mouth opens east-southeast into
    Byskefjärden — the marine disk centroid lies east of the mouth and
    can be at the same latitude or slightly north. Distance-only is
    the correct generic invariant.

    Parametrized (was a manual for-loop with silent `continue` on
    empty reaches — a bug that dropped BalticCoast for ONE river
    would have silently passed this test with zero assertions
    executed for that river)."""
    gdf, _cfg, reach_col = _load(short_name)
    mouth = gdf[gdf[reach_col] == "Mouth"]
    bc = gdf[gdf[reach_col] == "BalticCoast"]
    assert not mouth.empty, f"{short_name}: Mouth reach missing"
    assert not bc.empty, f"{short_name}: BalticCoast reach missing"
    # union_all() per GeoPandas 1.0+ (unary_union accessor deprecated)
    mouth_centroid = mouth.geometry.union_all().centroid
    bc_centroid = bc.geometry.union_all().centroid
    dist_deg = mouth_centroid.distance(bc_centroid)
    assert dist_deg > 0.01, (
        f"{short_name}: BalticCoast centroid {dist_deg:.4f}° from Mouth "
        f"centroid (expected > 0.01° = ~1 km). Disk likely centred on "
        f"land or on the mouth itself."
    )


# v0.48.0 cleanup: PROTO names that ship in example_baltic and were
# inherited as residue by each WGBAST fixture. Their Depths/Vels CSVs
# are pure source-template residue — the wire script reads from
# example_baltic now, so they're never needed in WGBAST fixtures.
# TimeSeriesInputs are NOT in the residue set: scripts/_scaffold_wgbast_rivers.py
# writes per-river T/Q calibration into them and the wire script copies
# the calibrated content to {Mouth,Lower,Middle,Upper}-TimeSeriesInputs.csv.
PROTO_REACHES_DEPTHS_VELS = [
    (proto, suffix)
    for proto in ("Nemunas", "Atmata", "Minija", "Sysa")
    for suffix in ("Depths", "Vels")
]

# v0.48.0 cleanup: FULLY_ORPHAN names — Lithuanian distributaries with
# no WGBAST counterpart. Their TimeSeriesInputs were git-deleted in
# v0.47.0 (commit fc08578). All 3 file types are forbidden.
FULLY_ORPHAN_REACHES_ALL = [
    (proto, suffix)
    for proto in ("Skirvyte", "Leite", "Gilija", "CuronianLagoon")
    for suffix in ("Depths", "Vels", "TimeSeriesInputs")
]

ALL_FORBIDDEN_PROTO_FILES = PROTO_REACHES_DEPTHS_VELS + FULLY_ORPHAN_REACHES_ALL


@pytest.mark.parametrize("river", WGBAST)
@pytest.mark.parametrize("proto,suffix", ALL_FORBIDDEN_PROTO_FILES)
def test_no_orphan_prototype_csvs(river: str, proto: str, suffix: str):
    """No prototype-named CSV residue in WGBAST fixture directories.

    PROTO cases (32: Nemunas/Atmata/Minija/Sysa × Depths/Vels × 4 rivers)
    drive the v0.48.0 cleanup itself: wire script now sources Depths/Vels
    from example_baltic directly. PROTO TimeSeriesInputs are intentionally
    kept (per-river T/Q calibration; see _scaffold_wgbast_rivers.py).

    FULLY_ORPHAN cases (48: Skirvyte/Leite/Gilija/CuronianLagoon × all 3
    suffixes × 4 rivers) are trivially-PASS today (v0.47.0 fc08578 already
    deleted them) — they exist as forward regression guards against
    future re-scaffolds without the deletion loop.
    """
    fixture_dir = ROOT / "tests" / "fixtures" / river
    forbidden = fixture_dir / f"{proto}-{suffix}.csv"
    assert not forbidden.exists(), (
        f"{forbidden.relative_to(ROOT)} is template residue and should not "
        f"exist in a v0.48+ WGBAST fixture. Re-run scripts/_scaffold_wgbast_rivers.py "
        f"to regenerate cleanly, or delete the file manually."
    )


PROTO_BALTIC_CSVS = [
    (proto, suffix)
    for proto in ("Nemunas", "Atmata", "Minija", "Sysa")
    for suffix in ("Depths", "Vels")
]


@pytest.mark.parametrize("proto,suffix", PROTO_BALTIC_CSVS)
def test_example_baltic_prototype_csvs_present(proto: str, suffix: str):
    """example_baltic must keep the 4 PROTO Depths/Vels CSVs.

    The wire script (_wire_wgbast_physical_configs.py:291) reads these
    as the canonical source when expanding per-cell hydraulics for
    each WGBAST river. If example_baltic is ever cleaned up, this test
    fails first and gives a clear pointer.
    """
    src = ROOT / "tests" / "fixtures" / "example_baltic" / f"{proto}-{suffix}.csv"
    assert src.exists(), (
        f"{src.relative_to(ROOT)} missing — wire script source. "
        f"Did example_baltic get cleaned up by mistake?"
    )
