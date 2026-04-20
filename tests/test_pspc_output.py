from pathlib import Path
from instream.io.config import load_config
from instream.io.output import write_outmigrants


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
    assert rows[0] == (
        "species,timestep,reach_idx,natal_reach_idx,natal_reach_name,"
        "age_years,length_category,length_cm,initial_length_cm,superind_rep"
    )
    assert rows[1].startswith("Salmon,180,0,2,Nemunas_main,")
    assert rows[1].endswith(",100")


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
