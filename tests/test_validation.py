"""Validation tests comparing Python output to NetLogo reference data.

These tests require NetLogo reference CSVs in tests/fixtures/reference/.
They are skipped when reference data is not available.
"""
import numpy as np
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
        ref_path = require_reference("Test-GIS-contents.csv")
        # TODO: Load reference CSV, load shapefile, compare each cell's attributes
        # Exact match on cell-ID, reach-name; rtol=1e-6 on area, dist-escape, frac-shelter, frac-spawn
        pytest.skip("Implementation pending — need to parse reference CSV format")


class TestCellDepthsMatchNetLogo:
    """Port of NetLogo test-cell-depths."""

    def test_cell_depths_match_netlogo(self):
        ref_path = require_reference("cell-depth-test-out.csv")
        # TODO: Pick 10 cells, interpolate over 50 geometric flow series
        # Compare to NetLogo reference, rtol=1e-6
        pytest.skip("Implementation pending — need to parse reference CSV format")


class TestCellVelocitiesMatchNetLogo:
    """Port of NetLogo test-cell-velocities."""

    def test_cell_velocities_match_netlogo(self):
        ref_path = require_reference("cell-vel-test-out.csv")
        # TODO: Same structure as depth test
        pytest.skip("Implementation pending — need to parse reference CSV format")


class TestDayLengthMatchesNetLogo:
    """Port of NetLogo test-day-length (will be filled in Phase 2)."""

    def test_day_length_matches_netlogo_reference(self):
        ref_path = require_reference("test-day-length.csv")
        pytest.skip("Phase 2 — light module not yet implemented")


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
    """Port of NetLogo write-interpolation-test-report (will be filled in Phase 3)."""

    def test_cmax_temp_interpolation_matches_netlogo(self):
        ref_path = require_reference("CMaxTempFunctTestOut.csv")
        pytest.skip("Phase 3 — growth module not yet implemented")


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
