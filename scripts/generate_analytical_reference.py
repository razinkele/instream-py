"""Generate analytical reference data for validation tests that need no NetLogo."""

import math
import numpy as np
from pathlib import Path

REF_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "reference"
REF_DIR.mkdir(parents=True, exist_ok=True)


def generate_day_length():
    """Test 4: Day length using the SAME solar-declination algorithm as NumpyBackend.compute_light()."""
    rows = []
    for lat in range(0, 91, 10):
        for jd in range(1, 366):
            decl = 23.45 * math.sin(math.radians((284 + jd) * 360.0 / 365.0))
            decl_rad = math.radians(decl)
            lat_rad = math.radians(lat)
            cos_ha = -math.tan(lat_rad) * math.tan(decl_rad)
            cos_ha = max(-1.0, min(1.0, cos_ha))
            hour_angle = math.degrees(math.acos(cos_ha))
            day_length = 2.0 * hour_angle / 360.0
            denom = math.cos(lat_rad) * math.cos(decl_rad)
            if abs(denom) < 1e-15:
                twilight_length = 0.0
            else:
                cos_tw = (
                    -math.sin(math.radians(6.0))
                    - math.sin(lat_rad) * math.sin(decl_rad)
                ) / denom
                cos_tw = max(-1.0, min(1.0, cos_tw))
                tw_ha = math.degrees(math.acos(cos_tw))
                twilight_length = max(0.0, (tw_ha - hour_angle) / 360.0)
            rows.append((lat, jd, day_length, twilight_length))
    with open(REF_DIR / "test-day-length.csv", "w") as f:
        f.write("latitude,julian_day,day_length,twilight_length\n")
        for r in rows:
            f.write("{},{},{:.10f},{:.10f}\n".format(*r))
    print("Generated test-day-length.csv ({} rows)".format(len(rows)))


def generate_cmax_interp():
    """Test 7: CMax temperature interpolation."""
    table = {0: 0.05, 2: 0.05, 10: 0.5, 22: 1.0, 23: 0.8, 25: 0.5, 30: 0.0}
    xs = sorted(table.keys())
    ys = [table[k] for k in xs]
    rows = []
    for t_int in range(0, 102, 2):
        t = float(t_int)
        val = float(np.interp(t, xs, ys))
        rows.append((t, val))
    with open(REF_DIR / "CMaxTempFunctTestOut.csv", "w") as f:
        f.write("temperature,cmax_temp_function\n")
        for r in rows:
            f.write("{:.1f},{:.10f}\n".format(*r))
    print("Generated CMaxTempFunctTestOut.csv ({} rows)".format(len(rows)))


def generate_gis_reference():
    """Test 1: Cell variables from shapefile."""
    import geopandas as gpd

    shp = (
        Path(__file__).parent.parent
        / "tests"
        / "fixtures"
        / "example_a"
        / "Shapefile"
        / "ExampleA.shp"
    )
    gdf = gpd.read_file(shp)
    with open(REF_DIR / "Test-GIS-contents.csv", "w") as f:
        f.write(
            "cell_id,reach_name,area_m2,dist_escape,num_hiding,frac_shelter,frac_spawn\n"
        )
        for _, row in gdf.iterrows():
            f.write(
                "{},{},{:.6f},{:.6f},{},{:.6f},{:.6f}\n".format(
                    row["ID_TEXT"],
                    row["REACH_NAME"],
                    row["AREA"],
                    row["M_TO_ESC"],
                    int(row["NUM_HIDING"]),
                    row["FRACVSHL"],
                    row["FRACSPWN"],
                )
            )
    print("Generated Test-GIS-contents.csv ({} rows)".format(len(gdf)))


def generate_depth_velocity_reference():
    """Tests 2-3: Cell depths and velocities at various flows."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from instream.io.hydraulics_reader import read_depth_table, read_velocity_table

    data_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "example_a"
    d_flows, d_vals = read_depth_table(data_dir / "ExampleA-Depths.csv")
    v_flows, v_vals = read_velocity_table(data_dir / "ExampleA-Vels.csv")
    n_cells = d_vals.shape[0]
    test_cells = np.linspace(0, n_cells - 1, min(10, n_cells), dtype=int)
    test_flows = np.geomspace(max(d_flows[0], 0.1), d_flows[-1], 20)
    # Round flows to 4 decimals so CSV round-trip is exact
    test_flows = np.round(test_flows, 4)
    with open(REF_DIR / "cell-depth-test-out.csv", "w") as f:
        f.write("cell_index,flow,depth_m\n")
        for ci in test_cells:
            for flow in test_flows:
                depth = max(0.0, float(np.interp(flow, d_flows, d_vals[ci])))
                f.write("{},{:.4f},{:.8f}\n".format(ci, flow, depth))
    with open(REF_DIR / "cell-vel-test-out.csv", "w") as f:
        f.write("cell_index,flow,velocity_ms\n")
        for ci in test_cells:
            for flow in test_flows:
                depth = float(np.interp(flow, d_flows, d_vals[ci]))
                vel = float(np.interp(flow, v_flows, v_vals[ci]))
                if depth <= 0:
                    vel = 0.0
                f.write("{},{:.4f},{:.8f}\n".format(ci, flow, max(0.0, vel)))
    print("Generated depth/velocity reference CSVs")


if __name__ == "__main__":
    generate_day_length()
    generate_cmax_interp()
    generate_gis_reference()
    generate_depth_velocity_reference()
