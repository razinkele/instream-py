"""Tests for the two-piece condition-survival function (inSALMO broken-stick)."""

import numpy as np

from instream.modules.survival import survival_condition_two_piece


def test_two_piece_sharp_drop_below_breakpoint():
    """Below breakpoint, survival drops much faster."""
    conditions = np.array([1.0, 0.8, 0.6, 0.4, 0.2])
    surv = survival_condition_two_piece(
        conditions,
        breakpoint=0.8,
        S_above_K8=0.99,
        S_below_K5=0.5,
        K5=0.5,
    )
    assert surv[0] > 0.95, "Good condition = high survival"
    assert surv[2] < surv[1], "Below breakpoint = sharper drop"
    drop_above = surv[0] - surv[1]  # 1.0->0.8
    drop_below = surv[1] - surv[3]  # 0.8->0.4
    assert drop_below > drop_above * 2, "Below breakpoint much steeper"


def test_two_piece_identical_at_breakpoint():
    conditions = np.array([0.8])
    surv = survival_condition_two_piece(
        conditions,
        breakpoint=0.8,
        S_above_K8=0.99,
        S_below_K5=0.5,
        K5=0.5,
    )
    assert abs(surv[0] - 0.99) < 0.01


def test_two_piece_clamps_to_zero_one():
    conditions = np.array([0.0, 2.0])
    surv = survival_condition_two_piece(
        conditions,
        breakpoint=0.8,
        S_above_K8=0.99,
        S_below_K5=0.5,
        K5=0.5,
    )
    assert np.all(surv >= 0)
    assert np.all(surv <= 1)
