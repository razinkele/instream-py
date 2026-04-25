"""v0.46 Task A4: in-panel cell-size regeneration.

Verifies that regenerating an existing fixture at a different cell size
produces a sensible cell-count change (smaller cell size → more cells)
and preserves the reach-name set.
"""
import shutil
import sys
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_regenerate_at_smaller_size_produces_more_cells(tmp_path):
    src_root = ROOT / "tests" / "fixtures" / "example_morrumsan"
    dst_root = tmp_path / "example_morrumsan"
    shutil.copytree(src_root, dst_root)
    shp = next((dst_root / "Shapefile").glob("*.shp"))

    cells = gpd.read_file(shp)
    n_before = len(cells)
    reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
    reaches_before = set(cells[reach_col].unique())

    from modules.create_model_grid import generate_cells

    reach_segments = {}
    for name, grp in cells.groupby(reach_col):
        reach_segments[name] = {
            "segments": list(grp.geometry),
            "frac_spawn": 0.0,
            "type": "water",
        }
    new_cells = generate_cells(
        reach_segments=reach_segments,
        cell_size=30.0,  # smaller than example_morrumsan's default
        cell_shape="hexagonal",
        buffer_factor=1.0,
        min_overlap=0.1,
    )
    n_after = len(new_cells)
    assert n_after > n_before, (
        f"smaller cell size should produce more cells: {n_before} → {n_after}"
    )
    new_reach_col = "reach_name" if "reach_name" in new_cells.columns else "REACH_NAME"
    reaches_after = set(new_cells[new_reach_col].unique())
    assert reaches_before == reaches_after, (
        f"reach set should be preserved: {reaches_before} → {reaches_after}"
    )
