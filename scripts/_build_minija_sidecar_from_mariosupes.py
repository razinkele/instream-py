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

# Reaches matched by name (case-insensitive substring on VARDAS).
REACH_NAMED = [
    ("Babrungas",      "Babrungas"),
    ("Salantas",       "Salantas"),
    ("Salpe",          "Šalpė"),                # YAML uses Salpe (no diacritic)
    ("CuronianLagoon", "KURŠIŲ MARIOS"),
]
# Reaches matched by SPATIAL overlap with an existing OSM centerline
# sidecar. GDR50 (mariosupes.gpkg) doesn't tag the lower Minija as
# "Minija" — it segments it under "Piktvardė", "Šyša", and unnamed hd1
# channels at Lankupiai/Drevernai. Filtering by intersection with the
# OSM Minija centerline buffer (250 m) catches all those segments
# regardless of name. Same trick gets the Atmata branch.
CENTERLINE_BUFFER_M = 250
SPATIAL_REACHES = [
    ("Minija",
     ROOT / "tests/fixtures/example_minija_basin/Shapefile"
     / "MinijaBasinExample-mainstem-osm-centerlines.shp"),
    # Atmata: spatial overlap with the Lankupiai-Drevernai bbox area.
    # We don't have an OSM centerline for Atmata, so use a bbox here.
]
ATMATA_BBOX = (21.20, 55.27, 21.50, 55.39)  # Lankupiai → Drevernai branch
# Šyša in GDR50 is a single 74 km² polygon that covers the entire
# Klaipėda-Šilutė delta — including the lower Minija (south of
# Lankupiai 55.34°N) AND the Atmata branch. Plain inclusion would
# add the entire delta as one reach; instead we CLIP Šyša to each
# reach's centerline / bbox buffer so we get only the river-relevant
# area. Same logic applies to other delta lump polygons we discover.
SYSA_NAME = "Šyša"
SYSA_CLIP_BUFFER_M = 250
SYSA_CLIP_TARGETS = [
    # (reach_name, centerline_shp_path | None, bbox | None)
    ("Minija",
     ROOT / "tests/fixtures/example_minija_basin/Shapefile"
     / "MinijaBasinExample-mainstem-osm-centerlines.shp",
     None),
    ("Atmata",
     None,
     ATMATA_BBOX),
]


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing source: {SRC}")
    print(f"[1/3] Reading {SRC.name}")
    g = gpd.read_file(SRC, layer="landuse").to_crs(epsg=4326)
    print(f"      total: {len(g)} polygons in EPSG:3346 (reprojected to 4326)")

    rows = []
    used_idx: set = set()  # avoid double-assigning a polygon to two reaches

    # Pass 1 — name match
    for reach_name, pattern in REACH_NAMED:
        mask = g["VARDAS"].astype(str).str.contains(pattern, case=False, na=False, regex=False)
        n = int(mask.sum())
        if n == 0:
            print(f"      [{reach_name}] 0 polygons matching '{pattern}'")
            continue
        for idx, prow in g.loc[mask].iterrows():
            rows.append({"REACH_NAME": reach_name, "geometry": prow.geometry})
            used_idx.add(idx)
        print(f"      [{reach_name}] {n} polygons matching '{pattern}'")

    # Pass 2 — spatial overlap with OSM centerlines (catches the lower
    # Minija segments named Piktvardė, M-1, M-2, etc. in GDR50, plus
    # unnamed hd1 channels at Lankupiai/Drevernai).
    for reach_name, centerline_shp in SPATIAL_REACHES:
        if not centerline_shp.exists():
            print(f"      [{reach_name}] missing centerline {centerline_shp.name}")
            continue
        cl = gpd.read_file(centerline_shp).to_crs(epsg=32634)
        cl_buf = cl.geometry.union_all().buffer(CENTERLINE_BUFFER_M)
        cl_buf_4326 = gpd.GeoSeries([cl_buf], crs="EPSG:32634").to_crs(4326).iloc[0]
        # Exclude Šyša from raw inclusion — it's a 74 km² delta lump
        # that we instead clip in pass 4. Including it raw here would
        # add the entire Klaipėda-Šilutė delta as a single Minija polygon.
        candidates = g[
            (g["GKODAS"] == "hd1")
            & (g["VARDAS"].astype(str) != SYSA_NAME)
            & (~g.index.isin(used_idx))
            & g.geometry.intersects(cl_buf_4326)
        ]
        for idx, prow in candidates.iterrows():
            rows.append({"REACH_NAME": reach_name, "geometry": prow.geometry})
            used_idx.add(idx)
        print(f"      [{reach_name}] {len(candidates)} additional hd1 polygons "
              f"within {CENTERLINE_BUFFER_M} m of {centerline_shp.stem}")

    # Pass 3 — Atmata: nameless hd1 polygons in the Lankupiai-Drevernai bbox.
    atmata_box = box(*ATMATA_BBOX)
    nameless = g["VARDAS"].isna() | (g["VARDAS"].astype(str).str.strip() == "")
    candidates = g[
        (g["GKODAS"] == "hd1")
        & nameless
        & (~g.index.isin(used_idx))
        & g.geometry.intersects(atmata_box)
    ]
    if not candidates.empty:
        for idx, prow in candidates.iterrows():
            rows.append({"REACH_NAME": "Atmata", "geometry": prow.geometry})
            used_idx.add(idx)
        print(f"      [Atmata] {len(candidates)} unnamed hd1 polygons in spatial bbox")
    else:
        print(f"      [Atmata] 0 unnamed hd1 polygons in spatial bbox {ATMATA_BBOX}")

    # Pass 4 — Šyša-clipping: the 74 km² Šyša polygon contains the lower
    # Minija + Atmata + entire delta. Clip it to each target reach's
    # centerline buffer / bbox so the relevant river-segments are
    # captured without dragging in the Šilutė area.
    sysa_polys = g[g["VARDAS"] == SYSA_NAME]
    if not sysa_polys.empty:
        sysa_union = sysa_polys.geometry.union_all()
        for reach_name, centerline_shp, bbox_tuple in SYSA_CLIP_TARGETS:
            if centerline_shp is not None and centerline_shp.exists():
                cl = gpd.read_file(centerline_shp).to_crs(epsg=32634)
                clip_geom_utm = cl.geometry.union_all().buffer(SYSA_CLIP_BUFFER_M)
                clip_geom = gpd.GeoSeries([clip_geom_utm], crs="EPSG:32634").to_crs(4326).iloc[0]
            elif bbox_tuple is not None:
                clip_geom = box(*bbox_tuple)
            else:
                continue
            piece = sysa_union.intersection(clip_geom)
            if piece.is_empty:
                print(f"      [Šyša→{reach_name}] empty intersection — skipping")
                continue
            # piece may be Polygon or MultiPolygon — explode to individual polys.
            if hasattr(piece, "geoms"):
                parts = list(piece.geoms)
            else:
                parts = [piece]
            n_added = 0
            for p in parts:
                if p.is_empty or not p.is_valid:
                    continue
                # filter out vanishingly small slivers (< 200 m²)
                p_area = gpd.GeoSeries([p], crs=4326).to_crs(epsg=32634).iloc[0].area
                if p_area < 200:
                    continue
                rows.append({"REACH_NAME": reach_name, "geometry": p})
                n_added += 1
            print(f"      [Šyša→{reach_name}] {n_added} clipped pieces added")

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
