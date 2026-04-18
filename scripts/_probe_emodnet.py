"""Verify EMODnet Bathymetry WCS serves a usable GeoTIFF for the Nemunas/Baltic bbox."""
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "emodnet"
OUT.mkdir(parents=True, exist_ok=True)
dst = OUT / "probe_baltic.tif"

# Coverage ID `emodnet__mean` verified via WCS GetCapabilities on 2026-04-18
url = "https://ows.emodnet-bathymetry.eu/wcs"
params = {
    "service": "WCS",
    "version": "2.0.1",
    "request": "GetCoverage",
    "coverageId": "emodnet__mean",
    "format": "image/tiff",
    "subset": ["Long(20.0,22.5)", "Lat(54.5,56.0)"],
}
print("Requesting EMODnet WCS GetCoverage...")
resp = requests.get(url, params=params, timeout=120, stream=True)
print(f"HTTP {resp.status_code}, Content-Type: {resp.headers.get('Content-Type')}")
resp.raise_for_status()
with open(dst, "wb") as f:
    for chunk in resp.iter_content(1 << 20):
        f.write(chunk)
print(f"Saved: {dst} ({dst.stat().st_size / 1_000_000:.1f} MB)")

import rasterio

with rasterio.open(dst) as src:
    print(f"CRS: {src.crs}")
    print(f"Bounds: {src.bounds}")
    print(f"Resolution: {src.res}")
    print(f"Shape: {src.shape}")
    print(f"Dtype: {src.dtypes}")
    arr = src.read(1)
    print(f"Depth range: min={arr.min()}, max={arr.max()}  "
          f"(EMODnet: negative = below sea level)")
