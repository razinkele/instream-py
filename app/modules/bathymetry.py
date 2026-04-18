"""EMODnet Bathymetry DTM fetch + per-cell depth sampler.

Workflow:
    1. fetch_emodnet_dtm(bbox) downloads a 1/16 arc-minute GeoTIFF once,
       caches it under app/data/emodnet/ keyed by bbox hash.
    2. sample_depth(gdf, tif_path) reads each cell's centroid depth.

Depths are reported as positive metres below sea surface (EMODnet stores
elevation as negative below datum; we flip the sign and clamp land to 0.1 m).

Data source: EMODnet Bathymetry Consortium. https://emodnet.ec.europa.eu/en/bathymetry
"""
from __future__ import annotations

import hashlib
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests

_EMODNET_WCS = "https://ows.emodnet-bathymetry.eu/wcs"
# Coverage IDs use double-underscore notation (`emodnet__mean`), verified via
# WCS GetCapabilities on 2026-04-18. `emodnet__mean` is the latest composite;
# pinned yearly releases (e.g. `emodnet__mean_2022`) are also available.
_EMODNET_COVERAGE_ID = "emodnet__mean"
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "emodnet"


def _cache_path_for_bbox(bbox: tuple[float, float, float, float]) -> Path:
    """Cache path for a bbox (hash of bbox coords).

    Uses SHA-1 with `usedforsecurity=False` for FIPS-mode Windows compatibility;
    the hash is a cache key, not a security boundary.
    """
    key = ",".join(f"{v:.4f}" for v in bbox)
    h = hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:12]
    return _CACHE_DIR / f"emodnet_{h}.tif"


def fetch_emodnet_dtm(bbox: tuple[float, float, float, float]) -> Path:
    """Download EMODnet DTM for bbox (lon_min, lat_min, lon_max, lat_max) if
    not already cached. Returns the local GeoTIFF path."""
    dst = _cache_path_for_bbox(bbox)
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    params = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": _EMODNET_COVERAGE_ID,
        "format": "image/tiff",
        "subset": [
            f"Long({bbox[0]},{bbox[2]})",
            f"Lat({bbox[1]},{bbox[3]})",
        ],
    }
    tmp = dst.with_suffix(".tif.part")
    resp = requests.get(_EMODNET_WCS, params=params, timeout=300, stream=True)
    resp.raise_for_status()
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(1 << 20):
            f.write(chunk)
    tmp.replace(dst)
    return dst


def sample_depth(gdf, tif_path: Path) -> np.ndarray:
    """Return an array of depths (positive metres below surface), one per row
    in *gdf*, sampled at each row's geometry centroid.

    Uses an adaptive projection to avoid shapely's "Geometry is in a geographic
    CRS" warning for centroid computation:
      - if the raster CRS is projected: reproject gdf to raster CRS, take
        centroid there, sample directly.
      - if the raster CRS is geographic (EMODnet is EPSG:4326): derive a UTM
        zone from the data (gdf.estimate_utm_crs()) so this works beyond
        UTM 34N if the bbox drifts.
    """
    import rasterio

    if not Path(tif_path).exists():
        raise FileNotFoundError(tif_path)

    with rasterio.open(tif_path) as src:
        src_crs = src.crs
        if src_crs is not None and src_crs.is_projected:
            gdf_proj = gdf.to_crs(src_crs) if gdf.crs != src_crs else gdf
            centroids = gdf_proj.geometry.centroid
            coords = [(c.x, c.y) for c in centroids]
        else:
            try:
                utm_crs = gdf.estimate_utm_crs()
            except Exception:
                utm_crs = "EPSG:32634"  # Baltic fallback
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                gdf_utm = gdf.to_crs(utm_crs)
                centroids_utm = gdf_utm.geometry.centroid
            centroids_wgs = gpd.GeoSeries(centroids_utm, crs=utm_crs).to_crs(
                src_crs or "EPSG:4326"
            )
            coords = [(c.x, c.y) for c in centroids_wgs]
        samples = np.array([v[0] for v in src.sample(coords)])

    # EMODnet stores elevation (negative below sea level) — flip to depth
    depths = -samples.astype(np.float64)
    # Land cells (elevation > 0) become negative depth — clamp to 0.1 m
    depths = np.where(depths < 0.1, 0.1, depths)
    return depths
