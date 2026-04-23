"""Phase 2 Task 2.5: SMC log-marginal-likelihood must be 0 under a
flat (zero-log-likelihood) observation model, for any number of
particles and temperature steps.

The original accumulator used np.exp(log_weights).mean() after shifting
by max_lw, introducing a spurious -log(N) per temperature step. The
correct formula is max_lw + log(sum(exp(log_weights_shifted))).
"""
import numpy as np


def test_log_marginal_is_zero_under_flat_likelihood():
    from salmopy.bayesian.smc import run_smc

    class _FakePrior:
        def __init__(self, name):
            self.name = name

        def sample(self, rng, n):
            return rng.standard_normal(n)

    def flat_ll(sim_val, observed):
        return 0.0

    def forward(params, seed):
        return {"metric": params["mu"] + params["sigma"]}

    result = run_smc(
        priors=[_FakePrior("mu"), _FakePrior("sigma")],
        run_model_fn=forward,
        observations=[{"metric_name": "metric", "observed": 0.0, "ll_fn": flat_ll}],
        n_particles=64,
        n_temperature_steps=4,
        rng=np.random.default_rng(0),
    )
    assert abs(result["log_marginal_likelihood"]) < 1e-9, (
        f"With zero log-likelihood, log_marginal_likelihood must be 0 "
        f"(no evidence). Got {result['log_marginal_likelihood']} — "
        f"smc.py:90 has an off-by-log(N) bug: np.exp(log_weights).mean() "
        f"introduces a spurious -log(N) per temperature step."
    )
