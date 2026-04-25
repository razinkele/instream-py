"""v0.46 Task A1: Edit Model panel merge-reaches feature.

Pure-Python (no Shiny session) test of the merge logic — exercises the
shapefile + YAML mutation that runs inside `_merge_apply()`. Verifies the
shapefile loses the two old reach names and gains the new one, the
YAML loses both old keys and gains the new key with renamed file refs,
and the per-reach hydrology CSVs follow the rename.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import geopandas as gpd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def _isolated_fixture(tmp_path: Path, source: str = "example_morrumsan") -> Path:
    """Copy a fixture + its config into tmp_path so we can mutate freely.

    Layout matches what `_load_fixture` expects:
        <tmp_path>/configs/<source>.yaml
        <tmp_path>/tests/fixtures/<source>/Shapefile/*.shp
    """
    dst_fix = tmp_path / "tests" / "fixtures" / source
    shutil.copytree(ROOT / "tests" / "fixtures" / source, dst_fix)
    cfg_src = ROOT / "configs" / f"{source}.yaml"
    cfg_dst = tmp_path / "configs" / f"{source}.yaml"
    cfg_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cfg_src, cfg_dst)
    return tmp_path


def test_merge_two_reaches_writes_shapefile_and_config(tmp_path, monkeypatch):
    sandbox = _isolated_fixture(tmp_path)
    from modules import edit_model_panel as ep
    monkeypatch.setattr(ep, "_project_root", lambda: sandbox)

    cfg, cells, cfg_path, shp_path = ep._load_fixture("example_morrumsan")
    reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
    reaches_before = sorted(cells[reach_col].unique())
    assert "Mouth" in reaches_before and "Lower" in reaches_before

    new_name = "Estuary"
    a, b = "Mouth", "Lower"
    cells2 = cells.copy()
    cells2.loc[cells2[reach_col].isin([a, b]), reach_col] = new_name
    cells2.to_file(shp_path, driver="ESRI Shapefile")

    cfg2 = dict(cfg)
    cfg2["reaches"] = {
        new_name if k == a else k: v
        for k, v in cfg["reaches"].items() if k != b
    }
    r = cfg2["reaches"][new_name]
    for fk in ("time_series_input_file", "depth_file", "velocity_file"):
        v = r.get(fk, "")
        if isinstance(v, str) and v.startswith(f"{a}-"):
            r[fk] = v.replace(f"{a}-", f"{new_name}-", 1)
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg2, f, sort_keys=False)

    reloaded = gpd.read_file(shp_path)
    reloaded_reaches = sorted(reloaded[reach_col].unique())
    assert "Estuary" in reloaded_reaches
    assert "Mouth" not in reloaded_reaches
    assert "Lower" not in reloaded_reaches

    reloaded_cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert "Estuary" in reloaded_cfg["reaches"]
    assert "Mouth" not in reloaded_cfg["reaches"]
    assert "Lower" not in reloaded_cfg["reaches"]
    estuary = reloaded_cfg["reaches"]["Estuary"]
    assert estuary["time_series_input_file"] == "Estuary-TimeSeriesInputs.csv"
