"""Tests for migration and reach connectivity."""

import numpy as np


class TestReachGraph:
    def test_builds_from_junctions(self):
        from salmopy.modules.migration import build_reach_graph

        # 3 reaches: Upper(jn 1-2), Middle(jn 2-3), Lower(jn 3-4)
        upstream_junctions = [1, 2, 3]
        downstream_junctions = [2, 3, 4]
        graph = build_reach_graph(upstream_junctions, downstream_junctions)
        # Upper's downstream junction (2) matches Middle's upstream (2)
        assert 1 in graph[0]  # reach 0 → reach 1
        assert 2 in graph[1]  # reach 1 → reach 2

    def test_last_reach_has_no_downstream(self):
        from salmopy.modules.migration import build_reach_graph

        graph = build_reach_graph([1, 2, 3], [2, 3, 4])
        assert len(graph[2]) == 0  # reach 2 has no downstream

    def test_single_reach(self):
        from salmopy.modules.migration import build_reach_graph

        graph = build_reach_graph([1], [2])
        assert len(graph[0]) == 0


class TestMigrationFitness:
    def test_small_fish_low_fitness(self):
        from salmopy.modules.migration import migration_fitness

        f = migration_fitness(length=3.0, L1=4.0, L9=10.0)
        assert f < 0.2

    def test_large_fish_high_fitness(self):
        from salmopy.modules.migration import migration_fitness

        f = migration_fitness(length=15.0, L1=4.0, L9=10.0)
        assert f > 0.8

    def test_bounded(self):
        from salmopy.modules.migration import migration_fitness

        for l in [1, 3, 5, 10, 20]:
            f = migration_fitness(l, L1=4.0, L9=10.0)
            assert 0 <= f <= 1


class TestDownstreamMigration:
    def test_fish_migrates_when_fitness_high(self):
        from salmopy.modules.migration import should_migrate

        result = should_migrate(
            migration_fit=0.8, best_habitat_fit=0.3, life_history=1
        )  # anad_juve
        assert result is True

    def test_fish_stays_when_habitat_better(self):
        from salmopy.modules.migration import should_migrate

        result = should_migrate(migration_fit=0.2, best_habitat_fit=0.5, life_history=1)
        assert result is False

    def test_resident_never_migrates(self):
        from salmopy.modules.migration import should_migrate

        result = should_migrate(
            migration_fit=0.99, best_habitat_fit=0.01, life_history=0
        )  # resident
        assert result is False

    def test_anad_adult_never_migrates_downstream(self):
        from salmopy.modules.migration import should_migrate

        result = should_migrate(
            migration_fit=0.99, best_habitat_fit=0.01, life_history=2
        )  # anad_adult
        assert result is False

    def test_migrate_to_downstream_reach(self):
        from salmopy.modules.migration import migrate_fish_downstream
        from salmopy.state.trout_state import TroutState

        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.reach_idx[0] = 0
        reach_graph = {0: [1], 1: [2], 2: []}
        outmigrants, _ = migrate_fish_downstream(ts, 0, reach_graph)
        assert ts.reach_idx[0] == 1
        assert len(outmigrants) == 0

    def test_fish_leaving_last_reach_becomes_outmigrant(self):
        from salmopy.modules.migration import migrate_fish_downstream
        from salmopy.state.trout_state import TroutState

        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.reach_idx[0] = 2
        ts.length[0] = 8.0
        ts.species_idx[0] = 0
        reach_graph = {0: [1], 1: [2], 2: []}
        outmigrants, _ = migrate_fish_downstream(ts, 0, reach_graph)
        assert not ts.alive[0]  # removed from simulation
        assert len(outmigrants) == 1
        assert outmigrants[0]["length"] == 8.0


class TestOutmigrantTracking:
    def test_bin_by_length_class(self):
        from salmopy.modules.migration import bin_outmigrant

        # Length classes [5, 7]: bins are <5, 5-7, >7
        bin_idx = bin_outmigrant(length=6.0, length_classes=[5, 7])
        assert bin_idx == 1  # middle bin

    def test_small_fish_first_bin(self):
        from salmopy.modules.migration import bin_outmigrant

        bin_idx = bin_outmigrant(length=3.0, length_classes=[5, 7])
        assert bin_idx == 0

    def test_large_fish_last_bin(self):
        from salmopy.modules.migration import bin_outmigrant

        bin_idx = bin_outmigrant(length=10.0, length_classes=[5, 7])
        assert bin_idx == 2


class TestPerSpeciesMigration:
    def test_different_species_use_own_migration_params(self):
        """Each species should use its own migrate_fitness_L1/L9."""
        from salmopy.modules.migration import migration_fitness

        sp_mig_L1 = np.array([4.0, 20.0])
        sp_mig_L9 = np.array([10.0, 30.0])

        f0 = migration_fitness(8.0, sp_mig_L1[0], sp_mig_L9[0])
        f1 = migration_fitness(8.0, sp_mig_L1[1], sp_mig_L9[1])

        assert f0 > 0.3, f"species 0 fitness {f0} should be moderate"
        assert f1 < 0.1, f"species 1 fitness {f1} should be very low"
        assert f0 > f1
