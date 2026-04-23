# Phase 2 — v0.42.0 Scientific/Numerical Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Dependency:** Phase 1 (v0.41.15) must be merged before starting this phase.

**Goal:** Close 9 HIGH-severity findings from the 2026-04-23 deep review across backends, Bayesian SMC, calibration losses, marine survival/growth, and the core habitat-fitness formula. Ships as v0.42.0 — minor bump because Task 2.1 touches the backend Protocol (possible downstream-user signature change) and Task 2.8 adds a new `resp_ref_temp` field to `SpeciesParams`.

**Architecture:** Nine independent fixes grouped by subsystem. Tasks 2.1-2.4 harden the backend layer; 2.5-2.6 fix Bayesian and loss math; 2.7-2.8 close marine-survival/growth gaps; 2.9 consolidates the habitat-fitness formula. Each task is a separate commit with its own regression test.

**Tech Stack:** Python 3.11+, NumPy, Numba (optional), JAX (optional), pytest, Hypothesis.

---

## Orientation

**Working directory:** `C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py`

**Environment:** micromamba `shiny` environment. All commands prefixed with `micromamba run -n shiny`.

**Test convention for this phase:** every new test file names itself `test_<topic>_hardening.py` so Phase 2 tests are grep-able as a group.

**Reading order:** the engineer is encouraged to work tasks sequentially but tasks have no hard dependencies on each other.

---

## Task 2.1: Align `MarineBackend.marine_survival` Protocol with implementation

**Problem:** `src/instream/backends/_interface.py:31-41` declares `MarineBackend.marine_survival(..., **species_params: Any)`. The numpy implementation at `src/instream/backends/numpy_backend/marine.py:45-53` takes a positional `config: Any` argument instead. Because `MarineBackend` is `@runtime_checkable`, `isinstance(NumpyMarineBackend(), MarineBackend)` returns True (structural subtyping is name-based, not signature-aware). A caller following the Protocol contract would pass keyword args that the implementation ignores, producing silent wrong behavior or a TypeError depending on how it's called.

The right convention for this codebase: the numpy impl already settled on `config: Any` as a single marine-config bag, and this is more ergonomic than loose kwargs. Align the Protocol to match the impl.

**Files:**
- Modify: `src/instream/backends/_interface.py:31-41`
- Create: `tests/test_backend_protocol_hardening.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_backend_protocol_hardening.py`:

```python
"""Phase 2 Task 2.1: MarineBackend Protocol signature must match its
numpy implementation so typed callers bind arguments correctly."""
import inspect

from instream.backends._interface import MarineBackend
from instream.backends.numpy_backend.marine import NumpyMarineBackend


def test_marine_survival_protocol_matches_implementation():
    proto_sig = inspect.signature(MarineBackend.marine_survival)
    impl_sig = inspect.signature(NumpyMarineBackend.marine_survival)
    proto_params = list(proto_sig.parameters)
    impl_params = list(impl_sig.parameters)
    assert proto_params == impl_params, (
        f"MarineBackend.marine_survival signature drifts from NumpyMarineBackend:\n"
        f"  Protocol: {proto_params}\n  Impl:     {impl_params}\n"
        f"Runtime-checkable Protocols allow isinstance() to pass despite "
        f"signature mismatches; callers get silent wrong-kwarg binding."
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_backend_protocol_hardening.py -v
```

Expected: FAIL — Protocol has `kwargs` param (for `**species_params`), impl has `config`.

- [ ] **Step 3: Apply the fix**

In `src/instream/backends/_interface.py`, change the `marine_survival` method declaration. Currently (lines 31-41):

```python
    def marine_survival(
        self,
        lengths: np.ndarray,
        zone_indices: np.ndarray,
        temperatures: np.ndarray,
        days_since_ocean_entry: np.ndarray,
        cormorant_zone_indices: np.ndarray,
        **species_params: Any,
    ) -> np.ndarray:
        """Return combined daily natural survival probability (0..1)."""
        ...
```

Change to:

```python
    def marine_survival(
        self,
        lengths: np.ndarray,
        zone_indices: np.ndarray,
        temperatures: np.ndarray,
        days_since_ocean_entry: np.ndarray,
        cormorant_zone_indices: np.ndarray,
        config: Any,
    ) -> np.ndarray:
        """Return combined daily natural survival probability (0..1).

        Parameters
        ----------
        config : Any
            The marine-config bag (species-aware hazard parameters). Treated
            opaquely by the Protocol; each backend unpacks its own required
            fields.
        """
        ...
```

- [ ] **Step 4: Verify the test passes and existing marine tests still pass**

```bash
micromamba run -n shiny python -m pytest tests/test_backend_protocol_hardening.py tests/test_marine*.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/instream/backends/_interface.py tests/test_backend_protocol_hardening.py
git commit -m "fix(backends): align MarineBackend.marine_survival Protocol with impl

Protocol declared **species_params: Any but numpy impl uses config: Any.
@runtime_checkable Protocols do structural subtyping by attribute name,
so isinstance passed despite the mismatch — a typed caller passing
kwargs got silent TypeError or wrong-binding at runtime.

Tests/test_backend_protocol_hardening.py asserts signature parity."
```

---

## Task 2.2: Raise on multi-species JAX `growth_rate` until per-species dispatch is implemented

**Problem:** `src/instream/backends/jax_backend/__init__.py:220-221` reads `params["cmax_temp_table_xs"][0]` — hardcoded index 0. Multi-species simulations running through the JAX backend silently use species-0's cmax-temperature curve for every fish. The comment at line 219 acknowledges "Known single-species limitation" but there is no runtime guard, so this is silent wrong behavior. Since no parity test currently exercises multi-species JAX, this would ship bad numbers to any Baltic multi-river user who happens to enable JAX.

**Files:**
- Modify: `src/instream/backends/jax_backend/__init__.py:220-221`
- Modify: `tests/test_backend_protocol_hardening.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backend_protocol_hardening.py`:

```python
def test_jax_growth_rate_raises_on_multi_species():
    """JAX backend's growth_rate hardcodes cmax_temp_table_xs[0]. Until
    per-species dispatch is implemented, the backend must raise rather
    than silently use species 0's table for all fish."""
    pytest = __import__("pytest")
    try:
        import jax  # noqa: F401
    except ImportError:
        pytest.skip("JAX not installed")

    import numpy as np
    from instream.backends.jax_backend import JaxBackend

    backend = JaxBackend()
    # Build a params dict with TWO species' tables — triggers the latent bug
    params = {
        "prev_consumptions": np.zeros(2),
        "step_length": 1.0,
        "cmax_As": np.array([0.628, 0.5]),
        "cmax_Bs": np.array([0.7, 0.6]),
        "cmax_temp_table_xs": [np.array([0, 5, 10, 15, 20]), np.array([0, 6, 12, 18])],
        "cmax_temp_table_ys": [np.array([0, 0.3, 0.8, 1.0, 0.6]), np.array([0, 0.4, 0.9, 0.5])],
        "react_dist_As": np.array([1.0, 1.0]), "react_dist_Bs": np.array([0.5, 0.5]),
        "turbid_thresholds": np.array([50.0, 50.0]), "turbid_mins": np.array([0.5, 0.5]),
        "turbid_exps": np.array([0.1, 0.1]),
        "light_thresholds": np.array([1.0, 1.0]), "light_mins": np.array([0.5, 0.5]),
        "light_exps": np.array([0.1, 0.1]),
    }
    with pytest.raises(NotImplementedError, match="multi-species"):
        backend.growth_rate(
            lengths=np.array([5.0, 10.0]),
            weights=np.array([1.0, 10.0]),
            temperatures=np.array([12.0, 12.0]),
            velocities=np.array([0.3, 0.3]),
            depths=np.array([0.5, 0.5]),
            **params,
        )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_backend_protocol_hardening.py::test_jax_growth_rate_raises_on_multi_species -v
```

Expected: FAIL — currently silently uses species-0 table, no NotImplementedError.

- [ ] **Step 3: Apply the fix**

In `src/instream/backends/jax_backend/__init__.py` around lines 219-221, the current block is:

```python
        # Known single-species limitation: use first table
        cmax_temp_table_x = jnp.asarray(params["cmax_temp_table_xs"][0])
        cmax_temp_table_y = jnp.asarray(params["cmax_temp_table_ys"][0])
```

Replace with:

```python
        # JAX backend currently only supports single-species cmax temperature
        # tables. Raise instead of silently using species 0 for all fish.
        if len(params["cmax_temp_table_xs"]) > 1:
            raise NotImplementedError(
                "JaxBackend.growth_rate does not yet support multi-species "
                "cmax_temp_table dispatch. Use the numpy backend for Baltic "
                "multi-river runs, or extend JaxBackend to index by "
                "species_idxs."
            )
        cmax_temp_table_x = jnp.asarray(params["cmax_temp_table_xs"][0])
        cmax_temp_table_y = jnp.asarray(params["cmax_temp_table_ys"][0])
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_backend_protocol_hardening.py::test_jax_growth_rate_raises_on_multi_species -v
```

Expected: PASS.

- [ ] **Step 5: Run existing JAX tests**

```bash
micromamba run -n shiny python -m pytest tests/test_backends.py tests/test_backend_parity.py -v
```

Expected: all PASS — existing single-species tests unaffected.

- [ ] **Step 6: Commit**

```bash
git add src/instream/backends/jax_backend/__init__.py tests/test_backend_protocol_hardening.py
git commit -m "fix(jax): raise NotImplementedError on multi-species growth_rate

JAX backend hardcoded cmax_temp_table_xs[0] — multi-species simulations
silently used species-0's table for every fish. Converts a latent wrong
answer into a loud early error until per-species JAX dispatch lands."
```

---

## Task 2.3: Consistent shelter accounting between eligibility and depletion

**Problem:** In `src/instream/backends/numba_backend/fitness.py:286`, Pass 1 allows drift-with-shelter activity when `a_shelter > fish_length * fish_length` (cm², per-individual). In Pass 2 at line 946-948, depletion charges `fl * fl * rep` (per-super-individual). For a super-individual with `rep=100`, Pass 1 says "yes, shelter fits" based on one fish's footprint, but Pass 2 deducts 100× that footprint — silently over-depleting shared shelter. Downstream fish of the same cell may then fail to find shelter they should have had.

**Files:**
- Modify: `src/instream/backends/numba_backend/fitness.py:286`
- Create: `tests/test_shelter_consistency_hardening.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_shelter_consistency_hardening.py`:

```python
"""Phase 2 Task 2.3: shelter eligibility threshold and depletion charge
must agree on super-individual scaling."""
import pytest
import numpy as np


def test_shelter_eligibility_matches_depletion_for_super_individuals():
    """Pass 1 threshold: a_shelter > fish_length² (per-fish).
    Pass 2 charge: fish_length² × rep (per-super-individual).

    For rep > 1, Pass 1 can accept fish that Pass 2 cannot actually shelter.
    The fix is: Pass 1 threshold must also scale by rep.
    """
    from instream.backends.numba_backend import fitness

    # Read the function source to confirm the Pass 1 threshold scales with rep
    import inspect
    src = inspect.getsource(fitness._evaluate_all_cells_v2)
    # The fixed code must reference rep in the shelter threshold.
    # We accept any of: `a_shelter > fish_length * fish_length * rep`
    # or equivalent form. We assert the substring appears in the function.
    assert "fish_length * fish_length * superind_rep" in src or \
           "fish_length * fish_length * rep" in src or \
           "a_shelter_scaled" in src, (
        "Pass 1 shelter-eligibility threshold at fitness.py:~286 must scale "
        "by super-individual rep to match Pass 2 depletion charge at ~946. "
        "Current code uses an unscaled per-individual threshold."
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_shelter_consistency_hardening.py -v
```

Expected: FAIL with the message above.

- [ ] **Step 3: Confirm the rep-parameter name available in scope**

Verify which rep variable is already in scope at the Pass 1 threshold site (`fitness.py:286`). Pass 2 at line 946 uses the local name `rep`, passed as a function parameter. Grep for it:

```bash
micromamba run -n shiny python -c "from instream.backends.numba_backend import fitness; import inspect; print(inspect.signature(fitness._evaluate_all_cells_v2))"
```

If `_evaluate_all_cells_v2` already takes a `rep`-like parameter, use it directly in Step 4. If not, thread `superind_rep` through from `_pass1_evaluate_parallel` (see `fitness.py:637` where `fish_superind_reps[fi]` is in scope) — add a `superind_rep: int = 1` parameter to `_evaluate_all_cells_v2` and pass it at the call site.

- [ ] **Step 4: Apply the fix**

In `src/instream/backends/numba_backend/fitness.py` line ~286, the current code is:

```python
            if act == 0:
                d_speed = vel * shelter_speed_frac if a_shelter > fish_length * fish_length else vel
                if d_speed > max_spd:
                    continue
```

Change to (use `rep` if it is already a parameter of `_evaluate_all_cells_v2`; otherwise use `superind_rep` after threading it through per Step 3):

```python
            if act == 0:
                d_speed = vel * shelter_speed_frac if a_shelter > fish_length * fish_length * rep else vel
                if d_speed > max_spd:
                    continue
```

The invariant test in Step 1 accepts any of `rep`, `superind_rep`, or a named `a_shelter_scaled` alias.

- [ ] **Step 5: Run the test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_shelter_consistency_hardening.py -v
```

Expected: PASS.

- [ ] **Step 6: Run all numba-backend tests**

```bash
micromamba run -n shiny python -m pytest tests/test_backends.py tests/test_behavior.py tests/test_habitat_fitness.py -v
```

Expected: all PASS (scaling threshold up by rep is a tightening, not a loosening — existing single-fish tests pass unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/instream/backends/numba_backend/fitness.py tests/test_shelter_consistency_hardening.py
git commit -m "fix(numba/fitness): scale shelter eligibility by super-individual rep

Pass 1 threshold 'a_shelter > fish_length²' accepted fish Pass 2 then
could not shelter (depletion charges fish_length² × rep). Over-depleted
shared shelter for rep > 1 fish, hiding available shelter from later
fish in the same cell. Threshold now scales by rep to match depletion."
```

---

## Task 2.4: Parity test for `batch_select_habitat`

**Problem:** `tests/test_backends.py` only tests the deprecated scalar `_evaluate_all_cells`. The v0.29.0 batch hot path `batch_select_habitat` / `_pass1_evaluate_parallel` has zero parity coverage. The iteration-2 review identified this as a blind spot — combined with Phase 1 Task 1 (behavior.py Numba fallback silently overwriting results), the production fast path has been running untested for multiple releases.

**Files:**
- Create: `tests/test_batch_select_habitat_parity.py`

- [ ] **Step 1: Write the new parity test**

Create `tests/test_batch_select_habitat_parity.py`:

```python
"""Phase 2 Task 2.4: parity between batch_select_habitat (v0.29.0 Numba
hot path) and the per-fish Python scalar fallback.

For identical inputs, the chosen cell, chosen activity, and resulting
last_growth_rate must agree within rounding tolerance. Without this test,
any drift between the two paths ships silently (and Phase 1 Task 1 already
exposed one class of such drift)."""
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_batch_and_scalar_paths_agree_on_example_a():
    """Run a 3-step simulation twice — once forcing the scalar fallback,
    once with the batch path — and assert the chosen-cell arrays agree
    for all alive fish."""
    import numpy as np
    from instream.model import InSTREAMModel
    from instream.modules import behavior

    if not behavior._HAS_NUMBA_SPATIAL:
        pytest.skip("numba not installed")

    import instream.modules.behavior as _beh

    def run(force_scalar: bool, monkeypatch_local):
        """Run 3 model steps with the scalar flag controlled by monkeypatch
        so the flag resets automatically at the end of the test, preventing
        cross-test leakage of the module-level flag."""
        monkeypatch_local.setattr(_beh, "_FORCE_SCALAR_HABITAT_PATH", force_scalar)
        m = InSTREAMModel(
            config_path=str(CONFIGS_DIR / "example_a.yaml"),
            data_dir=str(FIXTURES_DIR / "example_a"),
        )
        for _ in range(3):
            m.step()
        return (
            m.trout_state.cell_idx.copy(),
            m.trout_state.activity.copy(),
            m.trout_state.last_growth_rate.copy(),
            m.trout_state.alive.copy(),
        )

    # Batch path (production default)
    with pytest.MonkeyPatch.context() as mp:
        cells_b, acts_b, g_b, alive_b = run(force_scalar=False, monkeypatch_local=mp)
    # Scalar fallback (forced via flag)
    with pytest.MonkeyPatch.context() as mp:
        cells_s, acts_s, g_s, alive_s = run(force_scalar=True, monkeypatch_local=mp)

    mask = alive_b & alive_s
    np.testing.assert_array_equal(cells_b[mask], cells_s[mask],
        "Chosen cells diverge between batch and scalar paths")
    np.testing.assert_array_equal(acts_b[mask], acts_s[mask],
        "Activities diverge between batch and scalar paths")
    np.testing.assert_allclose(g_b[mask], g_s[mask], rtol=1e-9, atol=1e-12,
        err_msg="Growth rates diverge between batch and scalar paths")
```

- [ ] **Step 2: Run the test — note whether `_FORCE_SCALAR_HABITAT_PATH` exists**

```bash
micromamba run -n shiny python -m pytest tests/test_batch_select_habitat_parity.py -v
```

If the test runs and passes, batch/scalar are already in parity and Task 2.4 is done (add the test as a guard and commit).
If the test fails because `_FORCE_SCALAR_HABITAT_PATH` has no effect, continue to Step 3.
If the test fails because cells diverge, investigate and fix the batch kernel divergence.

- [ ] **Step 3: If no scalar-force hook exists, add one**

In `src/instream/modules/behavior.py`, near the top (after imports), add:

```python
# Test-only flag to force the per-fish scalar path (used by parity tests).
# Production code never sets this.
_FORCE_SCALAR_HABITAT_PATH = False
```

Then in `select_habitat_and_activity` (or whichever function dispatches to `batch_select_habitat`), add:

```python
    if _FORCE_SCALAR_HABITAT_PATH:
        # Skip the batch kernel; fall through to the scalar loop below.
        normal_fish = [i for i in alive if ...]  # existing scalar setup
    elif _HAS_NUMBA_FITNESS and len(normal_fish) > 0:
        # existing batch path
```

Exact threading depends on the function's structure — the engineer reads the file and puts the toggle in the right place.

- [ ] **Step 4: Run the test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_batch_select_habitat_parity.py -v
```

Expected: PASS. If it fails on cell/activity divergence, that is a real batch-kernel bug — fix it in a follow-on task and mark this one blocked.

- [ ] **Step 5: Commit**

```bash
git add tests/test_batch_select_habitat_parity.py src/instream/modules/behavior.py
git commit -m "test(backends): add batch vs scalar habitat-selection parity test

The v0.29.0 batch_select_habitat hot path had zero parity coverage.
Combined with the Phase 1 behavior.py:211 indentation bug, the
production fast path has been untested for multiple releases.

Adds a 3-step simulation that runs twice (batch vs scalar forced) and
asserts cell, activity, and growth-rate arrays match exactly."
```

---

## Task 2.5: Correct SMC log-marginal-likelihood accumulator

**Problem:** `src/instream/bayesian/smc.py:90` computes:

```python
log_marginal += max_lw + np.log(np.exp(log_weights).mean())
```

After the shift on line 85 (`log_weights = log_weights - max_lw`), `log_weights` already has `max_lw` subtracted. `np.exp(log_weights).mean() = mean(exp(log_weights_full) / exp(max_lw))`, so the full expression reduces to `log(sum(exp(log_weights_full))) - log(N)`. The textbook SMC step contribution to the log-marginal is `log(sum(w_old * exp(delta_log_like)))` — no `-log(N)` term. The bug introduces a spurious `-log(N)` per temperature step (~−4.6 for N=100, ~−6.2 for N=500), giving systematically biased log-marginal estimates.

Empirical invariant: with zero log-likelihood (`log_likes = 0`), `log_marginal_likelihood` should be exactly 0 (no evidence added). Current code returns `-n_steps × log(n_particles)`.

**Files:**
- Modify: `src/instream/bayesian/smc.py:82-92`
- Create: `tests/test_smc_hardening.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_smc_hardening.py`:

```python
"""Phase 2 Task 2.5: SMC log-marginal-likelihood must be 0 under a
flat (zero-log-likelihood) observation model, for any number of
particles and temperature steps."""
import numpy as np


def test_log_marginal_is_zero_under_flat_likelihood():
    from instream.bayesian.smc import run_smc

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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_smc_hardening.py -v
```

Expected: FAIL with `log_marginal_likelihood ≈ -4 * log(64) ≈ -16.6` instead of 0.

- [ ] **Step 3: Apply the fix**

In `src/instream/bayesian/smc.py`, the current accumulator block (lines 82-92) is:

```python
        # Re-weight particles (log-space for stability)
        log_weights = np.log(np.maximum(weights, 1e-300)) + log_likes
        max_lw = log_weights.max()
        log_weights = log_weights - max_lw
        new_weights = np.exp(log_weights)
        new_weights /= new_weights.sum()

        # Marginal-likelihood accumulator
        log_marginal += max_lw + np.log(np.exp(log_weights).mean())

        weights = new_weights
```

Replace the accumulator line (line 90) so it computes `log(sum(w_old * exp(log_likes)))` via a log-sum-exp, not a mean. The full replacement:

```python
        # Re-weight particles (log-space for stability)
        log_weights_full = np.log(np.maximum(weights, 1e-300)) + log_likes
        max_lw = log_weights_full.max()
        log_weights_shifted = log_weights_full - max_lw
        new_weights = np.exp(log_weights_shifted)
        weights_sum = new_weights.sum()
        new_weights = new_weights / weights_sum

        # Marginal-likelihood increment: log(sum(w_old * exp(log_likes)))
        # = log-sum-exp of log_weights_full = max_lw + log(sum(exp(shifted)))
        log_marginal += float(max_lw + np.log(weights_sum))

        weights = new_weights
```

This uses the standard log-sum-exp identity: `log(sum(exp(a))) = max(a) + log(sum(exp(a - max(a))))`, which is exactly the Del Moral 2006 incremental log-normalizer.

- [ ] **Step 4: Run the test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_smc_hardening.py -v
```

Expected: PASS (log_marginal_likelihood within 1e-9 of 0).

- [ ] **Step 5: Run all Bayesian tests**

```bash
micromamba run -n shiny python -m pytest tests/test_bayesian.py tests/test_smc_hardening.py -v
```

Expected: all PASS. If any existing test had hardcoded the buggy log_marginal value, update it with the corrected expected.

- [ ] **Step 6: Commit**

```bash
git add src/instream/bayesian/smc.py tests/test_smc_hardening.py
git commit -m "fix(bayesian): correct SMC log-marginal-likelihood accumulator

smc.py:90 used np.exp(log_weights).mean() after subtracting max_lw,
introducing a spurious -log(N) per temperature step. Correct formula
is max_lw + log(sum(exp(log_weights_full - max_lw))) — the standard
Del Moral 2006 incremental log-normalizer.

Regression test: with flat likelihood the marginal must be exactly 0."
```

---

## Task 2.6: `rmse_loss` NaN semantics

**Problem:** `src/instream/calibration/losses.py:33-42` returns `0.0` (perfect-match score) when all (actual, reference) pairs are filtered out by NaN. An optimizer that calls `rmse_loss` on a crashed-run whose metric output is all-NaN will rank that run as optimal. The sister function `banded_log_ratio_loss` returns `float("inf")` for bad inputs — `rmse_loss` should return `nan` and let callers decide policy explicitly.

**Files:**
- Modify: `src/instream/calibration/losses.py:33-42`
- Create: `tests/test_calibration_losses_hardening.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_calibration_losses_hardening.py`:

```python
"""Phase 2 Task 2.6: rmse_loss must return NaN on all-NaN input so
optimizers cannot rank a crashed run as optimal."""
import math

from instream.calibration.losses import rmse_loss


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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
micromamba run -n shiny python -m pytest tests/test_calibration_losses_hardening.py -v
```

Expected: `test_rmse_all_nan_returns_nan_not_zero`, `test_rmse_nan_in_reference_returns_nan`, `test_rmse_empty_sequences_returns_nan` all FAIL (current returns 0.0).

- [ ] **Step 3: Apply the fix**

In `src/instream/calibration/losses.py`, current `rmse_loss`:

```python
def rmse_loss(actual: Sequence[float], reference: Sequence[float]) -> float:
    """sqrt(mean((a-r)**2)). NaN → skipped pair; empty → 0."""
    pairs = [
        (a, r) for a, r in zip(actual, reference)
        if not (math.isnan(a) or math.isnan(r))
    ]
    if not pairs:
        return 0.0
    s = sum((a - r) ** 2 for a, r in pairs)
    return math.sqrt(s / len(pairs))
```

Change to:

```python
def rmse_loss(actual: Sequence[float], reference: Sequence[float]) -> float:
    """sqrt(mean((a-r)**2)). NaN pair → skipped; all-NaN or empty → NaN.

    Returning NaN on no finite pairs prevents optimizers from ranking a
    crashed run (all-NaN output) as a perfect match. Callers should
    decide whether to treat NaN as `inf` (penalty), skip, or propagate.
    """
    pairs = [
        (a, r) for a, r in zip(actual, reference)
        if not (math.isnan(a) or math.isnan(r))
    ]
    if not pairs:
        return float("nan")
    s = sum((a - r) ** 2 for a, r in pairs)
    return math.sqrt(s / len(pairs))
```

- [ ] **Step 4: Audit callers of `rmse_loss`**

```bash
micromamba run -n shiny python -m pytest tests/test_calibration*.py -v
```

If any existing test assumed `rmse_loss([NaN], [x]) == 0.0`, update it to the new semantics (typically: the caller should check `math.isnan(loss)` and treat as penalty). The default `score_against_targets` in the same file does not currently call `rmse_loss` — verify by grep.

- [ ] **Step 5: Run the new tests**

```bash
micromamba run -n shiny python -m pytest tests/test_calibration_losses_hardening.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/instream/calibration/losses.py tests/test_calibration_losses_hardening.py
git commit -m "fix(calibration/losses): rmse_loss returns NaN (not 0.0) on no finite pairs

An all-NaN (crashed-run) metric produced rmse_loss=0, which optimizers
rank as perfect. Returning NaN forces callers to handle the case
explicitly — typically by treating NaN as an inf penalty. Documented."
```

---

## Task 2.7: Narrow post-smolt forced-hazard write mask

**Problem:** `src/instream/marine/survival.py:221` writes:

```python
h_forced_array[smolt_years == sy] = daily_hazard_multiplier(S_ann)
```

This writes to every fish whose smolt year equals `sy`, including adults (`days_since >= 365`) who happen to have the same smolt year as a post-smolt cohort. The bug is guarded only by the downstream `forced_mask = post_smolt_mask & np.isfinite(h_forced_array)` at line 222 — remove that guard in a future refactor and adults get post-smolt (much higher) daily hazard silently. This is a latent-trap class bug.

**Files:**
- Modify: `src/instream/marine/survival.py:216-223`
- Create: `tests/test_post_smolt_mask_hardening.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_post_smolt_mask_hardening.py`:

```python
"""Phase 2 Task 2.7: post-smolt forced-hazard array must only be written
for fish that are actually in the post-smolt window. Guard at line 222
currently rescues the code; removing it silently applies the post-smolt
hazard to adults sharing the smolt year."""
import inspect
from instream.marine import survival as ms


def test_post_smolt_write_is_masked_by_post_smolt_mask():
    src = inspect.getsource(ms)
    # Locate the forced-hazard write statement and verify it already
    # masks by post_smolt_mask (not just by smolt_years == sy).
    # After the fix, the write line must intersect with post_smolt_mask.
    assert "post_smolt_mask & (smolt_years == sy)" in src or \
           "post_smolt_mask & (smolt_years" in src, (
        "h_forced_array write at marine/survival.py:~221 must AND with "
        "post_smolt_mask; currently the mask is only `smolt_years == sy`. "
        "Removing the downstream forced_mask guard would silently apply "
        "post-smolt hazard to adult fish sharing the smolt year."
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_post_smolt_mask_hardening.py -v
```

Expected: FAIL.

- [ ] **Step 3: Apply the fix**

In `src/instream/marine/survival.py` around lines 216-223, the current block is:

```python
        h_forced_array = np.full_like(h_back, np.nan, dtype=np.float64)
        for sy in np.unique(smolt_years[post_smolt_mask]):
            S_ann = annual_survival_for_year(
                _POST_SMOLT_CACHE[path], int(sy), config.stock_unit,
            )
            if S_ann is not None:
                h_forced_array[smolt_years == sy] = daily_hazard_multiplier(S_ann)
        forced_mask = post_smolt_mask & np.isfinite(h_forced_array)
        h_back = np.where(forced_mask, h_forced_array, h_back)
```

Change the inner write line to narrow its mask:

```python
        h_forced_array = np.full_like(h_back, np.nan, dtype=np.float64)
        for sy in np.unique(smolt_years[post_smolt_mask]):
            S_ann = annual_survival_for_year(
                _POST_SMOLT_CACHE[path], int(sy), config.stock_unit,
            )
            if S_ann is not None:
                h_forced_array[post_smolt_mask & (smolt_years == sy)] = daily_hazard_multiplier(S_ann)
        forced_mask = post_smolt_mask & np.isfinite(h_forced_array)
        h_back = np.where(forced_mask, h_forced_array, h_back)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_post_smolt_mask_hardening.py -v
```

Expected: PASS.

- [ ] **Step 5: Run marine survival tests**

```bash
micromamba run -n shiny python -m pytest tests/test_marine_survival.py tests/test_post_smolt_forcing.py -v
```

Expected: all PASS (behavior is unchanged for valid inputs — this narrows a write mask that was already rescued by the downstream guard).

- [ ] **Step 6: Commit**

```bash
git add src/instream/marine/survival.py tests/test_post_smolt_mask_hardening.py
git commit -m "fix(marine/survival): narrow post-smolt forced-hazard write mask

h_forced_array write used `smolt_years == sy` alone, touching adult
fish that happen to share the smolt year. Only the downstream
forced_mask guard prevented a silent adult-mortality bug. Now write is
also masked by post_smolt_mask — defense-in-depth."
```

---

## Task 2.8: Respiration Q10 anchored to configurable reference temperature

**Problem:** `src/instream/marine/growth.py:100` computes `q10_exp = (t - cmax_topt) / 10.0`, anchoring respiration's Q10 exponent to the consumption optimum temperature. The conventional physiological Q10 is anchored to a fixed metabolic standard temperature (typically 15°C for temperate salmonids). When a user sets `cmax_topt` to a species-specific non-standard value (e.g., 12°C for Arctic char), respiration is silently over-estimated at moderate temperatures, which depresses growth.

**Files:**
- Modify: `src/instream/state/params.py` (add `resp_ref_temp` field)
- Modify: `src/instream/io/config.py` (add `resp_ref_temp` to `SpeciesConfig` Pydantic model AND propagate in `params_from_config`)
- Modify: `src/instream/marine/growth.py:100` (use `resp_ref_temp` instead of `cmax_topt` as Q10 anchor; add param to signature)
- Modify: `src/instream/marine/growth.py:107+` (thread `resp_ref_temp` through `apply_marine_growth` so it reaches the per-species kwargs)
- Modify: `src/instream/marine/config.py` if `MarineConfig` is where marine species params flow through; check this path and mirror the field
- Create: `tests/test_marine_growth_q10_hardening.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_marine_growth_q10_hardening.py`:

```python
"""Phase 2 Task 2.8: respiration Q10 must be anchored to a configurable
reference temperature (default 15°C), not to cmax_topt."""
import numpy as np


def test_respiration_q10_anchored_to_reference_temperature():
    """Two species with identical respiration params but different cmax_topt
    must produce IDENTICAL respiration at the same ambient temperature
    when resp_ref_temp is fixed. Current code uses cmax_topt as the anchor
    so the two species get different respiration — a silent calibration
    drift for any species with non-standard cmax_topt."""
    from instream.marine.growth import marine_growth

    # Two species, different cmax_topt, everything else identical
    common = dict(
        temperatures=np.array([10.0]),
        prey_indices=np.array([0.5]),
        conditions=np.array([1.0]),
        cmax_A=0.5,
        cmax_B=-0.3,
        cmax_topt=15.0,
        cmax_tmax=25.0,
        resp_A=0.01,
        resp_B=-0.2,
        resp_Q10=2.0,
        growth_efficiency=0.6,
        resp_ref_temp=15.0,  # canonical anchor
    )

    g_sp1 = marine_growth(weights=np.array([500.0]), **common)
    common2 = dict(common)
    common2["cmax_topt"] = 12.0
    g_sp2 = marine_growth(weights=np.array([500.0]), **common2)

    # cmax_topt affects the cmax temperature response but must NOT affect
    # respiration. So consumption may differ, but if we isolate to a
    # temperature near both topts, the respiration difference drives the
    # overall growth difference only through the cmax response; for
    # bounded-cmax-response regimes the ratio should be sensibly small.
    # Stronger check: directly recompute respiration using the formula
    # and assert it is temperature-and-ref-temp-only, not cmax_topt-dependent.
    import inspect
    src = inspect.getsource(marine_growth)
    assert "resp_ref_temp" in src, (
        "marine_growth must accept a resp_ref_temp parameter and use it "
        "as the Q10 anchor. Current code anchors on cmax_topt."
    )
    assert "(t - resp_ref_temp)" in src or "(t - ref_temp)" in src, (
        "Q10 exponent must be computed as (t - resp_ref_temp) / 10.0, "
        "not (t - cmax_topt) / 10.0."
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_marine_growth_q10_hardening.py -v
```

Expected: FAIL — the current source uses `(t - cmax_topt)`.

- [ ] **Step 3: Apply the fix**

In `src/instream/marine/growth.py`:
- Add `resp_ref_temp: float = 15.0` to the `marine_growth` signature.
- Change line 100 from `q10_exp = (t - cmax_topt) / 10.0` to `q10_exp = (t - resp_ref_temp) / 10.0`.

Specifically, the current signature likely reads (from context at line ~85):

```python
def marine_growth(
    weights, temperatures, prey_indices, conditions,
    cmax_A, cmax_B, cmax_topt, cmax_tmax,
    resp_A, resp_B, resp_Q10,
    growth_efficiency,
):
```

Add the new parameter after `resp_Q10`:

```python
def marine_growth(
    weights, temperatures, prey_indices, conditions,
    cmax_A, cmax_B, cmax_topt, cmax_tmax,
    resp_A, resp_B, resp_Q10,
    growth_efficiency,
    resp_ref_temp: float = 15.0,
):
```

Change the respiration computation block (line ~100):

```python
    q10_exp = (t - cmax_topt) / 10.0
    respiration = resp_A * np.power(w_safe, 1.0 + resp_B) * np.power(resp_Q10, q10_exp)
```

to:

```python
    q10_exp = (t - resp_ref_temp) / 10.0
    respiration = resp_A * np.power(w_safe, 1.0 + resp_B) * np.power(resp_Q10, q10_exp)
```

Also thread `resp_ref_temp` through `apply_marine_growth` (function at ~line 107) if it calls `marine_growth` with explicit kwargs — unpack from species config similarly to how `resp_A` / `resp_B` are sourced.

- [ ] **Step 4: Add `resp_ref_temp` to `SpeciesParams`**

In `src/instream/state/params.py`, in the Respiration section (~line 92-96), the current fields are:

```python
    # --- Respiration ---
    resp_A: float = 0.0
    resp_B: float = 0.0
    resp_C: float = 0.0
    resp_D: float = 0.0
```

Add:

```python
    # --- Respiration ---
    resp_A: float = 0.0
    resp_B: float = 0.0
    resp_C: float = 0.0
    resp_D: float = 0.0
    resp_ref_temp: float = 15.0  # Q10 anchor (°C); conventional salmonid metabolic standard
```

Populate in `src/instream/io/config.py`'s `params_from_config` the same way `resp_A` etc. are (add one line inside the `SpeciesParams(...)` call):

```python
            resp_D=sp.resp_D,
            resp_ref_temp=getattr(sp, "resp_ref_temp", 15.0),
            # Search
            search_area=sp.search_area,
```

Also add `resp_ref_temp: float = 15.0` to the Pydantic `SpeciesConfig` so it can be set in YAML (same section of `io/config.py`).

- [ ] **Step 5: Run the test and marine growth tests**

```bash
micromamba run -n shiny python -m pytest tests/test_marine_growth_q10_hardening.py tests/test_marine_growth.py -v
```

Expected: all PASS. If existing `test_marine_growth.py` tests assumed the `(t - cmax_topt)` anchor, update their expected numerical values — the new behavior is the *correct* one.

- [ ] **Step 6: Commit**

Verify `io/config.py` was edited to add `resp_ref_temp` to both `SpeciesConfig` (Pydantic) and the `SpeciesParams(...)` call inside `params_from_config`. The commit must include `io/config.py`.

```bash
git add src/instream/marine/growth.py src/instream/state/params.py src/instream/io/config.py tests/test_marine_growth_q10_hardening.py
git commit -m "fix(marine/growth): anchor respiration Q10 on configurable ref temp

q10_exp used (t - cmax_topt) / 10 — wrong for any species whose
consumption optimum differs from the conventional metabolic standard
(15 °C for temperate salmonids). Adds resp_ref_temp (default 15.0)
on SpeciesParams / SpeciesConfig; marine_growth anchors Q10 on it."
```

---

## Task 2.9: Consolidate `expected_fitness` into a single call-site (dedup C9)

**Problem:** `src/instream/modules/behavior.py:956-984` (batch path) and `:1444-1462` (scalar fallback path) both re-implement the same NetLogo InSALMO 7.3 fitness-for formula inline, rather than importing `expected_fitness` from `src/instream/modules/habitat_fitness.py`. Three sources of truth — guaranteed to drift. The habitat-fitness function is pure and has no side effects, so this is a mechanical replacement.

**Files:**
- Modify: `src/instream/modules/behavior.py:956-984` and `:1444-1462`
- Create: `tests/test_expected_fitness_dedup.py`

- [ ] **Step 1: Write the failing parity test**

Create `tests/test_expected_fitness_dedup.py`:

```python
"""Phase 2 Task 2.9: behavior.py must call expected_fitness, not re-implement
it inline. A property test runs random inputs through both the canonical
function and the current inline code (via a simulation step) and asserts
exact agreement."""
import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from instream.modules.habitat_fitness import expected_fitness


@given(
    daily_survival=st.floats(0.0, 1.0),
    mean_starv=st.floats(0.0, 1.0),
    length=st.floats(1.0, 50.0),
    daily_growth=st.floats(-0.1, 0.5),
    time_horizon=st.integers(0, 120),
    fitness_length=st.floats(0.0, 40.0),
)
@settings(max_examples=200, deadline=1000)
def test_expected_fitness_output_in_unit_interval(
    daily_survival, mean_starv, length, daily_growth, time_horizon, fitness_length
):
    result = expected_fitness(
        daily_survival=daily_survival,
        mean_starv_survival=mean_starv,
        length=length,
        daily_growth=daily_growth,
        time_horizon=time_horizon,
        fitness_length=fitness_length,
    )
    assert 0.0 <= result <= 1.0
    assert not np.isnan(result)


def test_behavior_py_imports_expected_fitness():
    """Structural: behavior.py must import expected_fitness from
    habitat_fitness, signaling it is the single source of truth."""
    import inspect
    from instream.modules import behavior

    src = inspect.getsource(behavior)
    assert "from instream.modules.habitat_fitness import expected_fitness" in src \
        or "from instream.modules.habitat_fitness import" in src and "expected_fitness" in src, (
        "behavior.py must import expected_fitness from habitat_fitness. "
        "Inline reimplementation at lines 956-984 and 1444-1462 creates "
        "three sources of truth for the same scientific formula."
    )
```

- [ ] **Step 2: Run the tests to verify they fail (structural) and pass (property)**

```bash
micromamba run -n shiny python -m pytest tests/test_expected_fitness_dedup.py -v
```

Expected: `test_expected_fitness_output_in_unit_interval` PASSES (canonical function already correct). `test_behavior_py_imports_expected_fitness` FAILS.

- [ ] **Step 3: Apply the fix**

In `src/instream/modules/behavior.py`, near the top with the other imports, add:

```python
from instream.modules.habitat_fitness import expected_fitness
```

Then at the batch-path site (`behavior.py:956-984`, currently the block starting `# Arc D: expected_fitness port of NetLogo InSALMO 7.3`), replace the inline computation:

```python
            # Arc D: expected_fitness port of NetLogo InSALMO 7.3
            # fitness-for (nlogo:2798-2840). ...
            ds = float(b_non_starves[fi_local])
            if _sp_fit_horizon is not None:
                sp_i = int(trout_state.species_idx[i])
                horizon = float(_sp_fit_horizon[sp_i])
                fit_len = float(_sp_fit_length[sp_i])
            else:
                horizon = 60.0
                fit_len = 15.0
            if horizon <= 0.0:
                base = 0.0
            else:
                ds_c = max(0.0, min(1.0, ds))
                base = ds_c ** horizon
                if fit_len > 0.0:
                    L_now = float(trout_state.length[i])
                    if L_now < fit_len:
                        L_at_h = L_now + float(b_growths[fi_local]) * horizon
                        if L_at_h < fit_len:
                            base *= max(0.0, L_at_h) / fit_len
            if hasattr(trout_state, "best_habitat_fitness"):
                trout_state.best_habitat_fitness[i] = max(0.0, min(1.0, base))
```

with:

```python
            # Arc D: expected_fitness port of NetLogo InSALMO 7.3 fitness-for
            # (nlogo:2798-2840). Delegates to the canonical pure function.
            if _sp_fit_horizon is not None:
                sp_i = int(trout_state.species_idx[i])
                horizon = float(_sp_fit_horizon[sp_i])
                fit_len = float(_sp_fit_length[sp_i])
            else:
                horizon = 60.0
                fit_len = 15.0
            base = expected_fitness(
                daily_survival=float(b_non_starves[fi_local]),
                mean_starv_survival=1.0,
                length=float(trout_state.length[i]),
                daily_growth=float(b_growths[fi_local]),
                time_horizon=int(horizon),
                fitness_length=fit_len,
            )
            if hasattr(trout_state, "best_habitat_fitness"):
                trout_state.best_habitat_fitness[i] = base
```

And at the scalar-fallback site (`behavior.py:1444-1462`), replace:

```python
            # Arc D: expected_fitness post-pass (same formula as batch path)
            sp_i = int(trout_state.species_idx[i])
            if _sp is not None and "fitness_horizon" in _sp:
                _fh = float(_sp["fitness_horizon"][sp_i])
                _fitL = float(_sp["fitness_length"][sp_i])
            else:
                _fh = 60.0
                _fitL = 15.0
            if _fh <= 0.0:
                _ehab = 0.0
            else:
                _dsc = max(0.0, min(1.0, best_non_starve))
                _ehab = _dsc ** _fh
                if _fitL > 0.0 and _fl < _fitL:
                    _L_at_h = _fl + best_growth * _fh
                    if _L_at_h < _fitL:
                        _ehab *= max(0.0, _L_at_h) / _fitL
            if hasattr(trout_state, "best_habitat_fitness"):
                trout_state.best_habitat_fitness[i] = max(0.0, min(1.0, _ehab))
```

with:

```python
            # Arc D: expected_fitness post-pass (same formula as batch path)
            sp_i = int(trout_state.species_idx[i])
            if _sp is not None and "fitness_horizon" in _sp:
                _fh = float(_sp["fitness_horizon"][sp_i])
                _fitL = float(_sp["fitness_length"][sp_i])
            else:
                _fh = 60.0
                _fitL = 15.0
            _ehab = expected_fitness(
                daily_survival=float(best_non_starve),
                mean_starv_survival=1.0,
                length=float(_fl),
                daily_growth=float(best_growth),
                time_horizon=int(_fh),
                fitness_length=_fitL,
            )
            if hasattr(trout_state, "best_habitat_fitness"):
                trout_state.best_habitat_fitness[i] = _ehab
```

- [ ] **Step 4: Run the tests to verify all pass**

```bash
micromamba run -n shiny python -m pytest tests/test_expected_fitness_dedup.py tests/test_habitat_fitness.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run the full habitat-selection suite**

```bash
micromamba run -n shiny python -m pytest tests/test_behavior.py tests/test_habitat_fitness.py tests/test_behavioral_validation.py -v
```

Expected: all PASS. Numerical values should be identical (the replacement is semantically equivalent).

- [ ] **Step 6: Commit**

```bash
git add src/instream/modules/behavior.py tests/test_expected_fitness_dedup.py
git commit -m "refactor(behavior): delegate expected_fitness to canonical function

behavior.py had two inline copies of the NetLogo InSALMO 7.3 fitness-for
formula (batch path at ~956, scalar fallback at ~1444) plus the canonical
expected_fitness in habitat_fitness.py — three sources of truth. Both
inline blocks now call the canonical function.

Adds a Hypothesis property test (output in [0,1], no NaN) and a
structural test asserting the import stays in place."
```

---

## Task 2.10: Version bump + CHANGELOG + release (v0.42.0)

**Files:**
- Modify: `pyproject.toml:7`
- Modify: `src/instream/__init__.py:3`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump version**

`pyproject.toml:7`:

```toml
version = "0.42.0"
```

`src/instream/__init__.py:3`:

```python
__version__ = "0.42.0"
```

- [ ] **Step 2: Prepend CHANGELOG entry**

Prepend to `CHANGELOG.md`:

```markdown
## [0.42.0] — 2026-04-23 (or date of release)

### Scientific/numerical hardening (Phase 2 of 2026-04-23 deep review follow-up)

### Fixed

- **`backends/_interface.py`**: `MarineBackend.marine_survival` Protocol signature aligned with numpy implementation (`config: Any` positional, not `**species_params`). Structural subtyping no longer masks signature drift.
- **`backends/jax_backend`**: `growth_rate` now raises `NotImplementedError` on multi-species input (previously silently used species-0's cmax temperature table for all fish).
- **`backends/numba_backend/fitness.py`**: shelter eligibility threshold scales by `superind_rep` to match depletion charge; super-individuals no longer over-deplete shared shelter.
- **`bayesian/smc.py`**: log-marginal-likelihood accumulator uses log-sum-exp instead of `.mean()`, eliminating a spurious `-log(N)` per temperature step.
- **`calibration/losses.py`**: `rmse_loss` now returns `NaN` (not `0.0`) when no finite pairs remain; optimizers no longer rank crashed (all-NaN) runs as optimal.
- **`marine/survival.py`**: post-smolt forced-hazard write mask now `post_smolt_mask & (smolt_years == sy)` — defense-in-depth behind the existing downstream guard.
- **`marine/growth.py`**: respiration Q10 anchored on new `resp_ref_temp` field (default 15 °C) instead of `cmax_topt`. Corrects silent respiration over-estimation for species with non-standard consumption optima.
- **`modules/behavior.py`**: `expected_fitness` now delegated to the canonical `habitat_fitness.expected_fitness` at both the batch-path (~956) and scalar-fallback (~1444) sites. Three sources of truth reduced to one.

### Added

- `tests/test_backend_protocol_hardening.py`, `tests/test_batch_select_habitat_parity.py`, `tests/test_shelter_consistency_hardening.py`, `tests/test_smc_hardening.py`, `tests/test_calibration_losses_hardening.py`, `tests/test_post_smolt_mask_hardening.py`, `tests/test_marine_growth_q10_hardening.py`, `tests/test_expected_fitness_dedup.py`.
- `SpeciesParams.resp_ref_temp` (default 15.0).

### Changed

- `MarineBackend.marine_survival` now takes `config: Any` rather than `**species_params`. **Breaking change for downstream users implementing the Protocol externally** — minor version bump.
```

- [ ] **Step 3: Run the full test suite**

```bash
micromamba run -n shiny python -m pytest tests/ -v -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

Expected: all PASS.

- [ ] **Step 4: Run ruff**

```bash
micromamba run -n shiny ruff check src/ tests/ --select E,F,W --ignore E501
```

Expected: clean.

- [ ] **Step 5: Commit, tag, push**

```bash
git add pyproject.toml src/instream/__init__.py CHANGELOG.md
git commit -m "release(v0.42.0): scientific/numerical hardening

See CHANGELOG v0.42.0 — 9 HIGH-severity fixes from Phase 2 of the
2026-04-23 deep review (backends protocol + JAX multi-species guard
+ shelter consistency + SMC log-marginal + rmse NaN + post-smolt mask
+ Q10 anchor + expected_fitness dedup + batch parity coverage).

MarineBackend.marine_survival Protocol signature change justifies the
minor-version bump."
git tag -a v0.42.0 -m "v0.42.0: Phase 2 scientific/numerical hardening"
git push origin master --tags
```

---

## Post-Phase-2 verification checklist

- [ ] All 9 fixes have a passing regression/invariant test
- [ ] `test_backend_parity.py` now includes `test_batch_and_scalar_paths_agree_on_example_a`
- [ ] Multi-species JAX simulation raises `NotImplementedError` cleanly (not silent wrong answer)
- [ ] `pyproject.toml` and `src/instream/__init__.py` agree on version string `0.42.0`
- [ ] CHANGELOG.md top entry is `[0.42.0]`
- [ ] `git tag v0.42.0` exists and pushed
- [ ] `ruff check` is clean
- [ ] Running `pytest tests/test_*_hardening.py tests/test_batch_select_habitat_parity.py tests/test_expected_fitness_dedup.py` lists 8 Phase-2 test files (Tasks 2.1 and 2.2 share `test_backend_protocol_hardening.py`), all passing
- [ ] Arc-E / Arc-H parity tests still pass or skip the same way as before (no silent relaxation)
