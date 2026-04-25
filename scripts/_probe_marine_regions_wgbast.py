"""Throwaway probe: does Marine Regions WFS return named bay polygons
covering each WGBAST river mouth?"""
import requests

MARINE_REGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"


def _query_marine_regions(bbox_wgs84):
    west, south, east, north = bbox_wgs84
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "MarineRegions:iho",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{west},{south},{east},{north},EPSG:4326",
    }
    try:
        resp = requests.get(MARINE_REGIONS_WFS, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# A 0.5° bbox around each mouth (lon-low, lat-low, lon-high, lat-high)
RIVER_MOUTHS = {
    "tornionjoki": (24.142, 65.881),
    "simojoki":    (25.063, 65.619),
    "byskealven":  (21.182, 64.945),
    "morrumsan":   (14.745, 56.175),
}

for river, (lon, lat) in RIVER_MOUTHS.items():
    bbox = (lon - 0.5, lat - 0.5, lon + 0.5, lat + 0.5)
    print(f"\n=== {river}  mouth=({lon}, {lat}) ===")
    geoj = _query_marine_regions(bbox)
    if geoj is None:
        print("  WFS error or no response")
        continue
    feats = geoj.get("features", [])
    print(f"  {len(feats)} features in bbox")
    seen_names = set()
    for f in feats:
        name = (f.get("properties") or {}).get("name", "")
        gtype = (f.get("geometry") or {}).get("type", "")
        if name and name not in seen_names:
            seen_names.add(name)
            print(f"    - {name!r:35s} ({gtype})")
