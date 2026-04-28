"""Diagnose: do current BalticCoast cells overlap the Curonian Spit?
Also: does the lithuania_land_real polygon fully cover the spit?
"""
from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Load BalticCoast cells
    shp = ROOT / "tests/fixtures/example_baltic/Shapefile/BalticExample.shp"
    cells = gpd.read_file(shp)
    bc = cells[cells["REACH_NAME"] == "BalticCoast"].to_crs("EPSG:4326")
    print(f"BalticCoast cells: {len(bc)}")
    print(f"  bbox: {bc.total_bounds}")
    print(f"  geometry type: {bc.geometry.iloc[0].geom_type}")

    # Also KlaipedaStrait
    ks = cells[cells["REACH_NAME"] == "KlaipedaStrait"].to_crs("EPSG:4326")
    print(f"\nKlaipedaStrait cells: {len(ks)}")
    print(f"  bbox: {ks.total_bounds}")

    # Load Lithuanian land
    land_path = ROOT / "app/data/marineregions/lithuania_land_real.geojson"
    land = gpd.read_file(land_path)
    print(f"\nLithuania land polygon: {len(land)} feature(s)")
    g = land.geometry.iloc[0]
    print(f"  type: {g.geom_type}")
    if g.geom_type.startswith("Multi"):
        print(f"  parts: {len(g.geoms)}")
        for i, sub in enumerate(g.geoms):
            print(f"    part {i}: bounds={sub.bounds}, area_deg2={sub.area:.4f}")

    # Load spit polygon explicitly
    spit_path = ROOT / "app/data/marineregions/curonian_spit.geojson"
    if spit_path.exists():
        spit = gpd.read_file(spit_path)
        sg = spit.geometry.iloc[0]
        print(f"\nCuronian Spit polygon: {sg.geom_type}, bounds={sg.bounds}")
    else:
        sg = None
        print("\nNo curonian_spit.geojson")

    # Question 1: how many BalticCoast cells overlap the land polygon?
    land_union = unary_union(g) if g.geom_type.startswith("Multi") else g
    bc_overlapping = bc[bc.geometry.intersects(land_union)]
    print(f"\nBalticCoast cells intersecting land polygon: {len(bc_overlapping)}/{len(bc)}")
    if len(bc_overlapping) > 0:
        # Sample overlap fractions
        bc_proj = bc_overlapping.to_crs("EPSG:32634")
        land_proj = gpd.GeoDataFrame(
            geometry=[land_union], crs="EPSG:4326"
        ).to_crs("EPSG:32634").geometry.iloc[0]
        for i in range(min(5, len(bc_proj))):
            cell = bc_proj.geometry.iloc[i]
            inter = cell.intersection(land_proj)
            frac = inter.area / cell.area if cell.area > 0 else 0
            print(f"    sample cell: area={cell.area:.0f} m², overlap with land: {frac*100:.1f}%")

    # Question 2: does the spit polygon overlap the land polygon? (i.e., is spit included in land?)
    if sg is not None:
        spit_in_land = sg.intersection(land_union).area / sg.area if sg.area > 0 else 0
        print(f"\nSpit polygon coverage by land polygon: {spit_in_land*100:.1f}%")
        # And: do BalticCoast cells overlap the spit (whether or not it's "land")?
        bc_on_spit = bc[bc.geometry.intersects(sg)]
        print(f"BalticCoast cells intersecting spit polygon: {len(bc_on_spit)}/{len(bc)}")

    # Question 3: KlaipedaStrait — does it overlap land?
    ks_on_land = ks[ks.geometry.intersects(land_union)]
    print(f"\nKlaipedaStrait cells intersecting land polygon: {len(ks_on_land)}/{len(ks)}")
    if len(ks_on_land) > 0:
        ks_proj = ks_on_land.to_crs("EPSG:32634")
        land_proj = gpd.GeoDataFrame(
            geometry=[land_union], crs="EPSG:4326"
        ).to_crs("EPSG:32634").geometry.iloc[0]
        total_overlap_m2 = sum(
            ks_proj.geometry.iloc[i].intersection(land_proj).area
            for i in range(len(ks_proj))
        )
        print(f"  total KlaipedaStrait area on land: {total_overlap_m2 / 1e6:.2f} km²")


if __name__ == "__main__":
    main()
