"""Probe what real Baltic features OSM exposes in the Nemunas delta bbox."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from modules.create_model_osm import query_waterways, query_water_bodies  # noqa: E402


def main() -> None:
    # Lower Nemunas + delta + Curonian Lagoon + Baltic coast off Klaipeda
    bbox = (20.8, 54.9, 22.2, 55.95)
    print(f"Probing OSM bbox {bbox} ...\n")

    print("=== Rivers/streams ===")
    rivers = query_waterways("lithuania", bbox)
    print(f"Got {len(rivers)} features")
    if "waterway" in rivers.columns:
        for wt, grp in rivers.groupby("waterway"):
            print(f"  {wt}: {len(grp)}")

    print("\n=== Named waterways (top 25 by length) ===")
    if "nameText" in rivers.columns:
        rivers["length"] = rivers.geometry.length
        named = rivers[rivers["nameText"].fillna("").str.len() > 0]
        named = named.sort_values("length", ascending=False).head(25)
        for _, row in named.iterrows():
            wt = row.get("waterway", "?")
            print(f"  {row['nameText']:<30s} {wt:<8s} len={row['length']:.4f}")

    print("\n=== Water bodies ===")
    water = query_water_bodies("lithuania", bbox)
    print(f"Got {len(water)} features")
    if "water" in water.columns:
        for wt, grp in water.groupby(water["water"].fillna("")):
            print(f"  water={wt!r}: {len(grp)}")
    if "natural" in water.columns:
        for nt, grp in water.groupby(water["natural"].fillna("")):
            print(f"  natural={nt!r}: {len(grp)}")

    print("\n=== Large water bodies (top 15 by area) ===")
    water["area"] = water.geometry.area
    top = water.sort_values("area", ascending=False).head(15)
    for _, row in top.iterrows():
        name = row.get("nameText", "") or ""
        wt = row.get("water", "") or row.get("natural", "") or "?"
        print(f"  {name[:35]:<35s} type={wt:<12s} area_sqdeg={row['area']:.6f}")


if __name__ == "__main__":
    main()
