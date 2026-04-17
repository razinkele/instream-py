"""Regression tests for Phase 3 hardening (P3.1 / P3.4 / P3.5 / P3.6)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from instream.io.config import (
    BarrierDirectionConfig,
    SimulationConfig,
    SpeciesConfig,
)
from instream.modules.growth_math import safe_cmax_interp


# -----------------------------------------------------------------------
# P3.1: BarrierDirectionConfig probability validators
# -----------------------------------------------------------------------


class TestP31BarrierDirectionConfig:
    def test_default_is_pure_transmission(self):
        bd = BarrierDirectionConfig()
        assert bd.mortality == 0.0
        assert bd.deflection == 0.0
        assert bd.transmission == 1.0

    def test_valid_probs_sum_to_one(self):
        bd = BarrierDirectionConfig(
            mortality=0.2, deflection=0.3, transmission=0.5
        )
        assert math.isclose(
            bd.mortality + bd.deflection + bd.transmission, 1.0
        )

    def test_negative_prob_rejected(self):
        with pytest.raises(ValidationError):
            BarrierDirectionConfig(
                mortality=-0.1, deflection=0.0, transmission=1.1
            )

    def test_prob_above_one_rejected(self):
        with pytest.raises(ValidationError):
            BarrierDirectionConfig(
                mortality=1.5, deflection=0.0, transmission=0.0
            )

    def test_probs_not_summing_to_one_rejected(self):
        with pytest.raises(ValidationError):
            BarrierDirectionConfig(
                mortality=0.1, deflection=0.1, transmission=0.1
            )


# -----------------------------------------------------------------------
# P3.4: unknown species flag
# -----------------------------------------------------------------------


class TestP34SimulationConfigUnknownSpeciesFlag:
    def test_default_rejects_unknown_remap(self):
        sc = SimulationConfig(start_date="2024-01-01", end_date="2024-12-31")
        assert sc.allow_unknown_species_remap is False

    def test_flag_can_be_enabled(self):
        sc = SimulationConfig(
            start_date="2024-01-01",
            end_date="2024-12-31",
            allow_unknown_species_remap=True,
        )
        assert sc.allow_unknown_species_remap is True


# -----------------------------------------------------------------------
# P3.5a: spawn defense area meters canonicalisation
# -----------------------------------------------------------------------


class TestP35aSpawnDefenseUnits:
    def test_cm_backfills_meters(self):
        sp = SpeciesConfig(spawn_defense_area=30.0)
        assert math.isclose(sp.spawn_defense_area_m, 0.30)

    def test_m2_backfills_meters_and_cm(self):
        # 1 m² circular disk -> r = sqrt(1/pi) ~= 0.5642 m
        sp = SpeciesConfig(spawn_defense_area_m2=1.0)
        expected_r_m = math.sqrt(1.0 / math.pi)
        assert math.isclose(sp.spawn_defense_area_m, expected_r_m)
        assert math.isclose(sp.spawn_defense_area, expected_r_m * 100.0)

    def test_explicit_meters_wins(self):
        sp = SpeciesConfig(spawn_defense_area_m=0.25)
        assert math.isclose(sp.spawn_defense_area_m, 0.25)
        assert math.isclose(sp.spawn_defense_area, 25.0)

    def test_select_spawn_cell_uses_meters(self):
        from instream.modules.spawning import select_spawn_cell

        scores = np.array([0.8, 0.9, 0.7])
        candidates = np.array([10, 20, 30])
        redd_cells = np.array([20])
        # Mesh CRS is metres: put candidate 10 at 0.5 m from redd 20,
        # candidate 30 at 2.0 m from redd 20. A 1.0 m defense radius
        # should exclude both 10 (too close) and 20 (the redd itself
        # coincides with it), leaving 30 as the best.
        centroids_x = np.zeros(31, dtype=np.float64)
        centroids_y = np.zeros(31, dtype=np.float64)
        centroids_x[10] = 0.5
        centroids_x[20] = 0.0
        centroids_x[30] = 2.0
        best = select_spawn_cell(
            scores,
            candidates,
            redd_cells=redd_cells,
            centroids_x=centroids_x,
            centroids_y=centroids_y,
            defense_area_m=1.0,
        )
        assert best == 30


# -----------------------------------------------------------------------
# P3.5b: spawn_search_radius_m field present and defaults
# -----------------------------------------------------------------------


class TestP35bSpawnSearchRadiusField:
    def test_default_is_zero(self):
        sp = SpeciesConfig()
        assert sp.spawn_search_radius_m == 0.0

    def test_can_be_overridden(self):
        sp = SpeciesConfig(spawn_search_radius_m=2.5)
        assert sp.spawn_search_radius_m == 2.5


# -----------------------------------------------------------------------
# P3.6: safe_cmax_interp contract
# -----------------------------------------------------------------------


class TestP36SafeCmaxInterp:
    def test_empty_table_raises(self):
        with pytest.raises(ValueError):
            safe_cmax_interp(10.0, [], [])

    def test_mismatched_shape_raises(self):
        with pytest.raises(ValueError):
            safe_cmax_interp(10.0, [1.0, 2.0], [0.5])

    def test_single_row_is_flat(self):
        assert safe_cmax_interp(-50.0, [15.0], [0.7]) == 0.7
        assert safe_cmax_interp(15.0, [15.0], [0.7]) == 0.7
        assert safe_cmax_interp(50.0, [15.0], [0.7]) == 0.7

    def test_clamps_below_range(self):
        assert safe_cmax_interp(-5.0, [0.0, 10.0], [0.1, 1.0]) == 0.1

    def test_clamps_above_range(self):
        assert safe_cmax_interp(100.0, [0.0, 10.0], [0.1, 1.0]) == 1.0

    def test_interpolates_in_range(self):
        got = safe_cmax_interp(5.0, [0.0, 10.0], [0.0, 1.0])
        assert math.isclose(got, 0.5)

    def test_matches_cmax_temp_function(self):
        from instream.modules.growth import cmax_temp_function

        xs = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0]
        ys = [0.0, 0.2, 0.6, 1.0, 0.6, 0.0]
        for t in (-5.0, 0.0, 2.5, 7.5, 10.0, 17.5, 30.0):
            a = safe_cmax_interp(t, xs, ys)
            b = cmax_temp_function(t, xs, ys)
            assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), (
                t, a, b
            )

    def test_cmax_temp_function_empty_raises(self):
        from instream.modules.growth import cmax_temp_function

        with pytest.raises(ValueError):
            cmax_temp_function(10.0, [], [])
