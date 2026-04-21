"""Arc Q: Prior distributions for Bayesian calibration.

Defines a lightweight `Prior` dataclass and a default Baltic-salmon
prior set spanning the key WGBAST latent parameters: post-smolt
survival, M74 baseline, stray fraction, and fecundity multiplier.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
import numpy as np


@dataclass(frozen=True)
class Prior:
    """One parameter's prior distribution.

    shape ∈ {"uniform", "log_uniform", "beta"}.
    For "uniform" and "log_uniform", (lower, upper) are the bounds.
    For "beta", (lower, upper) are (alpha, beta) shape parameters.
    """
    name: str
    lower: float
    upper: float
    shape: str = "uniform"

    def sample(self, rng: np.random.Generator, n: int = 1) -> np.ndarray:
        if self.shape == "uniform":
            return rng.uniform(self.lower, self.upper, size=n)
        if self.shape == "log_uniform":
            return np.exp(
                rng.uniform(
                    np.log(self.lower), np.log(self.upper), size=n,
                )
            )
        if self.shape == "beta":
            # lower=alpha, upper=beta for beta-distribution
            return rng.beta(self.lower, self.upper, size=n)
        raise ValueError(f"unknown prior shape: {self.shape}")


# Default priors for Baltic salmon Bayesian calibration. Bounds widened
# from the published WGBAST envelope to allow SMC posterior-tail coverage.
BALTIC_SALMON_PRIORS: List[Prior] = [
    Prior("post_smolt_survival", 0.02, 0.18),
        # ICES (2023) WGBAST §2.5 3-12% envelope, widened to 2-18% for
        # SMC tail coverage.
    Prior("m74_baseline", 0.0, 0.30),
        # Vuorinen 2021 background YSFM fraction (non-peak years).
    Prior("stray_fraction", 0.0, 0.25),
        # Östergren 2021 homogenization evidence → 5-15% central estimate,
        # widened for SMC.
    Prior("fecundity_mult", 500.0, 900.0),
        # Brännäs 1988: 4-12k eggs per 70-100 cm female. The `fecund_mult`
        # parameter in spawning.py scales length^exp; 690 is the shipped
        # default (v0.18.0 calibration point).
]
