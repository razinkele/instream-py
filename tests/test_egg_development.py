"""Tests for egg development and redd emergence."""
import numpy as np


class TestEggDevelopment:
    def test_development_increases_with_temperature(self):
        from salmopy.modules.spawning import develop_eggs
        d_cold = develop_eggs(frac_developed=0.0, temperature=5.0, step_length=1.0,
                              devel_A=0.00190, devel_B=0.000500, devel_C=0.0000360)
        d_warm = develop_eggs(frac_developed=0.0, temperature=15.0, step_length=1.0,
                              devel_A=0.00190, devel_B=0.000500, devel_C=0.0000360)
        assert d_warm > d_cold

    def test_development_at_zero_degrees(self):
        from salmopy.modules.spawning import develop_eggs
        d = develop_eggs(frac_developed=0.0, temperature=0.0, step_length=1.0,
                         devel_A=0.00190, devel_B=0.000500, devel_C=0.0000360)
        # At T=0: increment = A + B*0 + C*0 = 0.0019
        np.testing.assert_allclose(d, 0.00190, rtol=1e-10)

    def test_development_accumulates(self):
        from salmopy.modules.spawning import develop_eggs
        d1 = develop_eggs(frac_developed=0.3, temperature=10.0, step_length=1.0,
                          devel_A=0.00190, devel_B=0.000500, devel_C=0.0000360)
        d2 = develop_eggs(frac_developed=0.0, temperature=10.0, step_length=1.0,
                          devel_A=0.00190, devel_B=0.000500, devel_C=0.0000360)
        # Both should get the same increment (development rate doesn't depend on current state)
        np.testing.assert_allclose(d1 - 0.3, d2, rtol=1e-10)

    def test_proportional_to_step_length(self):
        from salmopy.modules.spawning import develop_eggs
        d_full = develop_eggs(frac_developed=0.0, temperature=10.0, step_length=1.0,
                              devel_A=0.00190, devel_B=0.000500, devel_C=0.0000360)
        d_half = develop_eggs(frac_developed=0.0, temperature=10.0, step_length=0.5,
                              devel_A=0.00190, devel_B=0.000500, devel_C=0.0000360)
        np.testing.assert_allclose(d_half, d_full / 2, rtol=1e-10)

    def test_reaches_one_eventually(self):
        from salmopy.modules.spawning import develop_eggs
        frac = 0.0
        for _ in range(500):  # 500 days at T=10 should be enough
            frac = develop_eggs(frac_developed=frac, temperature=10.0, step_length=1.0,
                                devel_A=0.00190, devel_B=0.000500, devel_C=0.0000360)
            if frac >= 1.0:
                break
        assert frac >= 1.0


class TestReddEmergence:
    def test_emergence_when_developed(self):
        from salmopy.state.redd_state import ReddState
        from salmopy.state.trout_state import TroutState
        from salmopy.modules.spawning import redd_emergence
        rs = ReddState.zeros(5)
        rs.alive[0] = True
        rs.num_eggs[0] = 100
        rs.frac_developed[0] = 1.1  # fully developed
        rs.species_idx[0] = 0
        rs.cell_idx[0] = 3
        rs.reach_idx[0] = 0

        ts = TroutState.zeros(200)
        rng = np.random.default_rng(42)
        redd_emergence(rs, ts, rng,
                       emerge_length_min=3.5, emerge_length_mode=3.8,
                       emerge_length_max=4.1, weight_A=0.0041, weight_B=3.49,
                       species_index=0)
        # Some new trout should be created
        assert ts.num_alive() > 0

    def test_emerged_trout_has_correct_species(self):
        from salmopy.state.redd_state import ReddState
        from salmopy.state.trout_state import TroutState
        from salmopy.modules.spawning import redd_emergence
        rs = ReddState.zeros(5)
        rs.alive[0] = True
        rs.num_eggs[0] = 50
        rs.frac_developed[0] = 1.5
        rs.species_idx[0] = 0
        rs.cell_idx[0] = 3
        rs.reach_idx[0] = 0

        ts = TroutState.zeros(200)
        rng = np.random.default_rng(42)
        redd_emergence(rs, ts, rng,
                       emerge_length_min=3.5, emerge_length_mode=3.8,
                       emerge_length_max=4.1, weight_A=0.0041, weight_B=3.49,
                       species_index=0)
        alive = ts.alive_indices()
        assert np.all(ts.species_idx[alive] == 0)

    def test_emerged_trout_length_in_range(self):
        from salmopy.state.redd_state import ReddState
        from salmopy.state.trout_state import TroutState
        from salmopy.modules.spawning import redd_emergence
        rs = ReddState.zeros(5)
        rs.alive[0] = True
        rs.num_eggs[0] = 100
        rs.frac_developed[0] = 2.0
        rs.species_idx[0] = 0
        rs.cell_idx[0] = 3
        rs.reach_idx[0] = 0

        ts = TroutState.zeros(200)
        rng = np.random.default_rng(42)
        redd_emergence(rs, ts, rng,
                       emerge_length_min=3.5, emerge_length_mode=3.8,
                       emerge_length_max=4.1, weight_A=0.0041, weight_B=3.49,
                       species_index=0)
        alive = ts.alive_indices()
        assert np.all(ts.length[alive] >= 3.5)
        assert np.all(ts.length[alive] <= 4.1)

    def test_emerged_trout_age_zero(self):
        from salmopy.state.redd_state import ReddState
        from salmopy.state.trout_state import TroutState
        from salmopy.modules.spawning import redd_emergence
        rs = ReddState.zeros(5)
        rs.alive[0] = True
        rs.num_eggs[0] = 10
        rs.frac_developed[0] = 1.5
        rs.species_idx[0] = 0
        rs.cell_idx[0] = 3
        rs.reach_idx[0] = 0

        ts = TroutState.zeros(200)
        rng = np.random.default_rng(42)
        redd_emergence(rs, ts, rng,
                       emerge_length_min=3.5, emerge_length_mode=3.8,
                       emerge_length_max=4.1, weight_A=0.0041, weight_B=3.49,
                       species_index=0)
        alive = ts.alive_indices()
        assert np.all(ts.age[alive] == 0)

    def test_redd_dies_when_empty(self):
        """Arc E iter3 (2026-04-20): emergence spreads over 10 days. After
        10 calls, all 5 eggs should be drained and the redd dead."""
        from salmopy.state.redd_state import ReddState
        from salmopy.state.trout_state import TroutState
        from salmopy.modules.spawning import redd_emergence
        rs = ReddState.zeros(5)
        rs.alive[0] = True
        rs.num_eggs[0] = 5
        rs.frac_developed[0] = 10.0  # very developed — all eggs should emerge
        rs.species_idx[0] = 0
        rs.cell_idx[0] = 3
        rs.reach_idx[0] = 0

        ts = TroutState.zeros(200)
        rng = np.random.default_rng(42)
        for _ in range(10):
            redd_emergence(rs, ts, rng,
                           emerge_length_min=3.5, emerge_length_mode=3.8,
                           emerge_length_max=4.1, weight_A=0.0041, weight_B=3.49,
                           species_index=0, superind_max_rep=1)
        # Redd should be dead (all eggs emerged after 10-day spread)
        assert not rs.alive[0]

    def test_no_emergence_before_full_development(self):
        from salmopy.state.redd_state import ReddState
        from salmopy.state.trout_state import TroutState
        from salmopy.modules.spawning import redd_emergence
        rs = ReddState.zeros(5)
        rs.alive[0] = True
        rs.num_eggs[0] = 100
        rs.frac_developed[0] = 0.5  # not fully developed
        rs.species_idx[0] = 0

        ts = TroutState.zeros(200)
        rng = np.random.default_rng(42)
        redd_emergence(rs, ts, rng,
                       emerge_length_min=3.5, emerge_length_mode=3.8,
                       emerge_length_max=4.1, weight_A=0.0041, weight_B=3.49,
                       species_index=0)
        assert ts.num_alive() == 0  # no emergence
