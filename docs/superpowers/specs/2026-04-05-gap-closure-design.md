# Gap Closure Design Spec

**Date:** 2026-04-05
**Version:** v0.10.0 baseline
**Goal:** Close all 26 remaining gaps to reach full NetLogo parity + extensions

---

## Verified Gap Inventory

### Tier 1: Simulation Correctness (7 items)

#### GAP-1: Migration uses species_order[0]
- **Location:** `model.py:998-1000`
- **Problem:** `_do_migration()` fetches `migrate_fitness_L1/L9` from `self.config.species[self.species_order[0]]` — all fish get species-0 migration params regardless of their species.
- **Fix:** Move param lookup inside the fish loop. Index by `species_idx[i]` to get correct species config. Pre-build `_sp_mig_L1` and `_sp_mig_L9` arrays (shape `(n_species,)`) in `__init__` following the existing `_sp_arrays` pattern.
- **Also fix:** Lines 325-330 and 1096-1099 (fallback species for unknown names in population/arrival files — acceptable as warnings, but log them).
- **Test:** Add test with 2 species having different migration L1/L9; verify each species uses its own params.
- **Effort:** S

#### GAP-2: Solar irradiance overestimates
- **Location:** `numpy_backend/__init__.py:104-116`, `numba_backend/__init__.py:42`, `jax_backend/__init__.py:55-157`
- **Problem:** Uses noon solar elevation (`90 - |lat - decl|`) instead of daily-integral irradiance. Overestimates because average elevation < noon elevation.
- **Fix:** Replace with hour-angle integral formula:
  ```
  H = arccos(-tan(lat) * tan(decl))  # already computed for day_length
  I_daily = (S0 / pi) * (sin(lat)*sin(decl)*H + cos(lat)*cos(decl)*sin(H))
  irradiance = I_daily * light_correction * shading
  ```
  This integrates solar elevation over the entire daylight period. Update all 3 backends identically.
- **Test:** Add irradiance validation column to `test-day-length.csv` reference (generate from NetLogo `calcDailyMeanSolar`). Extend `TestDayLengthMatchesNetLogo` to check irradiance with rtol=1e-4.
- **Effort:** M

#### GAP-3: Light turbidity constant missing
- **Location:** All 3 backends, `compute_cell_light()` method
- **Problem:** Beer-Lambert formula is `light = irradiance * exp(-turbid_coef * turbidity * depth / 2)` but NetLogo has an additive constant: `exp(-(turbid_coef * turbidity + turbidity_const) * depth / 2)`.
- **Fix:** Add `turbidity_constant` parameter to `LightConfig` (default 0.0 for backward compatibility). Pass through to `compute_cell_light()`. Update all 3 backends.
- **Test:** Existing light tests with `turbidity_constant=0.0` must pass unchanged. Add test with non-zero constant.
- **Effort:** S

#### GAP-4: Fitness memory not implemented
- **Location:** `state/trout_state.py`, `modules/behavior.py`, `model.py`
- **Problem:** NetLogo uses an exponential moving average of past fitness to smooth habitat decisions. Config has `fitness_memory_frac` but it's never applied.
- **Fix:**
  1. Add `fitness_memory` array to `TroutState` (shape `(capacity,)`, init 0.0).
  2. After `select_habitat_and_activity()`, update: `fitness_memory[i] = frac * fitness_memory[i] + (1 - frac) * current_fitness`.
  3. Use `fitness_memory` (not raw fitness) in migration decisions (`_do_migration` compares migration fitness to `fitness_memory[i]` instead of `last_growth_rate[i]`).
- **Test:** Property test: fitness_memory converges to steady-state fitness after many steps. Integration test: fish with high memory fraction are more "sticky" to cells.
- **Effort:** M

#### GAP-5: Drift regeneration distance not applied
- **Location:** `io/config.py:209,247` (parsed), `model.py` resource replenishment section
- **Problem:** `drift_regen_distance` is in the config schema but never used. NetLogo regenerates drift food only for cells that are at least `drift_regen_distance` downstream of any feeding fish.
- **Fix:**
  1. After habitat selection (fish positions known), build set of occupied cells.
  2. During resource replenishment, for each cell: if any occupied cell is within `drift_regen_distance` upstream, reduce or skip drift replenishment.
  3. Requires spatial query: for each cell, check if upstream neighbors within distance are occupied.
  4. If `drift_regen_distance <= 0` (default), skip this logic entirely (backward compatible).
- **Test:** Place fish in cell A. Cell B is 50cm downstream. With `drift_regen_distance=100cm`, cell B should not regenerate drift. With distance=0, it should.
- **Effort:** M

#### GAP-6: Spawn defense area not applied
- **Location:** `io/config.py:130` (parsed), `modules/spawning.py`
- **Problem:** `spawn_defense_area` is configured but never used. NetLogo prevents new redds within this area of existing redds.
- **Fix:** In `select_spawn_cell()`, after scoring candidate cells, exclude cells where any existing alive redd has centroid within `spawn_defense_area` cm. Use FEMSpace KD-tree query on redd positions.
- **Test:** Place redd at cell A. Attempt spawn at cell B (within defense area) — should be blocked. Cell C (outside) — should succeed.
- **Effort:** S

#### GAP-7: Year shuffler not wired
- **Location:** `io/time_manager.py` (YearShuffler class exists), `model.py`
- **Problem:** `YearShuffler` is implemented but never instantiated or called in `InSTREAMModel`.
- **Fix:**
  1. Add `shuffle_years: bool = False` and `shuffle_seed: int = 0` to `SimulationConfig`.
  2. In `InSTREAMModel.__init__`, if `shuffle_years`, create `YearShuffler(seed)`.
  3. At year boundary in `step()`, call shuffler to remap time-series year index.
- **Test:** Run 3-year simulation with `shuffle_years=True`. Verify year order differs from sequential. Verify model completes without error.
- **Effort:** S

---

### Tier 2: Backend Vectorization (3 sprints worth)

#### Design Principle
The model currently bypasses backend methods with Python for-loops in `model.py` and `behavior.py`. The goal is to move these loops into vectorized backend methods, then have model.py call the backend instead.

**Sequential constraint:** `fitness_all()` + `deplete_resources()` are inherently serial (dominance-ordered resource consumption). Strategy:
- **NumPy:** Vectorize the per-fish computation but keep the fish-ordering loop. Gain: eliminate per-cell Python loop inside each fish's evaluation.
- **Numba:** JIT-compile the entire nested loop (fish × candidate × activity).
- **JAX:** Use `jax.lax.scan` over fish in dominance order with cell-state carry.

#### GAP-8: NumPy backend — 5 methods
Implement in `numpy_backend/__init__.py`:
- `growth_rate(trout_arrays, cell_arrays, reach_arrays, sp_arrays)` → `float[n_fish]`
- `survival(trout_arrays, cell_arrays, reach_arrays, sp_arrays, pisciv_densities)` → `float[n_fish]`
- `fitness_all(trout_arrays, cell_arrays, candidates, sp_arrays, ...)` → `(best_cell[n], best_activity[n], best_fitness[n])`
- `deplete_resources(cell_state, fish_idx, cell_idx, activity, intake, sp_rep)` → mutates cell_state
- `spawn_suitability(cell_state, sp_arrays)` → `float[n_cells]`

#### GAP-9: Numba backend — 6 methods
Port NumPy implementations to `@njit` functions. The existing `_evaluate_all_cells_numba` in `numba_backend/fitness.py` is a starting point for `fitness_all()`.

#### GAP-10: JAX backend — 3 methods
- `fitness_all()`: `jax.lax.scan` over fish in dominance order, carrying cell resource state.
- `deplete_resources()`: Part of the scan carry — cell resources are updated as each fish selects.
- `spawn_suitability()`: `jax.vmap` over cells with `jnp.interp`.

#### Refactor model.py
After backends implement these methods:
1. Replace the per-fish Python loops in `model.py:574-643` (survival) with `self.backend.survival(...)`.
2. Replace `select_habitat_and_activity()` internals with `self.backend.fitness_all(...)`.
3. Replace inline growth accumulation with `self.backend.growth_rate(...)`.
4. Keep the sequential dispatch pattern: model calls backend, backend handles vectorization.

---

### Tier 3: New Features

#### GAP-11: Angler harvest module
- **New file:** `src/instream/modules/harvest.py`
- **Config additions:** `HarvestConfig` in config.py with fields: `harvest_file` (CSV path), `bag_limit`, `min_length`, `season_start`, `season_end`, `catch_rate_per_angler_day`.
- **CSV format:** `date,num_anglers` (daily angler effort)
- **Logic:**
  1. Each day during harvest season, compute encounter probability per fish based on activity and cell depth.
  2. Apply size-selective mortality (fish >= `min_length` only).
  3. Track cumulative harvest per day, stop at `bag_limit`.
  4. Record harvest statistics in output.
- **Integration:** Call `_do_harvest()` in model.step() after survival, before spawning.
- **Test:** 5+ unit tests for encounter probability, size selectivity, bag limits. Integration test with Example A.
- **Effort:** L

#### GAP-12: Sensitivity analysis framework
- **New file:** `src/instream/modules/sensitivity.py`
- **Approach:** Morris screening (one-at-a-time perturbation) for initial exploration, Sobol indices for detailed analysis.
- **Config:** `SensitivityConfig` with `method` (morris/sobol), `parameters` (list of param names + ranges), `num_samples`, `output_metric` (e.g., "mean_population", "mean_length").
- **CLI:** `instream-sensitivity config.yaml --sensitivity sensitivity.yaml`
- **Implementation:**
  1. Generate parameter sample matrix (Morris trajectories or Sobol sequences via SALib).
  2. Run model N times with perturbed parameters (embarrassingly parallel).
  3. Compute sensitivity indices.
  4. Output: CSV of parameter importance rankings + optional tornado plot data.
- **Dependencies:** Add `SALib>=1.4` as optional dependency.
- **Test:** Smoke test with 2 parameters, 4 samples. Verify output format.
- **Effort:** L

#### GAP-13: Habitat restoration scenarios
- **No new module** — extend existing config.
- **Config addition:** `restoration_events` list in ReachConfig:
  ```yaml
  restoration_events:
    - date: 2012-06-01
      cells: [10, 11, 12]  # or "all"
      changes:
        frac_vel_shelter: 0.5
        num_hiding_places: 10
        frac_spawn: 0.8
  ```
- **Logic:** In `model.step()`, at day boundary, check if current date matches any restoration event. If so, apply cell modifications to `cell_state`.
- **Test:** Configure a restoration event; verify cell properties change on the target date.
- **Effort:** M

---

### Tier 4: Documentation & Validation

#### GAP-14: Sphinx documentation
- **Setup:** `docs/conf.py` with autodoc, napoleon (Google-style docstrings), RTD theme.
- **Structure:** index, installation, quickstart, user-manual, api-reference, ODD protocol, changelog.
- **Build:** `sphinx-build -b html docs/ docs/_build/`
- **CI:** Add docs build step to GitHub Actions.
- **Effort:** M

#### GAP-15: SpeciesParams completion
- **Location:** `state/params.py`
- **Fix:** Add all ~90 species parameters from `SpeciesConfig` fields to the frozen `SpeciesParams` dataclass. Update `params_from_config()` to populate all fields. This replaces `_sp_arrays` dict lookups with attribute access.
- **Backward compat:** Keep `_sp_arrays` as a thin wrapper initially; deprecate in next version.
- **Effort:** S

#### GAP-16: NetLogo cross-validation
- **Requirement:** Install NetLogo 7.4, run Example A/B test procedures, export CSVs.
- **Approach:** Use `netlogo-oracle` skill to generate reference data.
- **Update:** Replace Python-golden snapshots in `tests/fixtures/reference/` with actual NetLogo output where different.
- **Risk:** Low — existing tests already pass with Python-golden data. NetLogo data may reveal small numerical differences.
- **Effort:** M

---

## Sprint Plan

### Sprint 1: Simulation Correctness (GAP 1-7)
- **Duration estimate:** ~1 week
- **Dependencies:** None
- **Safety:** Each gap is independent. Fix, test, commit one at a time.
- **Gate:** All 615 existing tests pass + new tests for each gap.

### Sprint 2: NumPy Backend Vectorization (GAP-8)
- **Duration estimate:** ~1 week
- **Dependencies:** Sprint 1 (correctness fixes must be in place before vectorizing)
- **Safety:** Keep Python-loop fallback until vectorized version matches exactly. Compare outputs array-for-array.
- **Gate:** All tests pass. Benchmark shows no regression. Vectorized output == loop output to rtol=1e-12.

### Sprint 3: Numba + JAX Backend Vectorization (GAP 9-10)
- **Duration estimate:** ~1 week
- **Dependencies:** Sprint 2 (NumPy version is the reference)
- **Safety:** Cross-backend parity tests (numpy vs numba: rtol=1e-12, numpy vs jax: rtol=1e-10).
- **Gate:** All tests pass. Benchmark shows speedup vs Sprint 2.

### Sprint 4: New Features (GAP 11-13)
- **Duration estimate:** ~2 weeks
- **Dependencies:** Sprint 1 (correct base needed)
- **Safety:** New features are additive — disabled by default (no config = no effect). Each feature behind a config flag.
- **Gate:** All existing tests pass unchanged. New feature tests pass.

### Sprint 5: Validation & Params (GAP 15-16)
- **Duration estimate:** ~1 week
- **Dependencies:** Sprint 1 (correctness fixes may change validation baselines)
- **Safety:** Update golden snapshots only after verifying against NetLogo.
- **Gate:** 11/11 validation tests pass with NetLogo reference data.

### Sprint 6: Documentation (GAP-14)
- **Duration estimate:** ~3 days
- **Dependencies:** All previous sprints (docs should reflect final API)
- **Safety:** Docs-only changes, no code risk.
- **Gate:** `sphinx-build` succeeds. All pages render.

---

## Safety Protocol (All Sprints)

1. **Branch per sprint:** `sprint-N-<topic>` from master
2. **Commit per gap:** One logical change per commit, never batch unrelated fixes
3. **Test after every commit:** `conda run -n shiny python -m pytest tests/ -v`
4. **Benchmark after perf changes:** `conda run -n shiny python benchmarks/bench_full.py`
5. **No force-push:** Linear history, no rebasing published branches
6. **Validation gate:** All 11 validation tests must pass before merge
7. **Backward compatibility:** All config changes have defaults matching current behavior
8. **Rollback plan:** Each gap is independent — any single commit can be reverted without affecting others
