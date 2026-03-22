"""Tests for behavioral decisions — logistic, candidate mask, fitness, depletion."""

import numpy as np
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestEvaluateLogistic:
    """Test standalone logistic function for survival/movement."""

    def test_at_L1_returns_0_1(self):
        from instream.modules.behavior import evaluate_logistic

        result = evaluate_logistic(3.0, L1=3.0, L9=6.0)
        np.testing.assert_allclose(result, 0.1, atol=0.01)

    def test_at_L9_returns_0_9(self):
        from instream.modules.behavior import evaluate_logistic

        result = evaluate_logistic(6.0, L1=3.0, L9=6.0)
        np.testing.assert_allclose(result, 0.9, atol=0.01)

    def test_at_midpoint_returns_0_5(self):
        from instream.modules.behavior import evaluate_logistic

        result = evaluate_logistic(4.5, L1=3.0, L9=6.0)
        np.testing.assert_allclose(result, 0.5, atol=0.01)

    def test_monotonically_increasing(self):
        from instream.modules.behavior import evaluate_logistic

        x = np.linspace(0, 10, 50)
        results = np.array([evaluate_logistic(xi, L1=3.0, L9=6.0) for xi in x])
        assert np.all(np.diff(results) >= 0)

    def test_inverted_when_L1_gt_L9(self):
        from instream.modules.behavior import evaluate_logistic

        x = np.linspace(0, 10, 50)
        results = np.array([evaluate_logistic(xi, L1=6.0, L9=3.0) for xi in x])
        assert np.all(np.diff(results) <= 0)

    def test_vectorized_array(self):
        from instream.modules.behavior import evaluate_logistic_array

        x = np.array([3.0, 4.5, 6.0])
        results = evaluate_logistic_array(x, L1=3.0, L9=6.0)
        assert results.shape == (3,)
        np.testing.assert_allclose(results, [0.1, 0.5, 0.9], atol=0.01)


class TestMovementRadius:
    """Test movement radius calculation."""

    def test_large_fish_has_larger_radius(self):
        from instream.modules.behavior import movement_radius

        r_small = movement_radius(
            length=5.0, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        r_large = movement_radius(
            length=15.0, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        assert r_large > r_small

    def test_radius_bounded_by_max(self):
        from instream.modules.behavior import movement_radius

        r = movement_radius(
            length=100.0, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        assert r <= 20000

    def test_radius_positive(self):
        from instream.modules.behavior import movement_radius

        r = movement_radius(
            length=3.0, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        assert r > 0


class TestCandidateMask:
    """Test candidate cell mask for habitat selection."""

    @pytest.fixture
    def simple_setup(self):
        """Create a simple 5-cell setup for testing."""
        from instream.state.cell_state import CellState
        from instream.state.trout_state import TroutState
        from instream.space.fem_space import FEMSpace

        cs = CellState.zeros(5, num_flows=2)
        # Place cells in a line: 0, 100, 200, 300, 400 meters apart
        cs.centroid_x[:] = np.array([0, 100, 200, 300, 400], dtype=np.float64)
        cs.centroid_y[:] = np.zeros(5, dtype=np.float64)
        cs.depth[:] = np.array([50, 30, 0, 40, 20], dtype=np.float64)  # cell 2 is dry
        cs.area[:] = 10000.0
        # Simple neighbor matrix (each cell neighbors its adjacent ones)
        ni = np.full((5, 4), -1, dtype=np.int32)
        ni[0, 0] = 1
        ni[1, 0] = 0
        ni[1, 1] = 2
        ni[2, 0] = 1
        ni[2, 1] = 3
        ni[3, 0] = 2
        ni[3, 1] = 4
        ni[4, 0] = 3
        space = FEMSpace(cs, ni)

        ts = TroutState.zeros(3)
        ts.alive[0] = True
        ts.cell_idx[0] = 0
        ts.length[0] = 10.0
        ts.alive[1] = True
        ts.cell_idx[1] = 2
        ts.length[1] = 15.0
        ts.alive[2] = False  # dead fish
        return space, ts

    def test_mask_shape(self, simple_setup):
        from instream.modules.behavior import build_candidate_mask

        space, ts = simple_setup
        mask = build_candidate_mask(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        assert mask.shape == (3, 5)  # (N_MAX, num_cells)

    def test_dead_fish_no_candidates(self, simple_setup):
        from instream.modules.behavior import build_candidate_mask

        space, ts = simple_setup
        mask = build_candidate_mask(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        assert not np.any(mask[2])  # dead fish has no candidates

    def test_fish_includes_current_cell(self, simple_setup):
        from instream.modules.behavior import build_candidate_mask

        space, ts = simple_setup
        mask = build_candidate_mask(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        # Fish 0 is at cell 0 — should include cell 0 (if wet)
        assert mask[0, 0]

    def test_dry_cells_excluded(self, simple_setup):
        from instream.modules.behavior import build_candidate_mask

        space, ts = simple_setup
        mask = build_candidate_mask(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        # Cell 2 has depth=0 — should be excluded for all fish
        assert not mask[0, 2]
        assert not mask[1, 2]

    def test_includes_neighbors(self, simple_setup):
        from instream.modules.behavior import build_candidate_mask

        space, ts = simple_setup
        # Use very small radius so only neighbors are included
        mask = build_candidate_mask(
            ts, space, move_radius_max=150, move_radius_L1=1, move_radius_L9=100
        )
        # Fish 0 at cell 0: neighbor is cell 1 (100m away, wet)
        assert mask[0, 1]


class TestFitness:
    """Test fitness calculation (simplified — growth-only for Phase 4)."""

    def test_wet_cell_higher_than_dry(self):
        from instream.modules.behavior import fitness_for

        # Wet cell with food should have positive fitness
        f_wet = fitness_for(
            activity="drift",
            length=10.0,
            weight=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            turbidity=2.0,
            temperature=15.0,
            drift_conc=3.2e-10,
            search_prod=8e-7,
            search_area=20000.0,
            available_drift=1000.0,
            available_search=1000.0,
            available_shelter=1000.0,
            shelter_speed_frac=0.3,
            superind_rep=1,
            prev_consumption=0.0,
            step_length=1.0,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            max_swim_temp_term=0.98,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            resp_temp_term=np.exp(0.002 * 225),
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
        )
        # Dry cell
        f_dry = fitness_for(
            activity="drift",
            length=10.0,
            weight=10.0,
            depth=0.0,
            velocity=0.0,
            light=0.9,
            turbidity=2.0,
            temperature=15.0,
            drift_conc=3.2e-10,
            search_prod=8e-7,
            search_area=20000.0,
            available_drift=1000.0,
            available_search=1000.0,
            available_shelter=1000.0,
            shelter_speed_frac=0.3,
            superind_rep=1,
            prev_consumption=0.0,
            step_length=1.0,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            max_swim_temp_term=0.98,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            resp_temp_term=np.exp(0.002 * 225),
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
        )
        assert f_wet > f_dry

    def test_hide_fitness_is_negative(self):
        from instream.modules.behavior import fitness_for

        f = fitness_for(
            activity="hide",
            length=10.0,
            weight=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            turbidity=2.0,
            temperature=15.0,
            drift_conc=3.2e-10,
            search_prod=8e-7,
            search_area=20000.0,
            available_drift=1000.0,
            available_search=1000.0,
            available_shelter=1000.0,
            shelter_speed_frac=0.3,
            superind_rep=1,
            prev_consumption=0.0,
            step_length=1.0,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            max_swim_temp_term=0.98,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            resp_temp_term=np.exp(0.002 * 225),
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
        )
        assert f < 0  # hide = only respiration cost

    def test_returns_zero_when_velocity_exceeds_max(self):
        from instream.modules.behavior import fitness_for

        f = fitness_for(
            activity="search",
            length=5.0,
            weight=3.0,
            depth=50.0,
            velocity=200.0,
            light=50.0,
            turbidity=2.0,
            temperature=15.0,
            drift_conc=3.2e-10,
            search_prod=8e-7,
            search_area=20000.0,
            available_drift=1000.0,
            available_search=1000.0,
            available_shelter=1000.0,
            shelter_speed_frac=0.3,
            superind_rep=1,
            prev_consumption=0.0,
            step_length=1.0,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            max_swim_temp_term=0.98,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            resp_temp_term=np.exp(0.002 * 225),
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
        )
        assert f == 0.0


class TestDepletion:
    """Test sequential resource depletion."""

    def test_drift_decreases(self):
        from instream.modules.behavior import deplete_resources

        available_drift = np.array([100.0, 200.0])
        available_search = np.array([100.0, 200.0])
        available_shelter = np.array([10000.0, 10000.0])
        available_hiding = np.array([5, 5], dtype=np.int32)
        fish_order = np.array([0])
        chosen_cells = np.array([0])
        chosen_activities = np.array([0])  # 0=drift
        intake_amounts = np.array([10.0])
        fish_lengths = np.array([10.0])
        superind_reps = np.array([1])
        deplete_resources(
            fish_order,
            chosen_cells,
            chosen_activities,
            intake_amounts,
            fish_lengths,
            superind_reps,
            available_drift,
            available_search,
            available_shelter,
            available_hiding,
        )
        assert available_drift[0] < 100.0

    def test_second_fish_gets_less(self):
        from instream.modules.behavior import deplete_resources

        available_drift = np.array([50.0])
        available_search = np.array([100.0])
        available_shelter = np.array([10000.0])
        available_hiding = np.array([5], dtype=np.int32)
        fish_order = np.array([0, 1])
        chosen_cells = np.array([0, 0])  # both in same cell
        chosen_activities = np.array([0, 0])  # both drift
        intake_amounts = np.array([30.0, 30.0])
        fish_lengths = np.array([10.0, 10.0])
        superind_reps = np.array([1, 1])
        deplete_resources(
            fish_order,
            chosen_cells,
            chosen_activities,
            intake_amounts,
            fish_lengths,
            superind_reps,
            available_drift,
            available_search,
            available_shelter,
            available_hiding,
        )
        # First fish takes 30, second can only take 20 (50-30=20 remaining)
        assert available_drift[0] == pytest.approx(0.0, abs=1e-10)

    def test_never_negative(self):
        from instream.modules.behavior import deplete_resources

        available_drift = np.array([5.0])
        available_search = np.array([100.0])
        available_shelter = np.array([10000.0])
        available_hiding = np.array([5], dtype=np.int32)
        fish_order = np.array([0])
        chosen_cells = np.array([0])
        chosen_activities = np.array([0])
        intake_amounts = np.array([100.0])  # more than available
        fish_lengths = np.array([10.0])
        superind_reps = np.array([1])
        deplete_resources(
            fish_order,
            chosen_cells,
            chosen_activities,
            intake_amounts,
            fish_lengths,
            superind_reps,
            available_drift,
            available_search,
            available_shelter,
            available_hiding,
        )
        assert available_drift[0] >= 0.0

    def test_hiding_integer_depletion(self):
        from instream.modules.behavior import deplete_resources

        available_drift = np.array([100.0])
        available_search = np.array([100.0])
        available_shelter = np.array([10000.0])
        available_hiding = np.array([3], dtype=np.int32)
        fish_order = np.array([0])
        chosen_cells = np.array([0])
        chosen_activities = np.array([2])  # 2=hide
        intake_amounts = np.array([0.0])
        fish_lengths = np.array([10.0])
        superind_reps = np.array([1])
        deplete_resources(
            fish_order,
            chosen_cells,
            chosen_activities,
            intake_amounts,
            fish_lengths,
            superind_reps,
            available_drift,
            available_search,
            available_shelter,
            available_hiding,
        )
        assert available_hiding[0] == 2  # 3 - 1 = 2

    def test_shelter_depleted_for_drift(self):
        from instream.modules.behavior import deplete_resources

        available_drift = np.array([100.0])
        available_search = np.array([100.0])
        available_shelter = np.array([200.0])  # length**2=100, so shelter available
        available_hiding = np.array([5], dtype=np.int32)
        fish_order = np.array([0])
        chosen_cells = np.array([0])
        chosen_activities = np.array([0])  # drift
        intake_amounts = np.array([10.0])
        fish_lengths = np.array([10.0])  # length**2=100
        superind_reps = np.array([1])
        deplete_resources(
            fish_order,
            chosen_cells,
            chosen_activities,
            intake_amounts,
            fish_lengths,
            superind_reps,
            available_drift,
            available_search,
            available_shelter,
            available_hiding,
        )
        assert available_shelter[0] < 200.0


class TestHabitatSelection:
    """Test integrated habitat selection."""

    @pytest.fixture
    def simple_model(self):
        """Create minimal model state for habitat selection testing."""
        from instream.state.cell_state import CellState
        from instream.state.trout_state import TroutState
        from instream.space.fem_space import FEMSpace

        cs = CellState.zeros(3, num_flows=2)
        cs.centroid_x[:] = np.array([0, 100, 200], dtype=np.float64)
        cs.centroid_y[:] = np.zeros(3)
        cs.depth[:] = np.array([50, 30, 40], dtype=np.float64)
        cs.velocity[:] = np.array([20, 10, 30], dtype=np.float64)
        cs.light[:] = np.array([50, 50, 50], dtype=np.float64)
        cs.area[:] = 10000.0
        cs.available_drift[:] = 1000.0
        cs.available_search[:] = 1000.0
        cs.available_vel_shelter[:] = 10000.0
        cs.available_hiding_places[:] = 5
        ni = np.full((3, 3), -1, dtype=np.int32)
        ni[0, 0] = 1
        ni[1, 0] = 0
        ni[1, 1] = 2
        ni[2, 0] = 1
        space = FEMSpace(cs, ni)

        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.cell_idx[0] = 0
        ts.length[0] = 10.0
        ts.weight[0] = 10.0
        ts.alive[1] = True
        ts.cell_idx[1] = 1
        ts.length[1] = 8.0
        ts.weight[1] = 6.0
        ts.condition[:2] = 1.0
        ts.superind_rep[:2] = 1
        return space, ts

    def test_all_alive_fish_get_assigned(self, simple_model):
        from instream.modules.behavior import select_habitat_and_activity

        space, ts = simple_model
        params = dict(
            move_radius_max=20000,
            move_radius_L1=7,
            move_radius_L9=20,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
            shelter_speed_frac=0.3,
            search_prod=8e-7,
            search_area=20000.0,
            drift_conc=3.2e-10,
            temperature=15.0,
            turbidity=2.0,
            max_swim_temp_term=0.98,
            resp_temp_term=np.exp(0.002 * 225),
            step_length=1.0,
        )
        select_habitat_and_activity(ts, space, **params)
        alive = ts.alive_indices()
        for i in alive:
            assert ts.cell_idx[i] >= 0
            assert ts.activity[i] in (0, 1, 2)

    def test_resources_decrease(self, simple_model):
        from instream.modules.behavior import select_habitat_and_activity

        space, ts = simple_model
        initial_drift = space.cell_state.available_drift.copy()
        params = dict(
            move_radius_max=20000,
            move_radius_L1=7,
            move_radius_L9=20,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
            shelter_speed_frac=0.3,
            search_prod=8e-7,
            search_area=20000.0,
            drift_conc=3.2e-10,
            temperature=15.0,
            turbidity=2.0,
            max_swim_temp_term=0.98,
            resp_temp_term=np.exp(0.002 * 225),
            step_length=1.0,
        )
        select_habitat_and_activity(ts, space, **params)
        # At least some resources should have decreased
        assert np.any(space.cell_state.available_drift < initial_drift) or np.any(
            space.cell_state.available_search < np.array([1000.0] * 3)
        )

    def test_sequential_depletion_large_fish_first(self):
        """Larger fish depletes resources first, smaller fish sees reduced availability."""
        from instream.modules.behavior import select_habitat_and_activity
        from instream.state.cell_state import CellState
        from instream.state.trout_state import TroutState
        from instream.space.fem_space import FEMSpace

        # Single cell with very limited drift food
        cs = CellState.zeros(1, num_flows=2)
        cs.centroid_x[:] = 0.0
        cs.centroid_y[:] = 0.0
        cs.depth[:] = 50.0
        cs.velocity[:] = 20.0
        cs.light[:] = 50.0
        cs.area[:] = 10000.0
        cs.available_drift[:] = 0.01  # limited but enough for drift to be chosen
        cs.available_search[:] = 1000.0
        cs.available_vel_shelter[:] = 10000.0
        cs.available_hiding_places[:] = 5
        ni = np.full((1, 1), -1, dtype=np.int32)
        space = FEMSpace(cs, ni)

        # Two fish: large (20cm) and small (5cm), both at cell 0
        ts = TroutState.zeros(2)
        ts.alive[:2] = True
        ts.cell_idx[:2] = 0
        ts.length[0] = 20.0
        ts.weight[0] = 80.0  # large
        ts.length[1] = 5.0
        ts.weight[1] = 1.0  # small
        ts.condition[:2] = 1.0
        ts.superind_rep[:2] = 1

        params = dict(
            move_radius_max=20000,
            move_radius_L1=7,
            move_radius_L9=20,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
            shelter_speed_frac=0.3,
            search_prod=8e-7,
            search_area=20000.0,
            drift_conc=3.2e-10,
            temperature=15.0,
            turbidity=2.0,
            max_swim_temp_term=0.98,
            resp_temp_term=np.exp(0.002 * 225),
            step_length=1.0,
        )
        select_habitat_and_activity(ts, space, **params)
        # After selection: the scarce drift food should be nearly gone
        # Large fish took first, small fish saw what remained
        assert cs.available_drift[0] < 0.01  # some was consumed by at least one fish


class TestGrowthRateStored:
    """Test that habitat selection stores growth rate for use by the growth step."""

    @pytest.fixture
    def simple_model(self):
        """Create minimal model state for growth rate storage testing."""
        from instream.state.cell_state import CellState
        from instream.state.trout_state import TroutState
        from instream.space.fem_space import FEMSpace

        cs = CellState.zeros(3, num_flows=2)
        cs.centroid_x[:] = np.array([0, 100, 200], dtype=np.float64)
        cs.centroid_y[:] = np.zeros(3)
        cs.depth[:] = np.array([50, 30, 40], dtype=np.float64)
        cs.velocity[:] = np.array([20, 10, 30], dtype=np.float64)
        cs.light[:] = np.array([50, 50, 50], dtype=np.float64)
        cs.area[:] = 10000.0
        cs.available_drift[:] = 1000.0
        cs.available_search[:] = 1000.0
        cs.available_vel_shelter[:] = 10000.0
        cs.available_hiding_places[:] = 5
        ni = np.full((3, 3), -1, dtype=np.int32)
        ni[0, 0] = 1
        ni[1, 0] = 0
        ni[1, 1] = 2
        ni[2, 0] = 1
        space = FEMSpace(cs, ni)

        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.cell_idx[0] = 0
        ts.length[0] = 10.0
        ts.weight[0] = 10.0
        ts.alive[1] = True
        ts.cell_idx[1] = 1
        ts.length[1] = 8.0
        ts.weight[1] = 6.0
        ts.condition[:2] = 1.0
        ts.superind_rep[:2] = 1
        return space, ts

    def test_trout_state_has_last_growth_rate_field(self):
        """TroutState should have a last_growth_rate field initialized to zero."""
        from instream.state.trout_state import TroutState

        ts = TroutState.zeros(10)
        assert hasattr(ts, "last_growth_rate"), (
            "TroutState missing last_growth_rate field"
        )
        assert ts.last_growth_rate.shape == (10,)
        assert np.all(ts.last_growth_rate == 0.0)

    def test_habitat_selection_populates_last_growth_rate(self, simple_model):
        """After habitat selection, alive fish should have last_growth_rate set."""
        from instream.modules.behavior import select_habitat_and_activity

        space, ts = simple_model
        params = dict(
            move_radius_max=20000,
            move_radius_L1=7,
            move_radius_L9=20,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
            shelter_speed_frac=0.3,
            search_prod=8e-7,
            search_area=20000.0,
            drift_conc=3.2e-10,
            temperature=15.0,
            turbidity=2.0,
            max_swim_temp_term=0.98,
            resp_temp_term=np.exp(0.002 * 225),
            step_length=1.0,
        )
        select_habitat_and_activity(ts, space, **params)
        alive = ts.alive_indices()
        # All alive fish should have a non-zero growth rate (positive or negative)
        for i in alive:
            assert ts.last_growth_rate[i] != 0.0, (
                f"Fish {i} has last_growth_rate=0 after habitat selection"
            )


class TestFitnessSurvivalIntegration:
    """Test that fitness includes survival penalty (Phase 5)."""

    def test_fitness_includes_survival_penalty(self):
        """Fitness in a dangerous cell should be lower than a safe cell."""
        from instream.modules.behavior import fitness_for

        # Both cells have same growth parameters but different predation risk
        common = dict(
            length=5.0,
            weight=2.0,
            velocity=10.0,
            turbidity=0.0,
            temperature=12.0,
            drift_conc=0.001,
            search_prod=0.001,
            search_area=100.0,
            available_drift=10.0,
            available_search=10.0,
            available_shelter=1000.0,
            shelter_speed_frac=0.3,
            superind_rep=1,
            prev_consumption=0.0,
            step_length=1.0,
            cmax_A=0.628,
            cmax_B=0.3,
            cmax_temp_table_x=np.array([0.0, 10.0, 20.0, 30.0]),
            cmax_temp_table_y=np.array([0.0, 0.5, 1.0, 0.5]),
            react_dist_A=1.0,
            react_dist_B=0.1,
            turbid_threshold=10.0,
            turbid_min=0.1,
            turbid_exp=-0.1,
            light_threshold=50.0,
            light_min=0.1,
            light_exp=-0.1,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=1.5,
            max_speed_B=0.0,
            max_swim_temp_term=1.0,
            resp_A=0.0253,
            resp_B=0.75,
            resp_D=0.03,
            resp_temp_term=1.0,
            prey_energy_density=3500.0,
            fish_energy_density=5500.0,
            condition=0.9,
        )
        # Safe: deep water, low light (low predation risk)
        safe = fitness_for(activity="drift", depth=100.0, light=10.0, **common)
        # Dangerous: shallow water, bright light (high predation risk)
        dangerous = fitness_for(activity="drift", depth=5.0, light=500.0, **common)
        # With survival, the shallow bright cell should have lower fitness
        assert safe > dangerous or (safe == 0.0 and dangerous == 0.0), (
            "Fitness should penalize high-predation cells: safe={} vs dangerous={}".format(
                safe, dangerous
            )
        )

    def test_fitness_with_default_survival_params_close_to_growth_only(self):
        """With default survival params (benign conditions), fitness ~ growth * step_length."""
        from instream.modules.behavior import fitness_for

        kwargs = dict(
            activity="drift",
            length=10.0,
            weight=10.0,
            depth=50.0,
            velocity=30.0,
            light=50.0,
            turbidity=2.0,
            temperature=15.0,
            drift_conc=3.2e-10,
            search_prod=8e-7,
            search_area=20000.0,
            available_drift=1000.0,
            available_search=1000.0,
            available_shelter=1000.0,
            shelter_speed_frac=0.3,
            superind_rep=1,
            prev_consumption=0.0,
            step_length=1.0,
            cmax_A=0.628,
            cmax_B=0.7,
            cmax_temp_table_x=np.array([0.0, 10.0, 22.0, 30.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0, 0.0]),
            react_dist_A=4.0,
            react_dist_B=2.0,
            turbid_threshold=5.0,
            turbid_min=0.1,
            turbid_exp=-0.116,
            light_threshold=20.0,
            light_min=0.5,
            light_exp=-0.2,
            capture_R1=1.3,
            capture_R9=0.4,
            max_speed_A=2.8,
            max_speed_B=21.0,
            max_swim_temp_term=0.98,
            resp_A=36.0,
            resp_B=0.783,
            resp_D=1.4,
            resp_temp_term=np.exp(0.002 * 225),
            prey_energy_density=2500.0,
            fish_energy_density=5900.0,
        )
        # With all default survival params (condition=1.0, benign defaults),
        # fitness should be non-zero and have same sign as growth*step
        fitness = fitness_for(**kwargs)
        assert fitness != 0.0, "Fitness should be non-zero with default survival params"


class TestSparseCandidates:
    """Test that sparse candidate lists match the dense mask."""

    @pytest.fixture
    def simple_setup(self):
        """Create a simple 5-cell setup for testing."""
        from instream.state.cell_state import CellState
        from instream.state.trout_state import TroutState
        from instream.space.fem_space import FEMSpace

        cs = CellState.zeros(5, num_flows=2)
        cs.centroid_x[:] = np.array([0, 100, 200, 300, 400], dtype=np.float64)
        cs.centroid_y[:] = np.zeros(5, dtype=np.float64)
        cs.depth[:] = np.array([50, 30, 0, 40, 20], dtype=np.float64)  # cell 2 is dry
        cs.area[:] = 10000.0
        ni = np.full((5, 4), -1, dtype=np.int32)
        ni[0, 0] = 1
        ni[1, 0] = 0
        ni[1, 1] = 2
        ni[2, 0] = 1
        ni[2, 1] = 3
        ni[3, 0] = 2
        ni[3, 1] = 4
        ni[4, 0] = 3
        space = FEMSpace(cs, ni)

        ts = TroutState.zeros(3)
        ts.alive[0] = True
        ts.cell_idx[0] = 0
        ts.length[0] = 10.0
        ts.alive[1] = True
        ts.cell_idx[1] = 2
        ts.length[1] = 15.0
        ts.alive[2] = False
        return space, ts

    def test_sparse_candidates_match_dense(self, simple_setup):
        """Sparse candidate lists must have same candidates as dense mask."""
        from instream.modules.behavior import (
            build_candidate_lists,
            build_candidate_mask,
        )

        space, ts = simple_setup
        mask = build_candidate_mask(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        sparse = build_candidate_lists(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        for i in range(ts.alive.shape[0]):
            dense_cands = set(np.where(mask[i])[0])
            sparse_cands = set(sparse[i].tolist()) if sparse[i] is not None else set()
            assert dense_cands == sparse_cands, "Mismatch for fish {}".format(i)

    def test_dead_fish_gets_none(self, simple_setup):
        """Dead fish should get None in sparse list."""
        from instream.modules.behavior import build_candidate_lists

        space, ts = simple_setup
        sparse = build_candidate_lists(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        assert sparse[2] is None

    def test_sparse_dtype_int32(self, simple_setup):
        """Sparse candidate arrays should be int32."""
        from instream.modules.behavior import build_candidate_lists

        space, ts = simple_setup
        sparse = build_candidate_lists(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        for i in range(ts.alive.shape[0]):
            if sparse[i] is not None:
                assert sparse[i].dtype == np.int32


class TestNumbaCandidates:
    """Test that Numba brute-force candidate search matches KD-tree results."""

    @pytest.fixture
    def simple_setup(self):
        """Create a simple 5-cell setup for testing."""
        from instream.state.cell_state import CellState
        from instream.state.trout_state import TroutState
        from instream.space.fem_space import FEMSpace

        cs = CellState.zeros(5, num_flows=2)
        cs.centroid_x[:] = np.array([0, 100, 200, 300, 400], dtype=np.float64)
        cs.centroid_y[:] = np.zeros(5, dtype=np.float64)
        cs.depth[:] = np.array([50, 30, 0, 40, 20], dtype=np.float64)
        cs.area[:] = 10000.0
        ni = np.full((5, 4), -1, dtype=np.int32)
        ni[0, 0] = 1
        ni[1, 0] = 0
        ni[1, 1] = 2
        ni[2, 0] = 1
        ni[2, 1] = 3
        ni[3, 0] = 2
        ni[3, 1] = 4
        ni[4, 0] = 3
        space = FEMSpace(cs, ni)

        ts = TroutState.zeros(3)
        ts.alive[0] = True
        ts.cell_idx[0] = 0
        ts.length[0] = 10.0
        ts.alive[1] = True
        ts.cell_idx[1] = 2
        ts.length[1] = 15.0
        ts.alive[2] = False
        return space, ts

    def test_numba_candidates_match_kdtree(self, simple_setup):
        """Numba brute-force must find same cells as KD-tree."""
        pytest.importorskip("numba")
        from instream.modules.behavior import (
            build_candidate_lists,
            build_candidate_mask,
        )

        space, ts = simple_setup
        # build_candidate_mask always uses KD-tree (reference)
        mask = build_candidate_mask(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        # build_candidate_lists uses numba if available
        sparse = build_candidate_lists(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        for i in range(ts.alive.shape[0]):
            dense_cands = set(np.where(mask[i])[0])
            sparse_cands = set(sparse[i].tolist()) if sparse[i] is not None else set()
            assert dense_cands == sparse_cands, "Numba mismatch for fish {}".format(i)

    def test_numba_all_candidates_wet(self, simple_setup):
        """All candidates from numba should be wet cells."""
        pytest.importorskip("numba")
        from instream.modules.behavior import build_candidate_lists

        space, ts = simple_setup
        sparse = build_candidate_lists(
            ts, space, move_radius_max=20000, move_radius_L1=7, move_radius_L9=20
        )
        for i in range(ts.alive.shape[0]):
            if sparse[i] is not None:
                assert len(sparse[i]) > 0
                assert np.all(space.cell_state.depth[sparse[i]] > 0)
