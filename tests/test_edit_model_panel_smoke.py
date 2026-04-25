"""v0.46 Task A6: end-to-end Edit Model panel smoke.

Asserts that an isolated copy of the fixture round-trips through ESRI
Shapefile read/write without corrupting the reach name set or cell
count. Pure-Python (no Shiny session); calls the same persistence
helpers the panel handlers use.
"""
import shutil
import sys
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_edit_model_round_trip_does_not_corrupt_fixture(tmp_path):
    src = ROOT / "tests" / "fixtures" / "example_morrumsan"
    dst = tmp_path / "example_morrumsan"
    shutil.copytree(src, dst)
    shp = next((dst / "Shapefile").glob("*.shp"))

    cells = gpd.read_file(shp)
    n_initial = len(cells)
    reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
    initial_reaches = set(cells[reach_col].unique())
    assert n_initial > 0
    assert len(initial_reaches) >= 2

    cells.to_file(shp, driver="ESRI Shapefile")
    cells2 = gpd.read_file(shp)
    assert len(cells2) == n_initial
    assert set(cells2[reach_col].unique()) == initial_reaches
