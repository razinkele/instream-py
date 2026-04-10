# inSTREAM-py v0.13.0 — Comprehensive Implementation Plan (revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all v0.12.0 deferred items + lay InSALMON freshwater foundation.

**Architecture:** Six independent gap-closure tasks (Section 1), then eight sequential InSALMON foundation tasks (Section 2), then release (Section 3).

**Tech Stack:** Python 3.11+, Mesa 3.x, NumPy, Numba, JAX, interpax, Sphinx, hatch, pytest

**Spec:** `docs/superpowers/specs/2026-04-10-v013-comprehensive-design.md`

---

## File Map

### Section 1: Deferred Items
- Modify: `tests/test_validation.py` (fitness cross-validation)
- Modify: `tests/test_behavioral_validation.py` (sub-daily + harvest tests)
- Modify: `src/instream/backends/jax_backend/__init__.py` (spawn_suitability)
- Modify: `tests/test_backend_parity.py` (parity test)
- Create: `docs/source/conf.py`, `docs/source/index.rst`, `docs/source/api.rst`, `docs/Makefile`
- Create: `.github/workflows/docs.yml`, `.github/workflows/release.yml`
- Modify: `pyproject.toml` (metadata)
- Create: `src/instream/py.typed`

### Section 2: InSALMON Foundation
- Create: `src/instream/state/life_stage.py`
- Modify: `src/instream/state/trout_state.py`, `src/instream/model_day_boundary.py`, `src/instream/modules/migration.py`, `src/instream/modules/spawning.py`, `src/instream/modules/survival.py`, `src/instream/modules/behavior.py`, `src/instream/state/params.py`, `src/instream/io/config.py`, `src/instream/model.py`, `src/instream/model_environment.py`
- Modify: `tests/test_spawning.py` (life_history assertions)

---

## Task 1: Fitness Report NetLogo Cross-Validation

**Files:**
- Modify: `tests/test_validation.py`

The NetLogo CSV has 6 columns (skip 2 header lines):
```
trout-length,trout-weight,trout-condition,daily-pred-survival,growth (g/g/d),fitness
```

- [ ] **Step 1: Write the cross-validation test with actual comparison logic**

```python
class TestFitnessReportMatchesNetLogoCSV:
    """Cross-validate Python fitness against NetLogo write-fitness-report."""

    def test_netlogo_fitness_report(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("FitnessReportOut-netlogo.csv")
        ref = pd.read_csv(ref_path, skiprows=2)
        ref.columns = ref.columns.str.strip()

        # Sample every 1000th row (402K rows)
        ref_sample = ref.iloc[::1000].copy()

        # The fitness column in NetLogo is computed by fitness-for reporter
        # which uses: condition-based survival projection * growth projection
        # We need to understand the exact formula from the NetLogo model
        # Read write-fitness-report procedure to determine the formula
        
        mismatches = 0
        for _, row in ref_sample.iterrows():
            length = row["trout-length"]
            weight = row["trout-weight"]
            condition = row["trout-condition"]
            daily_surv = row["daily-pred-survival"]
            growth = row["growth (g/g/d)"]
            nl_fitness = row["fitness"]

            # Compute Python fitness using same inputs
            # Comparison logic is implemented in Step 2 after reading fitness-for formula
        assert False, "Step 2 not yet implemented — read NetLogo fitness-for first"
```

**This Step 1 test is intentionally failing** — it is a red-phase TDD test that will pass only after Step 2 implements the actual comparison.

- [ ] **Step 2: Read NetLogo fitness-for reporter and implement comparison**

Search `InSALMO7.4_2026-02-06_ExampleA.nlogox` for `to-report fitness-for`. Understand the formula, then replace the `assert False` in Step 1 with actual comparison logic. The CSV columns (`trout-condition`, `daily-pred-survival`, `growth (g/g/d)`) are inputs; `fitness` is the expected output. Compute Python fitness from those inputs and assert close at `rtol=1e-6`.

- [ ] **Step 3: Run test**

```bash
micromamba run -n shiny python -m pytest tests/test_validation.py::TestFitnessReportMatchesNetLogoCSV -v --tb=long
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_validation.py
git commit -m "feat: add fitness report NetLogo cross-validation test"
```

---

## Task 2: Sub-daily Behavioral Validation

**Files:**
- Modify: `tests/test_behavioral_validation.py`

Subdaily fixtures exist at `tests/fixtures/subdaily/hourly_example_a.csv`. Check `tests/test_subdaily.py` to see how the model is configured for subdaily mode — it likely uses a config override or modified time series path.

- [ ] **Step 1: Read test_subdaily.py to understand subdaily configuration**

```bash
head -80 tests/test_subdaily.py
```

- [ ] **Step 2: Write sub-daily population stability test**

Based on how test_subdaily.py configures the model:

```python
@pytest.mark.slow
class TestSubDailyPopulationStability:
    """Verify sub-daily mode produces plausible dynamics."""

    @pytest.fixture(scope="class")
    def model(self):
        # Configure exactly like test_subdaily.py does for hourly mode
        # Read test_subdaily.py in Step 1 to fill in this fixture
        pytest.skip("implement after reading test_subdaily.py config pattern")

    def test_population_persists_subdaily(self, model):
        alive = model.trout_state.alive.sum()
        assert alive > 0, "Population went extinct in sub-daily mode"
```

- [ ] **Step 3: Run and commit**

```bash
micromamba run -n shiny python -m pytest tests/test_behavioral_validation.py::TestSubDailyPopulationStability -v --tb=long -m slow
git add tests/test_behavioral_validation.py
git commit -m "feat: add sub-daily behavioral validation test"
```

---

## Task 3: Angler Harvest Behavioral Validation

**Files:**
- Modify: `tests/test_behavioral_validation.py`

- [ ] **Step 1: Read test_harvest.py and the harvest module to understand how harvest is triggered**

```bash
head -60 tests/test_harvest.py
head -40 src/instream/modules/harvest.py
```

- [ ] **Step 2: Write harvest behavior test**

```python
@pytest.mark.slow
class TestHarvestBehavior:
    """Verify harvest module produces realistic catch."""

    def test_harvest_callable(self):
        from instream.modules.harvest import compute_harvest
        assert callable(compute_harvest)

    def test_harvest_with_eligible_fish(self):
        # Based on how test_harvest.py sets up its test
        # Create a model with harvest config, run, check catch records
        pytest.skip("implement after reading test_harvest.py")
```

- [ ] **Step 3: Run and commit**

```bash
micromamba run -n shiny python -m pytest tests/test_behavioral_validation.py::TestHarvestBehavior -v --tb=long -m slow
git add tests/test_behavioral_validation.py
git commit -m "feat: add harvest behavioral validation test"
```

---

## Task 4: JAX Backend — spawn_suitability with interpax

**Files:**
- Modify: `src/instream/backends/jax_backend/__init__.py:534-543`
- Modify: `tests/test_backend_parity.py`

The current JAX code at line 534:
```python
def spawn_suitability(self, depths, velocities, frac_spawn, **params):
    area = params["area"]
    depth_suit = np.interp(np.asarray(depths), params["depth_table_x"], params["depth_table_y"])
    vel_suit = np.interp(np.asarray(velocities), params["vel_table_x"], params["vel_table_y"])
    return depth_suit * vel_suit * np.asarray(frac_spawn) * np.asarray(area)
```

- [ ] **Step 1: Replace np.interp with interpax.interp1d (keep **params signature)**

```python
def spawn_suitability(self, depths, velocities, frac_spawn, **params):
    """Compute spawn suitability for all cells (JAX-native interpolation)."""
    import interpax
    area = params["area"]
    depth_suit = interpax.interp1d(
        jnp.asarray(depths), jnp.asarray(params["depth_table_x"]),
        jnp.asarray(params["depth_table_y"]), method="linear"
    )
    vel_suit = interpax.interp1d(
        jnp.asarray(velocities), jnp.asarray(params["vel_table_x"]),
        jnp.asarray(params["vel_table_y"]), method="linear"
    )
    return depth_suit * vel_suit * jnp.asarray(frac_spawn) * jnp.asarray(area)
```

- [ ] **Step 2: Add intentional-fallback docstring to deplete_resources**

```python
def deplete_resources(self, ...):
    """Deplete cell resources sequentially (intentional NumPy fallback).

    Resource depletion is inherently serial — fish deplete shared cell
    resource pools in size order. Cannot be parallelized with jax.vmap.
    Overhead is O(N_fish), negligible vs O(N_fish × N_cells) habitat selection.
    """
```

- [ ] **Step 3: Add parity test**

In `tests/test_backend_parity.py`, add a test that compares JAX spawn_suitability against NumPy at `rtol=1e-10`.

- [ ] **Step 4: Run parity tests**

```bash
micromamba run -n shiny python -m pytest tests/test_backend_parity.py -v --tb=long
```

- [ ] **Step 5: Commit**

```bash
git add src/instream/backends/jax_backend/__init__.py tests/test_backend_parity.py
git commit -m "feat: JAX-native spawn_suitability with interpax, document deplete_resources fallback"
```

---

## Task 5: Sphinx Documentation Build

**Files:**
- Create: `docs/source/conf.py`, `docs/source/index.rst`, `docs/source/api.rst`
- Create: `docs/Makefile`
- Create: `.github/workflows/docs.yml`

- [ ] **Step 1: Create docs/source/ directory and conf.py**

```python
# docs/source/conf.py
project = "inSTREAM-py"
version = "0.13.0"
extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx.ext.viewcode"]
html_theme = "sphinx_rtd_theme"
```

- [ ] **Step 2: Create index.rst and api.rst**

- [ ] **Step 3: Create Makefile**

- [ ] **Step 4: Create .github/workflows/docs.yml for CI**

- [ ] **Step 5: Test build**

```bash
micromamba run -n shiny sphinx-build -b html docs/source docs/_build/html
```

- [ ] **Step 6: Add docs/_build/ to .gitignore, commit**

```bash
git add docs/source/ docs/Makefile .github/workflows/docs.yml .gitignore
git commit -m "feat: add Sphinx documentation build with autodoc and CI"
```

---

## Task 6: PyPI Packaging

**Files:**
- Modify: `pyproject.toml`
- Create: `src/instream/py.typed`
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Update pyproject.toml metadata**

Add: authors, readme, classifiers, project.urls. Do NOT change version (that's Task 15).

- [ ] **Step 2: Create py.typed marker and release workflow**

- [ ] **Step 3: Test build**

```bash
micromamba run -n shiny hatch build
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/instream/py.typed .github/workflows/release.yml
git commit -m "feat: add PyPI packaging metadata and release workflow"
```

---

## Task 7: LifeStage IntEnum (InSALMON names)

**Files:**
- Create: `src/instream/state/life_stage.py`
- Modify: 12+ files (see list below)

- [ ] **Step 1: Create life_stage.py with InSALMON design doc enum**

```python
"""Life stage definitions for inSTREAM/inSALMON fish agents."""
from enum import IntEnum


class LifeStage(IntEnum):
    """Life history stage stored as int8 in TroutState.life_history arrays.

    Names follow the InSALMON design doc (docs/plans/2026-04-08-insalmon-design.md)
    to avoid a breaking rename when marine stages are activated in v0.14.0.
    Values 3-6 are defined but not used until the marine domain is added.
    """
    FRY = 0              # post-emergence juvenile (was "resident")
    PARR = 1             # anadromous juvenile, pre-smolt (was "anad_juvenile")
    SPAWNER = 2          # active spawner (was "anad_adult")
    SMOLT = 3            # outmigrating juvenile (v0.14.0+)
    OCEAN_JUVENILE = 4   # marine feeding (v0.14.0+)
    OCEAN_ADULT = 5      # marine mature (v0.14.0+)
    RETURNING_ADULT = 6  # upstream migration to natal reach
```

- [ ] **Step 2: Find and replace all magic numbers**

```bash
grep -rn "life_history.*== [0126]" src/instream/ tests/
grep -rn "life_history\[.*\] = [0126]" src/instream/ tests/
grep -rn "life_history != [0126]" src/instream/ tests/
```

Replace each with the corresponding `LifeStage.XXX` name. Key locations:
- `model_day_boundary.py`: `life_history[i] == 2` → `LifeStage.SPAWNER`, `lh != 1` → `lh != LifeStage.PARR`, `lh_val = 2` → `LifeStage.RETURNING_ADULT`
- `modules/migration.py:24`: `life_history != 1` → `life_history != LifeStage.PARR`
- `modules/spawning.py:378`: `life_history[slots] = 0` → `LifeStage.FRY`
- `tests/test_spawning.py:358,370`: `life_history[slot] == 2` → `LifeStage.SPAWNER`

**IMPORTANT:** Adult arrivals (`model_day_boundary.py`, currently assigns `lh_val = 2`) should use `LifeStage.RETURNING_ADULT` (6), not `LifeStage.SPAWNER` (2). Returning adults hold until spawn season, then transition to SPAWNER. This is a semantic correction, not just a rename.

- [ ] **Step 3: Run full test suite**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 4: Commit ALL affected files**

Stage ALL files modified in Step 2 (grep results will show the full list):

```bash
git add src/instream/state/life_stage.py
git add -u src/instream/ tests/  # stages all modified tracked files in src/ and tests/
git commit -m "refactor: replace life_history magic numbers with LifeStage IntEnum

Uses InSALMON design doc names (FRY/PARR/SPAWNER/RETURNING_ADULT) to
avoid breaking rename when marine stages are added in v0.14.0.
Adult arrivals now use RETURNING_ADULT (6) not SPAWNER (2)."
```

---

## Task 8: Config Schema Updates

**Files:**
- Modify: `src/instream/io/config.py` (SpeciesConfig Pydantic model)
- Modify: `src/instream/state/params.py` (SpeciesParams frozen dataclass)

- [ ] **Step 1: Add new parameters to SpeciesConfig**

```python
# In SpeciesConfig (io/config.py)
mort_condition_K_crit: float = 0.8
fecundity_noise: float = 0.0
spawn_date_jitter_days: int = 0
outmigration_max_prob: float = 0.1
outmigration_min_length: float = 8.0
fitness_growth_weight: float = 1.0  # alpha for growth-fitness integration
```

- [ ] **Step 2: Add to SpeciesParams and params_from_config**

- [ ] **Step 3: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_config.py -v --tb=long
git add src/instream/io/config.py src/instream/state/params.py
git commit -m "feat: add InSALMON species parameters to config schema"
```

---

## Task 9: Outmigration Probability

**Files:**
- Modify: `src/instream/modules/migration.py`
- Modify: `src/instream/model_day_boundary.py`
- Create: `tests/test_outmigration.py`

- [ ] **Step 1: Write failing test**

```python
class TestOutmigrationProbability:
    def test_poor_fitness_increases_migration(self):
        from instream.modules.migration import outmigration_probability
        p_low = outmigration_probability(fitness=0.1, length=10.0, min_length=8.0, max_prob=0.1)
        p_high = outmigration_probability(fitness=0.9, length=10.0, min_length=8.0, max_prob=0.1)
        assert p_low > p_high

    def test_below_min_length_no_migration(self):
        from instream.modules.migration import outmigration_probability
        p = outmigration_probability(fitness=0.1, length=5.0, min_length=8.0, max_prob=0.1)
        assert p == 0.0
```

- [ ] **Step 2: Implement**

```python
def outmigration_probability(fitness, length, min_length, max_prob=0.1):
    """Fitness-based probability of downstream outmigration.

    Fish below min_length never migrate. Above min_length, probability
    increases as fitness decreases (poor conditions trigger outmigration).
    """
    if length < min_length:
        return 0.0
    return max_prob * max(0.0, 1.0 - fitness)
```

- [ ] **Step 3: Wire into _do_migration alongside existing should_migrate**

In `model_day_boundary.py`, add the outmigration probability check for `LifeStage.PARR` fish. Outmigrated fish are marked `alive=False` and tracked in `_outmigrants` (same as current behavior).

- [ ] **Step 4: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_outmigration.py tests/test_migration.py -v --tb=long
git add src/instream/modules/migration.py src/instream/model_day_boundary.py tests/test_outmigration.py
git commit -m "feat: add fitness-based outmigration probability for anadromous juveniles"
```

---

## Task 10: Condition Survival Enhancement

**Files:**
- Modify: `src/instream/modules/survival.py` (survival_condition, ~line 97-98)
- Uses: `mort_condition_K_crit` from Task 8

- [ ] **Step 1: Read current hardcoded threshold**

The `0.8` at survival.py:97-98 is the critical condition breakpoint.

- [ ] **Step 2: Replace with species parameter**

Pass `K_crit` from `SpeciesParams` through the call chain. Default `0.8` preserves backward compatibility.

- [ ] **Step 3: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_survival.py -v --tb=long
git add src/instream/modules/survival.py
git commit -m "feat: parameterize condition survival threshold per species"
```

---

## Task 11: Spawn Perturbation

**Files:**
- Modify: `src/instream/modules/spawning.py`
- Uses: `fecundity_noise`, `spawn_date_jitter_days` from Task 8

- [ ] **Step 1: Write failing test**

```python
class TestSpawnPerturbation:
    def test_fecundity_varies_with_noise(self):
        # Call create_redd with fecundity_noise > 0, different seeds
        # Assert egg counts differ
        pytest.skip("implement in Step 2")

    def test_zero_noise_is_deterministic(self):
        # Call create_redd with fecundity_noise=0
        # Assert same egg count regardless of seed
        pytest.skip("implement in Step 2")
```

- [ ] **Step 2: Add lognormal noise to fecundity in create_redd**

- [ ] **Step 3: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_spawning.py -v --tb=long
git add src/instream/modules/spawning.py tests/test_spawning.py
git commit -m "feat: add fecundity noise and spawn date jitter"
```

---

## Task 12: Adult Holding Behavior

**Files:**
- Modify: `src/instream/modules/behavior.py`
- Create: `tests/test_holding.py`

Activity code 4 ("hold") is documented in `trout_state.py:19` but never assigned in behavior.py.

- [ ] **Step 1: Read behavior.py select_habitat_and_activity to understand activity assignment**

- [ ] **Step 2: Add holding branch for RETURNING_ADULT fish**

Before the normal drift/search/hide fitness evaluation, check if the fish is `LifeStage.RETURNING_ADULT`. If so, select the lowest-velocity wet cell in range and assign `activity=4`.

- [ ] **Step 3: Write tests**

```python
class TestAdultHolding:
    def test_returning_adult_uses_hold_activity(self):
        # Set up fish with life_history=LifeStage.RETURNING_ADULT
        # After habitat selection, activity should be 4
        pytest.skip("implement in Step 2")
```

- [ ] **Step 4: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_holding.py -v --tb=long
git add src/instream/modules/behavior.py tests/test_holding.py
git commit -m "feat: explicit adult holding behavior for returning adults"
```

---

## Task 13: Growth-Fitness Integration

**Files:**
- Modify: `src/instream/model.py:82-96` (fitness EMA update + _do_survival call)
- Modify: `src/instream/model_environment.py` (_do_survival return value)

**Current state:** Fitness EMA at model.py:82-93 runs BEFORE `_do_survival` at line 96. Survival probabilities are not available during fitness update.

- [ ] **Step 1: Make _do_survival return per-fish survival probabilities**

In `model_environment.py`, change `_do_survival` to return the `survival_probs` array instead of discarding it.

- [ ] **Step 2: Move fitness EMA update to AFTER _do_survival**

In `model.py`, reorder:
```python
# Old:
# fitness EMA update (lines 82-93)
# _do_survival (line 96)

# New:
survival_probs = self._do_survival(step_length)
# fitness EMA update using both growth and survival
```

- [ ] **Step 3: Implement combined fitness formula**

```python
alpha = float(self._sp_arrays["fitness_growth_weight"][sp_idx])
growth_signal = float(self.trout_state.last_growth_rate[i])
surv_signal = float(survival_probs[i])
current = alpha * growth_signal + (1.0 - alpha) * surv_signal
# Then apply EMA as before
```

With `fitness_growth_weight=1.0` (default), this is identical to current behavior (pure growth EMA). Fully backward compatible.

- [ ] **Step 4: Run full suite**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 5: Commit**

```bash
git add src/instream/model.py src/instream/model_environment.py
git commit -m "feat: integrate survival projection into fitness metric

fitness = alpha * growth_ema + (1-alpha) * survival_ema
Default alpha=1.0 preserves current pure-growth behavior."
```

---

## Task 14: InSALMO Validation Gate

**Files:**
- Create: `tests/test_insalmo_validation.py`

Requires NetLogo GUI to generate reference data for InSALMO-specific behaviors.

- [ ] **Step 1: Run NetLogo with adult arrivals and outmigration enabled**

Use `InSALMO7.4_test.nlogox` in GUI. Generate reference data for:
- Adult arrival population counts
- Outmigrant counts and lengths

- [ ] **Step 2: Write validation tests**

```python
class TestInSALMOBehaviors:
    def test_returning_adults_hold(self):
        """Verify returning adults use holding behavior."""
        pytest.skip("implement after generating NetLogo reference data")

    def test_outmigration_occurs(self):
        """Verify some juveniles outmigrate based on fitness."""
        pytest.skip("implement after generating NetLogo reference data")
```

- [ ] **Step 3: Run and commit**

```bash
git add tests/test_insalmo_validation.py
git commit -m "feat: add InSALMO-specific validation tests"
```

---

## Task 15: Documentation and Release v0.13.0

**Files:**
- Modify: `CHANGELOG.md`, `README.md`, `pyproject.toml`, `src/instream/__init__.py`

- [ ] **Step 1: Run full test suite**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 2: Update docs/api-reference.md**

Add new modules: `life_stage.py`, updated migration.py, behavior.py.

- [ ] **Step 3: Build Sphinx docs**

```bash
micromamba run -n shiny sphinx-build -b html docs/source docs/_build/html
```

- [ ] **Step 4: Run frontend smoke test**

```bash
micromamba run -n shiny python -m pytest tests/test_app_smoke.py tests/test_simulation_wrapper.py -v --tb=short
```

- [ ] **Step 5: Update CHANGELOG.md with v0.13.0 entries**

- [ ] **Step 6: Bump version to 0.13.0**

- [ ] **Step 7: Commit, tag, push**

```bash
git add CHANGELOG.md README.md pyproject.toml src/instream/__init__.py docs/
git commit -m "release: v0.13.0 — deferred items, InSALMON foundation, Sphinx, PyPI"
git tag v0.13.0
git push origin master --tags
```

---

## Summary

| Task | Section | Description | Est. Time |
|------|---------|-------------|-----------|
| 1 | Deferred | Fitness report cross-validation (with actual logic) | 2 days |
| 2 | Deferred | Sub-daily behavioral validation | 1 day |
| 3 | Deferred | Harvest behavioral validation | 0.5 days |
| 4 | Deferred | JAX spawn_suitability with interpax (**params) | 1.5 days |
| 5 | Deferred | Sphinx docs at docs/source/ + CI build | 1.5 days |
| 6 | Deferred | PyPI packaging + release workflow | 1 day |
| 7 | InSALMON | LifeStage IntEnum (InSALMON names, 12+ files) | 1 day |
| 8 | InSALMON | Config schema updates for new params | 0.5 days |
| 9 | InSALMON | Outmigration probability | 1 day |
| 10 | InSALMON | Condition survival enhancement | 0.5 days |
| 11 | InSALMON | Spawn perturbation | 0.5 days |
| 12 | InSALMON | Adult holding behavior | 1 day |
| 13 | InSALMON | Growth-fitness integration (step reorder) | 2 days |
| 14 | InSALMON | InSALMO validation gate | 2 days |
| 15 | Release | Documentation and release | 1 day |
| — | Buffer | Section 1 overflow (Day 10) + Section 2 overflow (Day 20) | 2 days |

**Task estimates sum to 17 days. With 2 buffer days: 19 days. Expected total: 22 working days** (accounting for investigation time, NetLogo GUI runs, and debugging). Best case 17, worst case 28.

---

## Out of Scope (v0.14.0+)

- Marine domain (MarineDomain class, zones, ocean growth/survival, fishing)
- Environmental drivers (NetCDF, WMS)
- FreshwaterDomain/MarineDomain refactor of model.py (domain-dispatched step)
- TroutState marine fields (zone_idx, sea_winters, smolt_date, natal_reach_idx)
- Smoltification readiness accumulation (photoperiod + temperature trigger)
- Multi-generation simulation
- Ensemble runs
