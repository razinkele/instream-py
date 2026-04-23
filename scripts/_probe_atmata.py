"""Probe OSM for Atmata + audit widths of Minija / Gilija / Sysa / Atmata.

Reads from the already-cached clipped PBFs that generate_baltic_example.py
produced, so this runs fast (no re-fetch).
"""
from __future__ import annotations

from pathlib import Path


import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "modules"))

from create_model_osm import query_waterways  # noqa: E402


BBOX = (20.80, 54.95, 22.20, 55.95)  # same as generator


def main() -> None:
    print("Fetching waterways from Lithuania + Kaliningrad PBFs...")
    ww = query_waterways(("lithuania", "kaliningrad"), BBOX)
    ww_utm = ww.to_crs("EPSG:32634")
    print(f"Total features: {len(ww)}")

    # All unique names
    names = sorted(set(ww["nameText"].unique()) - {""})
    print(f"\nTotal distinct names in bbox: {len(names)}")

    # Hunt for Atmata specifically (ASCII, Lithuanian spelling)
    atmata_hits = ww[ww["nameText"].str.contains("Atmata", case=False, na=False)]
    print(f"\n=== Atmata hits: {len(atmata_hits)} ===")
    if len(atmata_hits):
        print(atmata_hits[["nameText", "DFDD"]].head(20))

    # Hunt for Rusnė / Rusne (delta split point)
    rusne = [n for n in names if "Rusn" in n or "rusn" in n.lower()]
    print(f"\nRusne-related names: {rusne[:10]}")

    # Major delta channel names — candidate hits
    delta_candidates = [n for n in names if any(
        key in n for key in ("Atmata", "Skirv", "Leit", "Gilij", "Šyš",
                              "Матрос", "Русне", "Nida", "Minija")
    )]
    print(f"\nDelta/lower-basin candidates: {sorted(delta_candidates)}")

    # Width audit for the current 4 focal reaches
    print("\n=== Per-reach geometry audit ===")
    targets = {
        "Nemunas": ("Nemunas",),
        "Minija":  ("Minija",),
        "Sysa":    ("Šyša",),
        "Gilija":  ("Матросовка", "Matrosovka", "Gilija"),
        "Atmata":  ("Atmata",),
        "Skirvyte":("Skirvytė",),
        "Leite":   ("Leitė",),
    }
    # Print the geographic extent of each reach's raw OSM features
    # (pre-clip) so we can see how far west/south each river extends.
    print("\n=== Raw OSM extents (pre-clip, WGS84) ===")
    print(f"{'Reach':<10} {'min_lon':>8} {'max_lon':>8} {'min_lat':>8} {'max_lat':>8}")
    print("-" * 50)
    for ascii_name, osm_targets in targets.items():
        hits = ww[ww["nameText"].isin(osm_targets)]
        if len(hits) == 0:
            continue
        all_coords = []
        for g in hits.geometry:
            if g.geom_type == "LineString":
                all_coords.extend(g.coords)
            elif g.geom_type == "MultiLineString":
                for sub in g.geoms:
                    all_coords.extend(sub.coords)
            elif g.geom_type == "Polygon":
                all_coords.extend(g.exterior.coords)
            elif g.geom_type == "MultiPolygon":
                for sub in g.geoms:
                    all_coords.extend(sub.exterior.coords)
        if not all_coords:
            continue
        xs = [c[0] for c in all_coords]
        ys = [c[1] for c in all_coords]
        print(f"{ascii_name:<10} {min(xs):>8.3f} {max(xs):>8.3f} "
              f"{min(ys):>8.3f} {max(ys):>8.3f}")
    print(f"{'Reach':<10} {'n_feat':>6}  {'L(lines km)':>12}  {'A(poly km2)':>12}  {'impl_w(m)':>10}")
    print("-" * 70)
    for ascii_name, osm_targets in targets.items():
        hits = ww_utm[ww_utm["nameText"].isin(osm_targets)]
        if len(hits) == 0:
            print(f"{ascii_name:<10} {'0':>6}  {'--':>12}  {'--':>12}  {'--':>10}  (no OSM match)")
            continue
        # Split lines vs polygons
        lines = hits[hits.geometry.geom_type.isin(["LineString", "MultiLineString"])]
        polys = hits[hits.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        L_km = lines.geometry.length.sum() / 1000.0 if len(lines) else 0.0
        A_km2 = polys.geometry.area.sum() / 1e6 if len(polys) else 0.0
        implied_w = (A_km2 * 1e6 / (L_km * 1000)) if L_km > 0 else None
        impl_str = f"{implied_w:.1f}" if implied_w is not None else "--"
        print(f"{ascii_name:<10} {len(hits):>6}  {L_km:>12.2f}  {A_km2:>12.3f}  {impl_str:>10}")


if __name__ == "__main__":
    main()
