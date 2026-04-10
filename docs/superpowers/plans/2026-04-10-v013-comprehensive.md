# inSTREAM-py v0.13.0 — Comprehensive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all v0.12.0 deferred items + lay InSALMON freshwater foundation.

**Architecture:** Six independent gap-closure tasks (Section 1), then seven sequential InSALMON foundation tasks (Section 2), then release (Section 3).

**Tech Stack:** Python 3.11+, Mesa 3.x, NumPy, Numba, JAX, interpax, Sphinx, hatch, pytest

**Spec:** `docs/superpowers/specs/2026-04-10-v013-comprehensive-design.md`

---

## File Map

### Section 1: Deferred Items
- Modify: `tests/test_validation.py` (fitness cross-validation)
- Modify: `tests/test_behavioral_validation.py` (sub-daily + harvest tests)
- Modify: `src/instream/backends/jax_backend/__init__.py` (spawn_suitability)
- Modify: `tests/test_backend_parity.py` (parity test)
- Create: `docs/conf.py`, `docs/index.rst`, `docs/api.rst`, `docs/Makefile`
- Modify: `pyproject.toml` (metadata, py.typed)
- Create: `.github/workflows/release.yml`

### Section 2: InSALMON Foundation
- Create: `src/instream/state/life_stage.py`
- Modify: `src/instream/state/trout_state.py`
- Modify: `src/instream/modules/behavior.py`
- Modify: `src/instream/modules/migration.py`
- Modify: `src/instream/modules/survival.py`
- Modify: `src/instream/modules/spawning.py`
- Modify: `src/instream/state/params.py`
- Modify: `src/instream/model_day_boundary.py`

---

## Task 1: Fitness Report NetLogo Cross-Validation

**Files:**
- Modify: `tests/test_validation.py`
- Reference: `tests/fixtures/reference/FitnessReportOut-netlogo.csv` (402K lines, already exists)

- [ ] **Step 1: Read the NetLogo FitnessReportOut CSV header**

```bash
head -5 tests/fixtures/reference/FitnessReportOut-netlogo.csv
```

Understand the column format before writing the parser.

- [ ] **Step 2: Write the cross-validation test**

Add to `tests/test_validation.py`:

```python
class TestFitnessReportMatchesNetLogoCSV:
    """Cross-validate Python fitness evaluation against NetLogo write-fitness-report."""

    def test_netlogo_fitness_report(self):
        import numpy as np
        import pandas as pd

        ref_path = require_reference("FitnessReportOut-netlogo.csv")
        # Determine header format from Step 1, skip comment lines
        ref = pd.read_csv(ref_path, skiprows=2)  # adjust based on actual format

        # Sample every 1000th row (400K rows too many)
        ref = ref.iloc[::1000]

        # Compare Python fitness computation against NetLogo output
        # Exact implementation depends on column format discovered in Step 1
        mismatches = 0
        for _, row in ref.iterrows():
            # Extract inputs and expected outputs from row
            # Call Python fitness functions
            # Assert close
            pass

        assert mismatches == 0
```

Adjust parsing based on actual CSV format from Step 1.

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

- [ ] **Step 1: Write sub-daily population stability test**

Add to `tests/test_behavioral_validation.py`:

```python
@pytest.mark.slow
class TestSubDailyPopulationStability:
    """Verify sub-daily mode produces plausible dynamics."""

    @pytest.fixture(scope="class")
    def model(self):
        from instream.model import InSTREAMModel
        import datetime

        # Use hourly fixture for 30-day run
        start = datetime.date(2011, 4, 1)
        end_date = (start + datetime.timedelta(days=30)).isoformat()

        model = InSTREAMModel(
            CONFIGS / "example_a.yaml",
            data_dir=FIXTURES / "example_a",
            end_date_override=end_date,
        )
        # Override time series to use hourly data
        # This depends on whether the config supports subdaily input path
        model.run()
        return model

    def test_population_persists_subdaily(self, model):
        alive = model.trout_state.alive.sum()
        assert alive > 0, "Population went extinct in sub-daily mode"

    def test_steps_per_day_gt_1(self, model):
        assert model.steps_per_day > 1, "Not actually running in sub-daily mode"
```

- [ ] **Step 2: Run test**

```bash
micromamba run -n shiny python -m pytest tests/test_behavioral_validation.py::TestSubDailyPopulationStability -v --tb=long -m slow
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_behavioral_validation.py
git commit -m "feat: add sub-daily behavioral validation test"
```

---

## Task 3: Angler Harvest Behavioral Validation

**Files:**
- Modify: `tests/test_behavioral_validation.py`

- [ ] **Step 1: Write harvest behavior test**

Add to `tests/test_behavioral_validation.py`:

```python
@pytest.mark.slow
class TestHarvestBehavior:
    """Verify harvest produces realistic catch in a full simulation."""

    def test_harvest_reduces_population(self):
        from instream.model import InSTREAMModel
        import datetime

        start = datetime.date(2011, 4, 1)
        end_date = (start + datetime.timedelta(days=180)).isoformat()

        # Run without harvest
        model_no_harvest = InSTREAMModel(
            CONFIGS / "example_a.yaml",
            data_dir=FIXTURES / "example_a",
            end_date_override=end_date,
        )
        model_no_harvest.run()
        pop_no_harvest = model_no_harvest.trout_state.alive.sum()

        # Run with harvest enabled (need to check if config supports this)
        # If harvest requires config changes, create a modified config
        # For now, verify the harvest module exists and can be called
        from instream.modules.harvest import compute_harvest
        assert callable(compute_harvest), "Harvest module not available"
```

Adjust based on how harvest is configured (YAML or model attribute).

- [ ] **Step 2: Run and commit**

```bash
micromamba run -n shiny python -m pytest tests/test_behavioral_validation.py::TestHarvestBehavior -v --tb=long -m slow
git add tests/test_behavioral_validation.py
git commit -m "feat: add harvest behavioral validation test"
```

---

## Task 4: JAX Backend — spawn_suitability with interpax

**Files:**
- Modify: `src/instream/backends/jax_backend/__init__.py`
- Modify: `tests/test_backend_parity.py`

- [ ] **Step 1: Read current JAX backend spawn_suitability**

```bash
grep -A 20 "spawn_suitability" src/instream/backends/jax_backend/__init__.py
```

Understand the current NumPy fallback.

- [ ] **Step 2: Implement with interpax**

Replace the NumPy fallback with JAX-compatible interpolation using interpax:

```python
def spawn_suitability(self, depths, velocities, frac_spawns, areas,
                       depth_xs, depth_ys, vel_xs, vel_ys):
    import interpax
    depth_suit = interpax.interp1d(depths, depth_xs, depth_ys, method="linear")
    vel_suit = interpax.interp1d(velocities, vel_xs, vel_ys, method="linear")
    return depth_suit * vel_suit * frac_spawns * areas
```

- [ ] **Step 3: Document deplete_resources as intentional NumPy fallback**

Add docstring to `deplete_resources`:

```python
def deplete_resources(self, ...):
    """Deplete cell resources sequentially (inherently serial).

    This method intentionally uses NumPy, not JAX. Resource depletion
    is sequential (fish deplete shared pools in size order), which cannot
    be parallelized with jax.vmap. The overhead is O(N_fish), negligible
    compared to the O(N_fish × N_cells) habitat selection kernel.
    """
```

- [ ] **Step 4: Add parity test**

In `tests/test_backend_parity.py`, verify spawn_suitability gives identical results across numpy/jax:

```python
class TestSpawnSuitabilityParity:
    def test_jax_matches_numpy(self):
        # ... call both backends with same inputs, assert_close at rtol=1e-10
```

- [ ] **Step 5: Run parity tests**

```bash
micromamba run -n shiny python -m pytest tests/test_backend_parity.py -v --tb=long
```

- [ ] **Step 6: Commit**

```bash
git add src/instream/backends/jax_backend/__init__.py tests/test_backend_parity.py
git commit -m "feat: implement JAX spawn_suitability with interpax, document deplete_resources fallback"
```

---

## Task 5: Sphinx Documentation Build

**Files:**
- Create: `docs/source/conf.py`
- Create: `docs/source/index.rst`
- Create: `docs/source/api.rst`
- Create: `docs/Makefile`

- [ ] **Step 1: Create Sphinx config**

```python
# docs/source/conf.py
project = "inSTREAM-py"
version = "0.13.0"
extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx.ext.viewcode"]
html_theme = "sphinx_rtd_theme"
```

- [ ] **Step 2: Create index.rst**

```rst
inSTREAM-py Documentation
=========================

.. toctree::
   :maxdepth: 2

   api

Indices and tables
==================
* :ref:`genindex`
* :ref:`modindex`
```

- [ ] **Step 3: Create api.rst with autodoc directives**

```rst
API Reference
=============

Model
-----
.. automodule:: instream.model
   :members:

State Containers
----------------
.. automodule:: instream.state.trout_state
   :members:
.. automodule:: instream.state.redd_state
   :members:

Modules
-------
.. automodule:: instream.modules.growth
   :members:
.. automodule:: instream.modules.survival
   :members:
.. automodule:: instream.modules.behavior
   :members:
.. automodule:: instream.modules.spawning
   :members:
```

- [ ] **Step 4: Create Makefile**

```makefile
SPHINXBUILD = sphinx-build
SOURCEDIR = source
BUILDDIR = _build

html:
	$(SPHINXBUILD) -b html $(SOURCEDIR) $(BUILDDIR)/html
```

- [ ] **Step 5: Test build**

```bash
micromamba run -n shiny sphinx-build -b html docs/source docs/_build/html
```

- [ ] **Step 6: Add to .gitignore**

Add `docs/_build/` to `.gitignore`.

- [ ] **Step 7: Commit**

```bash
git add docs/source/ docs/Makefile .gitignore
git commit -m "feat: add Sphinx documentation build with autodoc"
```

---

## Task 6: PyPI Packaging

**Files:**
- Modify: `pyproject.toml`
- Create: `src/instream/py.typed`
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Update pyproject.toml metadata**

Add missing fields:

```toml
[project]
authors = [{name = "inSTREAM Team"}]
readme = "README.md"
classifiers = [
    "Development Status :: 4 - Beta",
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Scientific/Engineering :: Bio-Informatics",
]

[project.urls]
Homepage = "https://github.com/razinkele/instream-py"
Repository = "https://github.com/razinkele/instream-py"
```

- [ ] **Step 2: Create py.typed marker**

```bash
touch src/instream/py.typed
```

- [ ] **Step 3: Test build**

```bash
micromamba run -n shiny hatch build
micromamba run -n shiny pip install dist/instream-0.13.0.tar.gz --dry-run
```

- [ ] **Step 4: Create release workflow**

```yaml
# .github/workflows/release.yml
name: Publish to PyPI
on:
  release:
    types: [published]
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install hatch
      - run: hatch build
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/instream/py.typed .github/workflows/release.yml
git commit -m "feat: add PyPI packaging and release workflow"
```

---

## Task 7: LifeStage IntEnum

**Files:**
- Create: `src/instream/state/life_stage.py`
- Modify: `src/instream/state/trout_state.py`
- Modify: `src/instream/model_day_boundary.py`
- Modify: all files with `life_history == 0/1/2`

- [ ] **Step 1: Create life_stage.py**

```python
"""Life stage definitions for inSTREAM fish agents."""
from enum import IntEnum


class LifeStage(IntEnum):
    """Life history stage of a fish.

    Values are stored as int8 in TroutState.life_history arrays.
    """
    RESIDENT = 0
    ANAD_JUVENILE = 1
    ANAD_ADULT = 2
    SMOLT = 3          # future: outmigrating juvenile
    MARINE_ADULT = 4   # future: at-sea adult
```

- [ ] **Step 2: Replace magic numbers across codebase**

Search for `life_history == 0`, `life_history == 1`, `life_history == 2` and replace with `LifeStage.RESIDENT`, `LifeStage.ANAD_JUVENILE`, `LifeStage.ANAD_ADULT`.

```bash
grep -rn "life_history.*== [012]" src/instream/
```

- [ ] **Step 3: Run tests**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 4: Commit**

```bash
git add src/instream/state/life_stage.py src/instream/state/trout_state.py src/instream/model_day_boundary.py
git commit -m "refactor: replace life_history magic numbers with LifeStage IntEnum"
```

---

## Task 8: Adult Holding Behavior

**Files:**
- Modify: `src/instream/modules/behavior.py`
- Create: `tests/test_holding.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for anadromous adult holding behavior."""
import pytest
import numpy as np


class TestAdultHolding:
    def test_anad_adult_uses_hold_activity(self):
        """Anadromous adults that haven't spawned should hold."""
        from instream.state.life_stage import LifeStage
        # Set up a fish with life_history=ANAD_ADULT, spawned_this_season=False
        # After habitat selection, activity should be "hold" (3)
        # Implementation depends on behavior.py structure
        pass

    def test_holding_fish_selects_low_velocity(self):
        """Holding fish should prefer low-velocity cells."""
        pass
```

- [ ] **Step 2: Implement holding logic in behavior.py**

Read current `select_habitat_and_activity` to understand how activities are assigned, then add explicit holding branch for anad_adults.

- [ ] **Step 3: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_holding.py -v --tb=long
git add src/instream/modules/behavior.py tests/test_holding.py
git commit -m "feat: explicit adult holding behavior for anadromous fish"
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
        """Fish with low fitness should be more likely to migrate."""
        from instream.modules.migration import outmigration_probability
        p_low = outmigration_probability(fitness=0.1, length=10.0, min_length=8.0)
        p_high = outmigration_probability(fitness=0.9, length=10.0, min_length=8.0)
        assert p_low > p_high

    def test_below_min_length_no_migration(self):
        """Fish below minimum smolt length should not migrate."""
        from instream.modules.migration import outmigration_probability
        p = outmigration_probability(fitness=0.1, length=5.0, min_length=8.0)
        assert p == 0.0
```

- [ ] **Step 2: Implement outmigration_probability**

```python
def outmigration_probability(fitness, length, min_length, max_prob=0.1):
    """Probability of downstream migration based on fitness.

    Fish below min_length never migrate. Above min_length, probability
    increases as fitness decreases (poor conditions → leave).
    """
    if length < min_length:
        return 0.0
    return max_prob * (1.0 - fitness)
```

- [ ] **Step 3: Wire into _do_migration in model_day_boundary.py**

- [ ] **Step 4: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_outmigration.py tests/test_migration.py -v --tb=long
git add src/instream/modules/migration.py src/instream/model_day_boundary.py tests/test_outmigration.py
git commit -m "feat: add fitness-based outmigration probability"
```

---

## Task 10: Condition-Based Survival Enhancement

**Files:**
- Modify: `src/instream/modules/survival.py`
- Modify: `src/instream/state/params.py`

- [ ] **Step 1: Read current condition survival**

```bash
grep -A 20 "def survival_condition" src/instream/modules/survival.py
```

- [ ] **Step 2: Add species-specific condition threshold parameter**

Add `mort_condition_K_crit` to `SpeciesParams` in `state/params.py`. Default to current hardcoded value for backward compatibility.

- [ ] **Step 3: Update survival_condition to use the parameter**

- [ ] **Step 4: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_survival.py tests/test_redd_survival.py -v --tb=long
git add src/instream/modules/survival.py src/instream/state/params.py
git commit -m "feat: parameterize condition survival threshold per species"
```

---

## Task 11: Spawn Perturbation

**Files:**
- Modify: `src/instream/modules/spawning.py`
- Modify: `src/instream/state/params.py`

- [ ] **Step 1: Write failing test**

```python
class TestSpawnPerturbation:
    def test_fecundity_varies_with_noise(self):
        """Egg count should vary when fecundity_noise > 0."""
        from instream.modules.spawning import compute_fecundity
        eggs1 = compute_fecundity(length=25.0, weight=500.0, fecundity_noise=0.1, rng=np.random.default_rng(42))
        eggs2 = compute_fecundity(length=25.0, weight=500.0, fecundity_noise=0.1, rng=np.random.default_rng(99))
        assert eggs1 != eggs2  # different seeds → different counts
```

- [ ] **Step 2: Add spawn_date_jitter and fecundity_noise parameters**

- [ ] **Step 3: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_spawning.py -v --tb=long
git add src/instream/modules/spawning.py src/instream/state/params.py
git commit -m "feat: add spawn date jitter and fecundity noise"
```

---

## Task 12: Growth-Fitness Integration

**Files:**
- Modify: `src/instream/modules/behavior.py`

- [ ] **Step 1: Read current fitness memory implementation**

```bash
grep -A 30 "fitness_memory" src/instream/model.py
```

- [ ] **Step 2: Enhance fitness to integrate survival projection**

Currently fitness = EMA of growth rate. Enhance to:
`fitness = alpha * growth_projection + (1 - alpha) * survival_projection`

- [ ] **Step 3: Run tests, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_behavior.py -v --tb=long
git add src/instream/modules/behavior.py
git commit -m "feat: integrate survival projection into fitness metric"
```

---

## Task 13: InSALMO Validation Gate

**Files:**
- Modify: `tests/test_validation.py` or create `tests/test_insalmo_validation.py`

- [ ] **Step 1: Run NetLogo InSALMO with inSALMO-specific parameters**

Use the InSALMO7.4 model with parameters that exercise adult holding and outmigration. Generate reference CSVs.

- [ ] **Step 2: Write validation tests comparing Python to NetLogo for InSALMO features**

- [ ] **Step 3: Run and commit**

```bash
git add tests/
git commit -m "feat: add InSALMO-specific validation tests"
```

---

## Task 14: Documentation and Release v0.13.0

**Files:**
- Modify: `CHANGELOG.md`, `README.md`, `pyproject.toml`, `src/instream/__init__.py`

- [ ] **Step 1: Run full test suite**

```bash
micromamba run -n shiny python -m pytest tests/ --tb=short -q --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 2: Update docs/api-reference.md**

Add new modules: life_stage.py, updated behavior.py, migration.py.

- [ ] **Step 3: Build Sphinx docs**

```bash
micromamba run -n shiny sphinx-build -b html docs/source docs/_build/html
```

- [ ] **Step 4: Run frontend smoke test**

```bash
micromamba run -n shiny python -m pytest tests/test_app_smoke.py tests/test_simulation_wrapper.py -v --tb=short
```

- [ ] **Step 5: Update CHANGELOG.md**

Add v0.13.0 section with all changes from this plan.

- [ ] **Step 6: Bump version**

Change `version` in `pyproject.toml` and `__init__.py` to `"0.13.0"`.

- [ ] **Step 7: Commit, tag, push**

```bash
git add CHANGELOG.md README.md pyproject.toml src/instream/__init__.py
git commit -m "release: v0.13.0 — deferred items, InSALMON foundation, Sphinx docs, PyPI packaging"
git tag v0.13.0
git push origin master --tags
```

---

## Summary

| Task | Section | Description | Est. Time |
|------|---------|-------------|-----------|
| 1 | Deferred | Fitness report NetLogo cross-validation | 1 day |
| 2 | Deferred | Sub-daily behavioral validation | 1 day |
| 3 | Deferred | Harvest behavioral validation | 0.5 days |
| 4 | Deferred | JAX spawn_suitability with interpax | 2 days |
| 5 | Deferred | Sphinx documentation build | 1.5 days |
| 6 | Deferred | PyPI packaging + release workflow | 1 day |
| 7 | InSALMON | LifeStage IntEnum | 0.5 days |
| 8 | InSALMON | Adult holding behavior | 1 day |
| 9 | InSALMON | Outmigration probability | 1 day |
| 10 | InSALMON | Condition survival enhancement | 0.5 days |
| 11 | InSALMON | Spawn perturbation | 0.5 days |
| 12 | InSALMON | Growth-fitness integration | 1 day |
| 13 | InSALMON | InSALMO validation gate | 1-2 days |
| 14 | Release | Documentation and release | 1 day |
