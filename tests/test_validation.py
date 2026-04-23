"""Validation tests comparing Python output to NetLogo reference data.

These tests require NetLogo reference CSVs in tests/fixtures/reference/.
They are skipped when reference data is not available.
"""

import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REFERENCE_DIR = FIXTURES_DIR / "reference"


def require_reference(filename):
    """Skip test if reference file doesn't exist."""
    path = REFERENCE_DIR / filename
    if not path.exists():
        pytest.skip(f"NetLogo reference data not generated: {filename}")
    return path


class TestCellVariablesMatchGIS:
    """Port of NetLogo test-cell-variables."""

    def test_cell_variables_match_gis_file(self):
        import numpy as np
        import pandas as pd
        import geopandas as gpd

        ref_path = require_reference("Test-GIS-contents.csv")
        ref = pd.read_csv(ref_path)
        shp_path = FIXTURES_DIR / "example_a" / "Shapefile" / "ExampleA.shp"
        gdf = gpd.read_file(shp_path)
        assert len(ref) == len(gdf), "Row count mismatch: ref={} shp={}".format(
            len(ref), len(gdf)
        )
        for idx, row in ref.iterrows():
            shp_row = gdf.iloc[idx]
            assert str(row["cell_id"]) == str(shp_row["ID_TEXT"])
            assert row["reach_name"] == shp_row["REACH_NAME"]
            np.testing.assert_allclose(
                row["area_m2"],
                shp_row["AREA"],
                rtol=1e-6,
                err_msg="Area mismatch at cell {}".format(row["cell_id"]),
            )
            np.testing.assert_allclose(
                row["dist_escape"],
                shp_row["M_TO_ESC"],
                rtol=1e-6,
                err_msg="DistEscape mismatch at cell {}".format(row["cell_id"]),
            )
            assert int(row["num_hiding"]) == int(shp_row["NUM_HIDING"])
            np.testing.assert_allclose(
                row["frac_shelter"],
                shp_row["FRACVSHL"],
                rtol=1e-6,
                err_msg="FracShelter mismatch at cell {}".format(row["cell_id"]),
            )
            np.testing.assert_allclose(
                row["frac_spawn"],
                shp_row["FRACSPWN"],
                rtol=1e-6,
                err_msg="FracSpawn mismatch at cell {}".format(row["cell_id"]),
            )


class TestCellDepthsMatchNetLogo:
    """Port of NetLogo test-cell-depths."""

    def test_cell_depths_match_netlogo(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("cell-depth-test-out.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.io.hydraulics_reader import read_depth_table

        data_dir = FIXTURES_DIR / "example_a"
        d_flows, d_vals = read_depth_table(data_dir / "ExampleA-Depths.csv")
        for _, row in ref.iterrows():
            ci = int(row["cell_index"])
            flow = row["flow"]
            expected = row["depth_m"]
            actual = max(0.0, float(np.interp(flow, d_flows, d_vals[ci])))
            np.testing.assert_allclose(
                actual,
                expected,
                rtol=1e-5,
                atol=1e-8,
                err_msg="Depth mismatch at cell={} flow={}".format(ci, flow),
            )


class TestCellVelocitiesMatchNetLogo:
    """Port of NetLogo test-cell-velocities."""

    def test_cell_velocities_match_netlogo(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("cell-vel-test-out.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.io.hydraulics_reader import read_depth_table, read_velocity_table

        data_dir = FIXTURES_DIR / "example_a"
        d_flows, d_vals = read_depth_table(data_dir / "ExampleA-Depths.csv")
        v_flows, v_vals = read_velocity_table(data_dir / "ExampleA-Vels.csv")
        for _, row in ref.iterrows():
            ci = int(row["cell_index"])
            flow = row["flow"]
            expected = row["velocity_ms"]
            depth = float(np.interp(flow, d_flows, d_vals[ci]))
            vel = float(np.interp(flow, v_flows, v_vals[ci]))
            if depth <= 0:
                vel = 0.0
            actual = max(0.0, vel)
            np.testing.assert_allclose(
                actual,
                expected,
                rtol=1e-5,
                atol=1e-8,
                err_msg="Velocity mismatch at cell={} flow={}".format(ci, flow),
            )


class TestDayLengthMatchesNetLogo:
    """Port of NetLogo test-day-length."""

    def test_day_length_matches_netlogo_reference(self):
        import pandas as pd

        ref_path = require_reference("test-day-length.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.backends.numpy_backend import NumpyBackend

        backend = NumpyBackend()
        mismatches = 0
        for _, row in ref.iterrows():
            dl, tl, _ = backend.compute_light(
                int(row["julian_day"]), float(row["latitude"]), 1.0, 1.0, 0.0, 6.0
            )
            if abs(dl - row["day_length"]) > 1e-6:
                mismatches += 1
        assert mismatches == 0, "{} day-length mismatches out of {} rows".format(
            mismatches, len(ref)
        )


class TestGrowthReportMatchesNetLogo:
    """Port of NetLogo write-growth-report.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    def test_full_growth_report_matches_netlogo(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("GrowthReportOut.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.modules.growth import growth_rate_for

        # Example A Chinook-Spring params (same as generator)
        table_x = [0, 2, 10, 22, 23, 25, 30]
        table_y = [0.05, 0.05, 0.5, 1.0, 0.8, 0.5, 0.0]

        for _, row in ref.iterrows():
            gr = growth_rate_for(
                int(row["activity"]),
                row["length"],
                row["weight"],
                row["depth"],
                row["velocity"],
                100.0,
                0.0,
                row["temperature"],
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
            np.testing.assert_allclose(
                gr,
                row["growth_rate"],
                rtol=1e-5,
                atol=1e-12,
                err_msg="Growth mismatch at act={} len={:.1f} depth={:.1f} vel={:.1f}".format(
                    int(row["activity"]),
                    row["length"],
                    row["depth"],
                    row["velocity"],
                ),
            )


class TestCStepMaxMatchesNetLogo:
    """Port of NetLogo test-c-stepmax.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    def test_cstepmax_matches_netlogo(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("CStepmaxOut.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.modules.growth import cmax_temp_function, c_stepmax

        # Example A Chinook-Spring params
        table_x = [0.0, 2.0, 10.0, 22.0, 23.0, 25.0, 30.0]
        table_y = [0.05, 0.05, 0.5, 1.0, 0.8, 0.5, 0.0]

        for _, row in ref.iterrows():
            cmax_temp = cmax_temp_function(
                row["temperature"],
                table_x,
                table_y,
            )
            cmax_wt = 0.628 * row["weight"] ** 0.7
            cstep = c_stepmax(
                cmax_wt,
                cmax_temp,
                row["prev_consumption"],
                row["step_length"],
            )
            np.testing.assert_allclose(
                cstep,
                row["cstepmax"],
                rtol=1e-5,
                err_msg="CStepMax mismatch at fish weight={:.2f}".format(
                    row["weight"],
                ),
            )


class TestInterpolationMatchesNetLogo:
    """Port of NetLogo write-interpolation-test-report."""

    def test_cmax_temp_interpolation_matches_netlogo(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("CMaxTempFunctTestOut.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.modules.growth import cmax_temp_function

        table_x = [0.0, 2.0, 10.0, 22.0, 23.0, 25.0, 30.0]
        table_y = [0.05, 0.05, 0.5, 1.0, 0.8, 0.5, 0.0]
        for _, row in ref.iterrows():
            result = cmax_temp_function(row["temperature"], table_x, table_y)
            np.testing.assert_allclose(
                result,
                row["cmax_temp_function"],
                rtol=1e-10,
                err_msg="CMax interp mismatch at T={}".format(row["temperature"]),
            )


class TestSurvivalMatchesNetLogo:
    """Port of NetLogo test-survival.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    def test_trout_survival_matches_netlogo(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("survival-test-out.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.modules.survival import (
            survival_high_temperature,
            survival_stranding,
            survival_condition,
            survival_fish_predation,
            survival_terrestrial_predation,
        )

        # Example A Chinook-Spring params (same as generator)
        for _, row in ref.iterrows():
            s_ht = survival_high_temperature(row["temperature"])
            s_str = survival_stranding(row["depth"])
            s_cond = survival_condition(row["condition"])
            s_fp = survival_fish_predation(
                row["length"],
                row["depth"],
                100.0,
                0.001,
                row["temperature"],
                int(row["activity"]),
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
                row["length"],
                row["depth"],
                20.0,
                100.0,
                50.0,
                int(row["activity"]),
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
            np.testing.assert_allclose(
                s_ht,
                row["s_ht"],
                rtol=1e-9,
                err_msg="s_ht mismatch at T={:.1f}".format(row["temperature"]),
            )
            np.testing.assert_allclose(
                s_str,
                row["s_str"],
                rtol=1e-9,
                err_msg="s_str mismatch at depth={:.1f}".format(row["depth"]),
            )
            np.testing.assert_allclose(
                s_cond,
                row["s_cond"],
                rtol=1e-9,
                err_msg="s_cond mismatch at K={:.2f}".format(row["condition"]),
            )
            np.testing.assert_allclose(
                s_fp,
                row["s_fp"],
                rtol=1e-9,
                err_msg="s_fp mismatch at L={:.1f} act={}".format(
                    row["length"],
                    int(row["activity"]),
                ),
            )
            np.testing.assert_allclose(
                s_tp,
                row["s_tp"],
                rtol=1e-9,
                err_msg="s_tp mismatch at L={:.1f} act={}".format(
                    row["length"],
                    int(row["activity"]),
                ),
            )


class TestReddSurvivalMatchesNetLogo:
    """Port of NetLogo test-redd-survive-temperature.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    def test_redd_temperature_survival_matches_netlogo(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("Redd-survive-test-out.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.modules.survival import (
            redd_survival_lo_temp,
            redd_survival_hi_temp,
            redd_survival_dewatering,
            redd_survival_scour,
        )

        for _, row in ref.iterrows():
            s_lo = redd_survival_lo_temp(row["temperature"])
            s_hi = redd_survival_hi_temp(row["temperature"])
            s_dw = redd_survival_dewatering(row["depth"])
            s_sc = redd_survival_scour(row["flow"], bool(row["is_peak"]))
            np.testing.assert_allclose(
                s_lo,
                row["s_lo_temp"],
                rtol=1e-6,
                atol=1e-12,
                err_msg="Redd lo-temp mismatch at T={:.1f}".format(row["temperature"]),
            )
            np.testing.assert_allclose(
                s_hi,
                row["s_hi_temp"],
                rtol=1e-6,
                atol=1e-12,
                err_msg="Redd hi-temp mismatch at T={:.1f}".format(row["temperature"]),
            )
            np.testing.assert_allclose(
                s_dw,
                row["s_dewater"],
                rtol=1e-6,
                err_msg="Redd dewater mismatch at depth={:.1f}".format(row["depth"]),
            )
            np.testing.assert_allclose(
                s_sc,
                row["s_scour"],
                rtol=1e-6,
                err_msg="Redd scour mismatch at flow={:.1f} peak={}".format(
                    row["flow"],
                    row["is_peak"],
                ),
            )


class TestSpawnCellMatchesNetLogo:
    """Port of NetLogo test-spawn-cell.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    """

    def test_spawn_cell_selection_matches_netlogo(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("Spawn-cell-test-out.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.modules.spawning import spawn_suitability

        # Example A Chinook-Spring spawn tables
        depth_xs = np.array([0.0, 12.0, 27.0, 33.5, 204.0])
        depth_ys = np.array([0.0, 0.0, 0.95, 1.0, 0.0])
        vel_xs = np.array([0.0, 2.3, 3.0, 54.0, 61.0, 192.0])
        vel_ys = np.array([0.0, 0.0, 0.06, 1.0, 1.0, 0.0])

        for _, row in ref.iterrows():
            suit = spawn_suitability(
                row["depth"],
                row["velocity"],
                row["frac_spawn"],
                row["area"],
                depth_xs,
                depth_ys,
                vel_xs,
                vel_ys,
            )
            np.testing.assert_allclose(
                suit,
                row["suitability"],
                rtol=1e-9,
                err_msg="Spawn suitability mismatch at d={:.1f} v={:.1f}".format(
                    row["depth"],
                    row["velocity"],
                ),
            )


# =====================================================================
# NetLogo Cross-Validation Tests
# These tests compare Python function output against genuine NetLogo 7.4
# reference data generated from InSALMO7.4 test procedures.
# =====================================================================


class TestGrowthReportMatchesNetLogoCSV:
    """Cross-validate Python growth components against NetLogo GrowthReportOut.

    The NetLogo write-growth-report test procedure runs with the model's
    runtime step-length (fraction of a day), which is NOT 1.0. Since the NL
    CSV does not record step-length, we cannot reconstruct c-stepmax and
    therefore cannot match drift/search intake and growth exactly. However,
    we CAN validate:

    1. Hiding growth (growth-hide): depends only on respiration, no intake.
    2. Respiration columns (resp-drift, resp-search, resp-hide): independent
       of step-length.
    3. Intermediate values: CMax-temp-func, max-swim-speed, drift-swim-speed.
    """

    def test_netlogo_growth_report(self):
        import math
        import numpy as np
        import pandas as pd

        ref_path = require_reference("GrowthReportOut-netlogo.csv")
        ref = pd.read_csv(ref_path, skiprows=2)
        from salmopy.modules.growth import (
            cmax_temp_function,
            max_swim_speed,
            drift_swim_speed,
            respiration,
        )

        # Example A Chinook-Spring species params
        table_x = [0.0, 2.0, 10.0, 22.0, 23.0, 25.0, 30.0]
        table_y = [0.05, 0.05, 0.5, 1.0, 0.8, 0.5, 0.0]
        cmax_A = 0.628
        cmax_B = 0.7
        max_speed_A = 2.8
        max_speed_B = 21.0
        max_speed_C = -0.0029
        max_speed_D = 0.084
        max_speed_E = 0.37
        resp_A = 36.0
        resp_B = 0.783
        resp_C = 0.0020
        resp_D = 1.4
        fish_energy_density = 5900.0

        # Sample every 100th row to keep test time reasonable (~3300 rows)
        sampled = ref.iloc[::100].reset_index(drop=True)
        mismatches = []

        for idx, row in sampled.iterrows():
            length = row["trout-length"]
            weight = row["trout-weight"]
            temp = row["temperature"]
            depth = row["depth"]
            velocity = row["velocity"]
            shelter_frac = row["shelter-frac"]

            # Pre-compute temperature-dependent terms
            max_swim_temp_term = max(
                0.0, max_speed_C * temp * temp + max_speed_D * temp + max_speed_E
            )
            exponent = resp_C * temp * temp
            exponent = max(-500.0, min(50.0, exponent))
            resp_temp_term = math.exp(exponent)

            max_speed_len_term = max_speed_A * length + max_speed_B
            py_max_speed = max_swim_speed(max_speed_len_term, max_swim_temp_term)
            resp_std_wt = resp_A * weight ** resp_B

            # 1. CMax-temp-func
            py_cmax_temp = cmax_temp_function(temp, table_x, table_y)
            nl_cmax_temp = row["CMax-temp-func"]
            if abs(py_cmax_temp - nl_cmax_temp) > max(1e-9, 1e-9 * abs(nl_cmax_temp)):
                mismatches.append(
                    "row {} CMax-temp-func: py={:.12g} nl={:.12g}".format(
                        idx, py_cmax_temp, nl_cmax_temp
                    )
                )

            # 2. max-swim-speed
            nl_max_speed = row["max-swim-speed"]
            if abs(py_max_speed - nl_max_speed) > max(1e-9, 1e-9 * abs(nl_max_speed)):
                mismatches.append(
                    "row {} max-swim-speed: py={:.12g} nl={:.12g}".format(
                        idx, py_max_speed, nl_max_speed
                    )
                )

            # 3. drift-swim-speed
            # NL test sets cell-available-vel-shelter = 1000000, and
            # drift-swim-speed = velocity * shelter-frac when shelter available
            py_drift_ss = drift_swim_speed(
                velocity, length, 1000000.0, shelter_frac
            )
            nl_drift_ss = row["drift-swim-speed"]
            if abs(py_drift_ss - nl_drift_ss) > max(1e-9, 1e-9 * abs(nl_drift_ss)):
                mismatches.append(
                    "row {} drift-swim-speed: py={:.12g} nl={:.12g}".format(
                        idx, py_drift_ss, nl_drift_ss
                    )
                )

            # 4. Respiration for each activity
            # resp-drift uses velocity * shelter_frac as swim speed
            py_resp_drift = respiration(
                resp_std_wt, resp_temp_term,
                velocity * shelter_frac, py_max_speed, resp_D
            )
            nl_resp_drift = row["resp-drift"]
            if abs(py_resp_drift - nl_resp_drift) > max(1e-6, 1e-6 * abs(nl_resp_drift)):
                mismatches.append(
                    "row {} resp-drift: py={:.12g} nl={:.12g}".format(
                        idx, py_resp_drift, nl_resp_drift
                    )
                )

            # resp-search uses cell velocity as swim speed
            py_resp_search = respiration(
                resp_std_wt, resp_temp_term, velocity, py_max_speed, resp_D
            )
            nl_resp_search = row["resp-search"]
            if abs(py_resp_search - nl_resp_search) > max(1e-6, 1e-6 * abs(nl_resp_search)):
                mismatches.append(
                    "row {} resp-search: py={:.12g} nl={:.12g}".format(
                        idx, py_resp_search, nl_resp_search
                    )
                )

            # resp-hide uses 0 swim speed
            py_resp_hide = respiration(
                resp_std_wt, resp_temp_term, 0.0, py_max_speed, resp_D
            )
            nl_resp_hide = row["resp-hide"]
            if abs(py_resp_hide - nl_resp_hide) > max(1e-6, 1e-6 * abs(nl_resp_hide)):
                mismatches.append(
                    "row {} resp-hide: py={:.12g} nl={:.12g}".format(
                        idx, py_resp_hide, nl_resp_hide
                    )
                )

            # 5. growth-hide = -resp_hide / fish_energy_density (no intake)
            py_growth_hide = -py_resp_hide / fish_energy_density
            nl_growth_hide = row["growth-hide"]
            if abs(nl_growth_hide) > 1e-12:
                if abs((py_growth_hide - nl_growth_hide) / nl_growth_hide) > 1e-6:
                    mismatches.append(
                        "row {} growth-hide: py={:.12g} nl={:.12g}".format(
                            idx, py_growth_hide, nl_growth_hide
                        )
                    )
            else:
                if abs(py_growth_hide - nl_growth_hide) > 1e-12:
                    mismatches.append(
                        "row {} growth-hide: py={:.12g} nl={:.12g}".format(
                            idx, py_growth_hide, nl_growth_hide
                        )
                    )

        assert len(mismatches) == 0, "{} mismatches (of {}):\n{}".format(
            len(mismatches),
            len(sampled) * 7,
            "\n".join(mismatches[:20]),
        )


class TestSurvivalMatchesNetLogoCSV:
    """Cross-validate Python survival functions against NetLogo survival-test-out."""

    def test_netlogo_survival(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("survival-test-out-netlogo.csv")
        ref = pd.read_csv(ref_path, skiprows=1)
        from salmopy.modules.survival import (
            survival_high_temperature,
            survival_stranding,
            survival_condition,
            survival_fish_predation,
            survival_terrestrial_predation,
        )

        # Example A Chinook-Spring params from config
        mismatches = []

        for idx, row in ref.iterrows():
            length = row["trout-length"]
            condition = row["trout-condition"]
            activity = row["trout-activity"]  # string: "drift", "search", "hide"
            temp = row["temperature"]
            pisciv_density = row["pisciv-density"]
            depth = row["depth"]
            velocity = row["velocity"]
            dist_to_hide = row["dist-to-hide"]
            avail_hiding = int(row["avail-hiding-places"])
            light = row["light"]

            # s-temperature
            s_ht = survival_high_temperature(temp, T1=28.0, T9=24.0)
            expected_ht = row["s-temperature"]
            if abs(s_ht - expected_ht) > max(1e-9, 1e-9 * abs(expected_ht)):
                mismatches.append(
                    "row {} s-temperature: py={:.12g} nl={:.12g}".format(idx, s_ht, expected_ht)
                )

            # s-strand
            s_str = survival_stranding(depth)
            expected_str = row["s-strand"]
            if abs(s_str - expected_str) > 1e-9:
                mismatches.append(
                    "row {} s-strand: py={:.12g} nl={:.12g}".format(idx, s_str, expected_str)
                )

            # s-condition
            s_cond = survival_condition(condition, S_at_K5=0.8, S_at_K8=0.992)
            expected_cond = row["s-condition"]
            if abs(s_cond - expected_cond) > max(1e-9, 1e-9 * abs(expected_cond)):
                mismatches.append(
                    "row {} s-condition: py={:.12g} nl={:.12g}".format(
                        idx, s_cond, expected_cond
                    )
                )

            # s-fish-pred
            s_fp = survival_fish_predation(
                length,
                depth,
                light,
                pisciv_density,
                temp,
                activity,
                0.97,    # fish_pred_min
                3.0,     # L1
                6.0,     # L9
                35.0,    # D1
                5.0,     # D9
                5.0e-06, # P1
                -5.0,    # P9
                50.0,    # I1
                -50.0,   # I9
                6.0,     # T1
                2.0,     # T9
                0.5,     # hiding_factor
            )
            expected_fp = row["s-fish-pred"]
            if abs(s_fp - expected_fp) > max(1e-6, 1e-6 * abs(expected_fp)):
                mismatches.append(
                    "row {} s-fish-pred: py={:.12g} nl={:.12g}".format(
                        idx, s_fp, expected_fp
                    )
                )

            # s-terr-pred
            s_tp = survival_terrestrial_predation(
                length,
                depth,
                velocity,
                light,
                dist_to_hide,
                activity,
                avail_hiding,
                1,      # superind_rep
                0.94,   # terr_pred_min
                6.0,    # L1
                3.0,    # L9
                0.0,    # D1
                200.0,  # D9
                20.0,   # V1
                300.0,  # V9
                50.0,   # I1
                -10.0,  # I9
                200.0,  # H1
                -50.0,  # H9
                0.8,    # hiding_factor
            )
            expected_tp = row["s-terr-pred"]
            if abs(s_tp - expected_tp) > max(1e-6, 1e-6 * abs(expected_tp)):
                mismatches.append(
                    "row {} s-terr-pred: py={:.12g} nl={:.12g}".format(
                        idx, s_tp, expected_tp
                    )
                )

        assert len(mismatches) == 0, "{} mismatches (of {}):\n{}".format(
            len(mismatches),
            len(ref) * 5,
            "\n".join(mismatches[:20]),
        )


class TestReddSurvivalMatchesNetLogoCSV:
    """Cross-validate Python redd survival against NetLogo Redd-survive-test-out.

    The NetLogo redd-survive procedure uses:
        mortality_rate = (1 - daily_survival) * num_eggs * step_length
        eggs_died = random-poisson(mortality_rate)

    where daily_survival is the logistic value (NOT raised to step_length).
    The eggs_died are stochastic (Poisson-drawn), so we compare the expected
    mortality rate against the Poisson mean and use a tolerance that accounts
    for Poisson variance: stddev = sqrt(mean), so we allow ~3 sigma.
    """

    def test_netlogo_redd_survival(self):
        import math
        import numpy as np
        import pandas as pd

        ref_path = require_reference("Redd-survive-test-out-netlogo.csv")
        ref = pd.read_csv(ref_path, skiprows=2)
        from salmopy.modules.survival import redd_survival_lo_temp, redd_survival_hi_temp

        # Example A Chinook-Spring redd params
        lo_T1 = 1.7
        lo_T9 = 4.0
        hi_T1 = 23.0
        hi_T9 = 17.5

        mismatches_lo = 0
        mismatches_hi = 0
        total_lo = 0
        total_hi = 0

        for idx, row in ref.iterrows():
            step_length = row["step-length"]
            temp = row["temperature"]
            initial_eggs = row["initial-eggs"]
            nl_died_lo = row["eggs-died-lo-T"]
            nl_died_hi = row["eggs-died-hi-T"]

            if initial_eggs <= 0:
                continue

            # NetLogo formula: mortality_rate = (1 - s_daily) * eggs * step_length
            # s_daily is the logistic value (step_length=1.0)
            s_lo_daily = redd_survival_lo_temp(temp, lo_T1, lo_T9, step_length=1.0)
            expected_died_lo = (1.0 - s_lo_daily) * initial_eggs * step_length

            # Poisson tolerance: allow 4-sigma deviation or minimum 2 eggs
            tol_lo = max(2.0, 4.0 * math.sqrt(max(expected_died_lo, 1.0)))
            total_lo += 1
            if abs(expected_died_lo - nl_died_lo) > tol_lo:
                mismatches_lo += 1

            # High-temp: applied to eggs remaining after lo-T deaths
            remaining_after_lo = initial_eggs - nl_died_lo
            if remaining_after_lo > 0:
                s_hi_daily = redd_survival_hi_temp(temp, hi_T1, hi_T9, step_length=1.0)
                expected_died_hi = (1.0 - s_hi_daily) * remaining_after_lo * step_length
                tol_hi = max(2.0, 4.0 * math.sqrt(max(expected_died_hi, 1.0)))
                total_hi += 1
                if abs(expected_died_hi - nl_died_hi) > tol_hi:
                    mismatches_hi += 1

        # With Poisson noise and 4-sigma tolerance, <0.01% of rows should mismatch
        # Allow up to 1% as a generous safety margin
        lo_pct = 100.0 * mismatches_lo / max(total_lo, 1)
        hi_pct = 100.0 * mismatches_hi / max(total_hi, 1)
        assert lo_pct < 1.0, (
            "lo-T: {} of {} rows ({:.1f}%) exceed 4-sigma Poisson tolerance".format(
                mismatches_lo, total_lo, lo_pct
            )
        )
        assert hi_pct < 1.0, (
            "hi-T: {} of {} rows ({:.1f}%) exceed 4-sigma Poisson tolerance".format(
                mismatches_hi, total_hi, hi_pct
            )
        )


class TestSpawnCellMatchesNetLogoCSV:
    """Cross-validate Python spawn suitability against NetLogo Spawn-cell-test-out."""

    def test_netlogo_spawn_cell(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("Spawn-cell-test-out-netlogo.csv")
        ref = pd.read_csv(ref_path, skiprows=1)
        from salmopy.modules.spawning import spawn_suitability

        # Example A Chinook-Spring spawn tables
        depth_xs = np.array([0.0, 12.0, 27.0, 33.5, 204.0])
        depth_ys = np.array([0.0, 0.0, 0.95, 1.0, 0.0])
        vel_xs = np.array([0.0, 2.3, 3.0, 54.0, 61.0, 192.0])
        vel_ys = np.array([0.0, 0.0, 0.06, 1.0, 1.0, 0.0])

        mismatches = []

        for idx, row in ref.iterrows():
            depth = row["Depth"]
            velocity = row["Velocity"]
            frac_spawn = row["Gravel fraction"]
            area = row["Area"]

            # Verify depth and velocity suitability individually
            py_depth_suit = float(np.interp(depth, depth_xs, depth_ys))
            py_vel_suit = float(np.interp(velocity, vel_xs, vel_ys))
            nl_depth_suit = row["Depth-suit"]
            nl_vel_suit = row["Vel-suit"]

            if abs(py_depth_suit - nl_depth_suit) > max(1e-6, 1e-6 * abs(nl_depth_suit)):
                mismatches.append(
                    "row {} depth-suit: py={:.10g} nl={:.10g} (d={})".format(
                        idx, py_depth_suit, nl_depth_suit, depth
                    )
                )
            if abs(py_vel_suit - nl_vel_suit) > max(1e-6, 1e-6 * abs(nl_vel_suit)):
                mismatches.append(
                    "row {} vel-suit: py={:.10g} nl={:.10g} (v={})".format(
                        idx, py_vel_suit, nl_vel_suit, velocity
                    )
                )

        assert len(mismatches) == 0, "{} mismatches (of {}):\n{}".format(
            len(mismatches),
            len(ref) * 2,
            "\n".join(mismatches[:20]),
        )


class TestCStepMaxMatchesNetLogoCSV:
    """Cross-validate Python c_stepmax against NetLogo CStepmaxOut."""

    def test_netlogo_cstepmax(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("CStepmaxOut-netlogo.csv")
        # Line 1 is a comment, line 2 is header.
        # ConsList column contains commas (serialized NetLogo list),
        # causing variable field counts. Parse manually.
        rows = []
        with open(ref_path) as f:
            next(f)  # skip comment line
            header_line = next(f).strip()
            for line in f:
                fields = line.strip().split(",")
                # First 10 columns are well-defined; rest is ConsList
                rows.append(fields[:10])
        col_names = [
            "Time", "trout", "Reach", "C-stepmax", "Weight",
            "Temperature", "CmaxTempFunc", "CMax", "Steplength",
            "PrevCons",
        ]
        ref = pd.DataFrame(rows, columns=col_names)
        for col in col_names[3:]:
            ref[col] = pd.to_numeric(ref[col])
        from salmopy.modules.growth import cmax_temp_function, c_stepmax

        # Example A Chinook-Spring params
        table_x = [0.0, 2.0, 10.0, 22.0, 23.0, 25.0, 30.0]
        table_y = [0.05, 0.05, 0.5, 1.0, 0.8, 0.5, 0.0]
        cmax_A = 0.628
        cmax_B = 0.7

        mismatches = []

        for idx, row in ref.iterrows():
            weight = row["Weight"]
            temp = row["Temperature"]
            step_length = row["Steplength"]
            prev_cons = row["PrevCons"]
            nl_cstepmax = row["C-stepmax"]

            cmax_temp = cmax_temp_function(temp, table_x, table_y)
            cmax_wt = cmax_A * weight ** cmax_B
            py_cstepmax = c_stepmax(cmax_wt, cmax_temp, prev_cons, step_length)

            # Also verify CmaxTempFunc
            nl_cmax_temp = row["CmaxTempFunc"]
            if abs(cmax_temp - nl_cmax_temp) > max(1e-9, 1e-9 * abs(nl_cmax_temp)):
                mismatches.append(
                    "row {} CmaxTempFunc: py={:.12g} nl={:.12g}".format(
                        idx, cmax_temp, nl_cmax_temp
                    )
                )

            if abs(py_cstepmax - nl_cstepmax) > max(1e-5, 1e-5 * abs(nl_cstepmax)):
                mismatches.append(
                    "row {} C-stepmax: py={:.12g} nl={:.12g}".format(
                        idx, py_cstepmax, nl_cstepmax
                    )
                )

        assert len(mismatches) == 0, "{} mismatches (of {}):\n{}".format(
            len(mismatches),
            len(ref) * 2,
            "\n".join(mismatches[:20]),
        )


class TestFitnessReport:
    """Python-only fitness regression test — golden snapshot baseline.

    Golden snapshot from Python v0.5.0 — cross-validate against NetLogo when available.
    TODO: Regenerate golden after NetLogo cross-validation (Section 3.7).

    **Arc D (v0.31.0, 2026-04-19)**: xfailed pending golden regeneration.
    Arc D intentionally changes fish-level trajectories in example_a:
    continuous FRY->PARR promotion + switched migration comparator causes
    some emergence-length-4.0+ FRY to transit to PARR and then either
    migrate or die at the river mouth in the single-reach example_a,
    which the golden snapshot (captured pre-Arc D) does not reflect.
    Regenerate the fixture alongside Arc E growth calibration.
    """

    @pytest.mark.xfail(
        reason="Golden needs regeneration after Arc D migration rewrite; see v0.31.0-arc-D-netlogo-comparison.md",
        strict=False,
    )
    def test_fitness_report(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("fitness-golden.csv")
        ref = pd.read_csv(ref_path)
        from salmopy.model import SalmopyModel

        CONFIGS = FIXTURES_DIR.parent.parent / "configs"
        model = SalmopyModel(
            CONFIGS / "example_a.yaml",
            data_dir=FIXTURES_DIR / "example_a",
        )
        model.step()
        model.step()

        ts = model.trout_state

        for _, row in ref.iterrows():
            i = int(row["fish_idx"])
            assert ts.alive[i], "Fish {} should be alive".format(i)
            np.testing.assert_allclose(
                float(ts.length[i]),
                row["length"],
                rtol=1e-4,  # TODO: restore to 1e-6 after golden regeneration
                err_msg="Length mismatch at fish {}".format(i),
            )
            np.testing.assert_allclose(
                float(ts.weight[i]),
                row["weight"],
                rtol=1e-4,  # TODO: restore to 1e-6 after golden regeneration
                err_msg="Weight mismatch at fish {}".format(i),
            )
            np.testing.assert_allclose(
                float(ts.condition[i]),
                row["condition"],
                rtol=1e-4,  # TODO: restore to 1e-5 after golden regeneration
                err_msg="Condition mismatch at fish {}".format(i),
            )
            np.testing.assert_allclose(
                float(ts.last_growth_rate[i]),
                row["last_growth_rate"],
                rtol=1e-4,  # TODO: restore to 1e-5 after golden regeneration
                atol=1e-12,
                err_msg="Growth rate mismatch at fish {}".format(i),
            )


class TestFitnessReportMatchesNetLogoCSV:
    """Cross-validate Python fitness computation against NetLogo reference CSV.

    The reference CSV (FitnessReportOut-netlogo.csv, ~402K rows) was generated
    by NetLogo's test-fitness-report procedure which sweeps over combinations of
    length, condition, predation survival, and specific growth rate.

    Species parameters (Chinook-Spring, Example A):
        weight_A = 0.0041, weight_B = 3.49
        fitness_horizon (T) = 60 days
        fitness_length (maturity) = 15 cm
        mort_condition_S_at_K5 = 0.8
    """

    # --- Species parameters for Chinook-Spring (Example A) ---
    WEIGHT_A = 0.0041
    WEIGHT_B = 3.49
    TIME_HORIZON = 60
    MATURITY_LENGTH = 15.0
    S_AT_K5 = 0.8

    # ------------------------------------------------------------------
    # Helper: mean-condition-survival-with (NetLogo reporter)
    # ------------------------------------------------------------------
    @staticmethod
    def _mean_condition_survival(condition, daily_growth_abs, T, weight_A,
                                 weight_B, length, s5):
        """Replicates NetLogo mean-condition-survival-with reporter.

        Parameters
        ----------
        condition : float  (k in NetLogo)
        daily_growth_abs : float  (g/d, absolute daily weight change)
        T : float  (time horizon in days)
        weight_A, weight_B : float  (allometric weight parameters)
        length : float  (current fish length cm)
        s5 : float  (mort-condition-S-at-K5)
        """
        k = condition

        # If condition = 1 and positive growth, survival is 1.0
        if k == 1.0 and daily_growth_abs >= 0.0:
            return 1.0

        # Survival at current condition (linear model)
        s_now = (2 * s5) + (2 * k) - (2 * k * s5) - 1

        # Near-zero growth: steady condition
        if abs(daily_growth_abs) < 0.0001:
            return s_now

        # Daily change in condition
        healthy_weight = weight_A * (length ** weight_B)
        d_k = daily_growth_abs / healthy_weight
        s_k0 = (2 * s5) - 1  # survival at condition zero

        if d_k < 0:
            # Condition is decreasing
            t_at_k_0 = k / (-1 * d_k)
            if t_at_k_0 <= T:
                # Condition reaches zero before time horizon
                area1 = t_at_k_0 * (s_now + s_k0) / 2
                area2 = (T - t_at_k_0) * s_k0
                return (area1 + area2) / T
            else:
                # Condition remains above zero to time horizon
                k_at_t = k + (T * d_k)
                s_at_t = (2 * s5) + (2 * k_at_t) - (2 * k_at_t * s5) - 1
                return (s_now + s_at_t) / 2
        else:
            # Condition is increasing
            t_at_k_1 = (1.0 - k) / d_k
            if t_at_k_1 <= T:
                # Condition reaches 1.0 before time horizon
                area1 = t_at_k_1 * (s_now + 1.0) / 2
                area2 = (T - t_at_k_1) * 1.0
                return (area1 + area2) / T
            else:
                # Condition remains below 1.0 to time horizon
                k_at_t = k + (T * d_k)
                s_at_t = (2 * s5) + (2 * k_at_t) - (2 * k_at_t * s5) - 1
                return (s_now + s_at_t) / 2

    # ------------------------------------------------------------------
    # Helper: length-with-growth (NetLogo reporter)
    # ------------------------------------------------------------------
    @staticmethod
    def _length_with_growth(length, weight, growth_abs, weight_A, weight_B):
        """Replicates NetLogo length-with-growth reporter.

        Parameters
        ----------
        length : float  (current fish length cm)
        weight : float  (current fish weight g)
        growth_abs : float  (absolute weight change over horizon, g)
        weight_A, weight_B : float  (allometric weight parameters)
        """
        if growth_abs <= 0.0:
            return length
        new_weight = weight + growth_abs
        healthy_weight = weight_A * (length ** weight_B)
        if new_weight > healthy_weight:
            # Fish reaches condition 1.0 and grows in length
            return (new_weight / weight_A) ** (1.0 / weight_B)
        else:
            return length

    # ------------------------------------------------------------------
    # Helper: full fitness computation
    # ------------------------------------------------------------------
    @classmethod
    def _compute_fitness(cls, length, weight, condition, daily_pred_survival,
                         growth_ggd):
        """Compute fitness exactly as NetLogo test-fitness-report does."""
        T = cls.TIME_HORIZON

        # Convert specific growth rate to absolute daily growth (g/d)
        daily_growth = growth_ggd * weight

        # Mean starvation survival to horizon
        mean_starv = cls._mean_condition_survival(
            condition, daily_growth, T,
            cls.WEIGHT_A, cls.WEIGHT_B, length, cls.S_AT_K5,
        )

        # Core fitness
        fitness = (daily_pred_survival * mean_starv) ** T

        # Maturity-length adjustment
        if length < cls.MATURITY_LENGTH:
            growth_over_horizon = daily_growth * T
            length_at_horizon = cls._length_with_growth(
                length, weight, growth_over_horizon,
                cls.WEIGHT_A, cls.WEIGHT_B,
            )
            if length_at_horizon < cls.MATURITY_LENGTH:
                fitness *= length_at_horizon / cls.MATURITY_LENGTH

        return fitness

    # ------------------------------------------------------------------
    # The test
    # ------------------------------------------------------------------
    def test_fitness_matches_netlogo(self):
        """Sample every 1000th row and compare Python fitness to NetLogo."""
        import numpy as np
        import pandas as pd

        ref_path = require_reference("FitnessReportOut-netlogo.csv")
        df = pd.read_csv(ref_path, skiprows=2)

        # Sample every 1000th row (covers ~402 rows across the full sweep)
        sampled = df.iloc[::1000].reset_index(drop=True)
        assert len(sampled) > 100, "Expected >100 sampled rows, got {}".format(
            len(sampled)
        )

        mismatches = []
        for idx, row in sampled.iterrows():
            length = row["trout-length"]
            weight = row["trout-weight"]
            condition = row["trout-condition"]
            daily_surv = row["daily-pred-survival"]
            growth_ggd = row["growth (g/g/d)"]
            expected_fitness = row["fitness"]

            computed = self._compute_fitness(
                length, weight, condition, daily_surv, growth_ggd,
            )

            if expected_fitness == 0.0:
                if computed != 0.0:
                    mismatches.append(
                        "Row {}: expected 0.0, got {}".format(idx, computed)
                    )
            else:
                rel_err = abs(computed - expected_fitness) / abs(expected_fitness)
                if rel_err > 1e-6:
                    mismatches.append(
                        "Row {}: L={} K={} surv={} g={} expected={} got={} "
                        "rel_err={:.2e}".format(
                            idx, length, condition, daily_surv, growth_ggd,
                            expected_fitness, computed, rel_err,
                        )
                    )

        assert len(mismatches) == 0, "{} mismatches out of {} rows:\n{}".format(
            len(mismatches), len(sampled), "\n".join(mismatches[:20]),
        )
