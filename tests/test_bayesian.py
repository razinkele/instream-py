"""Arc Q: Bayesian wrapper tests (prior + likelihood + SMC)."""
from __future__ import annotations
import math
import numpy as np

from instream.bayesian import (
    Prior,
    BALTIC_SALMON_PRIORS,
    log_likelihood_smolt_trap,
    log_likelihood_spawner_counter,
    run_smc,
)


# ===========================================================================
# Prior module
# ===========================================================================


def test_uniform_prior_samples_in_range():
    p = Prior("test", 0.0, 1.0, shape="uniform")
    rng = np.random.default_rng(42)
    s = p.sample(rng, n=1000)
    assert np.all(s >= 0.0)
    assert np.all(s <= 1.0)
    assert 0.4 < s.mean() < 0.6


def test_log_uniform_prior_samples_log_space():
    p = Prior("rate", 0.01, 100.0, shape="log_uniform")
    rng = np.random.default_rng(42)
    s = p.sample(rng, n=1000)
    # Should be log-uniform → median near sqrt(lower * upper) = 1.0
    assert abs(np.median(s) - 1.0) < 0.5
    assert s.min() >= 0.01
    assert s.max() <= 100.0


def test_baltic_prior_set_complete():
    """All 4 Baltic priors present with reasonable bounds."""
    names = {p.name for p in BALTIC_SALMON_PRIORS}
    assert names == {
        "post_smolt_survival", "m74_baseline",
        "stray_fraction", "fecundity_mult",
    }


def test_baltic_post_smolt_prior_covers_ices_envelope():
    """ICES (2023) §2.5 publishes 3-12% post-smolt envelope; prior must
    cover it (widened to 2-18% for SMC tail coverage)."""
    ps = next(p for p in BALTIC_SALMON_PRIORS if p.name == "post_smolt_survival")
    assert ps.lower <= 0.03 and ps.upper >= 0.12


# ===========================================================================
# Observation likelihoods
# ===========================================================================


def test_smolt_trap_poisson_likelihood_peaks_at_observed():
    """ln P is higher when simulated * efficiency ≈ observed."""
    # 10000 smolts * 0.65 eff = 6500 expected
    ll_peak = log_likelihood_smolt_trap(10000, 6500, 0.65)
    ll_off_low = log_likelihood_smolt_trap(5000, 6500, 0.65)
    ll_off_high = log_likelihood_smolt_trap(20000, 6500, 0.65)
    assert ll_peak > ll_off_low
    assert ll_peak > ll_off_high


def test_spawner_nb_likelihood_high_at_expected():
    """NB log-likelihood peaks near mu = simulated * detection."""
    # 100 simulated * 0.8 detection = 80 expected; observing 80 should be high
    ll_at = log_likelihood_spawner_counter(100, 80, 0.8, overdispersion_k=50.0)
    ll_far = log_likelihood_spawner_counter(100, 200, 0.8, overdispersion_k=50.0)
    assert ll_at > ll_far


# ===========================================================================
# SMC sampler — toy recoverable problem
# ===========================================================================


def test_smc_recovers_known_value_under_gaussian_noise():
    """Toy problem: posterior should concentrate near the true value.

    Generating process: `metric = true_value + noise`. Prior U(0, 1).
    Observation: metric = 0.6. SMC should return a posterior mean near 0.6.
    """
    priors = [Prior("x", 0.0, 1.0, shape="uniform")]

    def run_model(params, seed):
        return {"metric": params["x"]}

    def gaussian_log_like(sim, obs, sigma=0.05):
        return -0.5 * ((float(sim) - float(obs)) / sigma) ** 2

    observations = [{
        "metric_name": "metric",
        "observed": 0.6,
        "ll_fn": gaussian_log_like,
        "ll_kwargs": {"sigma": 0.05},
    }]

    result = run_smc(
        priors=priors,
        run_model_fn=run_model,
        observations=observations,
        n_particles=300,
        n_temperature_steps=8,
        rng=np.random.default_rng(42),
    )
    # Weighted mean ≈ true 0.6
    posterior_mean = np.sum(result["particles"][:, 0] * result["weights"])
    assert abs(posterior_mean - 0.6) < 0.1, (
        f"posterior mean {posterior_mean:.3f} far from true 0.6"
    )
    # Posterior std should be much smaller than prior std ≈ 0.29
    posterior_std = np.sqrt(
        np.sum(result["weights"] * (result["particles"][:, 0] - posterior_mean) ** 2)
    )
    assert posterior_std < 0.15


def test_smc_param_names_match_priors():
    priors = [
        Prior("a", 0.0, 1.0),
        Prior("b", 10.0, 20.0),
    ]
    result = run_smc(
        priors=priors,
        run_model_fn=lambda p, s: {"m": p["a"] + p["b"]},
        observations=[{
            "metric_name": "m",
            "observed": 10.5,
            "ll_fn": lambda sim, obs: -((sim - obs) ** 2),
        }],
        n_particles=50, n_temperature_steps=3,
        rng=np.random.default_rng(0),
    )
    assert result["param_names"] == ["a", "b"]
    assert result["particles"].shape == (50, 2)
