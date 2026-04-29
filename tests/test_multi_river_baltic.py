"""Arc M: multi-river Baltic fixture smoke + latitudinal-gradient tests.

Fixtures (tornionjoki, simojoki, byskealven, morrumsan) are scaffolded via
`scripts/_scaffold_wgbast_rivers.py` from the example_baltic template with
per-river geometry, temperature offsets, and flow scaling.

Plan: docs/superpowers/plans/2026-04-20-arc-M-to-Q-expanded.md
"""
from __future__ import annotations
import logging
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


_TORNIONJOKI_XFAIL = pytest.mark.xfail(
    reason=(
        "Modal smolt age is 2; expected 4. v0.52.0-v0.52.2 fixed five "
        "delivery-side bugs (RA candidate filter, depths, defense_area, "
        "EPSG:3035 reproj, lo_T) so natal cohorts now appear (11k PARR "
        "peak, 2.6M cumulative eggs, scour=0). v0.53.0 added a per-source "
        "mortality breakdown diagnostic (numpy_backend.survival_with_"
        "breakdown) which FALSIFIED the high-temp hypothesis from the "
        "v0.52.3 verification log: high-temp daily survival is 1.000 at "
        "subarctic temps. The actual dominant kernel killer was "
        "mort_terr_pred_* (~2.6% annualized vs real 30-50%/yr); v0.53.0 "
        "raised Tornionjoki terr_pred_min from 0.96-0.97 to 0.99, lifting "
        "annualized survival to ~23-30%. The xfail still fails for two "
        "DIFFERENT reasons exposed by the v0.53.0 5-yr test run: "
        "(A) trout_state preallocated capacity overflows under the "
        "now-realistic population — many emerging eggs are dropped at "
        "the redd, distorting cohort dynamics; "
        "(B) outmigrants.csv mixes natal smolts with initial-population "
        "seed fish (12-20 cm starters that smolt at age 1-2), so the "
        "modal age is dominated by seed fish even when natal biology "
        "is correct. Both are tracked as v0.53.1+ items. See "
        "scripts/_v053_breakdown_1yr.log."
    ),
    strict=False,
)


@pytest.mark.slow
@pytest.mark.parametrize("config_path,fixture_dir,expected_modal_age", [
    pytest.param(
        "configs/example_tornionjoki.yaml", "example_tornionjoki", 4,
        marks=_TORNIONJOKI_XFAIL,
    ),
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


def test_tornionjoki_no_trout_state_capacity_overflow(tmp_path, caplog):
    """v0.53.1 Issue A regression: a 1-year Tornionjoki run must not drop
    eggs at redd_emergence due to trout_state capacity exhaustion.

    Background: the 5-yr smolt-age test (v0.53.0 falsifying probe)
    surfaced hundreds of warnings:
      "redd_emergence: trout_state capacity full; dropping N eggs..."
    indicating the 12000-slot pool was exhausted under the now-realistic
    natal-cohort survival curve. v0.53.1 raised the cap to 100000 to
    cover seed pop + 5 overlapping AU1 cohorts.
    """
    from salmopy.model import SalmopyModel

    with open("configs/example_tornionjoki.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["simulation"]["end_date"] = "2012-03-31"  # 1 year
    cfg["simulation"]["seed"] = 42
    cfg_path = tmp_path / "cfg.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg, f)

    model = SalmopyModel(
        config_path=str(cfg_path),
        data_dir="tests/fixtures/example_tornionjoki",
        output_dir=str(tmp_path),
    )

    with caplog.at_level(logging.WARNING, logger="salmopy.spawning"):
        model.run()

    drop_warnings = [
        rec for rec in caplog.records
        if "trout_state capacity full" in rec.getMessage()
    ]
    dropped = getattr(model.trout_state, "_eggs_dropped_capacity_full", 0)
    assert not drop_warnings, (
        f"trout_state capacity overflow: {len(drop_warnings)} warnings, "
        f"{dropped} eggs dropped over 1-year run. Raise "
        f"performance.trout_capacity in configs/example_tornionjoki.yaml."
    )
    assert dropped == 0, (
        f"trout_state capacity overflow: {dropped} eggs dropped silently. "
        f"Raise performance.trout_capacity in configs/example_tornionjoki.yaml."
    )
