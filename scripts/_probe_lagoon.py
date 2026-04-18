"""Find the Curonian Lagoon in OSM, whatever it's tagged as."""
import sys
from pathlib import Path
from shapely.geometry import Point

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from modules.create_model_osm import query_water_bodies  # noqa: E402

BBOX = (20.80, 54.90, 22.20, 55.95)
wb = query_water_bodies("lithuania", BBOX)
print(f"Total water bodies: {len(wb)}")

# Probe several known lagoon points
seeds = [
    (20.95, 55.00),  # south (Kaliningrad side, might not be in LT PBF)
    (21.00, 55.30),  # center
    (21.05, 55.20),  # what we tried
    (21.15, 55.35),  # north
    (21.20, 55.50),  # northernmost near Klaipeda strait
]
for lon, lat in seeds:
    p = Point(lon, lat)
    hits = wb[wb.geometry.contains(p)]
    if len(hits) == 0:
        dists = wb.geometry.distance(p)
        i = dists.idxmin()
        nrow = wb.loc[i]
        print(f"({lon}, {lat}): NO CONTAINING -> nearest dist={dists.loc[i]:.4f}deg "
              f"name={(nrow.get('nameText') or '')[:30]!r} water={nrow.get('water') or '?'!r} "
              f"{nrow.geometry.geom_type}")
    else:
        for _, row in hits.iterrows():
            wb_utm = wb.to_crs("EPSG:32634")
            area = wb_utm.geometry.loc[row.name].area / 1e6
            print(f"({lon}, {lat}): HIT name={(row.get('nameText') or '')[:30]!r} "
                  f"water={row.get('water') or '?'!r} area={area:.2f} km² "
                  f"{row.geometry.geom_type}")

# Largest by area
print("\n-- top 5 by real area --")
wb_utm = wb.to_crs("EPSG:32634")
wb["area_km2"] = wb_utm.geometry.area / 1e6
top = wb.sort_values("area_km2", ascending=False).head(5)
for _, row in top.iterrows():
    name = (row.get("nameText") or "")[:40]
    print(f"  {name:<40s} water={(row.get('water') or ''):<10s} "
          f"area_km2={row['area_km2']:>10.2f} {row.geometry.geom_type}")
