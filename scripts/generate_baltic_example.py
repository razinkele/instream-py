"""Generate Baltic example: tributaries → meandering delta → Lagoon → Coastal Sea.

Spatial layout (schematic, north is up):

    COASTAL SEA (12×6 = 72 cells, 250m × 250m)
    ┌──────────────────────────────────────────────────────────────────────┐
    │                    Open nearshore marine waters                      │
    └──────────────────────────────┬───────────────────────────────────────┘
                                   │
    LAGOON (12×8 = 96 cells, 100m × 100m)
    ┌──────────────────────────────┴──────────────────────────────────┐
    │             Brackish transition (Curonian-lagoon-like)           │
    └─────┬──────────────────────┬───────────────────────┬────────────┘
          │                      │                       │
    ╔═════╧═══════╗    ╔═════════╧══════════╗    ╔═══════╧══════════╗
    ║  WestDelta  ║    ║   CentralDelta     ║    ║   EastDelta      ║
    ║  3×15 = 45  ║    ║   3×18 = 54        ║    ║   3×16 = 48      ║
    ║  meanders W ║    ║   main outflow     ║    ║   meanders E     ║
    ║  reed beds  ║    ║   deepest delta    ║    ║   shallow, warm  ║
    ╚═════╤═══════╝    ╚═════════╤══════════╝    ╚═══════╤══════════╝
          │                      │                       │
    ┌─────┴───────┐    ┌─────────┴──────────┐    ┌───────┴──────────┐
    │  WestTrib   │    │    MainStem        │    │   EastTrib       │
    │  3×20 = 60  │    │    4×30 = 120      │    │   3×25 = 75      │
    │  cold, steep│    │    main channel    │    │   warm, slow     │
    │  spawning   │    │    deep, wide      │    │   rearing        │
    └─────────────┘    └────────────────────┘    └──────────────────┘

    Total: 570 cells, ~5000 initial fish
    Marine zones: Estuary → Coastal → Baltic Proper (abstract)
    Delta channels meander with sinusoidal x-offsets.

CRS: EPSG:3035 (ETRS89/LAEA Europe)
"""

import math
from datetime import datetime, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import box, Polygon
from shapely.affinity import translate

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "example_baltic"
SHP_DIR = OUT / "Shapefile"
REACHES = {}


def _river_cells(reach_name, cols, rows, cell_w, cell_h, x_center, y_bottom,
                 frac_spawn_upper, hiding_base):
    """Generate straight rectangular river-reach cells."""
    cells = []
    x0_base = x_center - (cols * cell_w) / 2
    for row in range(rows):
        for col in range(cols):
            x0 = x0_base + col * cell_w
            y0 = y_bottom + row * cell_h
            dist_from_mouth = (rows - row) * cell_h
            is_edge = col == 0 or col == cols - 1
            cells.append({
                "geometry": box(x0, y0, x0 + cell_w, y0 + cell_h),
                "REACH_NAME": reach_name,
                "AREA": cell_w * cell_h,
                "M_TO_ESC": 60 + dist_from_mouth * 0.8,
                "NUM_HIDING": (hiding_base if is_edge else max(1, hiding_base - 2)),
                "FRACVSHL": (0.35 if is_edge else 0.15),
                "FRACSPWN": frac_spawn_upper if row >= rows * 0.4 else 0.05,
            })
    return cells


def _delta_cells(reach_name, cols, rows, cell_w, cell_h,
                 x_center, y_bottom, meander_amp, meander_freq,
                 hiding_base, frac_spawn):
    """Generate meandering delta channel cells.

    Cells follow a sinusoidal path: x_offset = meander_amp * sin(2π * row / meander_freq)
    Each row of cells is shifted horizontally to create the meander.
    """
    cells = []
    for row in range(rows):
        # Sinusoidal meander offset
        x_offset = meander_amp * math.sin(2 * math.pi * row / meander_freq)
        x0_base = x_center - (cols * cell_w) / 2 + x_offset
        y0 = y_bottom + row * cell_h
        for col in range(cols):
            x0 = x0_base + col * cell_w
            is_edge = col == 0 or col == cols - 1
            # Delta channels: moderate shelter from reed beds at edges
            cells.append({
                "geometry": box(x0, y0, x0 + cell_w, y0 + cell_h),
                "REACH_NAME": reach_name,
                "AREA": cell_w * cell_h,
                "M_TO_ESC": 30 + (rows - row) * cell_h * 0.5,
                "NUM_HIDING": (hiding_base + 1 if is_edge else hiding_base),
                "FRACVSHL": (0.20 if is_edge else 0.08),
                "FRACSPWN": frac_spawn,
            })
    return cells


def generate_shapefile():
    """Build the full multi-reach polygon grid with meandering delta."""
    all_cells = []

    # ── River reaches ──
    main_rows, main_h = 30, 20.0
    main_y0 = 0.0
    all_cells.extend(_river_cells(
        "MainStem", 4, main_rows, 18.0, main_h, x_center=0, y_bottom=main_y0,
        frac_spawn_upper=0.30, hiding_base=4,
    ))
    all_cells.extend(_river_cells(
        "WestTrib", 3, 20, 12.0, 18.0, x_center=-250, y_bottom=200,
        frac_spawn_upper=0.55, hiding_base=5,
    ))
    all_cells.extend(_river_cells(
        "EastTrib", 3, 25, 14.0, 20.0, x_center=270, y_bottom=100,
        frac_spawn_upper=0.20, hiding_base=3,
    ))

    # ── Delta channels (between river mouths and lagoon) ──
    # Start just above the top of the tallest river (MainStem)
    delta_y0 = main_y0 + main_rows * main_h + 15  # 15m gap

    # CentralDelta: continues from MainStem, gentle meander
    all_cells.extend(_delta_cells(
        "CentralDelta", 3, 18, 16.0, 18.0,
        x_center=0, y_bottom=delta_y0,
        meander_amp=25, meander_freq=12,  # gentle S-curve
        hiding_base=2, frac_spawn=0.05,
    ))
    # WestDelta: branches west, strong meander
    all_cells.extend(_delta_cells(
        "WestDelta", 3, 15, 14.0, 16.0,
        x_center=-180, y_bottom=delta_y0 + 30,
        meander_amp=45, meander_freq=10,  # pronounced meander
        hiding_base=3, frac_spawn=0.02,   # reed beds = more hiding
    ))
    # EastDelta: branches east, moderate meander
    all_cells.extend(_delta_cells(
        "EastDelta", 3, 16, 15.0, 17.0,
        x_center=200, y_bottom=delta_y0 + 15,
        meander_amp=35, meander_freq=11,
        hiding_base=2, frac_spawn=0.03,
    ))

    # ── Lagoon ──
    delta_top = delta_y0 + 18 * 18.0 + 30  # above tallest delta + gap
    lagoon_y0 = delta_top
    for row in range(8):
        for col in range(12):
            x0 = -600 + col * 100
            y0 = lagoon_y0 + row * 100
            is_shore = row == 0 or row == 7 or col == 0 or col == 11
            all_cells.append({
                "geometry": box(x0, y0, x0 + 100, y0 + 100),
                "REACH_NAME": "Lagoon",
                "AREA": 100 * 100,
                "M_TO_ESC": 25 + row * 8,
                "NUM_HIDING": (2 if is_shore else 0),
                "FRACVSHL": (0.06 if is_shore else 0.01),
                "FRACSPWN": 0.0,
            })

    # ── Coastal Sea: 25 cols × 12 rows = 300 cells, 400m × 400m ──
    # Represents ~48 km² of nearshore Baltic marine habitat
    coast_w, coast_h = 400.0, 400.0
    coast_cols, coast_rows = 25, 12
    coast_y0 = lagoon_y0 + 8 * 100 + 80
    for row in range(coast_rows):
        for col in range(coast_cols):
            x0 = -(coast_cols * coast_w) / 2 + col * coast_w
            y0 = coast_y0 + row * coast_h
            all_cells.append({
                "geometry": box(x0, y0, x0 + coast_w, y0 + coast_h),
                "REACH_NAME": "CoastalSea",
                "AREA": coast_w * coast_h,
                "M_TO_ESC": 150 + row * 20,
                "NUM_HIDING": 0,
                "FRACVSHL": 0.0,
                "FRACSPWN": 0.0,
            })

    # ── Assign cell IDs ──
    for i, cell in enumerate(all_cells):
        cell["ID_TEXT"] = f"CELL_{i + 1:04d}"

    gdf = gpd.GeoDataFrame(all_cells, crs="EPSG:3035")
    SHP_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(SHP_DIR / "BalticExample.shp")

    for rname in gdf["REACH_NAME"].unique():
        REACHES[rname] = int((gdf["REACH_NAME"] == rname).sum())
    total = len(gdf)
    print(f"  Shapefile: {total} cells")
    for rname, n in REACHES.items():
        print(f"    {rname:15s}: {n:4d} cells")
    return gdf


# ---------------------------------------------------------------------------
# Reach hydraulic/environmental parameters
# ---------------------------------------------------------------------------

REACH_PARAMS = {
    "MainStem": {
        "temp_mean": 8.5, "temp_amp": 8.5, "flow_base": 6.0, "turb_base": 2,
        "flows": [1.0, 2.0, 4.0, 6.0, 9.0, 14.0, 22.0, 40.0, 100.0, 500.0],
        "depth_base": 0.45, "depth_flood": 3.0,
        "vel_base": 0.30, "vel_flood": 1.5,
    },
    "WestTrib": {
        "temp_mean": 6.5, "temp_amp": 6.5, "flow_base": 2.0, "turb_base": 1,
        "flows": [0.3, 0.7, 1.2, 2.0, 3.5, 5.0, 8.0, 15.0, 40.0, 200.0],
        "depth_base": 0.25, "depth_flood": 1.8,
        "vel_base": 0.45, "vel_flood": 2.0,
    },
    "EastTrib": {
        "temp_mean": 9.5, "temp_amp": 8.0, "flow_base": 3.0, "turb_base": 3,
        "flows": [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 25.0, 60.0, 300.0],
        "depth_base": 0.35, "depth_flood": 2.5,
        "vel_base": 0.15, "vel_flood": 1.0,
    },
    "CentralDelta": {
        "temp_mean": 9.0, "temp_amp": 9.0, "flow_base": 4.5, "turb_base": 3,
        # Wider, slower than MainStem — flow spreads into delta
        "flows": [0.8, 1.5, 3.0, 4.5, 7.0, 10.0, 16.0, 30.0, 70.0, 350.0],
        "depth_base": 0.50, "depth_flood": 2.5,
        "vel_base": 0.12, "vel_flood": 0.8,
    },
    "WestDelta": {
        "temp_mean": 9.5, "temp_amp": 9.5, "flow_base": 2.5, "turb_base": 4,
        # Shallow, slow, reed-choked channel
        "flows": [0.5, 1.0, 1.8, 2.5, 4.0, 6.0, 10.0, 18.0, 45.0, 200.0],
        "depth_base": 0.35, "depth_flood": 1.8,
        "vel_base": 0.08, "vel_flood": 0.5,
    },
    "EastDelta": {
        "temp_mean": 10.0, "temp_amp": 9.5, "flow_base": 3.0, "turb_base": 4,
        # Moderate depth, warm, turbid
        "flows": [0.6, 1.2, 2.0, 3.0, 5.0, 7.0, 12.0, 22.0, 55.0, 250.0],
        "depth_base": 0.40, "depth_flood": 2.0,
        "vel_base": 0.10, "vel_flood": 0.6,
    },
    "Lagoon": {
        "temp_mean": 10.0, "temp_amp": 10.0, "flow_base": 15.0, "turb_base": 5,
        "flows": [5.0, 8.0, 12.0, 15.0, 22.0, 30.0, 45.0, 80.0, 150.0, 600.0],
        "depth_base": 2.0, "depth_flood": 4.0,
        "vel_base": 0.03, "vel_flood": 0.15,
    },
    "CoastalSea": {
        "temp_mean": 8.0, "temp_amp": 7.0, "flow_base": 40.0, "turb_base": 2,
        "flows": [10.0, 20.0, 30.0, 40.0, 60.0, 90.0, 130.0, 200.0, 400.0, 1000.0],
        "depth_base": 4.0, "depth_flood": 8.0,
        "vel_base": 0.01, "vel_flood": 0.08,
    },
}


def generate_time_series(reach_name):
    """Generate 27-year daily time series (2011-04-01 to 2038-03-31)."""
    start = datetime(2011, 4, 1)
    end = datetime(2038, 3, 31)
    path = OUT / f"{reach_name}-TimeSeriesInputs.csv"
    p = REACH_PARAMS[reach_name]
    rng = np.random.default_rng(42 + abs(hash(reach_name)) % 10000)

    with open(path, "w", newline="") as f:
        f.write(f"; Time series for Baltic example — {reach_name}\n")
        f.write("; Synthetic daily data (NOT REAL)\n")
        f.write("Date,temperature,flow,turbidity\n")
        d = start
        while d <= end:
            doy = d.timetuple().tm_yday
            temp = p["temp_mean"] + p["temp_amp"] * math.sin(
                2 * math.pi * (doy - 100) / 365
            )
            temp = max(0.5, temp + rng.normal(0, 0.5))
            spring = 3.0 * math.exp(-((doy - 115) ** 2) / 600)
            autumn = 1.0 * math.exp(-((doy - 290) ** 2) / 400)
            flow = p["flow_base"] * (1 + spring + autumn + 0.15 * rng.standard_normal())
            flow = max(0.3, flow)
            turb = max(0, p["turb_base"] + rng.integers(-1, 3))
            f.write(f"{d.month}/{d.day}/{d.year} 12:00,{temp:.1f},{flow:.2f},{turb}\n")
            d += timedelta(days=1)

    print(f"  TimeSeries: {reach_name}")


def generate_hydraulics(reach_name, n_cells):
    """Generate realistic depth and velocity lookup tables."""
    p = REACH_PARAMS[reach_name]
    flows = p["flows"]
    n_flows = len(flows)
    rng = np.random.default_rng(777 + abs(hash(reach_name)) % 10000)

    f_frac = np.array([(math.log(fl) - math.log(flows[0]))
                       / (math.log(flows[-1]) - math.log(flows[0]))
                       for fl in flows])

    for kind, base_key, flood_key, unit in [
        ("Depths", "depth_base", "depth_flood", "METERS"),
        ("Vels", "vel_base", "vel_flood", "M/S"),
    ]:
        fpath = OUT / f"{reach_name}-{kind}.csv"
        v_base = p[base_key]
        v_flood = p[flood_key]
        with open(fpath, "w", newline="") as f:
            f.write(f"; {kind} for Baltic example — {reach_name}\n")
            f.write("; Synthetic hydraulic data (NOT REAL)\n")
            f.write(f"; CELL {kind.upper()} IN {unit}\n")
            f.write(f"{n_flows},Number of flows in table"
                    + ",," * (n_flows - 1) + "\n")
            f.write("," + ",".join(f"{fl}" for fl in flows) + "\n")
            for c in range(1, n_cells + 1):
                cell_var = 0.7 + 0.6 * rng.random()
                vals = []
                for fi in range(n_flows):
                    v = cell_var * (v_base + (v_flood - v_base) * f_frac[fi])
                    vals.append(f"{max(0.001, v):.6f}")
                f.write(f"{c}," + ",".join(vals) + "\n")

    print(f"  Hydraulics: {reach_name} ({n_cells} cells)")


def generate_populations():
    """Generate initial populations and adult arrivals for all river reaches."""
    pop_path = OUT / "BalticExample-InitialPopulations.csv"
    with open(pop_path, "w", newline="") as f:
        f.write("; Trout initialization for Baltic example\n")
        f.write("; Baltic Atlantic salmon across river + delta reaches\n")
        f.write("; Species,Reach,Age,Number,Length min,Length mode,Length max\n")
        # River reaches
        f.write("BalticAtlanticSalmon,MainStem,0,1200,3,4.5,6\n")
        f.write("BalticAtlanticSalmon,MainStem,1,500,7,10,13\n")
        f.write("BalticAtlanticSalmon,MainStem,2,120,12,15,20\n")
        f.write("BalticAtlanticSalmon,WestTrib,0,600,3,4.2,5.5\n")
        f.write("BalticAtlanticSalmon,WestTrib,1,250,7,9.5,12\n")
        f.write("BalticAtlanticSalmon,WestTrib,2,60,12,14,18\n")
        f.write("BalticAtlanticSalmon,EastTrib,0,800,3.5,5,6.5\n")
        f.write("BalticAtlanticSalmon,EastTrib,1,350,8,11,14\n")
        f.write("BalticAtlanticSalmon,EastTrib,2,80,13,16,21\n")
        # Delta channels — smaller rearing populations
        f.write("BalticAtlanticSalmon,CentralDelta,0,300,3.5,5,6.5\n")
        f.write("BalticAtlanticSalmon,CentralDelta,1,100,8,10,13\n")
        f.write("BalticAtlanticSalmon,WestDelta,0,200,3,4.5,6\n")
        f.write("BalticAtlanticSalmon,WestDelta,1,80,7,9,12\n")
        f.write("BalticAtlanticSalmon,EastDelta,0,250,3.5,5,6.5\n")
        f.write("BalticAtlanticSalmon,EastDelta,1,90,8,10,13\n")
    total = 1200+500+120+600+250+60+800+350+80+300+100+200+80+250+90
    print(f"  Populations: {pop_path.name} ({total} fish total)")

    arr_path = OUT / "BalticExample-AdultArrivals.csv"
    with open(arr_path, "w", newline="") as f:
        f.write("; Adult arrivals for Baltic example\n")
        f.write("; Baltic Atlantic salmon returning to natal reaches\n")
        f.write("; Year,Species,Reach,Number,Fraction female,"
                "Arrival start,Arrival peak,Arrival end,"
                "Length min,Length mode,Length max\n")
        for year in range(2011, 2039):
            f.write(f"{year},BalticAtlanticSalmon,MainStem,150,0.55,"
                    f"5/15/{year},7/1/{year},8/31/{year},55,70,90\n")
            f.write(f"{year},BalticAtlanticSalmon,WestTrib,100,0.60,"
                    f"6/1/{year},7/15/{year},9/15/{year},50,65,85\n")
            f.write(f"{year},BalticAtlanticSalmon,EastTrib,120,0.50,"
                    f"5/20/{year},7/5/{year},9/1/{year},55,68,88\n")
            # Some adults use delta channels for holding/spawning
            f.write(f"{year},BalticAtlanticSalmon,CentralDelta,40,0.55,"
                    f"6/1/{year},7/15/{year},9/1/{year},55,68,85\n")
            f.write(f"{year},BalticAtlanticSalmon,WestDelta,25,0.60,"
                    f"6/15/{year},8/1/{year},9/15/{year},50,62,80\n")
            f.write(f"{year},BalticAtlanticSalmon,EastDelta,30,0.50,"
                    f"6/10/{year},7/20/{year},9/10/{year},52,65,82\n")
    print(f"  Arrivals: {arr_path.name} (465 adults/year across 6 reaches)")


def main():
    print("Generating Baltic example (tributaries → delta → lagoon → coast)...")
    print()
    OUT.mkdir(parents=True, exist_ok=True)

    gdf = generate_shapefile()
    print()

    for reach_name, n_cells in REACHES.items():
        generate_time_series(reach_name)
        generate_hydraulics(reach_name, n_cells)

    print()
    generate_populations()

    total = sum(REACHES.values())
    print(f"\nDone! {total} cells across {len(REACHES)} reaches → {OUT}")


if __name__ == "__main__":
    main()
