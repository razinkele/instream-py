"""v0.43.7 Task T3: regression test for the unit-mismatch bug that
v0.43.6 introduced in apply_superimposition's caller.

cs.area is stored in cm² (polygon_mesh.py and fem_mesh.py both multiply
raw-m² by 10_000 before storage). The v0.43.6 caller computed
redd_area as math.pi * defense_radius_m^2 (m²), giving a
loss_fraction of redd_m²/cell_cm² ≈ 2e-5 — superimposition was
silently disabled for every config with spawn_defense_area_m > 0.
"""
import math

import numpy as np

from salmopy.state.redd_state import ReddState
from salmopy.modules.spawning import apply_superimposition


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


def test_model_day_boundary_caller_converts_meters_to_cm():
    """Source-level check: model_day_boundary's apply_superimposition
    caller must compute redd_area in cm² (not m²) to match cs.area units.
    """
    import inspect
    from salmopy import model_day_boundary
    src = inspect.getsource(model_day_boundary)
    # Locate the v0.43.7 unit-fix block.
    needle_options = ("_dr_cm", "_redd_area_cm2", "* 100")
    assert any(s in src for s in needle_options), (
        "model_day_boundary apply_superimposition caller must perform "
        "meters→cm conversion on the defense radius. v0.43.6 passed m² "
        "vs cm² and silently disabled superimposition."
    )
    # Ensure the raw-m² pattern is NOT present
    assert "_redd_area_m2 = math.pi * _dr * _dr" not in src and \
           "math.pi * _dr * _dr" not in src, (
        "v0.43.6 buggy pattern 'math.pi * _dr * _dr' (m²) still present — "
        "would regress the unit fix."
    )
