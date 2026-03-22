# Roadmap to NetLogo Parity

**Date:** 2026-03-22
**Current version:** v0.2.0
**Overall completeness:** ~55% of tasks, ~58% of features

---

## Executive Summary

Reaching full NetLogo 7.4 parity requires work in 4 dimensions:

| Dimension | Current State | Gap | Effort |
|-----------|--------------|-----|--------|
| **Performance** | 179ms/step (3-4x slower) | `build_candidate_mask` is 76% of step | 3-4 hours |
| **Features** | 39/75 tasks done | Multi-reach, multi-species, migration, output | 12-16 weeks |
| **Validation** | 0/11 tests active | Need reference data + test logic | 2-4 weeks |
| **Completeness** | Single reach, single species | 15+ hardcoded [0] indices | 4-5 weeks |

**Critical path:** Performance parity is achievable in **one day**. Full feature parity requires **~20 weeks**.

---

## Dimension 1: Performance Parity (3-4x gap → 0x)

### Current Profile (179ms/step)

```
build_candidate_mask ████████████████████████████████████████  136ms (76%)
Numba fitness kernel ████████                                  31ms (17%)
Python loop overhead ██                                         8ms  (4%)
Everything else      █                                          4ms  (3%)
NetLogo target       ██████████                                45ms
```

### The Fix: Numba Brute-Force Candidate Search

Replace the KD-tree + Python loop in `build_candidate_mask` with a single `@numba.njit` function that computes Euclidean distances for all 1373 cells. For 346 fish x 1373 cells = 475K distance calculations, Numba does this in ~1ms.

```
After optimization:
Numba candidate search █                                        1ms
Numba fitness kernel   ████████████████                        29ms
Python overhead        ████                                      8ms
Depletion + bookkeep   ███                                       5ms
Total                  ████████████████████████                 43ms
NetLogo                ██████████████████████████               45ms
```

**Estimated effort:** 3-4 hours
**Expected result:** 179ms → ~43ms (4.2x faster, at or below NetLogo)

### Beyond Parity: Merged Kernel (~33ms)

Merge candidate search + fitness evaluation into one Numba function that iterates fish in size order, eliminating all Python loop overhead. This makes Python **faster than NetLogo** for the core computation.

---

## Dimension 2: Feature Parity (55% → 100%)

### Phase-by-Phase Completion Status

| Phase | Done | Total | Missing Items |
|-------|------|-------|---------------|
| 0 Scaffold | 6/8 | 75% | CI/CD pipeline |
| 1 Spatial | 4/6 | 67% | FEM mesh reader, validation tests |
| 2 Time/Light | 4/6 | 67% | Year shuffler, sub-daily scheduling |
| 3 Bioenergetics | 10/11 | 91% | Growth validation test |
| 4 Behavior | 5/8 | 63% | JAX kernel, fitness memory, validation |
| 5 Survival | 3/4 | 75% | Survival validation test |
| 6 Spawning | 5/7 | 71% | Adult arrivals, spawn validation test |
| 7 Migration | 4/5 | 80% | **Not wired to model.step()** |
| 8 Integration | 4/7 | 57% | Output system, batch runs |
| 9 Validation | 0/8 | 0% | **Entirely not started** |
| 10 Packaging | 1/5 | 20% | CLI, viz, docs |

### Priority 1: Wire Existing Dead Code (1-2 weeks)

These modules are **already implemented** but never called from `model.step()`:

| Module | Code Exists | What's Missing |
|--------|------------|----------------|
| Migration | `migration.py` — build_reach_graph, migrate_fish_downstream, bin_outmigrant | Call from step() after spawning |
| Adult arrivals | `population_reader.py` — partial | Add `_do_adult_arrivals()` step |
| Census output | `time_manager.py` — is_census() | Check each step, collect data |
| Year shuffler | `time_manager.py` — YearShuffler class exists | Wire to multi-year runs |

### Priority 2: Multi-Reach Support (2-3 weeks)

15+ hardcoded `[0]` indices in `model.py` that must become per-reach:

| Location | Current | Required |
|----------|---------|----------|
| Hydraulic loading | First reach only | Load per-reach tables, update per-reach flow |
| Light computation | Reach[0] shading/turbidity | Per-reach light parameters |
| Resource reset | Reach[0] drift/search params | Per-reach resource parameters |
| Temperature/turbidity | `reach_state.*[0]` scalars | Per-fish via `reach_idx` |
| Temp intermediates | `[0, 0]` indices | `[reach_idx, species_idx]` |
| Spawning | First reach flow/params | Per-reach spawn criteria |
| Redd development | First reach conditions | Per-redd reach conditions |

**Test case:** Example B has 3 reaches (Upstream, Middle, Downstream) with junction connectivity 1→2→3→4.

### Priority 3: Multi-Species Support (2 weeks)

Every `species_order[0]` in `model.py` must dispatch by `trout_state.species_idx[i]`:

- Growth parameters (cmax_A/B, weight_A/B, resp_A/B/D)
- Survival parameters (all mort_* logistic coefficients)
- Spawning parameters (season, min conditions, fecundity)
- Movement radius
- Piscivore length threshold

**Test case:** Example B has 3 species (Chinook-Fall, Chinook-Spring, Rainbow) with substantially different parameters.

### Priority 4: Output System (1-2 weeks)

NetLogo generates 7 output file types. None exist in Python:

1. **Population census** — fish counts by species/age/reach on census days
2. **Individual fish output** — per-fish state at census
3. **Cell output** — hydraulics and resources per cell
4. **Redd output** — redd status and mortality tracking
5. **Outmigrant output** — fish leaving the system
6. **Habitat summary** — area by depth/velocity class
7. **Growth/survival report** — diagnostic bioenergetics report

### Priority 5: Missing Ecological Processes (2-3 weeks)

| Process | Effort | Impact |
|---------|--------|--------|
| Redd superimposition | [M] | Egg mortality when redds overlap |
| Spawn defense area | [S] | Territory exclusion during spawning |
| Drift regeneration distance | [M] | Spatial food replenishment |
| Life history transitions | [S] | Anadromous adult→spawner→die, juvenile→outmigrant |
| Light turbidity constant | [S] | `attenuation = coef * turbidity + const` (currently missing `+ const`) |
| Fitness memory | [M] | Running average of growth/survival for decision-making |

### Priority 6: Sub-Daily Scheduling — InSTREAM-SD (4-6 weeks)

Entirely absent. Requires:
- Multiple habitat selections per day
- Resource repletion between sub-steps
- Peaking flow input format
- Memory arrays for within-day tracking
- Modified time manager with sub-day steps

---

## Dimension 3: Scientific Validation (0% → 100%)

### Validation Test Activation Strategy

**5 tests can be activated immediately** (analytical, no NetLogo needed):

| Test | Method | Effort |
|------|--------|--------|
| 1. Cell variables vs GIS | Read shapefile, compare | 30 min |
| 2. Cell depths | `np.interp` on depth CSV tables | 1 hour |
| 3. Cell velocities | Same as depths | 30 min |
| 4. Day length | Astronomical formula (Glarner 2018) | 30 min |
| 7. CMax interpolation | Table lookup sweep | 15 min |

**5 tests need NetLogo reference data:**

| Test | NetLogo Procedure | Complexity |
|------|-------------------|------------|
| 5. Growth report | `write-growth-report` | 82,944 rows, full bioenergetics |
| 6. CStepMax | `test-c-stepmax` | Fish-level consumption limits |
| 8. Trout survival | `test-survival` | 6 logistic sources |
| 9. Redd survival | `test-redd-survive-temperature` | 4 egg mortality sources |
| 10. Spawn cell | `test-spawn-cell` | Suitability tables + cell ranking |

**1 test is Python-only:**
- 11. Fitness report — golden snapshot from first validated Python run

### Reference Data Generation Options

1. **Analytical computation** (tests 1-4, 7) — Python script, no NetLogo
2. **NetLogo headless** — Install NetLogo 7.0.3, run test procedures via BehaviorSpace
3. **pyNetLogo** — Python bridge to NetLogo JVM (requires NetLogo installed)
4. **Manual one-time run** — Open NetLogo GUI, run each procedure, collect CSVs

**Java 25 is installed** on this machine. NetLogo 7.0.3 is **not installed** but can be downloaded (~377MB).

### Tolerance Hierarchy (from IMPLEMENTATION_PLAN)

| Comparison | Tolerance | Why |
|-----------|-----------|-----|
| numpy ↔ numba | rtol=1e-12 | Same FP operations, same order |
| numpy ↔ jax | rtol=1e-10 | XLA may reorder FP ops |
| Python ↔ NetLogo | rtol=1e-6 | Different RNG, FP accumulation order |

### Known Divergence Sources

| Source | Impact | Mitigation |
|--------|--------|-----------|
| RNG (PCG64 vs Mersenne Twister) | Complete trajectory divergence for stochastic processes | Use distributional comparisons, not trajectory matching |
| Agent scheduling order | Different resource depletion sequences | Both use size-ordered; should match for same-size fish |
| FP accumulation | ±1e-6 after 15+ chained operations | Use rtol=1e-6 |
| Integer egg truncation | ±1 egg per redd per step | Use atol=1 for egg counts |

### Behavioral Validation (Beyond Unit Tests)

For publication-ready validation:
1. **Population dynamics** — Does population stabilize/grow/crash correctly over 2.5 years?
2. **Size distribution** — Do fish reach realistic size distributions?
3. **Spatial patterns** — Do large fish select deep/fast habitat, small fish shallow/slow?
4. **Spawning** — Correct season, location, fecundity?
5. **Mortality patterns** — Which source dominates by season?
6. **Statistical equivalence** — TOST (two one-sided t-tests) on population means

---

## Dimension 4: Remaining Technical Debt

### Architecture Issues

| Issue | Effort | Impact |
|-------|--------|--------|
| Two parallel parameter objects (SpeciesParams vs SpeciesConfig) | [M] | Confusion about source of truth |
| 27 missing config parameters (debug flags, output control, display) | [S] | Completeness |
| 10 unused config parameters (drift_regen, spawn_defense, etc.) | [M] | Dead config values |
| No CI/CD pipeline | [M] | No automated testing |
| No FEM mesh backend | [L] | Required for new-geometry applications |
| No JAX backend | [L] | GPU/ensemble support |

### Missing Infrastructure

| Item | Effort |
|------|--------|
| CI/CD with GitHub Actions | [M] — 1-2 days |
| CLI with click/typer | [S] — 1 day |
| Visualization (Mesa viz or matplotlib) | [M] — 1 week |
| Sphinx documentation build | [M] — 2-3 days |

---

## Recommended Execution Order

### Sprint 1: Performance Parity + Quick Validation (1 week)

| Day | Task | Outcome |
|-----|------|---------|
| 1 | Numba brute-force candidate search | Step time ≤ 45ms |
| 2 | Generate analytical reference data (tests 1-4, 7) | 5 validation tests active |
| 3 | Activate analytical validation tests | 5/11 tests passing |
| 4 | Wire migration to model.step() | Dead code becomes live |
| 5 | Wire adult arrivals + census output | Basic output capability |

### Sprint 2: Multi-Reach + Multi-Species (3 weeks)

| Week | Task | Outcome |
|------|------|---------|
| 1 | Multi-reach hydraulics, light, resources | Per-reach computation |
| 2 | Multi-species parameter dispatch | Per-fish species lookup |
| 3 | Integration testing with Example B | 3 reaches x 3 species working |

### Sprint 3: Output System + Ecological Processes (2 weeks)

| Week | Task | Outcome |
|------|------|---------|
| 1 | Output system (7 file types) | Census, individual, cell, redd output |
| 2 | Redd superimposition, drift regen, fitness memory | Ecological completeness |

### Sprint 4: Full Validation (2 weeks)

| Week | Task | Outcome |
|------|------|---------|
| 1 | Install NetLogo, generate reference data (tests 5-10) | All reference CSVs |
| 2 | Activate remaining validation tests + behavioral checks | 11/11 tests, publication-ready |

### Sprint 5: Polish + InSTREAM-SD (4-6 weeks, lower priority)

| Task | Outcome |
|------|---------|
| Sub-daily scheduling | InSTREAM-SD capability |
| JAX backend | GPU ensemble runs |
| FEM mesh backend | New geometry support |
| CI/CD + CLI + visualization | Production-ready |

---

## Summary Metrics

| Metric | Current (v0.2.0) | After Sprint 1 | After Sprint 4 | Full Parity |
|--------|-------------------|----------------|-----------------|-------------|
| Step time | 179 ms | **≤45 ms** | ≤45 ms | ≤45 ms |
| vs NetLogo | 3-4x slower | **≤1x** | ≤1x | ≤1x |
| Tasks done | 39/75 (52%) | 44/75 (59%) | 60/75 (80%) | 75/75 (100%) |
| Validation | 0/11 (0%) | 5/11 (45%) | **11/11 (100%)** | 11/11 |
| Multi-reach | No | No | **Yes** | Yes |
| Multi-species | No | No | **Yes** | Yes |
| Output files | None | Basic | **7 types** | 7 types |
| Estimated time | — | **1 week** | **8 weeks** | **20 weeks** |
