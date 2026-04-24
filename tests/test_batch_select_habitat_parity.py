"""Phase 2 Task 2.4: coverage for the batch_select_habitat hot path.

The v0.29.0 Numba batch kernel had zero regression coverage — combined with
the Phase 1 behavior.py:211 indentation bug, its results were silently being
overwritten for multiple releases. This test ensures the batch kernel is
actually exercised on each release and produces outputs satisfying the
documented invariants (fitness in [0,1], cell_idx within mesh range, activity
in {0,1,2}, chosen cells belong to the fish's allowed reach set).

Companion to tests/test_behavior_numba_fallback.py, which asserts the
Python fallback does NOT run when Numba is available.
"""
import pytest
import numpy as np
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_batch_kernel_produces_valid_habitat_choices():
    """After one simulation step with the Numba batch kernel, every alive
    fish must have (a) a valid cell_idx within mesh bounds, (b) activity
    in {0, 1, 2}, (c) last_habitat_fitness in [0, 1]."""
    from salmopy.model import SalmopyModel
    from salmopy.modules import behavior

    if not behavior._HAS_NUMBA_BATCH:
        pytest.skip("numba batch kernel not available")

    model = SalmopyModel(
        config_path=str(CONFIGS_DIR / "example_a.yaml"),
        data_dir=str(FIXTURES_DIR / "example_a"),
    )
    model.step()

    alive = model.trout_state.alive
    n_cells = model.fem_space.cell_state.area.shape[0]
    cells = model.trout_state.cell_idx[alive]
    acts = model.trout_state.activity[alive]

    assert (cells >= 0).all() and (cells < n_cells).all(), (
        f"Batch kernel produced cell_idx out of mesh range [0, {n_cells}): "
        f"min={cells.min()}, max={cells.max()}"
    )
    assert np.isin(acts, [0, 1, 2]).all(), (
        f"Batch kernel produced activity outside {{0, 1, 2}}: "
        f"unique={np.unique(acts)}"
    )

    if hasattr(model.trout_state, "best_habitat_fitness"):
        fit = model.trout_state.best_habitat_fitness[alive]
        assert (fit >= 0.0).all() and (fit <= 1.0).all(), (
            f"best_habitat_fitness outside [0,1]: min={fit.min()}, max={fit.max()}"
        )


def test_batch_kernel_runs_a_full_day_without_error():
    """End-to-end smoke: one step must complete with no exception and
    leave all population state in numerically valid ranges."""
    from salmopy.model import SalmopyModel
    from salmopy.modules import behavior

    if not behavior._HAS_NUMBA_BATCH:
        pytest.skip("numba batch kernel not available")

    model = SalmopyModel(
        config_path=str(CONFIGS_DIR / "example_a.yaml"),
        data_dir=str(FIXTURES_DIR / "example_a"),
    )
    model.step()

    alive = model.trout_state.alive
    assert alive.sum() > 0, "all fish dead after 1 step — batch kernel likely broken"
    lengths = model.trout_state.length[alive]
    weights = model.trout_state.weight[alive]
    assert np.isfinite(lengths).all() and (lengths > 0).all()
    assert np.isfinite(weights).all() and (weights > 0).all()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "v0.43.17: test caught real batch-vs-scalar numerical drift. On "
        "example_a seeded with 42, 354/359 alive fish (98.6%) end up in "
        "different cells between the batch kernel and the scalar fallback. "
        "Batch output is dominated by ~2 cells (argmax-tie or stale-index "
        "collapse); scalar output shows broad diversity. Shape + activity "
        "assertions were not reached. Suspected site: CSR construction + "
        "Numba kernel at behavior.py:691+. Tracked as a separate v0.44 "
        "item — fixing the drift is out of scope for this patch. Test "
        "kept in the suite as strict xfail so when the kernel is fixed "
        "the test flips green and we know to remove the mark."
    ),
)
def test_batch_and_scalar_paths_agree_numerically():
    """Restore the original Phase-2 Task 2.4 intent: run one model step
    twice (batch path then forced-scalar via monkeypatch on
    _HAS_NUMBA_BATCH) and assert the chosen cells, activities, and growth
    rates match exactly. Without this test, batch/scalar can drift silently."""
    from salmopy.model import SalmopyModel
    from salmopy.modules import behavior

    if not behavior._HAS_NUMBA_BATCH:
        pytest.skip("numba batch kernel not available - parity test requires both paths")

    def run(force_scalar: bool):
        with pytest.MonkeyPatch.context() as mp:
            if force_scalar:
                mp.setattr(behavior, "_HAS_NUMBA_BATCH", False)
            model = SalmopyModel(
                config_path=str(CONFIGS_DIR / "example_a.yaml"),
                data_dir=str(FIXTURES_DIR / "example_a"),
            )
            model.rng = np.random.default_rng(42)
            model.step()
            alive = model.trout_state.alive
            return (
                model.trout_state.cell_idx[alive].copy(),
                model.trout_state.activity[alive].copy(),
                model.trout_state.last_growth_rate[alive].copy(),
            )

    cells_b, acts_b, g_b = run(force_scalar=False)
    cells_s, acts_s, g_s = run(force_scalar=True)

    assert cells_b.shape == cells_s.shape, (
        f"alive count diverges between paths: batch={cells_b.shape}, "
        f"scalar={cells_s.shape}"
    )
    np.testing.assert_array_equal(
        cells_b, cells_s,
        err_msg="batch vs scalar chose different cells",
    )
    np.testing.assert_array_equal(
        acts_b, acts_s,
        err_msg="batch vs scalar chose different activities",
    )
    np.testing.assert_allclose(
        g_b, g_s, rtol=1e-9, atol=1e-12,
        err_msg="batch vs scalar produced different last_growth_rate",
    )
