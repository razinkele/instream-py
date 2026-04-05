# Gap Closure Design Spec

**Date:** 2026-04-05 (revised after review)
**Version:** v0.10.0 baseline
**Goal:** Close all remaining gaps to reach full NetLogo parity + extensions

---

## Verified Gap Inventory

### Tier 1: Simulation Correctness (9 items)

#### GAP-1: Migration uses species_order[0]
- **Location:** `model.py:998-1000`
- **Problem:** `_do_migration()` fetches `migrate_fitness_L1/L9` from `self.config.species[self.species_order[0]]` — all fish get species-0 migration params regardless of their species.
- **Fix:** Pre-build `migrate_fitness_L1/L9` into `_sp_arrays` in `__init__`. In `_do_migration`, index by `species_idx[i]`.
- **Test:** Integration test: instantiate model with 2 species having different migration L1/L9, run `_do_migration`, verify per-species dispatch.
- **Effort:** S

#### GAP-2: Solar irradiance overestimates
- **Location:** `numpy_backend/__init__.py:104-114`, `numba_backend/__init__.py:41-53`, `jax_backend/__init__.py:115-125`
- **Problem:** Uses noon solar elevation instead of daily-integral irradiance. Overestimates.
- **Fix:** Replace with hour-angle integral formula:
  ```
  H = arccos(-tan(lat) * tan(decl))  # already computed for day_length
  I_daily = (S0 / pi) * (sin(lat)*sin(decl)*H + cos(lat)*cos(decl)*sin(H))
  irradiance = I_daily * light_correction * shading
  ```
  This yields daily-integrated insolation (not daily-mean). Update all 3 backends identically.
- **Test:** Analytical tests for known cases. Backend parity tests.
- **Note:** This WILL change light-dependent golden snapshots in `tests/fixtures/reference/`. Regenerate after fix.
- **Effort:** M

#### GAP-3: Light turbidity constant not passed to backends
- **Location:** All 3 backends `compute_cell_light()`, `model.py:506-512`
- **Problem:** `light_turbid_const` already exists in `ReachConfig` (line 214) and `ReachParams` (line 251) with default 0.0. But `model.py` never passes it to `compute_cell_light()`, and the backends don't accept it. The Beer-Lambert formula lacks the additive constant.
- **Fix:** Add `turbid_const` parameter to `compute_cell_light()` in all 3 backends and `_interface.py`. Pass `reach_cfg.light_turbid_const` from model.py. Formula: `attenuation = turbid_coef * turbidity + turbid_const`.
- **Test:** Existing tests pass with default 0.0 (unchanged behavior). New test with non-zero constant.
- **Effort:** S

#### GAP-4: Fitness memory not implemented
- **Location:** `state/trout_state.py`, `model.py`
- **Problem:** NetLogo uses an exponential moving average of past fitness to smooth habitat decisions. No `fitness_memory_frac` config field exists (the existing `fitness_horizon` is a different concept — days-ahead projection, not EMA smoothing).
- **Fix:**
  1. Add `fitness_memory_frac: float = 0.0` to `SpeciesConfig` (new field, default 0.0 = no memory = current behavior).
  2. Add `fitness_memory` array to `TroutState`.
  3. After habitat selection, update EMA. Initialize `fitness_memory` from `last_growth_rate` on first step to avoid spurious day-1 migration.
  4. Use `fitness_memory` in migration decisions.
- **Tier justification:** Behavioral refinement, not a correctness bug. Classified Tier 1 because it affects migration decisions which are ecologically significant for anadromous species.
- **Effort:** M

#### GAP-5: Drift regeneration distance not applied
- **Location:** `io/config.py:209,247` (parsed), `model.py` resource replenishment
- **Problem:** `drift_regen_distance` is in config but never used.
- **Fix:** After habitat selection (when fish positions are known), block drift regen for cells within `drift_regen_distance` (Euclidean) of cells occupied by drift-feeding fish.
- **Note:** Uses Euclidean distance as proxy for hydraulic upstream distance. This is an approximation; true hydrological direction would require flow-direction data not currently in the model.
- **Effort:** M

#### GAP-6: Spawn defense area not applied
- **Location:** `io/config.py:130` (parsed), `modules/spawning.py`
- **Problem:** `spawn_defense_area` is configured but never used.
- **Fix:** In `select_spawn_cell()`, exclude candidate cells within `spawn_defense_area` cm of existing alive redds.
- **Effort:** S

#### GAP-7: Year shuffler not wired
- **Location:** `io/time_manager.py` (YearShuffler class exists), `model.py`
- **Problem:** `YearShuffler` is implemented but never instantiated or called.
- **Fix:**
  1. Add `shuffle_years: bool = False` and `shuffle_seed: int = 0` to `SimulationConfig`.
  2. In `__init__`, extract available years from time-series DataFrame indices.
  3. Create `YearShuffler(available_years, seed)`.
  4. Modify `TimeManager.get_conditions()` to accept an optional `year_override` parameter, or add a `set_year_remap()` method that remaps the internal date lookup.
  5. The `get_conditions` gap check (1.5 days) must be bypassed or adjusted when year remapping is active.
- **Effort:** M (not S — requires TimeManager integration)

#### GAP-8a: split_superindividuals uses np.max across species
- **Location:** `model.py:657`
- **Problem:** `split_superindividuals(self.trout_state, float(np.max(_sml_arr)))` takes the maximum `superind_max_length` across ALL species. Fish of small-bodied species never get split because the threshold is set by the largest species.
- **Fix:** Pass per-species threshold array to `split_superindividuals`. Inside the function, look up `superind_max_length[species_idx[i]]` for each fish.
- **Test:** Two species with different max lengths. Verify small-species fish are split at the correct threshold.
- **Effort:** S

#### GAP-8b: Life history never set to anad_adult
- **Location:** `model.py:1140` (adult arrivals), `model.py:_do_migration`
- **Problem:** Adult arrivals are hardcoded to `life_history = 0` (resident). No fish ever gets `life_history = 2` (anad_adult). This means: (a) anadromous adults never die after spawning (NetLogo behavior), (b) `should_migrate` only triggers for `life_history == 1` — adults are ignored.
- **Fix:** Set `life_history = 2` for adult arrivals of anadromous species. Add post-spawn mortality for `life_history == 2` fish (die after spawning, matching NetLogo).
- **Test:** Adult arrival with anadromous species → `life_history == 2`. After spawning → fish dies.
- **Effort:** S

---

### Tier 2: Backend Vectorization (3 sprints worth)

#### Design Principle
The model bypasses backend methods with Python for-loops. Goal: move loops into vectorized backend methods.

**Sequential constraint:** `fitness_all()` + `deplete_resources()` are inherently serial.

**JAX status:** `growth_rate()` and `survival()` are already fully implemented in the JAX backend (lines 159-514). Only `fitness_all()`, `deplete_resources()`, and `spawn_suitability()` remain.

#### GAP-9: NumPy backend — 5 methods
- `growth_rate`, `survival`, `fitness_all`, `deplete_resources`, `spawn_suitability`

#### GAP-10: Numba backend — 6 methods
- Same 5 + `evaluate_logistic`. Port from NumPy reference.

#### GAP-11: JAX backend — 3 remaining methods
- `fitness_all()`: `jax.lax.scan` over fish in dominance order.
- `deplete_resources()`: Part of the scan carry.
- `spawn_suitability()`: `jax.vmap` over cells.

#### Refactor model.py
Replace Python for-loops with backend dispatch calls.

---

### Tier 3: New Features

#### GAP-12: Angler harvest module
- **New file:** `src/instream/modules/harvest.py`
- **Integration:** Call in model.step() after survival, before spawning.
- **Note:** If Sprint 2/3 vectorizes the survival loop, harvest integration must use the new calling convention.
- **Effort:** L

#### GAP-13: Sensitivity analysis framework
- **Approach:** Morris screening + Sobol indices via SALib.
- **Effort:** L

#### GAP-14: Habitat restoration scenarios
- Config-driven cell modifications at specified dates.
- **Effort:** M

---

### Tier 4: Documentation & Validation

#### GAP-15: Sphinx documentation
- **Effort:** M

#### GAP-16: SpeciesParams completion
- Add all ~90 species parameters to frozen dataclass.
- **Effort:** S

#### GAP-17: NetLogo cross-validation
- Generate reference data from actual NetLogo 7.4 runs.
- **Effort:** M

#### GAP-18: Missing output types
- **Problem:** Two of seven NetLogo output types are not implemented: habitat summary (area by depth/velocity class) and growth/survival diagnostic report.
- **Location:** `io/output.py`
- **Effort:** M

---

## Sprint Plan

### Sprint 1: Simulation Correctness (GAP 1-8b)
- **Duration:** ~1.5 weeks (9 items)
- **Dependencies:** None
- **Safety:** Each gap is independent. Fix, test, commit one at a time.
- **Gate:** All existing tests pass + new tests for each gap.
- **Note:** GAP-2 (irradiance) will require regenerating golden snapshots.

### Sprint 2: NumPy Backend Vectorization (GAP-9)
- **Duration:** ~1 week
- **Dependencies:** Sprint 1
- **Safety:** Keep Python-loop fallback. Compare outputs array-for-array.
- **Gate:** Vectorized output == loop output to rtol=1e-12.

### Sprint 3: Numba + JAX Backend Vectorization (GAP 10-11)
- **Duration:** ~1 week
- **Dependencies:** Sprint 2 (NumPy version is the reference)
- **Safety:** Cross-backend parity tests.
- **Note:** Rollback of Sprint 2 would break Sprint 3 parity tests.

### Sprint 4: New Features (GAP 12-14)
- **Duration:** ~2 weeks
- **Dependencies:** Sprint 1 (correct base). Sprint 2/3 if features touch vectorized code paths.
- **Safety:** Disabled by default. Each feature behind a config flag.

### Sprint 5: Validation & Params (GAP 16-17)
- **Duration:** ~1 week
- **Dependencies:** Sprint 1 (correctness fixes may change baselines)

### Sprint 6: Documentation & Output (GAP 15, 18)
- **Duration:** ~1 week
- **Dependencies:** All previous sprints

---

## Safety Protocol (All Sprints)

1. **Branch per sprint:** `sprint-N-<topic>` from master
2. **Commit per gap:** One logical change per commit
3. **Test after every commit:** `conda run -n shiny python -m pytest tests/ -v`
4. **Benchmark after perf changes:** `conda run -n shiny python benchmarks/bench_full.py`
5. **No force-push:** Linear history
6. **Validation gate:** All 11 validation tests must pass before merge
7. **Backward compatibility:** All config changes have defaults matching current behavior
8. **Rollback plan:** Tier 1 gaps are independently revertible. Tier 2 Sprint 3 depends on Sprint 2.
9. **Golden snapshot regeneration:** After GAP-2 (irradiance), run `scripts/generate_analytical_reference.py` and commit updated reference CSVs.
