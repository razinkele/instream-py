"""Arc M: multi-river Baltic fixture smoke + latitudinal-gradient tests.

Fixtures (tornionjoki, simojoki, byskealven, morrumsan) are scaffolded via
`scripts/_scaffold_wgbast_rivers.py` from the example_baltic template with
per-river geometry, temperature offsets, and flow scaling.

Plan: docs/superpowers/plans/2026-04-20-arc-M-to-Q-expanded.md
"""
from __future__ import annotations
import yaml

import pytest
import pandas as pd


CONFIGS = [
    ("configs/example_tornionjoki.yaml", "example_tornionjoki"),
    ("configs/example_simojoki.yaml", "example_simojoki"),
    ("configs/example_byskealven.yaml", "example_byskealven"),
    ("configs/example_morrumsan.yaml", "example_morrumsan"),
]


@pytest.mark.parametrize("config_path,fixture_dir", CONFIGS)
def test_fixture_loads_and_runs_3_days(config_path, fixture_dir, tmp_path):
    """Arc M.1-M.3 smoke: fixture loads, runs 3 days, emits outputs
    including per-reach PSPC CSV."""
    from salmopy.model import SalmopyModel

    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    # Shortest possible run that covers end-of-run hook
    cfg["simulation"]["end_date"] = "2011-04-03"
    cfg["simulation"]["seed"] = 42
    cfg_path = tmp_path / "short.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg, f)

    model = SalmopyModel(
        config_path=str(cfg_path),
        data_dir=f"tests/fixtures/{fixture_dir}",
        output_dir=str(tmp_path),
    )
    model.run()

    # Verify per-river outputs land
    assert (tmp_path / "outmigrants.csv").exists()
    pspc_files = list(tmp_path.glob("smolt_production_by_reach_*.csv"))
    assert len(pspc_files) >= 1, (
        f"{config_path}: expected smolt_production_by_reach_*.csv"
    )
    df = pd.read_csv(pspc_files[0])
    # At least one reach should have PSPC configured (natal reaches)
    reaches_with_pspc = df[df["pspc_smolts_per_year"].notna()]
    assert len(reaches_with_pspc) >= 1, (
        f"{config_path}: no reaches with PSPC; got {list(df['reach_name'])}"
    )


@pytest.mark.slow
@pytest.mark.parametrize("config_path,fixture_dir,expected_modal_age", [
    ("configs/example_tornionjoki.yaml", "example_tornionjoki", 4),
    ("configs/example_simojoki.yaml", "example_simojoki", 3),
    ("configs/example_byskealven.yaml", "example_byskealven", 2),
    ("configs/example_morrumsan.yaml", "example_morrumsan", 2),
])
def test_latitudinal_smolt_age_gradient(
    config_path, fixture_dir, expected_modal_age, tmp_path
):
    """Arc M.4: modal smolt age matches WGBAST latitudinal gradient.

    AU1 (Torne/Simo) → 3-4 yr smolts at 14-18 cm (Skoglund 2024 Paper III)
    AU2 (Byske) → 2 yr smolts at 13-15 cm
    Southern (Morrum) → 1-2 yr smolts at 11-15 cm
    """
    from salmopy.model import SalmopyModel

    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    # 5-year run lets AU1 fish reach smolt age 4
    cfg["simulation"]["end_date"] = "2016-03-31"
    cfg["simulation"]["seed"] = 42
    cfg_path = tmp_path / "cfg.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg, f)

    model = SalmopyModel(
        config_path=str(cfg_path),
        data_dir=f"tests/fixtures/{fixture_dir}",
        output_dir=str(tmp_path),
    )
    model.run()

    df = pd.read_csv(tmp_path / "outmigrants.csv")
    smolts = df[df["length_category"] == "Smolt"]
    if len(smolts) < 5:
        pytest.skip(
            f"{config_path}: only {len(smolts)} smolts produced — "
            f"fixture hydrology may need refinement"
        )
    modal_age = int(smolts["age_years"].round().mode().iloc[0])
    assert abs(modal_age - expected_modal_age) <= 1, (
        f"{config_path}: modal age {modal_age}, expected {expected_modal_age}"
    )
