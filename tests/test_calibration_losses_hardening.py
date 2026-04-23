"""Phase 2 Task 2.6: rmse_loss must return NaN on all-NaN input so
optimizers cannot rank a crashed run as optimal."""
import math

from salmopy.calibration.losses import rmse_loss


def test_rmse_all_nan_returns_nan_not_zero():
    result = rmse_loss([float("nan")] * 3, [1.0, 2.0, 3.0])
    assert math.isnan(result), (
        f"rmse_loss with all-NaN actual must return NaN (current: {result}). "
        "Returning 0.0 lets an all-NaN (crashed) run appear as a perfect match."
    )


def test_rmse_nan_in_reference_returns_nan():
    result = rmse_loss([1.0, 2.0, 3.0], [float("nan")] * 3)
    assert math.isnan(result)


def test_rmse_empty_sequences_returns_nan():
    result = rmse_loss([], [])
    assert math.isnan(result)


def test_rmse_happy_path_still_works():
    result = rmse_loss([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert result == 0.0


def test_rmse_partial_nan_uses_finite_pairs():
    """Partial NaN: drop the NaN pair, compute on the rest."""
    result = rmse_loss([1.0, float("nan"), 3.0], [1.0, 5.0, 3.0])
    assert result == 0.0  # the finite pairs are (1,1) and (3,3)
