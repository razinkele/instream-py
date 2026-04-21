"""Arc Q: Bayesian life-cycle wrapper for SalmoPy.

Wraps the existing calibration framework (Sobol/Morris/Nelder-Mead/GP) in a
Bayesian posterior-inference shell comparable to WGBAST's Bayesian model
(Kuikka, Vanhatalo & Pulkkinen 2014, DOI 10.1214/13-sts431). Conditions on
smolt-trap counts + spawner-counter data from WGBAST monitored rivers,
emits posteriors over post-smolt survival, M74 baseline, stray fraction,
and fecundity.

Modules
-------
- `prior`    — Prior dataclass + Baltic salmon default priors
- `observation_model` — Poisson smolt-trap + NB spawner-counter likelihoods
- `smc`      — Sequential Monte Carlo ABC-SMC with tempered likelihood
"""
from __future__ import annotations

from instream.bayesian.prior import Prior, BALTIC_SALMON_PRIORS
from instream.bayesian.observation_model import (
    log_likelihood_smolt_trap,
    log_likelihood_spawner_counter,
)
from instream.bayesian.smc import run_smc

__all__ = [
    "Prior",
    "BALTIC_SALMON_PRIORS",
    "log_likelihood_smolt_trap",
    "log_likelihood_spawner_counter",
    "run_smc",
]
