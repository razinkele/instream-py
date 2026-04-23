"""Probe Marine Regions WFS to find a typeName that returns Curonian Lagoon
(MRGID 3642) as a polygon.

Strategy: discovery probe against the gazetteer and bay/lagoon layers
identified via GetCapabilities (2026-04-18). MRGID field name varies by
layer, so we try a few common spellings.
"""
from __future__ import annotations

import json
import requests

WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"
MRGID = 3642  # Curonian Lagoon

# Ordered from most-likely to least-likely for a named lagoon.
TYPE_NAMES = [
    "MarineRegions:gazetteer_polygon",
    "MarineRegions:world_bay_gulf",
    "MarineRegions:world_estuary_delta",
    "MarineRegions:seavox_v19",
]

# Attribute names that different layers use for the Marine Regions ID.
MRGID_FIELDS = ["MRGID", "mrgid", "gaz_id", "id"]


def main() -> None:
    for tn in TYPE_NAMES:
        # First try each MRGID field spelling
        found = False
        for field in MRGID_FIELDS:
            params = {
                "service": "WFS", "version": "2.0.0", "request": "GetFeature",
                "typeNames": tn,
                "cql_filter": f"{field}={MRGID}",
                "outputFormat": "application/json",
                "count": "1",
            }
            try:
                resp = requests.get(WFS, params=params, timeout=30)
            except Exception as exc:
                print(f"{tn} filter={field}: FAIL ({exc})")
                continue
            if resp.status_code != 200:
                continue
            try:
                data = resp.json()
            except Exception:
                continue
            feats = data.get("features", [])
            if feats:
                print(f"{tn} filter={field}={MRGID}: HTTP 200, {len(feats)} feature(s)")
                print(f"  geom type: {feats[0].get('geometry', {}).get('type', '?')}")
                props = feats[0].get("properties", {})
                print(f"  attrs: {list(props.keys())[:12]}")
                print("  first 200 chars of geometry JSON:")
                print("  " + json.dumps(feats[0].get("geometry"))[:200])
                found = True
                return
        if not found:
            # Layer exists but MRGID not a field — try a bbox-based name filter
            params = {
                "service": "WFS", "version": "2.0.0", "request": "GetFeature",
                "typeNames": tn,
                "bbox": "20.5,54.4,22.0,56.0,EPSG:4326",
                "outputFormat": "application/json",
                "count": "5",
            }
            try:
                resp = requests.get(WFS, params=params, timeout=30)
            except Exception as exc:
                print(f"{tn} bbox-probe: FAIL ({exc})")
                continue
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    continue
                feats = data.get("features", [])
                print(f"{tn} bbox-probe: HTTP 200, {len(feats)} feature(s) in Baltic bbox")
                for f in feats[:5]:
                    p = f.get("properties", {})
                    name = p.get("name") or p.get("PREF_NAME") or p.get("gaz_name") or p.get("NAME") or "?"
                    mr = p.get("MRGID") or p.get("mrgid") or p.get("gaz_id") or "?"
                    print(f"    MRGID={mr}  name={name}")
            else:
                print(f"{tn} bbox-probe: HTTP {resp.status_code}")

    print(f"\nNo typeName returned MRGID {MRGID}.")
    print("Fallback: download shapefile manually from "
          f"https://marineregions.org/gazetteer.php?p=details&id={MRGID}")


if __name__ == "__main__":
    main()
