"""Tests for SoA state containers."""
import numpy as np
import pytest


class TestTroutState:
    def test_zeros_creates_correct_shape(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(100)
        assert ts.length.shape == (100,)
        assert ts.weight.shape == (100,)
        assert ts.alive.shape == (100,)
        assert ts.condition.shape == (100,)
        assert ts.age.shape == (100,)
        assert ts.species_idx.shape == (100,)
        assert ts.cell_idx.shape == (100,)
        assert ts.reach_idx.shape == (100,)
        assert ts.activity.shape == (100,)
        assert ts.sex.shape == (100,)
        assert ts.superind_rep.shape == (100,)
        assert ts.life_history.shape == (100,)

    def test_zeros_all_dead(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(100)
        assert ts.num_alive() == 0

    def test_dtype_float64(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(50)
        assert ts.length.dtype == np.float64
        assert ts.weight.dtype == np.float64
        assert ts.condition.dtype == np.float64

    def test_first_dead_slot_on_empty(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(100)
        assert ts.first_dead_slot() == 0

    def test_first_dead_slot_with_alive(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(100)
        ts.alive[0] = True
        ts.alive[1] = True
        ts.alive[2] = True
        assert ts.first_dead_slot() == 3

    def test_first_dead_slot_when_full_returns_minus_one(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(5)
        ts.alive[:] = True
        assert ts.first_dead_slot() == -1

    def test_alive_indices(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(10)
        ts.alive[2] = True
        ts.alive[7] = True
        indices = ts.alive_indices()
        np.testing.assert_array_equal(indices, [2, 7])

    def test_has_memory_arrays(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(50, max_steps_per_day=6)
        assert ts.growth_memory.shape == (50, 6)
        assert ts.consumption_memory.shape == (50, 6)
        assert ts.survival_memory.shape == (50, 6)

    def test_has_cached_intermediates(self):
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(50)
        assert ts.resp_std_wt_term.shape == (50,)
        assert ts.max_speed_len_term.shape == (50,)
        assert ts.cmax_wt_term.shape == (50,)


class TestReddState:
    def test_zeros_creates_correct_shape(self):
        from instream.state.redd_state import ReddState
        rs = ReddState.zeros(200)
        assert rs.alive.shape == (200,)
        assert rs.num_eggs.shape == (200,)
        assert rs.frac_developed.shape == (200,)
        assert rs.species_idx.shape == (200,)
        assert rs.cell_idx.shape == (200,)

    def test_zeros_all_dead(self):
        from instream.state.redd_state import ReddState
        rs = ReddState.zeros(200)
        assert rs.num_alive() == 0

    def test_has_output_fields(self):
        from instream.state.redd_state import ReddState
        rs = ReddState.zeros(50)
        assert rs.eggs_initial.shape == (50,)
        assert rs.eggs_lo_temp.shape == (50,)
        assert rs.eggs_hi_temp.shape == (50,)
        assert rs.eggs_dewatering.shape == (50,)
        assert rs.eggs_scour.shape == (50,)


class TestCellState:
    def test_has_static_fields(self):
        from instream.state.cell_state import CellState
        cs = CellState.zeros(26)
        assert cs.area.shape == (26,)
        assert cs.centroid_x.shape == (26,)
        assert cs.centroid_y.shape == (26,)
        assert cs.reach_idx.shape == (26,)
        assert cs.num_hiding_places.shape == (26,)
        assert cs.dist_escape.shape == (26,)
        assert cs.frac_vel_shelter.shape == (26,)
        assert cs.frac_spawn.shape == (26,)

    def test_has_dynamic_fields(self):
        from instream.state.cell_state import CellState
        cs = CellState.zeros(26)
        assert cs.depth.shape == (26,)
        assert cs.velocity.shape == (26,)
        assert cs.light.shape == (26,)

    def test_has_resource_fields(self):
        from instream.state.cell_state import CellState
        cs = CellState.zeros(26)
        assert cs.available_drift.shape == (26,)
        assert cs.available_search.shape == (26,)
        assert cs.available_vel_shelter.shape == (26,)
        assert cs.available_hiding_places.shape == (26,)

    def test_has_hydraulic_tables(self):
        from instream.state.cell_state import CellState
        cs = CellState.zeros(26, num_flows=10)
        assert cs.depth_table_flows.shape == (10,)
        assert cs.depth_table_values.shape == (26, 10)
        assert cs.vel_table_flows.shape == (10,)
        assert cs.vel_table_values.shape == (26, 10)


class TestReachState:
    def test_has_timeseries_fields(self):
        from instream.state.reach_state import ReachState
        rs = ReachState.zeros(3)
        assert rs.flow.shape == (3,)
        assert rs.temperature.shape == (3,)
        assert rs.turbidity.shape == (3,)

    def test_has_intermediate_arrays(self):
        from instream.state.reach_state import ReachState
        rs = ReachState.zeros(3, num_species=2)
        assert rs.cmax_temp_func.shape == (3, 2)
        assert rs.max_swim_temp_term.shape == (3, 2)
        assert rs.resp_temp_term.shape == (3, 2)
        assert rs.scour_param.shape == (3,)
        assert rs.is_flow_peak.shape == (3,)


class TestParams:
    def test_species_params_is_frozen(self):
        from instream.state.params import SpeciesParams
        sp = SpeciesParams(
            name="Rainbow",
            cmax_A=0.628, cmax_B=0.7,
            weight_A=0.0041, weight_B=3.49,
        )
        with pytest.raises((AttributeError, TypeError)):
            sp.cmax_A = 999.0

    def test_species_params_stores_values(self):
        from instream.state.params import SpeciesParams
        sp = SpeciesParams(
            name="Rainbow",
            cmax_A=0.628, cmax_B=0.7,
            weight_A=0.0041, weight_B=3.49,
        )
        assert sp.cmax_A == 0.628
        assert sp.weight_B == 3.49

    def test_params_store_interpolation_tables_as_numpy(self):
        from instream.state.params import SpeciesParams
        sp = SpeciesParams(
            name="Test",
            cmax_A=1.0, cmax_B=1.0,
            weight_A=1.0, weight_B=1.0,
            cmax_temp_table_x=np.array([0.0, 10.0, 20.0]),
            cmax_temp_table_y=np.array([0.05, 0.5, 1.0]),
        )
        assert isinstance(sp.cmax_temp_table_x, np.ndarray)
        assert sp.cmax_temp_table_x.dtype == np.float64
