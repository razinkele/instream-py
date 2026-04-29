from pathlib import Path
import pandas as pd
from salmopy.io.config import load_config
from salmopy.io.output import write_outmigrants, write_smolt_production_by_reach


def test_outmigrants_csv_10col_netlogo_compat(tmp_path: Path):
    outmigrants = [
        {
            "species_idx": 0,
            "timestep": 180,
            "natal_reach_idx": 2,
            "natal_reach_name": "Nemunas_main",
            "age_years": 1.5,
            "length_category": "Juvenile",
            "length": 12.3,
            "initial_length": 2.5,
            "superind_rep": 100,
            "reach_idx": 0,
        },
    ]
    path = write_outmigrants(outmigrants, ["Salmon"], tmp_path)
    rows = path.read_text().splitlines()
    # v0.53.1 Issue B: appended `is_natal` column (InSALMON-only). The
    # original 10-column NetLogo-compat schema is still the prefix.
    assert rows[0] == (
        "species,timestep,reach_idx,natal_reach_idx,natal_reach_name,"
        "age_years,length_category,length_cm,initial_length_cm,superind_rep,"
        "is_natal"
    )
    assert rows[1].startswith("Salmon,180,0,2,Nemunas_main,")
    # `,100` is now followed by `,False` (record built without is_natal,
    # so write_outmigrants defaults to False).
    assert rows[1].endswith(",100,False")


def test_reach_config_accepts_pspc(tmp_path: Path):
    """Arc K.2: ReachConfig.pspc_smolts_per_year accepts a number from YAML."""
    # Load example_baltic.yaml as a base, then patch one reach with PSPC.
    # Using the existing fixture avoids duplicating the full simulation schema.
    cfg = load_config("configs/example_baltic.yaml")
    first_reach_name = next(iter(cfg.reaches))
    # Default: field exists with None
    assert hasattr(cfg.reaches[first_reach_name], "pspc_smolts_per_year")
    # Simulate a config-level override
    cfg.reaches[first_reach_name].pspc_smolts_per_year = 12000
    assert cfg.reaches[first_reach_name].pspc_smolts_per_year == 12000


def test_smolt_production_by_reach_csv(tmp_path):
    """Arc K.3: write_smolt_production_by_reach groups outmigrants by
    natal_reach_idx and emits % PSPC achievement."""
    outmigrants = [
        {"species_idx": 0, "length": 12.3, "reach_idx": 0, "natal_reach_idx": 0},
        {"species_idx": 0, "length": 11.1, "reach_idx": 0, "natal_reach_idx": 0},
        {"species_idx": 0, "length": 13.0, "reach_idx": 0, "natal_reach_idx": 2},
    ]
    reach_names = ["Nemunas_main", "Neris", "Zeimena"]
    reach_pspc = [5000.0, 2000.0, 1000.0]
    path = write_smolt_production_by_reach(
        outmigrants, reach_names, reach_pspc, year=2011, output_dir=tmp_path
    )
    df = pd.read_csv(path)
    assert set(df.columns) == {
        "year", "reach_idx", "reach_name",
        "smolts_produced", "pspc_smolts_per_year", "pspc_achieved_pct",
    }
    row0 = df[df["reach_idx"] == 0].iloc[0]
    assert row0["smolts_produced"] == 2
    assert abs(row0["pspc_achieved_pct"] - (2 / 5000 * 100)) < 1e-6
    row1 = df[df["reach_idx"] == 1].iloc[0]
    assert row1["smolts_produced"] == 0
    assert row1["pspc_achieved_pct"] == 0.0


def test_end_to_end_pspc_on_tiny_baltic(tmp_path):
    """Arc K.4: end-of-run hook emits smolt_production_by_reach_{year}.csv.

    Uses the existing Baltic fixture directory via `data_dir` override so
    the Shapefile/ + per-reach CSV data is found. Copies only the YAML
    to tmp_path for end_date shortening.
    """
    import yaml
    import pandas as pd
    from salmopy.model import SalmopyModel

    # Copy YAML shortening end_date, keep data_dir pointing at the fixture.
    with open("configs/example_baltic.yaml") as f:
        cfg_dict = yaml.safe_load(f)
    cfg_dict["simulation"]["end_date"] = "2011-01-03"
    cfg_dict["simulation"]["seed"] = 42
    cfg_path = tmp_path / "baltic_tiny.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg_dict, f)

    model = SalmopyModel(
        config_path=str(cfg_path),
        data_dir="tests/fixtures/example_baltic",
        output_dir=str(tmp_path),
    )
    model.run()

    pspc_files = list(tmp_path.glob("smolt_production_by_reach_*.csv"))
    assert len(pspc_files) >= 1, (
        f"Expected smolt_production_by_reach_*.csv; got {list(tmp_path.iterdir())}"
    )
    df = pd.read_csv(pspc_files[0])
    assert {"reach_idx", "smolts_produced", "pspc_achieved_pct"}.issubset(
        df.columns
    )
    # Nemunas, Atmata, Minija have PSPC; others don't
    reaches_with_pspc = df[df["pspc_smolts_per_year"].notna()]
    assert len(reaches_with_pspc) == 3, (
        f"Expected 3 reaches with PSPC, got {list(reaches_with_pspc['reach_name'])}"
    )


def test_smolt_production_by_reach_weights_by_superind_rep(tmp_path):
    """Regression for output.py:219-223: PSPC must weight each outmigrant
    by superind_rep. Each outmigrant dict represents a super-individual."""
    outmigrants = [
        {"species_idx": 0, "natal_reach_idx": 0, "superind_rep": 100},
        {"species_idx": 0, "natal_reach_idx": 0, "superind_rep": 50},
        {"species_idx": 0, "natal_reach_idx": 1, "superind_rep": 10},
    ]
    reach_names = ["Reach_A", "Reach_B"]
    reach_pspc = [1000.0, 100.0]
    path = write_smolt_production_by_reach(
        outmigrants, reach_names, reach_pspc, year=2025, output_dir=tmp_path
    )
    df = pd.read_csv(path)
    row_a = df[df["reach_idx"] == 0].iloc[0]
    assert row_a["smolts_produced"] == 150, (
        f"Expected rep-weighted count 150 (=100+50), got {row_a['smolts_produced']}"
    )
    row_b = df[df["reach_idx"] == 1].iloc[0]
    assert row_b["smolts_produced"] == 10


def test_smolt_production_missing_superind_rep_defaults_to_one(tmp_path):
    """Legacy outmigrant dicts without superind_rep still count as 1 (current test compat)."""
    outmigrants = [
        {"species_idx": 0, "natal_reach_idx": 0, "length": 12.0, "reach_idx": 0},
        {"species_idx": 0, "natal_reach_idx": 0, "length": 11.0, "reach_idx": 0},
    ]
    reach_names = ["Only"]
    reach_pspc = [100.0]
    path = write_smolt_production_by_reach(
        outmigrants, reach_names, reach_pspc, year=2025, output_dir=tmp_path
    )
    df = pd.read_csv(path)
    assert df.iloc[0]["smolts_produced"] == 2


def test_smolt_production_csv_handles_none_pspc(tmp_path):
    """Reaches with pspc_smolts_per_year=None emit empty pct (NaN after CSV read)."""
    outmigrants = [
        {"species_idx": 0, "length": 12.0, "reach_idx": 0, "natal_reach_idx": 1},
    ]
    reach_names = ["MainStem", "LagoonEdge"]
    reach_pspc = [5000.0, None]
    path = write_smolt_production_by_reach(
        outmigrants, reach_names, reach_pspc, year=2020, output_dir=tmp_path
    )
    df = pd.read_csv(path)
    lagoon = df[df["reach_idx"] == 1].iloc[0]
    assert lagoon["smolts_produced"] == 1
    # pandas parses empty cell as NaN
    assert pd.isna(lagoon["pspc_achieved_pct"])
    assert pd.isna(lagoon["pspc_smolts_per_year"])
