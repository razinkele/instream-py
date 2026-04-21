"""Arc Q: Observation likelihoods for Bayesian calibration.

Poisson log-likelihood for smolt-trap counts, negative-binomial for
spawner-counter data. Matches WGBAST observation-model conventions
(ICES 2023 §3 trap-count uncertainty treatment).
"""
from __future__ import annotations
import math


def log_likelihood_smolt_trap(
    simulated_smolts: float,
    observed_count: int,
    trap_efficiency: float,
) -> float:
    """Poisson log-likelihood of observed smolt-trap count.

    lambda = simulated_smolts * trap_efficiency
    ln P(obs | lambda) = obs * ln(lambda) - lambda - ln(obs!)

    Parameters
    ----------
    simulated_smolts : float
        Total smolt production predicted by the model for this river-year.
    observed_count : int
        Trap-caught smolts.
    trap_efficiency : float
        Posterior-mean capture probability (0-1), from WGBAST mark-recapture.
    """
    lam = max(1e-9, float(simulated_smolts) * float(trap_efficiency))
    obs = int(observed_count)
    log_factorial = math.lgamma(obs + 1) if obs > 0 else 0.0
    return obs * math.log(lam) - lam - log_factorial


def log_likelihood_spawner_counter(
    simulated_spawners: float,
    observed_count: int,
    detection_probability: float,
    overdispersion_k: float = 50.0,
) -> float:
    """Negative-binomial log-likelihood for spawner-counter data.

    Parameterization: `p = k / (k + mu)`, giving `Var(X) = mu + mu²/k`.
    Default k=50 corresponds to CV ≈ 15% at mu=100, matching Orell &
    Erkinaro 2007's observed 10-15% inter-observer agreement for
    Riverwatcher video counters on Finnish rivers.

    k can be overridden per-counter. Pass `overdispersion_k=30.0` etc.
    for noisier devices (older resistivity counters).
    """
    mu = max(1e-9, float(simulated_spawners) * float(detection_probability))
    k = float(overdispersion_k)
    obs = int(observed_count)
    p = k / (k + mu)
    # ln P = ln Γ(k+obs) - ln Γ(k) - ln obs! + k ln p + obs ln(1-p)
    return (
        math.lgamma(k + obs) - math.lgamma(k) - math.lgamma(obs + 1)
        + k * math.log(p) + obs * math.log(max(1e-300, 1 - p))
    )
