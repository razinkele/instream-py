"""Tests for output writer module."""


def test_write_population_census(tmp_path):
    from salmopy.io.output import write_population_census

    records = [
        {
            "date": "2011-06-15",
            "num_alive": 300,
            "mean_length": 12.5,
            "mean_weight": 25.0,
            "num_redds": 0,
        },
        {
            "date": "2011-09-30",
            "num_alive": 250,
            "mean_length": 14.0,
            "mean_weight": 30.0,
            "num_redds": 5,
        },
    ]
    path = write_population_census(records, tmp_path)
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 3  # header + 2 rows


def test_write_population_census_empty(tmp_path):
    from salmopy.io.output import write_population_census

    result = write_population_census([], tmp_path)
    assert result is None


def test_write_fish_snapshot(tmp_path):
    from salmopy.state.trout_state import TroutState
    from salmopy.io.output import write_fish_snapshot

    ts = TroutState.zeros(10)
    ts.alive[:3] = True
    ts.length[:3] = [10.0, 12.0, 8.0]
    ts.weight[:3] = [15.0, 20.0, 10.0]
    ts.condition[:3] = 1.0
    path = write_fish_snapshot(ts, ["Rainbow"], "2011-06-15", tmp_path)
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 4  # header + 3 fish


def test_write_redd_snapshot(tmp_path):
    from salmopy.state.redd_state import ReddState
    from salmopy.io.output import write_redd_snapshot

    rs = ReddState.zeros(5)
    rs.alive[0] = True
    rs.cell_idx[0] = 3
    rs.num_eggs[0] = 100
    path = write_redd_snapshot(rs, ["Rainbow"], "2011-06-15", tmp_path)
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2  # header + 1 redd


def test_write_outmigrants(tmp_path):
    from salmopy.io.output import write_outmigrants

    outmigrants = [
        {"species_idx": 0, "length": 12.5, "reach_idx": 0},
        {"species_idx": 0, "length": 14.0, "reach_idx": 1},
    ]
    path = write_outmigrants(outmigrants, ["Rainbow"], tmp_path)
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 3  # header + 2 records


def test_write_outmigrants_empty(tmp_path):
    from salmopy.io.output import write_outmigrants

    path = write_outmigrants([], ["Rainbow"], tmp_path)
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1  # header only


import numpy as np


class TestWriteHabitatSummary:
    def test_writes_csv_with_correct_columns(self, tmp_path):
        from salmopy.io.output import write_habitat_summary

        cs = type(
            "CS",
            (),
            {
                "reach_idx": np.array([0, 0, 0]),
                "depth": np.array([15.0, 45.0, 120.0]),
                "velocity": np.array([8.0, 25.0, 70.0]),
                "area": np.array([100.0, 200.0, 300.0]),
            },
        )()
        path = write_habitat_summary(cs, {0: "TestReach"}, str(tmp_path), "2012-06-01")
        import csv

        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) > 0
        assert "reach" in rows[0]
        assert "depth_class" in rows[0]
        assert "total_area_cm2" in rows[0]


class TestWriteGrowthReport:
    def test_writes_per_species_stats(self, tmp_path):
        from salmopy.io.output import write_growth_report
        from salmopy.state.trout_state import TroutState

        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.alive[1] = True
        ts.species_idx[0] = 0
        ts.species_idx[1] = 0
        ts.length[0] = 10.0
        ts.length[1] = 12.0
        ts.weight[0] = 5.0
        ts.weight[1] = 8.0
        ts.condition[0] = 0.9
        ts.condition[1] = 0.95
        ts.last_growth_rate[0] = 0.1
        ts.last_growth_rate[1] = -0.05
        path = write_growth_report(ts, ["Chinook"], str(tmp_path), "2012-06-01")
        import csv

        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["species"] == "Chinook"
        assert int(rows[0]["num_alive"]) == 2
        assert float(rows[0]["mean_length"]) == 11.0
