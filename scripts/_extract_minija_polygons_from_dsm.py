"""Derive Minija river-area polygons from the precomputed flow-accumulation
rasters in ``C:\\dsm_work\\``.

This script supersedes the on-the-fly DSM pipeline. The owner of the GIS
DataBase ran ``run_hydro.py`` (which uses gis-hydro-mcp internally) and
left the outputs at:

    C:\\dsm_work\\aoi_dsm.tif       1 m DSM (1m pixels, 4×4 km AOI)
    C:\\dsm_work\\aoi_filled.tif    2 m sink-filled DEM
    C:\\dsm_work\\aoi_flowacc.tif   2 m flow accumulation
    C:\\dsm_work\\aoi_flowdir_d8.tif 2 m D8 flow direction
    C:\\dsm_work\\aoi_streams.tif   2 m stream mask (acc ≥ 500 cells)

We just need to threshold ``aoi_flowacc.tif`` at multiple drainage levels,
filter tiny components, polygonize, buffer, dissolve, and save as a sidecar
shapefile under the example_minija_basin fixture.

The AOI is at EPSG:3346 (LKS-94) bounds (322227–326228 E, 6168498–6172499 N)
which corresponds roughly to a 4×4 km window of the lower-mid Minija valley
near Lankupiai/Drevernai.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from scipy.ndimage import label as ndi_label
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
ACC_PATH = Path(r"C:\dsm_work\aoi_flowacc.tif")
OUT_DIR = ROOT / "tests" / "fixtures" / "example_minija_basin" / "Shapefile"
TARGET_CRS_EPSG = 3035  # match rest of fixture (LAEA Europe)

# Drainage tiers (in 2 m pixel cells; 1 cell = 4 m²).
#   creek    : 250 cells = 1000 m² upslope = ~0.001 km² (tiny stream)
#   river    : 5000 cells = 20,000 m² ≈ 0.02 km²
#   mainstem : 100k cells = 0.4 km² catchment (Minija main path)
TIERS = [
    {"name": "creek",    "threshold": 250,    "buffer_m": 3.0,  "min_cells": 200},
    {"name": "river",    "threshold": 5000,   "buffer_m": 8.0,  "min_cells": 100},
    {"name": "mainstem", "threshold": 100000, "buffer_m": 14.0, "min_cells": 50},
]


def main() -> None:
    if not ACC_PATH.exists():
        raise SystemExit(
            f"missing {ACC_PATH} — run C:\\dsm_work\\run_hydro.py first."
        )
    print(f"[1/3] Read flow-accumulation raster {ACC_PATH.name}")
    with rasterio.open(ACC_PATH) as src:
        acc = src.read(1)
        nodata_val = src.nodata
        if nodata_val is not None and not np.isnan(nodata_val):
            acc[acc == nodata_val] = 0.0
        # NaN nodata → treat as 0
        if np.isnan(acc).any():
            acc = np.nan_to_num(acc, nan=0.0)
        transform = src.transform
        src_crs = src.crs
        px = src.transform.a
        print(f"      shape={acc.shape}, pixel={px} m, max_acc={int(acc.max()):,} cells "
              f"({int(acc.max())*px*px/1e6:.3f} km²)")

    print("[2/3] Threshold each tier + filter tiny components + polygonize")
    poly_rows: list = []
    for tier in TIERS:
        thr = tier["threshold"]
        if thr > acc.max():
            print(f"      tier '{tier['name']}': skipped (threshold {thr:,} > max acc)")
            continue
        mask = (acc >= thr).astype(np.uint8)
        components, n_comp = ndi_label(mask)
        sizes = np.bincount(components.ravel())
        keep = np.zeros_like(mask)
        kept = 0
        for i in range(1, len(sizes)):
            if sizes[i] >= tier["min_cells"]:
                keep |= (components == i).astype(np.uint8)
                kept += 1
        n_cells = int(keep.sum())
        print(f"      {tier['name']}: {n_comp} components → {kept} kept ≥{tier['min_cells']} cells; "
              f"{n_cells:,} cells = {n_cells*px*px/1e6:.3f} km²")
        for geom, _ in features.shapes(keep, mask=keep.astype(bool), transform=transform):
            poly_rows.append({
                "tier": tier["name"],
                "buffer_m": tier["buffer_m"],
                "geometry": shape(geom),
            })

    if not poly_rows:
        raise SystemExit("no polygons produced")

    print(f"[3/3] Buffer + dissolve per tier + reproject + save")
    gdf = gpd.GeoDataFrame(poly_rows, geometry="geometry", crs=src_crs)
    gdf["geometry"] = [g.buffer(b) for g, b in zip(gdf.geometry, gdf["buffer_m"])]
    # Dissolve per tier so overlapping ribbons merge into clean polygons.
    gdf = (
        gdf[["tier", "geometry"]]
        .dissolve(by="tier", as_index=False)
        .explode(index_parts=False)
        .reset_index(drop=True)
    )
    gdf = gdf.to_crs(epsg=TARGET_CRS_EPSG)
    gdf["REACH_NAME"] = gdf["tier"].map(lambda t: f"Minija-DSM-{t}")

    out_path = OUT_DIR / "MinijaBasinExample-dsm-derived-osm-polygons.shp"
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        stale = out_path.with_suffix(ext)
        if stale.exists():
            stale.unlink()
    gdf[["REACH_NAME", "tier", "geometry"]].to_file(out_path, driver="ESRI Shapefile")
    print(f"      wrote {out_path.relative_to(ROOT)} ({len(gdf)} polygons)")
    print("\nTier breakdown:")
    print(gdf.groupby("tier").size())


if __name__ == "__main__":
    main()
