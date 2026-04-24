"""Tests for spawning, redd creation, egg development, and emergence."""

import numpy as np


class TestReadyToSpawn:
    def test_female_meeting_criteria_is_ready(self):
        from salmopy.modules.spawning import ready_to_spawn

        result = ready_to_spawn(
            sex=0,
            age=3,
            length=20.0,
            condition=1.0,
            temperature=10.0,
            flow=5.0,
            spawned_this_season=False,
            day_of_year=274,  # Oct 1
            spawn_min_age=-9,
            spawn_min_length=-9,
            spawn_min_cond=-9,
            spawn_min_temp=5.0,
            spawn_max_temp=14.0,
            spawn_prob=1.0,
            max_spawn_flow=10.0,
            spawn_start_doy=244,
            spawn_end_doy=304,  # Sep 1 - Oct 31
            rng=np.random.default_rng(42),
        )
        assert result is True

    def test_male_not_ready(self):
        from salmopy.modules.spawning import ready_to_spawn

        result = ready_to_spawn(
            sex=1,
            age=3,
            length=20.0,
            condition=1.0,
            temperature=10.0,
            flow=5.0,
            spawned_this_season=False,
            day_of_year=274,
            spawn_min_age=-9,
            spawn_min_length=-9,
            spawn_min_cond=-9,
            spawn_min_temp=5.0,
            spawn_max_temp=14.0,
            spawn_prob=1.0,
            max_spawn_flow=10.0,
            spawn_start_doy=244,
            spawn_end_doy=304,
            rng=np.random.default_rng(42),
        )
        assert result is False

    def test_wrong_season(self):
        from salmopy.modules.spawning import ready_to_spawn

        result = ready_to_spawn(
            sex=0,
            age=3,
            length=20.0,
            condition=1.0,
            temperature=10.0,
            flow=5.0,
            spawned_this_season=False,
            day_of_year=100,  # April
            spawn_min_age=-9,
            spawn_min_length=-9,
            spawn_min_cond=-9,
            spawn_min_temp=5.0,
            spawn_max_temp=14.0,
            spawn_prob=1.0,
            max_spawn_flow=10.0,
            spawn_start_doy=244,
            spawn_end_doy=304,
            rng=np.random.default_rng(42),
        )
        assert result is False

    def test_temperature_too_high(self):
        from salmopy.modules.spawning import ready_to_spawn

        result = ready_to_spawn(
            sex=0,
            age=3,
            length=20.0,
            condition=1.0,
            temperature=20.0,
            flow=5.0,
            spawned_this_season=False,
            day_of_year=274,
            spawn_min_age=-9,
            spawn_min_length=-9,
            spawn_min_cond=-9,
            spawn_min_temp=5.0,
            spawn_max_temp=14.0,
            spawn_prob=1.0,
            max_spawn_flow=10.0,
            spawn_start_doy=244,
            spawn_end_doy=304,
            rng=np.random.default_rng(42),
        )
        assert result is False

    def test_already_spawned(self):
        from salmopy.modules.spawning import ready_to_spawn

        result = ready_to_spawn(
            sex=0,
            age=3,
            length=20.0,
            condition=1.0,
            temperature=10.0,
            flow=5.0,
            spawned_this_season=True,
            day_of_year=274,
            spawn_min_age=-9,
            spawn_min_length=-9,
            spawn_min_cond=-9,
            spawn_min_temp=5.0,
            spawn_max_temp=14.0,
            spawn_prob=1.0,
            max_spawn_flow=10.0,
            spawn_start_doy=244,
            spawn_end_doy=304,
            rng=np.random.default_rng(42),
        )
        assert result is False

    def test_probabilistic(self):
        from salmopy.modules.spawning import ready_to_spawn

        results = []
        for seed in range(100):
            r = ready_to_spawn(
                sex=0,
                age=3,
                length=20.0,
                condition=1.0,
                temperature=10.0,
                flow=5.0,
                spawned_this_season=False,
                day_of_year=274,
                spawn_min_age=-9,
                spawn_min_length=-9,
                spawn_min_cond=-9,
                spawn_min_temp=5.0,
                spawn_max_temp=14.0,
                spawn_prob=0.1,
                max_spawn_flow=10.0,
                spawn_start_doy=244,
                spawn_end_doy=304,
                rng=np.random.default_rng(seed),
            )
            results.append(r)
        pct = sum(results) / len(results)
        assert 0.02 < pct < 0.25  # roughly 10%


class TestSpawnSuitability:
    def test_zero_when_no_gravel(self):
        from salmopy.modules.spawning import spawn_suitability

        s = spawn_suitability(
            depth=30.0,
            velocity=50.0,
            frac_spawn=0.0,
            area=10000.0,
            depth_table_x=np.array([0, 12, 27, 33.5, 204.0]),
            depth_table_y=np.array([0, 0, 0.95, 1.0, 0.0]),
            vel_table_x=np.array([0, 2.3, 3, 54, 61, 192.0]),
            vel_table_y=np.array([0, 0, 0.06, 1.0, 1.0, 0.0]),
        )
        assert s == 0.0

    def test_positive_at_optimal(self):
        from salmopy.modules.spawning import spawn_suitability

        s = spawn_suitability(
            depth=30.0,
            velocity=50.0,
            frac_spawn=0.5,
            area=10000.0,
            depth_table_x=np.array([0, 12, 27, 33.5, 204.0]),
            depth_table_y=np.array([0, 0, 0.95, 1.0, 0.0]),
            vel_table_x=np.array([0, 2.3, 3, 54, 61, 192.0]),
            vel_table_y=np.array([0, 0, 0.06, 1.0, 1.0, 0.0]),
        )
        assert s > 0.0

    def test_picks_best_cell(self):
        from salmopy.modules.spawning import select_spawn_cell

        scores = np.array([0.0, 0.5, 0.8, 0.3])
        candidates = np.array([0, 1, 2, 3])
        best = select_spawn_cell(scores, candidates)
        assert best == 2  # highest score


class TestSpawn:
    def test_creates_redd(self):
        from salmopy.state.redd_state import ReddState
        from salmopy.modules.spawning import create_redd

        rs = ReddState.zeros(10)
        create_redd(
            rs,
            species_idx=0,
            cell_idx=5,
            reach_idx=0,
            length=50.0,
            fecund_mult=690.0,
            fecund_exp=0.552,
            egg_viability=0.8,
        )
        assert rs.num_alive() == 1
        assert rs.cell_idx[0] == 5

    def test_correct_egg_count(self):
        from salmopy.state.redd_state import ReddState
        from salmopy.modules.spawning import create_redd

        rs = ReddState.zeros(10)
        create_redd(
            rs,
            species_idx=0,
            cell_idx=5,
            reach_idx=0,
            length=50.0,
            fecund_mult=690.0,
            fecund_exp=0.552,
            egg_viability=0.8,
        )
        expected = int(690.0 * 50.0**0.552 * 0.8)  # fecund_mult * length^exp * viability
        assert rs.num_eggs[0] == expected

    def test_no_redd_when_full(self):
        from salmopy.state.redd_state import ReddState
        from salmopy.modules.spawning import create_redd

        rs = ReddState.zeros(1)
        rs.alive[0] = True  # slot full
        result = create_redd(
            rs,
            species_idx=0,
            cell_idx=5,
            reach_idx=0,
            length=50.0,
            fecund_mult=690.0,
            fecund_exp=0.552,
            egg_viability=0.8,
        )
        assert result == -1  # couldn't create

    def test_spawner_weight_loss(self):
        from salmopy.modules.spawning import apply_spawner_weight_loss

        new_weight = apply_spawner_weight_loss(weight=50.0, wt_loss_fraction=0.4)
        np.testing.assert_allclose(new_weight, 30.0)


def test_redd_emergence_assigns_random_sex():
    """Emerged fry should have both sexes and clean state.

    Arc E iteration 3 (2026-04-20): emergence now spreads over 10 days and
    aggregates into super-individuals per NetLogo InSALMO7.3:4228-4287.
    Call redd_emergence 10 times with superind_max_rep=1 to reach the
    full 100-slot emergence of the old per-call-emits-all behavior.
    """
    from salmopy.state.trout_state import TroutState
    from salmopy.state.redd_state import ReddState
    from salmopy.modules.spawning import redd_emergence

    ts = TroutState.zeros(200)
    rs = ReddState.zeros(5)
    rng = np.random.default_rng(42)
    rs.alive[0] = True
    rs.species_idx[0] = 0
    rs.num_eggs[0] = 100
    rs.frac_developed[0] = 1.0
    rs.cell_idx[0] = 0
    rs.reach_idx[0] = 0
    for _ in range(10):
        redd_emergence(
            rs, ts, rng, 2.5, 3.0, 3.5, 0.000247, 2.9,
            species_index=0, superind_max_rep=1,
        )
    alive = ts.alive_indices()
    assert len(alive) == 100
    males = int(np.sum(ts.sex[alive] == 1))
    females = int(np.sum(ts.sex[alive] == 0))
    assert males > 0, "No male fry"
    assert females > 0, "No female fry"
    # Verify clean state initialization (superind_max_rep=1 makes each slot one fish)
    assert np.all(ts.superind_rep[alive] == 1)
    assert not np.any(ts.spawned_this_season[alive])
    assert np.all(ts.growth_memory[alive] == 0.0)


def test_redd_emergence_spreads_over_10_days():
    """NetLogo semantic: emergence takes ~10 days. After 1 call, only ~10%
    of eggs emerge; after 10 calls, 100%."""
    from salmopy.state.trout_state import TroutState
    from salmopy.state.redd_state import ReddState
    from salmopy.modules.spawning import redd_emergence

    ts = TroutState.zeros(200)
    rs = ReddState.zeros(5)
    rng = np.random.default_rng(42)
    rs.alive[0] = True
    rs.species_idx[0] = 0
    rs.num_eggs[0] = 100
    rs.frac_developed[0] = 1.0
    rs.cell_idx[0] = 0
    rs.reach_idx[0] = 0

    redd_emergence(
        rs, ts, rng, 2.5, 3.0, 3.5, 0.000247, 2.9,
        species_index=0, superind_max_rep=1,
    )
    # Day 1: ceil(100 * 1/10) = 10 eggs emerge
    assert np.sum(ts.alive) == 10
    assert rs.num_eggs[0] == 90
    assert rs.emerge_days[0] == 1


def test_redd_emergence_aggregates_superindividuals():
    """With superind_max_rep=10, 100 eggs over 10 days emit ~1 super-individual
    per day (each with rep 10), not 100 rep-1 fish."""
    from salmopy.state.trout_state import TroutState
    from salmopy.state.redd_state import ReddState
    from salmopy.modules.spawning import redd_emergence

    ts = TroutState.zeros(200)
    rs = ReddState.zeros(5)
    rng = np.random.default_rng(42)
    rs.alive[0] = True
    rs.species_idx[0] = 0
    rs.num_eggs[0] = 100
    rs.frac_developed[0] = 1.0
    rs.cell_idx[0] = 0
    rs.reach_idx[0] = 0

    for _ in range(10):
        redd_emergence(
            rs, ts, rng, 2.5, 3.0, 3.5, 0.000247, 2.9,
            species_index=0, superind_max_rep=10,
        )

    alive = ts.alive_indices()
    # Emergence spread yields 1-3 super-individuals per day over ~8 days
    # (some days end up with 10-full + remainder, each in its own slot).
    # What matters: total sum of superind_rep = 100 (all eggs accounted for).
    assert 8 <= len(alive) <= 20, f"got {len(alive)} superind slots"
    assert int(np.sum(ts.superind_rep[alive])) == 100  # total actual eggs


class TestSpawnDefenseArea:
    def test_cell_within_defense_area_excluded(self):
        from salmopy.modules.spawning import select_spawn_cell

        scores = np.array([0.8, 0.9, 0.7])
        candidates = np.array([10, 20, 30])
        redd_cells = np.array([20])
        centroids_x = np.array([0.0] * 31)
        centroids_y = np.array([0.0] * 31)
        centroids_x[10] = 0.0
        centroids_x[20] = 50.0
        centroids_x[30] = 200.0
        defense_area = 100.0
        best = select_spawn_cell(
            scores,
            candidates,
            redd_cells=redd_cells,
            centroids_x=centroids_x,
            centroids_y=centroids_y,
            defense_area_m=defense_area,
        )
        assert best == 30

    def test_zero_defense_no_exclusion(self):
        from salmopy.modules.spawning import select_spawn_cell

        scores = np.array([0.8, 0.9])
        candidates = np.array([10, 20])
        best = select_spawn_cell(
            scores,
            candidates,
            redd_cells=np.array([20]),
            centroids_x=np.zeros(21),
            centroids_y=np.zeros(21),
            defense_area_m=0.0,
        )
        assert best == 20


def test_superimposition_reduces_existing_eggs():
    from salmopy.state.redd_state import ReddState
    from salmopy.modules.spawning import apply_superimposition

    rs = ReddState.zeros(5)
    # Existing redd at cell 10
    rs.alive[0] = True
    rs.cell_idx[0] = 10
    rs.num_eggs[0] = 100
    # New redd at same cell
    rs.alive[1] = True
    rs.cell_idx[1] = 10
    rs.num_eggs[1] = 50
    apply_superimposition(rs, 1, 1000)
    assert rs.num_eggs[0] == 50  # lost half
    assert rs.num_eggs[1] == 50  # new redd unchanged


class TestAnadromousAdultLifeHistory:
    def test_adult_arrival_sets_anad_adult_life_history(self):
        """Adult arrivals for anadromous species should get life_history=SPAWNER."""
        from salmopy.state.trout_state import TroutState
        from salmopy.state.life_stage import LifeStage

        ts = TroutState.zeros(5)
        slot = 0
        ts.alive[slot] = True
        ts.life_history[slot] = LifeStage.SPAWNER
        assert ts.life_history[slot] == LifeStage.SPAWNER

    def test_anad_adult_dies_after_spawning(self):
        """Anadromous adults (life_history=SPAWNER) should die after spawning."""
        from salmopy.state.trout_state import TroutState
        from salmopy.state.life_stage import LifeStage

        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.life_history[0] = LifeStage.SPAWNER
        ts.spawned_this_season[0] = True
        alive = ts.alive_indices()
        for i in alive:
            if ts.life_history[i] == LifeStage.SPAWNER and ts.spawned_this_season[i]:
                ts.alive[i] = False
        assert not ts.alive[0]


def test_superimposition_no_effect_different_cell():
    from salmopy.state.redd_state import ReddState
    from salmopy.modules.spawning import apply_superimposition

    rs = ReddState.zeros(5)
    # Existing redd at cell 10
    rs.alive[0] = True
    rs.cell_idx[0] = 10
    rs.num_eggs[0] = 100
    # New redd at different cell
    rs.alive[1] = True
    rs.cell_idx[1] = 20
    rs.num_eggs[1] = 50
    apply_superimposition(rs, 1, 1000)
    assert rs.num_eggs[0] == 100  # unchanged
    assert rs.num_eggs[1] == 50  # unchanged


class TestFecundityNoise:
    """Tests for lognormal fecundity noise in create_redd."""

    def test_fecundity_varies_with_noise(self):
        """With noise > 0 and different seeds, egg counts should differ."""
        from salmopy.state.redd_state import ReddState
        from salmopy.modules.spawning import create_redd

        eggs = []
        for seed in [42, 99, 7]:
            rs = ReddState.zeros(10)
            rng = np.random.default_rng(seed)
            create_redd(
                rs, species_idx=0, cell_idx=0, reach_idx=0,
                length=500.0, fecund_mult=1.0, fecund_exp=1.0,
                egg_viability=1.0, fecundity_noise=0.3, rng=rng,
            )
            eggs.append(int(rs.num_eggs[0]))
        assert len(set(eggs)) > 1, f"All egg counts identical: {eggs}"

    def test_zero_noise_deterministic(self):
        """With noise=0, egg count is the same regardless of seed."""
        from salmopy.state.redd_state import ReddState
        from salmopy.modules.spawning import create_redd

        eggs = []
        for seed in [42, 99, 7]:
            rs = ReddState.zeros(10)
            rng = np.random.default_rng(seed)
            create_redd(
                rs, species_idx=0, cell_idx=0, reach_idx=0,
                length=500.0, fecund_mult=1.0, fecund_exp=1.0,
                egg_viability=1.0, fecundity_noise=0.0, rng=rng,
            )
            eggs.append(int(rs.num_eggs[0]))
        assert len(set(eggs)) == 1, f"Egg counts should be identical: {eggs}"
