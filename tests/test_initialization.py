"""Tests for trout population initialization."""
import numpy as np
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestReadInitialPopulations:
    def test_returns_list_of_dicts(self):
        from instream.io.population_reader import read_initial_populations
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        assert isinstance(pops, list)
        assert len(pops) == 3  # 3 age classes

    def test_first_row_values(self):
        from instream.io.population_reader import read_initial_populations
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        p = pops[0]
        assert p["species"] == "Rainbow"
        assert p["reach"] == "ExampleA"
        assert p["age"] == 0
        assert p["number"] == 300
        assert p["length_min"] == pytest.approx(4.0)
        assert p["length_mode"] == pytest.approx(6.1)
        assert p["length_max"] == pytest.approx(7.0)

    def test_total_fish_count(self):
        from instream.io.population_reader import read_initial_populations
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        total = sum(p["number"] for p in pops)
        assert total == 360


class TestBuildTroutState:
    def test_count(self):
        from instream.io.population_reader import read_initial_populations, build_initial_trout_state
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        ts = build_initial_trout_state(pops, capacity=500, weight_A=0.0041, weight_B=3.49,
                                       species_index=0, seed=42)
        assert ts.num_alive() == 360

    def test_age_distribution(self):
        from instream.io.population_reader import read_initial_populations, build_initial_trout_state
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        ts = build_initial_trout_state(pops, capacity=500, weight_A=0.0041, weight_B=3.49,
                                       species_index=0, seed=42)
        alive = ts.alive_indices()
        ages = ts.age[alive]
        assert np.sum(ages == 0) == 300
        assert np.sum(ages == 1) == 50
        assert np.sum(ages == 2) == 10

    def test_lengths_in_range(self):
        from instream.io.population_reader import read_initial_populations, build_initial_trout_state
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        ts = build_initial_trout_state(pops, capacity=500, weight_A=0.0041, weight_B=3.49,
                                       species_index=0, seed=42)
        alive = ts.alive_indices()
        # Age 0: 4-7cm
        age0 = alive[ts.age[alive] == 0]
        assert np.all(ts.length[age0] >= 4.0)
        assert np.all(ts.length[age0] <= 7.0)
        # Age 1: 9-15cm
        age1 = alive[ts.age[alive] == 1]
        assert np.all(ts.length[age1] >= 9.0)
        assert np.all(ts.length[age1] <= 15.0)

    def test_weights_from_length(self):
        from instream.io.population_reader import read_initial_populations, build_initial_trout_state
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        ts = build_initial_trout_state(pops, capacity=500, weight_A=0.0041, weight_B=3.49,
                                       species_index=0, seed=42)
        alive = ts.alive_indices()
        expected_weights = 0.0041 * ts.length[alive] ** 3.49
        np.testing.assert_allclose(ts.weight[alive], expected_weights, rtol=1e-10)

    def test_condition_is_one(self):
        from instream.io.population_reader import read_initial_populations, build_initial_trout_state
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        ts = build_initial_trout_state(pops, capacity=500, weight_A=0.0041, weight_B=3.49,
                                       species_index=0, seed=42)
        alive = ts.alive_indices()
        np.testing.assert_allclose(ts.condition[alive], 1.0)

    def test_species_index(self):
        from instream.io.population_reader import read_initial_populations, build_initial_trout_state
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        ts = build_initial_trout_state(pops, capacity=500, weight_A=0.0041, weight_B=3.49,
                                       species_index=0, seed=42)
        alive = ts.alive_indices()
        assert np.all(ts.species_idx[alive] == 0)

    def test_deterministic_with_seed(self):
        from instream.io.population_reader import read_initial_populations, build_initial_trout_state
        pops = read_initial_populations(FIXTURES_DIR / "example_a" / "ExampleA-InitialPopulations.csv")
        ts1 = build_initial_trout_state(pops, capacity=500, weight_A=0.0041, weight_B=3.49,
                                        species_index=0, seed=42)
        ts2 = build_initial_trout_state(pops, capacity=500, weight_A=0.0041, weight_B=3.49,
                                        species_index=0, seed=42)
        np.testing.assert_array_equal(ts1.length[ts1.alive_indices()],
                                      ts2.length[ts2.alive_indices()])


class TestRandomTriangular:
    def test_within_bounds(self):
        from instream.io.population_reader import random_triangular
        rng = np.random.default_rng(42)
        values = random_triangular(3.0, 5.0, 8.0, 1000, rng)
        assert np.all(values >= 3.0)
        assert np.all(values <= 8.0)

    def test_mode_near_peak(self):
        from instream.io.population_reader import random_triangular
        rng = np.random.default_rng(42)
        values = random_triangular(3.0, 5.0, 8.0, 10000, rng)
        # Mode should be near 5.0 — histogram peak
        hist, edges = np.histogram(values, bins=50)
        peak_bin = np.argmax(hist)
        peak_center = (edges[peak_bin] + edges[peak_bin + 1]) / 2
        assert abs(peak_center - 5.0) < 1.0

    def test_returns_correct_size(self):
        from instream.io.population_reader import random_triangular
        rng = np.random.default_rng(42)
        values = random_triangular(1.0, 2.0, 3.0, 50, rng)
        assert len(values) == 50
