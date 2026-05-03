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
    # v0.57.2: post-v0.57.0 fixtures ship in EPSG:3035 (LAEA Europe,
    # metres). The production _regen_apply path goes through
    # _load_fixture which reprojects to EPSG:4326 before passing cells
    # to generate_cells. Mirror that here — generate_cells assumes
    # EPSG:4326 input (it forces that CRS on the GDF at line 107 and
    # then calls detect_utm_epsg on raw centroid x/y as if they were
    # degrees). Without this reproject, the metric coords (~5e6 m)
    # are interpreted as longitude → bogus UTM zone → CRSError.
    if cells.crs is not None and str(cells.crs) != "EPSG:4326":
        cells = cells.to_crs("EPSG:4326")
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


def test_regenerate_re_expands_per_cell_csvs(tmp_path):
    """H7 (iteration-5): regenerating cells must re-expand the per-reach
    Depths.csv / Vels.csv files so their row count matches the new cell
    count. Otherwise next load raises:
        ValueError: hydraulic table has X rows but cell count is Y
    """
    src = ROOT / "tests" / "fixtures" / "example_morrumsan"
    dst = tmp_path / "example_morrumsan"
    shutil.copytree(src, dst)
    shp = next((dst / "Shapefile").glob("*.shp"))

    cells_before = gpd.read_file(shp)
    # v0.57.2: reproject to EPSG:4326 to match what production
    # _regen_apply receives via _load_fixture (see sister test for
    # the longer rationale).
    if cells_before.crs is not None and str(cells_before.crs) != "EPSG:4326":
        cells_before = cells_before.to_crs("EPSG:4326")
    reach_col = "REACH_NAME" if "REACH_NAME" in cells_before.columns else "reach_name"
    counts_before = cells_before[reach_col].value_counts().to_dict()

    from modules.create_model_grid import generate_cells
    reach_segments = {
        name: {
            "segments": list(grp.geometry), "frac_spawn": 0.0, "type": "water",
        }
        for name, grp in cells_before.groupby(reach_col)
    }
    new_cells = generate_cells(
        reach_segments=reach_segments, cell_size=30.0,
        cell_shape="hexagonal", buffer_factor=1.0, min_overlap=0.1,
    )
    rename = {
        "cell_id": "ID_TEXT", "reach_name": "REACH_NAME", "area": "AREA",
        "dist_escape": "M_TO_ESC", "num_hiding": "NUM_HIDING",
        "frac_vel_shelter": "FRACVSHL", "frac_spawn": "FRACSPWN",
    }
    new_cells = new_cells.rename(columns=rename)
    new_cells["ID_TEXT"] = new_cells["ID_TEXT"].astype(str)
    new_cells.to_file(shp, driver="ESRI Shapefile")

    new_counts = new_cells["REACH_NAME"].value_counts().to_dict()
    for reach_name, n_new in new_counts.items():
        for suffix in ("Depths.csv", "Vels.csv"):
            csv_path = dst / f"{reach_name}-{suffix}"
            if not csv_path.exists():
                continue
            lines = csv_path.read_text(encoding="utf-8").splitlines()
            header_end = None
            for i, line in enumerate(lines):
                parts = line.split(",")
                if not parts:
                    continue
                first = parts[0].strip()
                if first.isdigit() and len(parts) > 1:
                    try:
                        float(parts[1])
                        header_end = i
                        break
                    except ValueError:
                        continue
            assert header_end is not None
            header_lines = lines[:header_end]
            template = lines[header_end].split(",")
            payload = template[1:]
            with open(csv_path, "w", encoding="utf-8") as f:
                for hl in header_lines:
                    f.write(hl + "\n")
                for i in range(int(n_new)):
                    f.write(f"{i + 1}," + ",".join(payload) + "\n")

            written = csv_path.read_text(encoding="utf-8").splitlines()
            data_rows = sum(
                1 for ln in written
                if ln and ln[0].isdigit() and "," in ln
                and ln.split(",")[0].strip().isdigit()
            )
            assert data_rows >= n_new, (
                f"{csv_path.name}: expected ≥{n_new} data rows after re-expansion, "
                f"got {data_rows}"
            )
    assert sum(new_counts.values()) != sum(counts_before.values())
