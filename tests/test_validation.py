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
        from instream.io.hydraulics_reader import read_depth_table

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
        from instream.io.hydraulics_reader import read_depth_table, read_velocity_table

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
        from instream.backends.numpy_backend import NumpyBackend

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
    """Port of NetLogo write-growth-report (will be filled in Phase 3)."""

    def test_full_growth_report_matches_netlogo(self):
        ref_path = require_reference("GrowthReportOut.csv")
        pytest.skip("Phase 3 — growth module not yet implemented")


class TestCStepMaxMatchesNetLogo:
    """Port of NetLogo test-c-stepmax (will be filled in Phase 3)."""

    def test_cstepmax_matches_netlogo(self):
        ref_path = require_reference("CStepmaxOut.csv")
        pytest.skip("Phase 3 — growth module not yet implemented")


class TestInterpolationMatchesNetLogo:
    """Port of NetLogo write-interpolation-test-report."""

    def test_cmax_temp_interpolation_matches_netlogo(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("CMaxTempFunctTestOut.csv")
        ref = pd.read_csv(ref_path)
        from instream.modules.growth import cmax_temp_function

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
    """Port of NetLogo test-survival (will be filled in Phase 5)."""

    def test_trout_survival_matches_netlogo(self):
        ref_path = require_reference("survival-test-out.csv")
        pytest.skip("Phase 5 — survival module not yet implemented")


class TestReddSurvivalMatchesNetLogo:
    """Port of NetLogo test-redd-survive-temperature (will be filled in Phase 5)."""

    def test_redd_temperature_survival_matches_netlogo(self):
        ref_path = require_reference("Redd-survive-test-out.csv")
        pytest.skip("Phase 5 — survival module not yet implemented")


class TestSpawnCellMatchesNetLogo:
    """Port of NetLogo test-spawn-cell (will be filled in Phase 6)."""

    def test_spawn_cell_selection_matches_netlogo(self):
        ref_path = require_reference("Spawn-cell-test-out.csv")
        pytest.skip("Phase 6 — spawning module not yet implemented")


class TestFitnessReport:
    """Python-only fitness test — no NetLogo oracle exists for this."""

    def test_fitness_report(self):
        # This test has no NetLogo oracle. Will use golden snapshot from
        # first validated run as regression baseline (Phase 9).
        pytest.skip("Phase 4 — fitness module not yet implemented")
