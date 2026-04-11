# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.16.0] - 2026-04-11

### Fixed — Lifecycle hardening

- **Ghost-smoltified fry bug**: `spawning.redd_emergence` reused dead `TroutState` slots for new fry but never reset the v0.14.0 marine fields (`zone_idx`, `sea_winters`, `smolt_date`, `smolt_readiness`). If the previous occupant had smoltified, the new fry inherited its marine state and appeared in analyses as a 3–4 cm "smolt" that had never been at sea. Same bug fixed in the adult-arrival slot reuse path in `model_day_boundary` (newly-arrived spawners were inheriting `zone_idx=2`, `sea_winters=1..3` from dead Baltic adults). Regression test in `tests/test_ghost_smolt_fix.py`.
- **Adult-arrival slot contamination**: new `SPAWNER` fish created from the outmigrant-return queue now get their marine fields reset and their `natal_reach_idx` properly assigned to the arrival reach.

### Added

- **FRY → PARR automatic transition**: on January 1, every living FRY with `age >= 1` is promoted to PARR. Previously FRY had no progression rule, so natural-spawned cohorts never became smolt candidates — only test fixtures with manually-seeded PARR could exercise the freshwater → marine pipeline. 4 unit tests in `tests/test_fry_to_parr.py`.
- **`MarineDomain.total_smoltified` and `total_returned`**: lifetime cumulative counters that survive `TroutState` slot reuse. Previously the E2E tests queried final-state arrays, which are destroyed when a dead fish's slot gets reused by new spawning. The counters are incremented by `_do_migration` and `check_adult_return` as each event occurs.

### Changed

- **`migrate_fish_downstream` return signature**: now returns `(outmigrants, smoltified)` instead of just `outmigrants`. The boolean indicates whether this call transitioned a PARR to SMOLT, used by `_do_migration` to increment the cumulative counter. All callers (two in `model_day_boundary`, three in `test_marine.py`, two in `test_migration.py`) updated.
- **`check_adult_return` return signature**: now returns `int` (number of fish that returned this call) instead of `None`. The caller in `model.py` accumulates it into `MarineDomain.total_returned`.
- **`TroutState.alive` / `is_alive` unification**: the legacy `is_alive` fallback throughout `marine/domain.py`, `marine/survival.py`, `marine/fishing.py` is removed. `_MockTroutState` in `tests/test_marine.py` renamed its attribute to match the real `TroutState.alive`. There is no longer an `is_alive` name anywhere in `src/`.
- **E2E marine tests** now assert on the durable counters (`model._marine_domain.total_smoltified > 0`, `total_returned > 0`) instead of scanning `TroutState.smolt_date` — a historically fragile check.

### Infrastructure

- **845 tests** (was 841 in v0.15.0), 9 skipped, 0 failing. Full suite runtime ~18.4 min.
- One pre-existing test in `test_behavioral_validation.py::TestPopulationDynamicsExampleB` was fixed during this cycle: it was silently broken by the initial FRY→PARR promotion (before the anadromous species gate was added) — the rainbow-trout-only Example B population was going extinct on Jan 1 when FRY got promoted to PARR and then killed at the river mouth. Gated promotion on `is_anadromous=True` restored Example B correctness.

### Known gaps (carried into v0.17.0)

- Sphinx `docs/source/` not yet built in CI (sections added in v0.15.0 but never rendered).
- Kelt survival (iteroparous repeat spawning) not implemented — fish die after spawning.
- Hatchery-vs-wild origin fish not distinguished.

---

## [0.15.0] - 2026-04-11

### Added — Marine ecology (inSALMON Sub-project B)

- **Marine growth bioenergetics** (`instream/marine/growth.py`): simplified Hanson et al. 1997 Fish Bioenergetics 3.0 model. Pure-function `marine_growth()` computes daily weight delta from CMax temperature response, allometric scaling, prey index, condition, and K2 growth efficiency. Starvation (negative growth) supported.
- **Marine survival — 5 natural mortality sources** (`instream/marine/survival.py`):
  1. Seal predation — size-dependent logistic (L1/L9 bounds)
  2. Cormorant predation — size-dependent logistic, restricted to nearshore zones, with post-smolt vulnerability decay over configurable window (default 28 d)
  3. Background mortality — constant daily rate
  4. Temperature stress — threshold-triggered daily hazard (>20 °C default)
  5. M74 syndrome — per-cohort daily probability
  Hazards combine multiplicatively: `survival = ∏(1 − h_i)`.
- **Fishing module** (`instream/marine/fishing.py`): `GearConfig` with logistic/normal selectivity curves, seasonal `open_months`, zone restrictions, `daily_effort`, and `bycatch_mortality`. `fishing_mortality()` implements the per-encounter harvest/bycatch logic from the design document. `HarvestRecord` dataclass for daily accumulation.
- **MarineBackend Protocol** (`instream/backends/_interface.py`) with `NumpyMarineBackend` delegating adapter (`instream/backends/numpy_backend/marine.py`). Runtime-checkable, mirroring the existing `ComputeBackend` pattern for future JAX/Numba ports.
- **MarineConfig v0.15.0 parameters**: CMax coefficients (`marine_cmax_A/B/topt/tmax`), respiration (`marine_resp_A/B/Q10`), `marine_growth_efficiency`, seal/cormorant/background/temperature/M74 hazards, post-smolt vulnerability days, conditional maturation probabilities per sea-winter, and `MarineFishingConfig` with `gear_types` dict. All fields optional with design-document defaults — v0.14.0 configs remain valid unchanged.
- **`MarineDomain.daily_step()` orchestration**: growth, natural survival, and fishing mortality wired in after zone migration and life-stage progression. RNG threaded through constructor.
- **`HarvestRecord` log**: `MarineDomain.harvest_log` accumulates gear-level catches per step.
- **75 new tests** (`tests/test_marine_growth.py`, `tests/test_marine_survival.py`, `tests/test_marine_fishing.py`, `tests/test_marine_backend.py`, plus 2 new E2E assertions in `tests/test_marine_e2e.py`). Includes a cohort-attrition integration test calibrated against the ICES WGBAST 2-year survivorship band.

### Changed

- **Cormorant zone matching** (`marine/survival.py`): now case-and-whitespace-insensitive. Previous exact-match silently disabled cormorant predation in configs where zone names differed in case (e.g. `Estuary` vs `estuary`).
- **Hazard ceiling defaults lowered** to sustainable values:
  `marine_mort_seal_max_daily` 0.02 → 0.003,
  `marine_mort_cormorant_max_daily` 0.03 → 0.010.
  The design-document values were peak-event ceilings; applied literally they collapse a 2-year cohort to <1% survival (~50× observed). New defaults land inside the ICES WGBAST 5–15% survivorship band.
- `MarineDomain.__init__` now accepts an optional `rng` parameter (defaults to a fresh `numpy.random.default_rng()` for backward compat).

### Infrastructure

- **841 tests** (was 766 in v0.14.0), all passing. Full suite runtime ~12.8 min.
- Backward compatible: no v0.14.0 test modified except to add fields required by the new growth/survival code paths to the legacy `_MockTroutState` helper.

### Known gaps (carried into v0.16.0)

- Ghost-smoltified fry: ~170 fry per run receive `smolt_date >= 0` while still at 3–4 cm length. Pre-existing v0.14.0 behaviour, exposed but not fixed here.
- `TroutState.alive` vs `is_alive` naming inconsistency still papered over via `hasattr` fallback.
- Sphinx `docs/source/` still not created (tracked since v0.13.0).
- FRY→PARR automatic transition still missing.

---

## [0.14.0] - 2026-04-09

### Added
- **Marine domain scaffolding**: `MarineDomain` class with `ZoneState`, `StaticDriver`, and `MarineConfig` (pydantic-validated)
- **TroutState marine fields**: 5 new fields — `zone_idx`, `sea_winters`, `smolt_date`, `natal_reach_idx`, `smolt_readiness`
- **Smolt exit**: PARR fish transition to SMOLT at river mouth when `marine` config section present
- **Smolt readiness**: Spring-window photoperiod + temperature accumulation drives PARR→SMOLT transition
- **Zone migration**: Time-based SMOLT→OCEAN_JUVENILE→OCEAN_ADULT transitions through Estuary→Coastal→Baltic zones
- **Adult return**: OCEAN_ADULT fish return to natal freshwater reach with valid `cell_idx`
- **Freshwater zone_idx guards**: 10 alive-fish loops guarded to exclude marine fish from freshwater calculations
- **Example marine config**: `configs/example_marine.yaml` with 3 Baltic Sea zones
- **E2E lifecycle test**: Full freshwater→marine→return cycle verified

### Changed
- Existing configs without a `marine` section are fully backward-compatible — no behaviour change

### Infrastructure
- 766 tests (was 729), all passing

---

## [0.13.0] - 2026-04-09

### Added
- **InSALMON foundation**: `LifeStage` IntEnum (FRY/PARR/SPAWNER/SMOLT/OCEAN_JUVENILE/OCEAN_ADULT/RETURNING_ADULT)
- 6 new species config parameters: `mort_condition_K_crit`, `fecundity_noise`, `spawn_date_jitter_days`, `outmigration_max_prob`, `outmigration_min_length`, `fitness_growth_weight`
- Outmigration probability: fitness-based migration decision for PARR-stage fish
- Condition survival enhancement: parameterized `K_crit` threshold replaces hardcoded value
- Spawn perturbation: fecundity noise and spawn date jitter for stochastic spawning
- Adult holding behavior: `activity=4` assigned to RETURNING_ADULT fish
- Growth-fitness integration: alpha-weighted EMA combining growth rate and survival fitness
- Fitness report NetLogo cross-validation (17 validation tests total)
- Sub-daily behavioral validation (4 tests)
- Harvest behavioral validation (5 tests)
- JAX `spawn_suitability` with interpax (replaces `np.interp` fallback)
- Sphinx documentation build: `docs/source/` with autodoc configuration
- PyPI packaging: `py.typed` marker, complete classifiers, release workflow metadata

### Changed
- Validation test total: 17 tests (was 16), all passing

### Fixed
- No regressions — 729 passed, 6 skipped

---

## [0.12.0] - 2026-04-10

### Added
- Behavioral validation suite: population dynamics (Example A + B), size distribution, habitat selection, spawning/recruitment (13 tests)
- NetLogo 7.4 cross-validation for growth report, survival, redd survival, spawn cell, CStepMax (5 tests against genuine NetLogo output)
- FitnessReportOut from NetLogo write-fitness-report procedure

### Changed
- model.py decomposed into 3 mixin classes: model_init.py (370 lines), model_environment.py (275 lines), model_day_boundary.py (400 lines). Residual model.py: 108 lines
- Fitness golden snapshot regenerated from validated code

### Fixed
- Species mapping warning eliminated (Example A fixture updated to use Chinook-Spring)
- _debug_alignment.py excluded from pytest collection via conftest.py
- Stale C:\Users\DELL path references cleaned across documentation
- 4 outdated roadmap documents archived to docs/archive/

### Infrastructure
- 709+ tests (was 691), 16/16 validation tests passing
- collect_ignore properly configured in conftest.py (not pyproject.toml)

---

## [0.11.0] - 2026-04-05

### Added
- Angler harvest module with size-selective mortality, bag limits, and CSV schedule (`modules/harvest.py`)
- Morris one-at-a-time sensitivity analysis framework (`modules/sensitivity.py`)
- Config-driven habitat restoration scenarios (cell property modification at scheduled dates)
- Fitness memory (exponential moving average) for smoother habitat selection decisions
- Drift regeneration distance blocking for cells near drift-feeding fish
- Spawn defense area exclusion for new redd placement
- YearShuffler wiring for stochastic multi-year time series remapping
- Anadromous adult life history transitions and post-spawn mortality
- Habitat summary and growth report output types (7 total output writers)
- SpeciesParams completed with all ~90 species parameter fields
- Cross-backend parity tests for survival, spawn_suitability, evaluate_logistic
- `InSTREAMModel` now accepts `ModelConfig` objects directly (enables programmatic config)

### Fixed
- Migration now uses per-species `migrate_fitness_L1/L9` instead of species_order[0]
- Solar irradiance uses daily-integral formula instead of overestimating noon-elevation
- Beer-Lambert light attenuation includes `light_turbid_const` additive term
- Superindividual split uses per-species `superind_max_length` threshold
- Numba `evaluate_logistic` supports array L1/L9 parameters

### Performance
- Vectorized survival computation in NumPy backend (replaces 80-line per-fish loop)
- Implemented `survival`, `growth_rate`, `spawn_suitability`, `deplete_resources` in all 3 backends
- Survival loop in model.py replaced with single `backend.survival()` dispatch

### Infrastructure
- 674 tests (was 499), 11/11 validation tests passing
- Gap-closure design spec and reviewed implementation plans

---

## [0.10.0] - 2026-03-23

### Added
- Add /deploy skill for laguna.ku.lt Shiny Server deployment
- Add main Shiny app entry point with sidebar, tabs, and extended_task
- Add spatial panel module (shiny_deckgl map + matplotlib fallback)
- Add population panel module (plotly line chart)
- Add simulation wrapper with config overrides and results collection

### Changed
- Update README with Shiny frontend, JAX backend, FEM mesh in completed features
- Add frontend optional-dependencies (shiny, plotly, shiny-deckgl)

---

## [0.9.0] - 2026-03-22

### Added
- Add automated release script, replace bump_version.py
- Implement JAX vectorized growth_rate and survival kernels

---

## [0.8.0] - 2026-03-22

### Added
- JAX compute backend: `update_hydraulics`, `compute_light`, `compute_cell_light`, `evaluate_logistic`, `interp1d` implemented with `jax.vmap` vectorization
- FEM mesh reader (`space/fem_mesh.py`): reads triangular meshes via meshio (River2D .2dm, GMSH .msh, and all meshio-supported formats)
- FEM mesh computes centroids, areas, and edge-based adjacency from element connectivity
- 7 new tests: JAX backend cross-validation against NumpyBackend, FEM mesh reading/area/adjacency

### Changed
- `get_backend("jax")` now returns a working JaxBackend (was NotImplementedError)
- FEM mesh areas automatically convert m^2 to cm^2

---

## [0.7.0] - 2026-03-22

### Added
- **InSTREAM-SD sub-daily scheduling**: multiple habitat selections per day with variable flow
- Auto-detection of input frequency (hourly, 6-hourly, daily) from time-series timestamps
- SubDailyScheduler with row-pointer advancement, is_day_boundary, substep_index
- Partial resource repletion between sub-steps (drift + search food regeneration)
- Growth accumulation in memory arrays, applied once at day boundary
- Solar irradiance cached per day, cell light recomputed each sub-step (depth-dependent)
- Synthetic hourly and peaking fixture data for testing
- 10 new sub-daily integration tests + 2 daily regression tests
- GitHub Actions CI pipeline

### Changed
- model.step() restructured into sub-step operations (every step) and day-boundary operations (end of day)
- TroutState.max_steps_per_day auto-sized from detected input frequency
- Survival applied each sub-step with `** step_length` scaling
- Spawning, redd development, census, age increment only at day boundaries

### Fixed
- Substep index off-by-one in TimeManager (solar cache population)
- Growth accumulation count at day boundary

---

## [0.6.0] - 2026-03-22

### Added
- All 11 validation tests now active (was 0 at v0.1.0, 5 at v0.3.0)
- 6 new golden-snapshot reference CSVs: CStepMax, growth report, trout survival, redd survival, spawn cell suitability, fitness snapshot
- Reference data generator covers all ecological modules (growth, survival, spawning, fitness)

### Validation
- 11/11 tests passing: GIS, depths, velocities, day length, CMax interpolation, CStepMax, growth report, trout survival, redd survival, spawn cell, fitness
- Golden snapshots from Python v0.5.0 — ready for cross-validation against NetLogo when available
- Note: NetLogo not installed; reference data computed by Python implementation itself (regression guard)

---

## [0.5.0] - 2026-03-22

### Added
- Output writer module (`io/output.py`) with 6 file types: census, fish/redd/cell snapshots, outmigrants, summary
- `write_outputs()` method on InSTREAMModel, called automatically at end of `run()`
- Redd superimposition: existing redd eggs reduced when new redd placed on same cell
- Working CLI: `instream config.yaml --output-dir results/ --end-date 2012-01-01`
- 8 new tests (output writers, superimposition)

### Changed
- `create_redd()` returns slot index (not bool) for superimposition support
- `run()` now calls `write_outputs()` at completion
- CLI uses argparse with config, --data-dir, --output-dir, --end-date, --quiet

---

## [0.4.0] - 2026-03-22

### Added
- Multi-reach support: per-reach hydraulic loading, light computation, resource reset
- Multi-species support: per-fish species parameter dispatch via pre-built arrays
- Per-fish reach-based temperature, turbidity, and intermediate lookups
- Multi-species initial population loading from CSV
- Per-reach per-species spawning and redd development
- Example B config (3 reaches x 3 species) generated from NLS
- Example B integration tests (init + 10-day + 30-day runs)
- Case-insensitive shapefile column name resolution

### Changed
- model.py no longer hardcodes reach_order[0] or species_order[0]
- Habitat selection uses per-fish species/reach parameters
- Survival loop uses per-fish species/reach mortality parameters
- Piscivore density computed with per-species length threshold

---

## [0.3.0] - 2026-03-22

### Added
- Numba brute-force candidate search replacing KD-tree queries (136ms -> 15ms)
- Sparse per-fish candidate lists replacing dense (2000, 1373) boolean mask
- 5 analytical validation tests activated (day length, CMax interpolation, GIS, depths, velocities)
- Reference data generator script (`scripts/generate_analytical_reference.py`)
- Migration wired into model.step() with reach graph construction
- Census day data collection wired into model.step()
- Adult arrivals stub (ready for multi-reach/species)

### Performance
- Full step: 179ms -> 98ms (1.8x faster, 633x vs original)
- Candidate mask build: 136ms -> 15ms (9x faster via Numba brute-force)
- Estimated full 912-day run: 2.2 min -> 1.4 min
- Now within 2-3x of NetLogo performance (was 130x slower at v0.1.0)

### Validation
- 5/11 validation tests now active (was 0/11)
- Tests use analytically computed reference data (no NetLogo dependency)

---

## [0.2.0] - 2026-03-22

### Added
- Survival-integrated fitness function (Phase 5)
- Piscivore density computed from fish distribution
- Annual age increment on January 1
- Numba @njit compiled fitness evaluation kernel (60x speedup)
- Hypothesis property-based tests
- Performance regression tests
- Population file configurable via YAML
- `netlogo-oracle` skill for validation data generation
- `validation-checker` agent for implementation completeness

### Fixed
- Random sex assignment for initial population and emerged fish
- `spawned_this_season` reset at spawn season start
- Growth stored during habitat selection (not recomputed from depleted resources)
- Deferred imports moved to module level
- Condition factor updated after spawning weight loss
- Division-by-zero guards on all logistic functions
- Clamped max_swim_temp_term >= 0, resp_temp_term overflow guard
- Zombie fish at weight=0 (condition=0 now lethal)
- Egg count rounding (np.round instead of truncation)
- Negative velocity and egg development clamped to non-negative
- Survival probability raised to step_length power
- Redd survival uses logistic^step_length formula
- Logistic exp() argument clipped to prevent overflow

### Changed
- `evaluate_logistic` uses math.exp instead of np.exp (2.7x faster)
- `survival_condition` uses min/max instead of np.clip (55x faster)
- `cmax_temp_function` uses bisect instead of np.interp (4.8x faster)
- Habitat selection inner loop pre-computes step/fish invariants
- Vectorized hydraulic interpolation using searchsorted + lerp
- Batch redd emergence (eliminates O(eggs*capacity) scan)
- Integer activity codes in growth and survival functions

### Performance
- Full step: 62s -> 179ms (346x faster)
- Full 912-day run: ~129 min -> ~2.1 min (61x faster)

## [0.1.0] - 2026-03-20

### Added
- Initial Python implementation of inSTREAM 7.4
- Mesa 3.x model orchestration
- SoA state containers (TroutState, CellState, ReddState, ReachState)
- FEMSpace with KD-tree spatial queries
- Wisconsin bioenergetics (growth, consumption, respiration)
- 5 survival sources (temperature, stranding, condition, fish predation, terrestrial predation)
- Spawning, egg development, redd emergence
- Migration framework
- YAML configuration with NLS converter
- NumPy and Numba compute backends
- 376 unit tests
