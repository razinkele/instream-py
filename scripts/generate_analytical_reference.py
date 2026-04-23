"""Generate analytical reference data for validation tests that need no NetLogo."""

import math
import numpy as np
from pathlib import Path

try:
    import salmopy  # noqa: F401
except ImportError as _exc:
    raise SystemExit(
        f"salmopy not importable: {_exc}\n"
        "This script requires salmopy to be installed in the active "
        "environment (e.g. `micromamba run -n shiny python scripts/generate_analytical_reference.py`)."
    )


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

    from salmopy.io.hydraulics_reader import read_depth_table, read_velocity_table

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


def generate_cstepmax_reference():
    """Test 6: CStepMax values for fish under various conditions.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    from salmopy.model import SalmopyModel
    from salmopy.modules.growth import cmax_temp_function, c_stepmax

    CONFIGS = Path(__file__).parent.parent / "configs"
    FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures" / "example_a"
    model = SalmopyModel(CONFIGS / "example_a.yaml", data_dir=FIXTURES)

    # Run 5 steps to get fish into various states
    for _ in range(5):
        model.step()

    ts = model.trout_state
    alive = ts.alive_indices()
    temperature = float(model.reach_state.temperature[0])
    sp = model.species_params[model.species_order[0]]
    cmax_table_x = sp.cmax_temp_table_x.tolist()
    cmax_table_y = sp.cmax_temp_table_y.tolist()
    sp_cfg = model.config.species[model.species_order[0]]

    with open(REF_DIR / "CStepmaxOut.csv", "w") as f:
        f.write(
            "fish_idx,weight,temperature,cmax_temp_func,cmax,step_length,"
            "prev_consumption,cstepmax\n"
        )
        for i in alive[:50]:  # first 50 fish
            weight = float(ts.weight[i])
            prev_cons = float(np.sum(ts.consumption_memory[i]))
            cmax_temp = cmax_temp_function(temperature, cmax_table_x, cmax_table_y)
            cmax_wt = sp_cfg.cmax_A * weight**sp_cfg.cmax_B
            cmax_val = cmax_wt * cmax_temp
            cstep = c_stepmax(cmax_wt, cmax_temp, prev_cons, 1.0)
            f.write(
                "{},{:.6f},{:.4f},{:.6f},{:.6f},{:.2f},{:.6f},{:.6f}\n".format(
                    int(i),
                    weight,
                    temperature,
                    cmax_temp,
                    cmax_val,
                    1.0,
                    prev_cons,
                    cstep,
                )
            )
    print("Generated CStepmaxOut.csv ({} rows)".format(min(len(alive), 50)))


def generate_growth_report_reference():
    """Test 5: Growth report for systematic fish/cell combinations.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    from salmopy.modules.growth import growth_rate_for

    lengths = [5.0, 10.0, 15.0, 20.0, 25.0]
    depths = [10.0, 30.0, 50.0, 100.0]
    velocities = [5.0, 15.0, 30.0]
    activities = [0, 1, 2]
    temperature = 12.0

    # Example A Chinook-Spring params
    weight_A = 0.0041
    weight_B = 3.49
    table_x = [0, 2, 10, 22, 23, 25, 30]
    table_y = [0.05, 0.05, 0.5, 1.0, 0.8, 0.5, 0.0]

    with open(REF_DIR / "GrowthReportOut.csv", "w") as f:
        f.write("activity,length,weight,depth,velocity,temperature,growth_rate\n")
        for act in activities:
            for length in lengths:
                weight = weight_A * length**weight_B
                for depth in depths:
                    for vel in velocities:
                        gr = growth_rate_for(
                            act,
                            length,
                            weight,
                            depth,
                            vel,
                            100.0,
                            0.0,
                            temperature,
                            3.2e-10,
                            8.0e-07,
                            20000.0,
                            10.0,
                            10.0,
                            1000.0,
                            0.3,
                            1,
                            0.0,
                            1.0,
                            0.628,
                            0.7,
                            table_x,
                            table_y,
                            4.0,
                            2.0,
                            5.0,
                            0.1,
                            -0.116,
                            20.0,
                            0.5,
                            -0.2,
                            1.3,
                            0.4,
                            2.8,
                            21.0,
                            1.0,
                            36.0,
                            0.783,
                            1.4,
                            1.0,
                            2500.0,
                            5900.0,
                        )
                        f.write(
                            "{},{:.1f},{:.6f},{:.1f},{:.1f},{:.1f},{:.10f}\n".format(
                                act,
                                length,
                                weight,
                                depth,
                                vel,
                                temperature,
                                gr,
                            )
                        )
    print("Generated GrowthReportOut.csv")


def generate_survival_reference():
    """Test 8: Survival probabilities for systematic conditions.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    from salmopy.modules.survival import (
        survival_high_temperature,
        survival_stranding,
        survival_condition,
        survival_fish_predation,
        survival_terrestrial_predation,
    )

    temperatures = [5.0, 10.0, 15.0, 20.0, 25.0, 28.0]
    depths = [0.0, 10.0, 30.0, 80.0]
    conditions = [0.5, 0.7, 0.85, 0.95, 1.0]
    lengths = [5.0, 10.0, 15.0, 20.0]

    with open(REF_DIR / "survival-test-out.csv", "w") as f:
        f.write(
            "temperature,depth,condition,length,activity,"
            "s_ht,s_str,s_cond,s_fp,s_tp,s_total\n"
        )
        for temp in temperatures:
            for depth in depths:
                for cond in conditions:
                    for length in lengths:
                        for act in [0, 1, 2]:
                            s_ht = survival_high_temperature(temp)
                            s_str = survival_stranding(depth)
                            s_cond = survival_condition(cond)
                            s_fp = survival_fish_predation(
                                length,
                                depth,
                                100.0,
                                0.001,
                                temp,
                                act,
                                0.97,
                                3.0,
                                6.0,
                                35.0,
                                5.0,
                                5.0e-06,
                                -5.0,
                                50.0,
                                -50.0,
                                6.0,
                                2.0,
                                0.5,
                            )
                            s_tp = survival_terrestrial_predation(
                                length,
                                depth,
                                20.0,
                                100.0,
                                50.0,
                                act,
                                10,
                                1,
                                0.94,
                                6.0,
                                3.0,
                                0.0,
                                200.0,
                                20.0,
                                300.0,
                                50.0,
                                -10.0,
                                200.0,
                                -50.0,
                                0.8,
                            )
                            s_total = s_ht * s_str * s_cond * s_fp * s_tp
                            f.write(
                                "{:.1f},{:.1f},{:.2f},{:.1f},{},{:.10f},"
                                "{:.10f},{:.10f},{:.10f},{:.10f},{:.10f}\n".format(
                                    temp,
                                    depth,
                                    cond,
                                    length,
                                    act,
                                    s_ht,
                                    s_str,
                                    s_cond,
                                    s_fp,
                                    s_tp,
                                    s_total,
                                )
                            )
    print("Generated survival-test-out.csv")


def generate_redd_survival_reference():
    """Test 9: Redd egg survival for temperature ranges.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    from salmopy.modules.survival import (
        redd_survival_lo_temp,
        redd_survival_hi_temp,
        redd_survival_dewatering,
        redd_survival_scour,
    )

    temperatures = np.arange(-2.0, 30.0, 1.0)
    depths = [0.0, 5.0, 20.0, 50.0]
    flows = [1.0, 5.0, 10.0, 50.0]

    with open(REF_DIR / "Redd-survive-test-out.csv", "w") as f:
        f.write(
            "temperature,depth,flow,is_peak,s_lo_temp,s_hi_temp,s_dewater,s_scour\n"
        )
        for temp in temperatures:
            for depth in depths:
                for flow in flows:
                    for is_peak in [False, True]:
                        s_lo = redd_survival_lo_temp(float(temp))
                        s_hi = redd_survival_hi_temp(float(temp))
                        s_dw = redd_survival_dewatering(float(depth))
                        s_sc = redd_survival_scour(float(flow), is_peak)
                        f.write(
                            "{:.1f},{:.1f},{:.1f},{},{:.10f},{:.10f},{:.10f},{:.10f}\n".format(
                                temp,
                                depth,
                                flow,
                                int(is_peak),
                                s_lo,
                                s_hi,
                                s_dw,
                                s_sc,
                            )
                        )
    print("Generated Redd-survive-test-out.csv")


def generate_spawn_cell_reference():
    """Test 10: Spawn cell suitability scores.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    from salmopy.modules.spawning import spawn_suitability

    depths = np.arange(0.0, 250.0, 10.0)
    velocities = np.arange(0.0, 200.0, 10.0)
    # Example A Chinook-Spring spawn tables
    depth_xs = np.array([0.0, 12.0, 27.0, 33.5, 204.0])
    depth_ys = np.array([0.0, 0.0, 0.95, 1.0, 0.0])
    vel_xs = np.array([0.0, 2.3, 3.0, 54.0, 61.0, 192.0])
    vel_ys = np.array([0.0, 0.0, 0.06, 1.0, 1.0, 0.0])

    with open(REF_DIR / "Spawn-cell-test-out.csv", "w") as f:
        f.write("depth,velocity,frac_spawn,area,suitability\n")
        for d in depths:
            for v in velocities[:10]:  # limit to keep file small
                suit = spawn_suitability(
                    float(d),
                    float(v),
                    0.5,
                    50000.0,
                    depth_xs,
                    depth_ys,
                    vel_xs,
                    vel_ys,
                )
                f.write("{:.1f},{:.1f},0.5,50000.0,{:.10f}\n".format(d, v, suit))
    print("Generated Spawn-cell-test-out.csv")


def generate_fitness_golden():
    """Test 11: Fitness golden snapshot from first validated Python run.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    from salmopy.model import SalmopyModel

    CONFIGS = Path(__file__).parent.parent / "configs"
    FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures" / "example_a"
    model = SalmopyModel(CONFIGS / "example_a.yaml", data_dir=FIXTURES)
    model.step()
    model.step()

    ts = model.trout_state
    alive = ts.alive_indices()

    with open(REF_DIR / "fitness-golden.csv", "w") as f:
        f.write("fish_idx,cell_idx,activity,length,weight,condition,last_growth_rate\n")
        for i in alive[:100]:
            f.write(
                "{},{},{},{:.6f},{:.6f},{:.6f},{:.10f}\n".format(
                    int(i),
                    int(ts.cell_idx[i]),
                    int(ts.activity[i]),
                    float(ts.length[i]),
                    float(ts.weight[i]),
                    float(ts.condition[i]),
                    float(ts.last_growth_rate[i]),
                )
            )
    print("Generated fitness-golden.csv ({} rows)".format(min(len(alive), 100)))


if __name__ == "__main__":
    generate_day_length()
    generate_cmax_interp()
    generate_gis_reference()
    generate_depth_velocity_reference()
    generate_cstepmax_reference()
    generate_growth_report_reference()
    generate_survival_reference()
    generate_redd_survival_reference()
    generate_spawn_cell_reference()
    generate_fitness_golden()
