from pathlib import Path
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
