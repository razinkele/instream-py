"""v0.43.5 Task A3: spawner_origin CSV must emit row-normalized
proportions alongside raw counts."""
import pandas as pd
from salmopy.io.output import write_spawner_origin_matrix


def test_spawner_origin_has_count_and_prop_columns(tmp_path):
    spawners = [
        {"natal_reach_idx": 0, "reach_idx": 0, "superind_rep": 100},
        {"natal_reach_idx": 0, "reach_idx": 1, "superind_rep": 50},
        {"natal_reach_idx": 1, "reach_idx": 1, "superind_rep": 20},
    ]
    reach_names = ["A", "B"]
    path = write_spawner_origin_matrix(spawners, reach_names, year=2025, output_dir=tmp_path)
    df = pd.read_csv(path)

    assert "natal_reach_idx" in df.columns
    assert "natal_reach" in df.columns
    assert "count_A" in df.columns and "count_B" in df.columns
    assert "prop_A" in df.columns and "prop_B" in df.columns

    row0 = df.iloc[0]
    assert row0["count_A"] == 100
    assert row0["count_B"] == 50
    assert abs(row0["prop_A"] + row0["prop_B"] - 1.0) < 1e-6
    assert abs(row0["prop_A"] - 100 / 150) < 1e-6

    row1 = df.iloc[1]
    assert row1["count_B"] == 20
    assert row1["prop_B"] == 1.0


def test_spawner_origin_empty_natal_row_has_zero_proportions(tmp_path):
    """A natal reach with zero spawners must still appear with prop=0."""
    spawners = [
        {"natal_reach_idx": 0, "reach_idx": 0, "superind_rep": 10},
    ]
    reach_names = ["A", "B"]
    path = write_spawner_origin_matrix(spawners, reach_names, year=2025, output_dir=tmp_path)
    df = pd.read_csv(path)
    assert len(df) == 2
    row_b = df[df["natal_reach"] == "B"].iloc[0]
    assert row_b["prop_A"] == 0.0
    assert row_b["prop_B"] == 0.0
