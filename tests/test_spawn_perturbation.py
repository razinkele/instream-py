"""Tests for stochastic spawn-cell perturbation (Task 7)."""

import numpy as np
from instream.modules.spawning import select_spawn_cell


def test_spawn_cell_varies_with_noise():
    """With perturbation, different calls may select different cells."""
    rng = np.random.default_rng(42)
    scores = np.array([0.90, 0.89])
    candidates = np.array([0, 1])

    selections = [
        select_spawn_cell(scores, candidates, rng=rng, noise_sd=0.15)
        for _ in range(100)
    ]
    unique = set(selections)
    assert len(unique) > 1, "With noise, should sometimes pick cell 1"


def test_spawn_cell_no_noise_deterministic():
    """Without noise, always picks highest score."""
    scores = np.array([0.90, 0.89, 0.50])
    candidates = np.array([0, 1, 2])

    result = select_spawn_cell(scores, candidates)
    assert result == 0  # highest score
