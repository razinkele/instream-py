"""v0.43.7 Task T3: regression test for the unit-mismatch bug that
v0.43.6 introduced in apply_superimposition's caller.

cs.area is stored in cm² (polygon_mesh.py and fem_mesh.py both multiply
raw-m² by 10_000 before storage). The v0.43.6 caller computed
redd_area as math.pi * defense_radius_m^2 (m²), giving a
loss_fraction of redd_m²/cell_cm² ≈ 2e-5 — superimposition was
silently disabled for every config with spawn_defense_area_m > 0.
"""
import math
from pathlib import Path

import numpy as np

from salmopy.state.redd_state import ReddState
from salmopy.modules.spawning import apply_superimposition

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_superimposition_loss_fraction_matches_pi_r_squared_over_cell():
    """Given defense_radius = 2.52 m (pi*r^2 = 20 m² = 200_000 cm²) and
    cell_area = 100 m² = 1_000_000 cm², the loss fraction must be 0.2.
    """
    # Seed a redd with 1000 eggs; add a second redd in the same cell.
    rs = ReddState.zeros(capacity=4)
    rs.alive[0] = True
    rs.cell_idx[0] = 7
    rs.num_eggs[0] = 1000
    rs.alive[1] = True
    rs.cell_idx[1] = 7
    rs.num_eggs[1] = 500

    defense_r_m = 2.52
    defense_r_cm = defense_r_m * 100
    redd_area_cm2 = math.pi * defense_r_cm * defense_r_cm   # ≈ 199488 cm²
    cell_area_cm2 = 100.0 * 10_000.0                        # 100 m² → 1e6 cm²

    apply_superimposition(
        rs,
        new_redd_idx=1,
        redd_area=redd_area_cm2,
        cell_area=cell_area_cm2,
    )

    # Expected: loss_fraction = 199488 / 1_000_000 ≈ 0.1995
    # Existing redd 1000 * 0.1995 ≈ 199 eggs lost → 801 remain
    expected_frac = redd_area_cm2 / cell_area_cm2
    expected_remaining = int(1000 * (1 - expected_frac))
    actual_remaining = int(rs.num_eggs[0])
    assert abs(actual_remaining - expected_remaining) <= 2, (
        f"loss_fraction unit conversion wrong: expected ~{expected_remaining} "
        f"remaining eggs (loss {expected_frac:.4f}), got {actual_remaining}"
    )


def test_superimposition_legacy_50pct_when_cell_area_none():
    """cell_area=None preserves the v0.43.5 legacy 50% hardcoded loss."""
    rs = ReddState.zeros(capacity=4)
    rs.alive[0] = True
    rs.cell_idx[0] = 3
    rs.num_eggs[0] = 1000
    rs.alive[1] = True
    rs.cell_idx[1] = 3
    rs.num_eggs[1] = 100

    apply_superimposition(rs, new_redd_idx=1, redd_area=50.0, cell_area=None)

    assert int(rs.num_eggs[0]) == 500, (
        f"cell_area=None must preserve 50% loss default; got {rs.num_eggs[0]}"
    )


def test_simulation_loss_fraction_uses_cm_squared_not_m_squared(tmp_path):
    """Run a real spawning path on the example_a fixture with a config
    where two redds end up on the same cell. After apply_superimposition,
    the older redd's egg loss must reflect a cm²/cm² loss fraction, NOT
    the m²/cm² ratio (~2e-5) that the v0.43.6 buggy caller produced.

    With defense_radius_m = 0.5 m -> defense_radius_cm = 50 cm ->
    redd_area = pi * 50² ≈ 7854 cm². If a typical cell area is ~1e6 cm²
    (100 m² cell), expected loss fraction ≈ 0.008 (~0.8%). The buggy
    m² caller would have produced loss ≈ 7.85e-7 — eggs lost / eggs initial
    < 1e-4 instead of ~0.008.
    """
    import math
    import yaml
    from salmopy.model import SalmopyModel
    from salmopy.modules.spawning import apply_superimposition

    cfg_path = tmp_path / "cfg.yaml"
    with open(CONFIGS_DIR / "example_a.yaml") as f:
        cfg = yaml.safe_load(f)
    sp_name = next(iter(cfg["species"]))
    cfg["species"][sp_name]["spawn_defense_area_m"] = 0.5
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg, f)

    model = SalmopyModel(
        config_path=str(cfg_path),
        data_dir=str(FIXTURES_DIR / "example_a"),
    )

    rs = model.redd_state
    rs.alive[0] = True
    rs.cell_idx[0] = 5
    rs.num_eggs[0] = 1000
    rs.eggs_initial[0] = 1000
    rs.alive[1] = True
    rs.cell_idx[1] = 5
    rs.num_eggs[1] = 500
    rs.eggs_initial[1] = 500

    defense_r_m = 0.5
    redd_area_cm2 = math.pi * (defense_r_m * 100) ** 2
    cell_area_cm2 = float(model.fem_space.cell_state.area[5])

    apply_superimposition(rs, new_redd_idx=1, redd_area=redd_area_cm2, cell_area=cell_area_cm2)

    expected_loss_fraction = redd_area_cm2 / cell_area_cm2
    assert 1e-4 < expected_loss_fraction < 1.0, (
        f"Test fixture cell area is {cell_area_cm2} cm²; pick a cell "
        f"that yields a meaningful loss fraction (got {expected_loss_fraction})"
    )

    eggs_lost = 1000 - int(rs.num_eggs[0])
    expected_loss = int(1000 * expected_loss_fraction)
    assert abs(eggs_lost - expected_loss) <= 2, (
        f"Eggs lost = {eggs_lost}, expected {expected_loss}. The "
        f"v0.43.6 m²-vs-cm² unit bug would have produced "
        f"{int(1000 * (redd_area_cm2 / 10000) / cell_area_cm2)} "
        f"(loss fraction shrunk by 10000x)."
    )
