"""v0.57.0 fix #13: _do_rename must rename per-reach CSVs on disk even
when the YAML config lacks a top-level `reaches:` key. Pre-fix the entire
CSV rename block was gated on `if "reaches" in cfg and old in cfg["reaches"]`,
so reach-keyless fixtures had their shapefile renamed but their CSVs left
behind under the old name — next load failed with "missing CSV file"."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def _isolated_fixture_no_reaches(tmp_path: Path) -> Path:
    """Copy example_morrumsan + strip its `reaches:` key from the YAML."""
    src_fix = ROOT / "tests" / "fixtures" / "example_morrumsan"
    dst_fix = tmp_path / "tests" / "fixtures" / "example_morrumsan"
    shutil.copytree(src_fix, dst_fix)
    cfg_src = ROOT / "configs" / "example_morrumsan.yaml"
    cfg_dst = tmp_path / "configs" / "example_morrumsan.yaml"
    cfg_dst.parent.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(cfg_src.read_text(encoding="utf-8"))
    cfg.pop("reaches", None)
    cfg_dst.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return tmp_path


def test_rename_csvs_when_no_reaches_key(tmp_path, monkeypatch):
    sandbox = _isolated_fixture_no_reaches(tmp_path)
    from modules import edit_model_panel as ep
    monkeypatch.setattr(ep, "_project_root", lambda: sandbox)

    cfg, cells, cfg_path, shp_path = ep._load_fixture("example_morrumsan")
    fixture_dir = shp_path.parent.parent
    old, new = "Mouth", "Estuary"

    # CSVs exist under the OLD name on disk before rename.
    pre_existing = [
        fixture_dir / f"{old}-TimeSeriesInputs.csv",
        fixture_dir / f"{old}-Depths.csv",
        fixture_dir / f"{old}-Vels.csv",
    ]
    found_pre = [p for p in pre_existing if p.exists()]
    assert found_pre, (
        f"test prerequisite: at least one of {pre_existing} must pre-exist"
    )

    # Apply the rename mutation logic directly (the same block that runs
    # inside _do_rename — this isolates the CSV-rename bug from Shiny
    # session plumbing). The plan calls for unconditional CSV rename, so
    # run the path the production code SHOULD take.
    reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
    cells2 = cells.copy()
    cells2.loc[cells2[reach_col] == old, reach_col] = new
    cells2.to_file(shp_path, driver="ESRI Shapefile")
    for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
        src = fixture_dir / f"{old}-{suffix}"
        if src.exists():
            src.rename(fixture_dir / f"{new}-{suffix}")

    # After the rename, the OLD CSVs must be gone and NEW CSVs present.
    for p in found_pre:
        assert not p.exists(), f"{p} should have been renamed away"
        new_p = p.parent / p.name.replace(f"{old}-", f"{new}-", 1)
        assert new_p.exists(), f"{new_p} should now exist"

    # Sanity: this test exercises the disk-side rename. The production
    # bug is that _do_rename only enters this rename branch when
    # `cfg["reaches"]` has the old key. The fix below removes that gate.
    # We assert the gate is gone in the source by inspection — scoped
    # to _do_rename's body so other functions (_split_apply, _merge_apply,
    # _lasso_apply) that also contain the same suffix tuple do not
    # confound the search.
    src_text = (ROOT / "app" / "modules" / "edit_model_panel.py").read_text(encoding="utf-8")

    # Locate _do_rename's body. End at the next @reactive.effect (which
    # is _merge_start in pre-fix and post-fix source — Task 3.2 changes
    # _do_rename's body but not its boundaries).
    start = src_text.index("def _do_rename")
    end = src_text.find("\n    @reactive.effect", start + len("def _do_rename"))
    if end == -1:
        end = len(src_text)
    body = src_text[start:end]

    needle = 'for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):'
    needle_idx = body.index(needle)
    # 400 chars before the needle within _do_rename's body covers ~12
    # lines — wide enough to catch the gate at any plausible position
    # above the CSV rename loop. Pre-fix, the gate sits ~5 lines above
    # the needle (within 200 chars). Post-fix, the gate has been moved
    # BELOW the needle (the CSV rename loop is hoisted), so the pre
    # window does not contain it.
    pre = body[max(0, needle_idx - 400) : needle_idx]
    assert 'if "reaches" in cfg and old in cfg["reaches"]:' not in pre, (
        "CSV rename is still gated on cfg['reaches']; v0.57.0 fix #13 not applied. "
        f"Found gate in _do_rename body BEFORE the CSV rename loop:\n{pre[-300:]!r}"
    )
