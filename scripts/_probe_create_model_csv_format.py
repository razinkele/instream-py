"""Throwaway probe: does a Create Model exported Depths.csv load via
the simulation's _parse_hydraulic_csv?"""
import sys
import tempfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

from modules.create_model_export import export_template_csvs  # noqa: E402
from salmopy.io.hydraulics_reader import _parse_hydraulic_csv  # noqa: E402

# Build a minimal cells GDF
cells = gpd.GeoDataFrame(
    {
        "cell_id": ["C0001", "C0002", "C0003"],
        "reach_name": ["R1"] * 3,
    },
    geometry=[Polygon([(0,0),(1,0),(1,1),(0,1)]) for _ in range(3)],
    crs="EPSG:4326",
)

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    export_template_csvs(
        reaches={"R1": {}},
        cells_gdf=cells,
        output_dir=td,
        start_date="2026-04-25",
    )
    depths_path = td / "R1-Depths.csv"
    print(f"\n=== {depths_path.name} (head 4 lines) ===")
    for line in depths_path.read_text().splitlines()[:4]:
        print(f"  {line!r}")
    print("\n=== _parse_hydraulic_csv output ===")
    try:
        flows, values, ids = _parse_hydraulic_csv(depths_path, return_cell_ids=True)
        print(f"  flows: {flows}")
        print(f"  values shape: {values.shape}")
        print(f"  cell_ids: {ids}")
    except Exception as exc:
        print(f"  RAISED: {type(exc).__name__}: {exc}")
