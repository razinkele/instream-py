# inSTREAM-py v0.13.0 — Comprehensive Design Spec

**Date:** 2026-04-10
**Current version:** 0.12.0 (709 tests, 108-line model.py, NetLogo cross-validation)
**Target version:** 0.13.0
**Scope:** Complete all deferred v0.12.0 items + begin InSALMON marine extension foundation

---

## Motivation

v0.12.0 established scientific credibility (NetLogo cross-validation, behavioral validation, clean architecture). v0.13.0 has two goals:

1. **Close remaining gaps** — the 6 items deferred from v0.12.0
2. **Lay foundation for InSALMON** — the marine extension that adds anadromous Atlantic salmon lifecycle, which is the project's primary scientific deliverable for the HORIZON EUROPE grant

---

## Section 1: Deferred v0.12.0 Items (Days 1-8)

### 1.1 write-fitness-report Cross-Validation (1 day)

NetLogo 7.0.3 is now installed and `write-fitness-report` was generated as `FitnessReportOut-netlogo.csv` (402K lines). Add a cross-validation test that parses this CSV and compares against Python's fitness evaluation.

**Files:**
- Modify: `tests/test_validation.py` — add `TestFitnessReportMatchesNetLogoCSV`
- Reference: `tests/fixtures/reference/FitnessReportOut-netlogo.csv` (already exists)

### 1.2 Sub-daily Behavioral Validation (1 day)

The sub-daily mode (InSTREAM-SD, added in v0.7.0) has 10 unit tests but no behavioral validation proving the model produces plausible dynamics in hourly/peaking mode.

**Add to `tests/test_behavioral_validation.py`:**
- `TestSubDailyPopulationStability` — run Example A with hourly input for 30 days, assert population persists and growth is applied at day boundaries only
- Uses existing `tests/fixtures/subdaily/hourly_example_a.csv` fixture

### 1.3 Angler Harvest Behavioral Validation (0.5 days)

Harvest module (v0.11.0) has 5 unit tests but no validation that it produces realistic catch rates in a full simulation.

**Add to `tests/test_behavioral_validation.py`:**
- `TestHarvestBehavior` — run Example A with harvest enabled, assert: harvest occurs, catch < population, size selectivity working (harvested fish meet minimum length)

### 1.4 JAX Backend Completion (2 days)

Two methods still fall back to NumPy: `deplete_resources` and `spawn_suitability`.

**`deplete_resources`:** Inherently sequential (fish deplete shared cell resources in size order). Cannot be vectorized with `jax.vmap`. Options:
- (a) Keep NumPy fallback — pragmatic, no performance loss since depletion is O(N_fish) not O(N_fish × N_cells)
- (b) Implement with `jax.lax.scan` — theoretically possible but complex and fragile
- **Recommendation: (a)** — document as intentional, not a gap

**`spawn_suitability`:** Uses `np.interp` which has no JAX equivalent. Options:
- (a) Use `interpax` (already a dependency) for JAX-compatible interpolation
- (b) Keep NumPy fallback
- **Recommendation: (a)** — straightforward, `interpax>=0.3` is already in `[project.optional-dependencies]`

**Files:**
- Modify: `src/instream/backends/jax_backend/__init__.py` — implement `spawn_suitability` with interpax
- Modify: `tests/test_backend_parity.py` — add spawn_suitability parity test
- Document `deplete_resources` NumPy fallback as intentional in docstring

### 1.5 Sphinx Documentation Build (1.5 days)

Set up basic Sphinx docs with autodoc for the API reference.

**Files:**
- Create: `docs/conf.py`, `docs/index.rst`, `docs/api.rst`
- Create: `docs/Makefile`
- Modify: `pyproject.toml` — verify docs dependencies
- Add GitHub Actions step to build docs on push

### 1.6 PyPI Packaging (1 day)

Make `pip install instream` work. The project already uses hatch build system.

**Steps:**
- Verify `pyproject.toml` metadata (author, URLs, classifiers)
- Add `py.typed` marker for type checking
- Test build: `hatch build`
- Test install: `pip install dist/instream-0.13.0.tar.gz`
- Publish to TestPyPI first, then PyPI
- Add GitHub Actions release workflow

---

## Section 2: InSALMON Foundation — Phase 1 (Days 9-15)

Based on `docs/plans/2026-04-08-insalmon-design.md`. This section implements only the freshwater foundation (Milestone 1), not the marine extension.

### 2.1 LifeStage IntEnum (0.5 days)

Replace magic numbers (0=resident, 1=anad_juve, 2=anad_adult) with a proper IntEnum.

**Files:**
- Create: `src/instream/state/life_stage.py` — `LifeStage(IntEnum)` with RESIDENT, ANAD_JUVENILE, ANAD_ADULT, SMOLT, MARINE_ADULT (future-proofing)
- Modify: `src/instream/state/trout_state.py` — type hint `life_history` as LifeStage
- Modify: all files referencing `life_history == 0/1/2` — use enum names
- Modify: `src/instream/model_day_boundary.py` — post-spawn mortality check

### 2.2 Adult Holding Behavior (1 day)

Anadromous adults that haven't spawned yet should use "hold" activity (minimizing energy expenditure while waiting for spawn season). Currently partially implemented.

**Files:**
- Modify: `src/instream/modules/behavior.py` — explicit holding logic for anad_adults
- Add tests: holding fish don't drift-feed, holding fish select low-velocity cells

### 2.3 Outmigration Probability (1 day)

Juvenile fish decide to migrate downstream based on a fitness-based probability (not just reaching a size threshold). This is the smoltification trigger for Atlantic salmon.

**Files:**
- Modify: `src/instream/modules/migration.py` — add `outmigration_probability()` function
- Modify: `src/instream/model_day_boundary.py` — call outmigration check during migration phase
- Tests: verify probability increases with poor fitness, decreases with good fitness

### 2.4 Condition-Based Survival Enhancement (0.5 days)

Enhance condition survival to use species-specific parameters for the critical condition threshold (currently hardcoded).

**Files:**
- Modify: `src/instream/modules/survival.py` — parameterize condition survival thresholds
- Modify: `src/instream/state/params.py` — add `mort_condition_K_crit` parameter

### 2.5 Spawn Perturbation (0.5 days)

Add stochastic variation to spawning decisions (spawn date jitter, fecundity noise).

**Files:**
- Modify: `src/instream/modules/spawning.py` — add spawn_date_jitter and fecundity_noise parameters
- Tests: verify jittered timing and variable egg counts

### 2.6 Growth-Fitness Integration (1 day)

The fitness function currently uses a simple EMA of growth rate. InSALMON requires a more sophisticated fitness metric that integrates growth and survival projections.

**Files:**
- Modify: `src/instream/modules/behavior.py` — enhance fitness calculation
- Tests: verify fitness responds to both growth and survival signals

### 2.7 InSALMO Validation Gate (1 day)

Run the v7.4 NetLogo model with InSALMO-specific parameters and compare Python output.

**Files:**
- Add: validation tests comparing InSALMO-specific behavior (adult holding, outmigration)
- Reference data from NetLogo

---

## Section 3: Documentation & Release (Days 16-17)

### 3.1 CHANGELOG, README, Version Bump

- Update CHANGELOG.md with v0.13.0 entries
- Update README.md metrics
- Bump to 0.13.0 in pyproject.toml and __init__.py

### 3.2 Sphinx Docs Generation

- Build HTML docs
- Verify API autodoc covers all public modules

### 3.3 Tag and Push

- `git tag v0.13.0 && git push origin master --tags`

---

## Timeline Summary

| Days | Section | Deliverable |
|------|---------|-------------|
| 1-2 | 1.1-1.3 | Fitness cross-validation, sub-daily + harvest behavioral tests |
| 3-4 | 1.4 | JAX spawn_suitability with interpax, deplete_resources documented |
| 5-6 | 1.5 | Sphinx docs build |
| 7-8 | 1.6 | PyPI packaging + release workflow |
| 9 | 2.1 | LifeStage IntEnum |
| 10 | 2.2 | Adult holding behavior |
| 11 | 2.3 | Outmigration probability |
| 12 | 2.4-2.5 | Condition survival + spawn perturbation |
| 13 | 2.6 | Growth-fitness integration |
| 14-15 | 2.7 | InSALMO validation gate |
| 16-17 | 3.1-3.3 | Documentation and release |

**Expected: 17 working days.** Best case 14, worst case 22 (if InSALMO validation reveals issues).

## Dependencies

```
Section 1 items are independent — can be parallelized
Section 2 items are sequential (2.1 → 2.2 → 2.3 → ... → 2.7)
Section 3 depends on all above
```

## Out of Scope (v0.14.0+)

- Marine domain (zones, ocean growth, marine survival, fishing)
- Environmental drivers (NetCDF, WMS)
- Multi-generation simulation
- Ensemble runs
- Web deployment / cloud infrastructure
