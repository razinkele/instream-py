"""Replace the OSM-overlay polygon sidecars with Lithuanian topographic
GDR50 river polygons from ``C:\\Users\\arturas.baziukas\\Documents\\mariosupes.gpkg``.

Per user 2026-05-02: "use ... mariosupes.gpkg as main source for minija basin".

The mariosupes.gpkg file contains the Lithuanian GDR50 topographic
``landuse`` layer filtered to hydrographic features (GKODAS ``hd1`` =
river polygons, ``hd5`` = lakes/reservoirs). It includes proper
river-area polygons that follow real river morphology — far better
than OSM's sparse coverage for these Lithuanian streams.

Coverage of basin reaches:
  Minija          3 polygons,  1.21 km² (one massive polygon spans the
                                          entire main stem)
  Babrungas       3 polygons,  0.69 km²
  Salantas        3 polygons,  0.094 km²
  Šalpė           1 polygon,   0.010 km²
  Curonian Lagoon 2 polygons, 399 km² (KURŠIŲ MARIOS)
  Atmata          0 by-name (likely row 365 by-spatial — unnamed
                              404 km² polygon at the right location)
  Veiviržas       0 (not in this dataset)

Output: a single sidecar shapefile that replaces both the v0.56.4
mainstem + tributaries OSM polygon sidecars AND the v0.56.13
DSM-derived polygons.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(r"C:\Users\arturas.baziukas\Documents\mariosupes.gpkg")
OUT_DIR = ROOT / "tests" / "fixtures" / "example_minija_basin" / "Shapefile"
TARGET_CRS_EPSG = 3035  # match rest of fixture

# Reach name → list of patterns (case-insensitive substring) OR a bbox
# tuple (lon_w, lat_s, lon_e, lat_n) for spatial-only matches.
REACH_NAMED = [
    ("Minija",         "Minija"),
    ("Babrungas",      "Babrungas"),
    ("Salantas",       "Salantas"),
    ("Salpe",          "Šalpė"),                # YAML uses Salpe (no diacritic)
    ("CuronianLagoon", "KURŠIŲ MARIOS"),
]
# Atmata is not named in mariosupes.gpkg. The unnamed 0.4 km² polygon
# at lon 21.292-21.374, lat 55.577-55.670 (row 365 of the source) is
# spatially the Atmata branch by location. We accept any unnamed hd1
# polygon intersecting the Atmata bbox.
ATMATA_BBOX = (21.20, 55.27, 21.50, 55.39)  # Lankupiai → Drevernai branch


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing source: {SRC}")
    print(f"[1/3] Reading {SRC.name}")
    g = gpd.read_file(SRC, layer="landuse").to_crs(epsg=4326)
    print(f"      total: {len(g)} polygons in EPSG:3346 (reprojected to 4326)")

    rows = []
    # Preserve None/NaN in VARDAS so the unnamed-polygon filter below
    # works correctly (str.contains on NaN produces NaN with na=False
    # → False, so name-match still skips them).
    for reach_name, pattern in REACH_NAMED:
        mask = g["VARDAS"].astype(str).str.contains(pattern, case=False, na=False, regex=False)
        n = int(mask.sum())
        if n == 0:
            print(f"      [{reach_name}] 0 polygons matching '{pattern}'")
            continue
        for _, prow in g.loc[mask].iterrows():
            rows.append({"REACH_NAME": reach_name, "geometry": prow.geometry})
        print(f"      [{reach_name}] {n} polygons matching '{pattern}'")

    # Atmata — spatial intersection (no name in source). Match any hd1
    # river polygon that's nameless (VARDAS isna OR empty string) and
    # intersects the Lankupiai-Drevernai bbox.
    atmata_box = box(*ATMATA_BBOX)
    nameless = g["VARDAS"].isna() | (g["VARDAS"].astype(str).str.strip() == "")
    unnamed_river = g[(g["GKODAS"] == "hd1") & nameless]
    in_box = unnamed_river[unnamed_river.geometry.intersects(atmata_box)]
    if not in_box.empty:
        for _, prow in in_box.iterrows():
            rows.append({"REACH_NAME": "Atmata", "geometry": prow.geometry})
        print(f"      [Atmata] {len(in_box)} unnamed hd1 polygons in spatial bbox")
    else:
        print(f"      [Atmata] 0 unnamed hd1 polygons in spatial bbox {ATMATA_BBOX}")

    if not rows:
        raise SystemExit("no polygons collected — aborting")

    print(f"[2/3] Build sidecar GeoDataFrame ({len(rows)} polygons)")
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf = gdf.to_crs(epsg=TARGET_CRS_EPSG)
    print(gdf.groupby("REACH_NAME").size())

    print(f"[3/3] Write sidecar shapefile")
    out = OUT_DIR / "MinijaBasinExample-gdr50-osm-polygons.shp"
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        stale = out.with_suffix(ext)
        if stale.exists():
            stale.unlink()
    gdf.to_file(out, driver="ESRI Shapefile")
    print(f"      wrote {out.relative_to(ROOT)}")

    # Also delete the now-obsolete sidecars so the overlay isn't cluttered
    # by the old OSM-polygons (sparse) + DSM-derived (axis-aligned ribbons).
    obsolete = [
        "MinijaBasinExample-mainstem-osm-polygons",
        "MinijaBasinExample-tributaries-osm-polygons",
        "MinijaBasinExample-dsm-derived-osm-polygons",
    ]
    for stem in obsolete:
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            p = OUT_DIR / f"{stem}{ext}"
            if p.exists():
                p.unlink()
                print(f"      removed obsolete: {p.name}")


if __name__ == "__main__":
    main()
