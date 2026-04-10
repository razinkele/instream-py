# inSTREAM-py v0.13.0 — Comprehensive Design Spec (revised)

**Date:** 2026-04-10 (revised after 3-agent review)
**Current version:** 0.12.0 (709 tests, 108-line model.py, NetLogo cross-validation)
**Target version:** 0.13.0
**Scope:** Complete all deferred v0.12.0 items + begin InSALMON freshwater foundation

---

## Motivation

v0.12.0 established scientific credibility (NetLogo cross-validation, behavioral validation, clean architecture). v0.13.0 has two goals:

1. **Close remaining gaps** — the 6 items deferred from v0.12.0
2. **Lay foundation for InSALMON** — the marine extension for anadromous Atlantic salmon lifecycle, the project's primary HORIZON EUROPE deliverable

---

## Section 1: Deferred v0.12.0 Items (Days 1-10)

### 1.1 write-fitness-report Cross-Validation (2 days)

`FitnessReportOut-netlogo.csv` (402K lines) is already generated. CSV columns:
```
trout-length,trout-weight,trout-condition,daily-pred-survival,growth (g/g/d),fitness
```

The NetLogo fitness report sweeps condition (0.8-1.0), daily-pred-survival (0.95-1.0), and growth (-0.01 to 0.03) for each fish length/weight. The Python fitness function must reproduce the `fitness` column from those inputs.

**Files:**
- Modify: `tests/test_validation.py` — add `TestFitnessReportMatchesNetLogoCSV` with actual comparison logic (not a placeholder)
- Reference: `tests/fixtures/reference/FitnessReportOut-netlogo.csv`

### 1.2 Sub-daily Behavioral Validation (1 day)

Sub-daily mode has 10 unit tests but no behavioral validation. Subdaily fixtures exist: `tests/fixtures/subdaily/hourly_example_a.csv` and `peaking_example_a.csv`.

**Add to `tests/test_behavioral_validation.py`:**
- `TestSubDailyPopulationStability` — run Example A with hourly input for 30 days
- Must configure model to use the subdaily time series (check how `test_subdaily.py` does it)

### 1.3 Angler Harvest Behavioral Validation (0.5 days)

**Add to `tests/test_behavioral_validation.py`:**
- `TestHarvestBehavior` — verify harvest module can be called and produces plausible results

### 1.4 JAX Backend Completion (1.5 days)

**`spawn_suitability`:** Replace `np.interp` with `interpax.interp1d`. Must match the Protocol signature: `spawn_suitability(self, depths, velocities, frac_spawn, **params)` where params contains `area`, `depth_table_x`, `depth_table_y`, `vel_table_x`, `vel_table_y`. The JAX implementation at `jax_backend/__init__.py:534` currently uses `np.interp(np.asarray(depths), params["depth_table_x"], params["depth_table_y"])` — replace `np.interp` with `interpax.interp1d` keeping the same `**params` interface.

**`deplete_resources`:** Keep NumPy fallback. Document as intentional (inherently sequential — fish deplete shared cell resources in size order).

### 1.5 Sphinx Documentation Build (1.5 days)

Create Sphinx docs at `docs/source/` (new subdirectory, separates source from built docs).

**Files:**
- Create: `docs/source/conf.py`, `docs/source/index.rst`, `docs/source/api.rst`
- Create: `docs/Makefile`
- Add: `.github/workflows/docs.yml` — build docs on push (separate from release workflow)
- Add: `docs/_build/` to `.gitignore`

### 1.6 PyPI Packaging (1 day)

**Files:**
- Modify: `pyproject.toml` — add author, URLs, classifiers
- Create: `src/instream/py.typed`
- Create: `.github/workflows/release.yml` — publish on GitHub release

---

## Section 2: InSALMON Foundation (Days 11-20)

Based on `docs/plans/2026-04-08-insalmon-design.md`. Freshwater foundation only — no marine domain.

### 2.1 LifeStage IntEnum (1 day)

**Use the InSALMON design doc enum names from the start** (not the old inSTREAM names):

```python
class LifeStage(IntEnum):
    FRY = 0           # post-emergence juvenile (was "resident")
    PARR = 1          # anadromous juvenile, pre-smolt (was "anad_juvenile")
    SPAWNER = 2       # active spawner (was "anad_adult")
    SMOLT = 3         # outmigrating juvenile
    OCEAN_JUVENILE = 4 # marine feeding (v0.14.0+)
    OCEAN_ADULT = 5    # marine mature (v0.14.0+)
    RETURNING_ADULT = 6 # upstream migration to natal reach
```

**Rationale:** The old names (`RESIDENT=0, ANAD_JUVENILE=1, ANAD_ADULT=2`) would require a breaking rename in v0.14.0 when marine stages are added. The design doc explicitly warns about this.

**Scope:** 12+ files reference `life_history` magic numbers, including:
- `model_day_boundary.py` (3 locations: post-spawn mortality, migration guard, adult arrivals)
- `modules/migration.py` (should_migrate `life_history != 1`)
- `modules/spawning.py` (emergence sets `life_history = 0`)
- `tests/test_spawning.py` (assertions on `life_history == 2`)

All must be updated in the same commit. Tests must be updated too.

### 2.2 Config Schema Updates (0.5 days)

Add new species parameters to `io/config.py` Pydantic schema so they load from YAML:
- `mort_condition_K_crit` (Section 2.4)
- `fecundity_noise` (Section 2.5)
- `spawn_date_jitter_days` (Section 2.5)
- `outmigration_max_prob` (Section 2.3)
- `outmigration_min_length` (Section 2.3)

Without this, params added to `SpeciesParams` would silently use defaults.

### 2.3 Outmigration Probability (1 day)

Add `outmigration_probability(fitness, length, min_length, max_prob)` to `migration.py`. This extends (not replaces) the existing `should_migrate()` — both are called during `_do_migration`. The new function adds a fitness-based probability gate for anadromous juveniles.

**What happens to outmigrated fish:** They are marked `alive=False` and recorded in `_outmigrants` (same as current behavior in `migrate_fish_downstream`). MarineSpace doesn't exist yet — outmigrated fish leave the system. This is correct for freshwater-only validation.

### 2.4 Condition-Based Survival Enhancement (0.5 days)

Parameterize the hardcoded `K_crit = 0.8` threshold in `survival_condition()` (survival.py:97-98). Add `mort_condition_K_crit` to `SpeciesParams` with default `0.8` for backward compatibility.

### 2.5 Spawn Perturbation (0.5 days)

Add `fecundity_noise` (lognormal multiplier, default 0.0 = no noise) and `spawn_date_jitter_days` (uniform ±N days, default 0) to spawning. Currently `create_redd` computes eggs deterministically.

### 2.6 Adult Holding Behavior (1 day)

Activity code 4 ("hold") exists as a comment in `trout_state.py:19` but has no implementation in `behavior.py`. Add explicit holding branch for `LifeStage.RETURNING_ADULT` fish: they select the lowest-velocity available cell and use activity=4, bypassing drift/search/hide fitness evaluation.

### 2.7 Growth-Fitness Integration (2 days)

**Current state:** Fitness = EMA of `last_growth_rate` (model.py:82-93). Updated BEFORE survival is computed (line 96).

**Enhancement:** `fitness = alpha * growth_ema + (1 - alpha) * survival_ema`

**Step ordering fix:** Move the fitness EMA update to AFTER `_do_survival()` returns, so survival probabilities from the current step are available. `_do_survival` must return per-fish survival values (currently discarded after `apply_mortality`).

**Formula:** `alpha` is a new species parameter `fitness_growth_weight` (default 1.0 = current behavior, pure growth EMA). This is fully backward compatible.

### 2.8 InSALMO Validation Gate (2 days)

Run NetLogo InSALMO with adult arrivals enabled, verify:
- Adults arrive and hold
- Outmigration occurs for juveniles with poor fitness
- Spawning by returning adults
- Compare population dynamics trajectories

**Requires NetLogo GUI** (headless doesn't work for this model).

---

## Section 3: Documentation & Release (Days 21-22)

### 3.1 Update docs, CHANGELOG, README, version bump
### 3.2 Build Sphinx HTML docs
### 3.3 Tag v0.13.0 and push

---

## Timeline Summary

| Days | Section | Deliverable |
|------|---------|-------------|
| 1-2 | 1.1 | Fitness report cross-validation (actual test logic, not placeholder) |
| 3 | 1.2-1.3 | Sub-daily + harvest behavioral validation |
| 4-5 | 1.4 | JAX spawn_suitability with interpax (matching **params Protocol) |
| 6-7 | 1.5 | Sphinx docs at docs/source/ + CI build workflow |
| 8-9 | 1.6 | PyPI packaging + release workflow |
| 10 | — | Buffer / Section 1 overflow |
| 11 | 2.1 | LifeStage IntEnum (InSALMON names, 12+ files) |
| 12 | 2.2 | Config schema updates for new params |
| 13 | 2.3 | Outmigration probability |
| 14 | 2.4-2.5 | Condition survival + spawn perturbation |
| 15 | 2.6 | Adult holding behavior |
| 16-17 | 2.7 | Growth-fitness integration (step reordering + survival EMA) |
| 18-19 | 2.8 | InSALMO validation gate |
| 20 | — | Buffer / Section 2 overflow |
| 21-22 | 3.1-3.3 | Documentation and release |

**Expected: 22 working days.** Best case 17, worst case 28.

## Dependencies

```
Section 1 items are independent (can parallelize 1.1-1.3, then 1.4, then 1.5-1.6)
    Note: 1.5 (Sphinx) should come before 1.6 (PyPI) — Sphinx needs stable metadata
Section 2 is sequential: 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7 → 2.8
Section 3 depends on all above
```

## Out of Scope (v0.14.0+)

- Marine domain (MarineDomain class, zones, ocean growth/survival, fishing)
- Environmental drivers (NetCDF, WMS)
- FreshwaterDomain/MarineDomain refactor of model.py (domain-dispatched step)
- TroutState marine fields (zone_idx, sea_winters, smolt_date, natal_reach_idx)
- Smoltification readiness accumulation (photoperiod + temperature trigger)
- Multi-generation simulation
- Ensemble runs
