"""Regression test for behavior.py:211 indentation bug.

When Numba is available, the Python KD-tree fallback must NOT run —
its result would overwrite the Numba-computed candidate lists.
"""
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_numba_path_does_not_invoke_python_fallback(monkeypatch):
    from salmopy.modules import behavior

    if not behavior._HAS_NUMBA_SPATIAL:
        pytest.skip("numba not installed")

    from salmopy.model import SalmopyModel
    model = SalmopyModel(
        config_path=str(CONFIGS_DIR / "example_a.yaml"),
        data_dir=str(FIXTURES_DIR / "example_a"),
    )
    assert hasattr(model.fem_space, "_geo_offsets"), (
        "Expected Numba geo-cache to be built; test precondition failed"
    )

    def tripwire(*args, **kwargs):
        raise AssertionError(
            "fem_space.cells_in_radius was called — Python fallback ran "
            "despite Numba being available. The `for i in range(n_fish)` "
            "loop in behavior.py must be indented under `else:`."
        )
    monkeypatch.setattr(model.fem_space, "cells_in_radius", tripwire)

    sp_cfg = model.config.species[model.species_order[0]]
    candidate_lists = behavior.build_candidate_lists(
        trout_state=model.trout_state,
        fem_space=model.fem_space,
        move_radius_max=sp_cfg.move_radius_max,
        move_radius_L1=sp_cfg.move_radius_L1,
        move_radius_L9=sp_cfg.move_radius_L9,
        reach_allowed=None,
    )
    assert len(candidate_lists) == model.trout_state.alive.shape[0]
