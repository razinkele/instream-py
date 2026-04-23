"""Arc Q: Sequential Monte Carlo posterior sampler.

ABC-SMC with tempered likelihood. Samples priors, runs the forward
model once per (particle, temperature step), re-weights by tempered
log-likelihood, and resamples when ESS drops below half the particle
count. Returns the posterior particles + weights + log-marginal
likelihood.

Reference: Sisson et al. 2007 (ABC-SMC); Del Moral et al. 2006
(particle approximations to sequences of distributions).
"""
from __future__ import annotations
from typing import Callable, Dict, List, Sequence, Optional
import numpy as np


def run_smc(
    priors: Sequence,
    run_model_fn: Callable[[Dict[str, float], int], Dict],
    observations: List[Dict],
    n_particles: int = 500,
    n_temperature_steps: int = 10,
    rng: Optional[np.random.Generator] = None,
) -> Dict:
    """ABC-SMC posterior inference.

    Parameters
    ----------
    priors : sequence of Prior objects
        Prior distributions over latent parameters.
    run_model_fn : (params_dict, seed) -> dict
        Forward simulator. Must return a dict with the same keys as each
        observation's `metric_name`.
    observations : list of dicts
        Each dict must contain:
          "metric_name" (str): key into run_model_fn's return dict.
          "observed" (float/int): observed value.
          "ll_fn" (callable): takes (simulated_value, observed_value,
                               **fixed_kwargs) -> float.
          "ll_kwargs" (dict, optional): passed to ll_fn (e.g. trap_efficiency).
    n_particles : int
        Number of particles in the posterior ensemble.
    n_temperature_steps : int
        Number of annealing steps from prior (T=0) to posterior (T=1).
    rng : numpy.random.Generator, optional

    Returns
    -------
    dict with keys:
        particles : (n_particles, n_params) array
        weights : (n_particles,) array
        log_marginal_likelihood : float
        param_names : list of str
    """
    rng = rng or np.random.default_rng(42)

    # 1. Sample priors
    particles = np.stack(
        [p.sample(rng, n=n_particles) for p in priors], axis=1,
    )
    weights = np.ones(n_particles) / n_particles
    log_marginal = 0.0

    # 2. Tempered annealing schedule (T=1/K, 2/K, ..., 1)
    temperatures = np.linspace(
        0.0, 1.0, n_temperature_steps + 1,
    )[1:]

    for t_idx, temp in enumerate(temperatures):
        # Evaluate log-likelihood at this temperature
        log_likes = np.zeros(n_particles)
        for i in range(n_particles):
            params = {p.name: float(particles[i, j]) for j, p in enumerate(priors)}
            sim = run_model_fn(params, 42 + t_idx * n_particles + i)
            for obs in observations:
                sim_val = sim[obs["metric_name"]]
                kwargs = obs.get("ll_kwargs", {})
                log_likes[i] += float(temp) * obs["ll_fn"](
                    sim_val, obs["observed"], **kwargs
                )

        # Re-weight particles (log-space for stability)
        log_weights = np.log(np.maximum(weights, 1e-300)) + log_likes
        max_lw = log_weights.max()
        log_weights = log_weights - max_lw
        new_weights = np.exp(log_weights)
        new_weights /= new_weights.sum()

        # Marginal-likelihood accumulator
        log_marginal += max_lw + np.log(np.exp(log_weights).mean())

        weights = new_weights

        # Resample when ESS drops below half
        ess = 1.0 / (weights**2).sum()
        if ess < n_particles / 2:
            idx = rng.choice(n_particles, size=n_particles, p=weights)
            particles = particles[idx]
            weights = np.ones(n_particles) / n_particles

    return {
        "particles": particles,
        "weights": weights,
        "log_marginal_likelihood": float(log_marginal),
        "param_names": [p.name for p in priors],
    }
