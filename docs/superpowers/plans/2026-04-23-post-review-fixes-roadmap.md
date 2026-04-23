# Post-Review Fixes — Master Roadmap

> **For agentic workers:** This is a roadmap spanning ~51 findings from the 2026-04-23 deep codebase review. It is split into 6 phases, each shippable as its own release/PR. Phase 1 has a full TDD plan already written at `2026-04-23-phase1-critical-correctness.md`. Phases 2-6 list scope + files + exit criteria; write a detailed plan per phase before executing.

**Goal:** Systematically close all findings from the 2026-04-23 deep review across simulation-core, scientific outputs, frontend, backends, infrastructure, and documentation.

**Architecture:** Six sequential phases, each an independent PR with its own release tag. Phase 1 lands critical correctness (v0.41.15) immediately. Phases 2-4 are parallelizable after Phase 1 (independent subsystems). Phases 5-6 are hygiene and can land anytime.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, Numba (optional), JAX (optional), Shiny, deck.gl, GitHub Actions.

---

## Release Strategy

| Phase | Target Version | Scope | Size | Parallelizable? |
|---|---|---|---|---|
| 1 | **v0.41.15** | 8 CRITICAL correctness + deps + 1 HIGH (deck.gl) | ~11 commits | No (must land first) |
| 2 | **v0.42.0** | High-severity scientific/numerical hardening | ~10 commits (9 fixes + release) | Yes (after P1) |
| 3 | **v0.42.1** | Frontend regression sweep | ~6 commits | Yes (after P1) |
| 4 | **v0.42.2** | CI + test-suite hardening | ~7 commits | Yes (after P1) |
| 5 | **v0.42.3** | Documentation sync | ~5 commits | Any time |
| 6 | **v0.42.4** | Medium/low hygiene | ~15 commits | Any time |

---

## Phase 1 — v0.41.15 Critical Correctness Patch

**Status:** Plan written in full at `2026-04-23-phase1-critical-correctness.md`.

**Scope:** 8 CRITICAL + 1 companion HIGH (movement_panel deck.gl).

| # | File:Line | Fix |
|---|---|---|
| C1 | `src/instream/modules/behavior.py:211-227` | Indent Python KD-tree fallback under the `else:` branch. |
| C2 | `src/instream/model_init.py:347` | Initialize `max_lifetime_weight` for initial population. |
| C3 | `src/instream/model_day_boundary.py:252-255` | Remove bulk RETURNING_ADULT→SPAWNER promotion; restore per-fish promotion at line 369. |
| C4 | `src/instream/io/output.py:219-223` | Weight PSPC counts by `superind_rep`. |
| C5 | `src/instream/state/params.py:102` + `src/instream/io/config.py:544` | Add `spawn_defense_area_m` to `SpeciesParams`; populate in `params_from_config`. |
| C6 | `pyproject.toml:21-30` | Declare `meshio>=5.3` as core dependency (imported unconditionally in `fem_mesh.py`). |
| C7 | `pyproject.toml:36-50` | Add `[calibration]` extra declaring `SALib>=1.4` + `scikit-learn>=1.3`; make `[dev]` include it. |
| C8 | `src/instream/model_init.py:516-528` | Replace silent `except Exception: pass` around marine species-weight propagation with an `hasattr` guard so real errors surface. |
| H1 | `app/modules/movement_panel.py:39-41` | Convert `get_fill_color` → `getFillColor` (deck.gl camelCase). |

**Exit criteria:** All 9 fixes landed with regression tests. `__version__` bumped to 0.41.15. CHANGELOG entry written. `ruff check src/ tests/ --select E,F,W --ignore E501` passes. Fresh `pip install -e .` and `pip install -e ".[dev]"` both succeed in a clean environment.

---

## Phase 2 — v0.42.0 Scientific/Numerical Hardening

**Dependency:** Phase 1 merged.

**Scope:** HIGH-severity findings in backends, calibration, bayesian, marine.

### Tasks

| # | File:Line | Finding | Fix shape |
|---|---|---|---|
| 2.1 | `src/instream/backends/_interface.py:31-41` vs `numpy_backend/marine.py:45-53` | `MarineBackend.marine_survival` Protocol/impl signature mismatch | Align both to `config: Any` OR expand impl to `**species_params`. Add Protocol-conformance test. |
| 2.2 | `src/instream/backends/jax_backend/__init__.py:220-221` | Multi-species JAX silently uses `cmax_temp_table_xs[0]` for all species | Raise `NotImplementedError` when `len(cmax_temp_table_xs) > 1`. Add a multi-species parity test that currently skips JAX. |
| 2.3 | `src/instream/backends/numba_backend/fitness.py:286` vs `:946-948` | Shelter eligibility check ignores `superind_rep`; depletion charges `length² × rep` | Align Pass 1 threshold to `a_shelter > length² * rep`. |
| 2.4 | `tests/test_backends.py`, `tests/test_backend_parity.py` | Zero parity coverage of `batch_select_habitat` | Add test calling `batch_select_habitat` on a small CSR input; compare against Python scalar loop over same candidates. |
| 2.5 | `src/instream/bayesian/smc.py:83-91` | Log-marginal-likelihood accumulator double-counts `max_lw`; uses `.mean()` where log-sum-exp is required | Replace with standard SMC incremental `log(sum(w_old * exp(delta_log_like)))` formula. Test: zero-log-likelihood input must produce `log_marginal_likelihood ≈ 0`. |
| 2.6 | `src/instream/calibration/losses.py:36-42` | `rmse_loss` returns `0.0` (perfect) for all-NaN input | Return `float("nan")`. Document that callers must handle NaN with explicit policy. |
| 2.7 | `src/instream/marine/survival.py:221` | Post-smolt forced-hazard write not masked by `post_smolt_mask` | Change to `h_forced_array[post_smolt_mask & (smolt_years == sy)] = ...`. Add regression test. |
| 2.8 | `src/instream/marine/growth.py:100` | Respiration Q10 anchored to `cmax_topt`, not a fixed metabolic standard temp | Add `resp_ref_temp: float = 15.0` field to `SpeciesParams`; use it as Q10 anchor. |
| 2.9 | `src/instream/modules/behavior.py:~956, ~1444` | `expected_fitness` formula duplicated inline at two sites instead of importing from `habitat_fitness.py` — three sources of truth for the same scientific expression | Import `expected_fitness` from `instream.modules.habitat_fitness`; call it at both sites. Add a property test asserting parity with the canonical function. |

> **Dropped during verification:**
> - `interpax` was flagged as undeclared — actually IS in `[jax]` (pyproject.toml:43).
> - SMC particle seeds indexed by position after resampling — examined Del Moral 2006 pattern: this is standard ABC-SMC behavior (each temperature step is a fresh stochastic evaluation). Not a bug.

**Exit criteria:** All 9 tasks landed with regression tests. `test_backend_parity.py` now exercises `batch_select_habitat`. Multi-species JAX paths raise clearly. `expected_fitness` has a single source of truth.

---

## Phase 3 — v0.42.1 Frontend Regression Sweep

**Dependency:** Phase 1 merged (H1 movement_panel already done there).

**Scope:** Shiny frontend correctness and laguna-deploy-compat fixes.

### Tasks

| # | File:Line | Finding | Fix shape |
|---|---|---|---|
| 3.1 | `app/app.py:420` | Plotly loaded from CDN → blocked by Edge/Firefox tracking prevention on laguna | Download `plotly-2.35.2.min.js` to `app/www/`; reference via `ui.tags.script(src="plotly-2.35.2.min.js")`. |
| 3.2 | `app/modules/spatial_panel.py:349-350` | Hardcoded `epsg=32634` (UTM 34N) centroid reprojection | Use `cells.estimate_utm_crs()`; cache result on `fem_space._utm_crs`. Add test with non-Baltic bbox. |
| 3.3 | `app/app.py:555-589` | Outer `_poll_progress` `except Exception: pass` hides sim failures | Log + `_sim_state.set("error")` on exception; add test with a forced malformed queue item. |
| 3.4 | `tests/e2e/_debug_lagoon_cells.py` | Untracked scratch script in tests tree | Move to `scratch/` outside `tests/` (or delete). Add to `tests/e2e/conftest.py` `collect_ignore` as a safety net. |
| 3.5 | `tests/test_e2e_spatial.py:59` | Fixture uses `--reload` flag; unreliable on OneDrive paths | Remove `--reload` from the test-app command list. |
| 3.6 | Global sweep | Ensure no other `get_fill_color`/`get_line_color`/`get_line_width` exists in `app/` after P1 | Run `grep -rn 'get_fill_color\|get_line_color\|get_line_width' app/` — must return empty. Add a ruff custom rule OR a pytest collection-time assertion to prevent regression. |

**Exit criteria:** laguna.ku.lt deploy renders all four plot panels with tracking prevention on. `grep` for snake_case deck.gl props returns empty.

---

## Phase 4 — v0.42.2 CI + Test-Suite Hardening

**Dependency:** Phase 1 merged.

**Scope:** CI workflow correctness, oracle-test visibility, fixture-scope leaks.

### Tasks

| # | File:Line | Finding | Fix shape |
|---|---|---|---|
| 4.1 | `.github/workflows/ci.yml:47` | Main `test` job runs `-m slow` tests (no deselection); they run twice | Add `-m "not slow"` to the main `test` command. `test-slow` job remains as-is. |
| 4.2 | `.github/workflows/ci.yml` | `fail_under=80` coverage gate not enforced | Add a coverage step using `pytest-cov`: `pytest --cov=instream --cov-fail-under=80`. |
| 4.3 | `tests/conftest.py` new hook | Oracle CSVs can be absent with zero visibility — suite green with zero NetLogo parity | Add `pytest_configure` hook: when `tests/fixtures/reference/` is empty AND `CI_NO_ORACLE` is unset, emit a loud warning. Optionally: fail hard under `CI=1`. |
| 4.4 | `tests/test_validation.py:1006` | Stale `@pytest.mark.xfail(strict=False)` for fitness-report — 12 releases behind Arc D | Regenerate `fitness-golden.csv` via the `netlogo-oracle` skill/workflow; remove the xfail. If golden regen is blocked, flip `strict=True` so surprise passes fail loudly. |
| 4.5 | `tests/test_e2e_spatial.py` | Module-level `_sim_ran = False` global is a scope="session" fixture in disguise | Replace with `@pytest.fixture(scope="session", autouse=True)` that triggers the sim once. |
| 4.6 | `tests/test_backend_parity.py` | `rng = np.random.default_rng(12345)` at `scope="module"` — state leaks between tests | Change to `scope="function"` OR seed explicitly inside each test. |
| 4.7 | `tests/test_app_smoke.py` | Module-level `sys.path.insert` can fail collection on import error | Guard with `try/except ImportError` at module top; skip module with a clear reason if fails. |
| 4.8 | `tests/test_properties.py` | No Hypothesis coverage of `habitat_fitness.evaluate_fitness`, Arc D migration comparator, `rmse_loss` NaN invariant | Add three property tests: (a) `evaluate_fitness` output in `[0, 1]`; (b) migration comparator is transitive; (c) `rmse_loss` returns NaN iff all inputs NaN. |

**Exit criteria:** CI time roughly halved (slow tests no longer duplicated). Coverage gate enforced. Oracle-absent runs emit a visible warning.

---

## Phase 5 — v0.42.3 Documentation Sync

**Dependency:** None.

**Scope:** Bring all docs to the current version and enum state; prevent regression via a release-script fix.

### Tasks

| # | File:Line | Finding | Fix shape |
|---|---|---|---|
| 5.1 | `README.md:9` | Shield badge stuck at `v0.33.0` | Update shield URL to current `__version__`. Extend `scripts/release.py:166-170`'s regex to cover the shield URL pattern. Add a `scripts/release.py` test that roundtrips a version bump. |
| 5.2 | `CHANGELOG.md` | No entry for `0.41.14` | Add entry documenting v0.41.14 diff from v0.41.13. |
| 5.3 | `scripts/release.py` pre-flight check | CHANGELOG top and `__version__` can drift | Add a pre-release check: fail if `re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog)` group(1) != `instream.__version__`. |
| 5.4 | `docs/api-reference.md:3,87` | Document version "0.1.0"; `life_history` enum documented with pre-v0.13.0 names (`resident`, `anad_juve`, `anad_adult`) | Regenerate enum table from `src/instream/state/life_stage.py` (FRY=0, PARR=1, SPAWNER=2, SMOLT=3, OCEAN_JUVENILE=4, OCEAN_ADULT=5, RETURNING_ADULT=6, KELT=7). Bump version header to current. |
| 5.5 | `docs/user-manual.md:3` | Document version "0.1.0" | Bump version header. |
| 5.6 | `docs/NETLOGO_PARITY_ROADMAP.md` | 2026-03-22 snapshot; claims 0/11 validation tests active | Archive under `docs/releases/archive-2026-03-22-parity-roadmap.md`. Replace the canonical path with a redirect to `docs/validation/wgbast-roadmap-complete.md`. |

**Exit criteria:** Grep for `Version 0.1.0` in `docs/` returns empty. Release script automatically updates the shield.

---

## Phase 6 — v0.42.4 Medium/Low Hygiene

**Dependency:** None.

**Scope:** ~15 MEDIUM and LOW findings; quality-of-life and defensive-programming fixes.

### Tasks (grouped by subsystem)

**IO / config:**
- 6.1 `src/instream/io/m74_forcing.py:28` — replace `assert` column-validation with `raise ValueError`.
- 6.2 `src/instream/io/population_reader.py:11-29` — guard `len(parts) < 7` with a diagnostic including path + line number.
- 6.3 `src/instream/io/output.py` all writers — switch to write-then-rename atomic pattern via `tempfile.NamedTemporaryFile` + `shutil.move`.
- 6.4 `src/instream/io/config.py:111-330` — add `field_validator` on all probability fields (`spawn_prob`, `spawn_egg_viability`, `mass_floor_survival`, `kelt_survival_prob`, `outmigration_max_prob`) enforcing `[0, 1]`; non-negative guards on length/distance fields.

**Marine:**
- 6.5 `src/instream/modules/migration.py:129-138` — refresh `smolt_date` when a kelt re-enters the ocean.
- 6.6 `src/instream/io/output.py:283-293` — document whether `spawner_origin_matrix` is raw counts or row-proportions; if proportions, normalize on write.

**Biology:**
- 6.7 `src/instream/modules/spawning.py:260-285` — implement `redd_area / cell_area` fraction for `apply_superimposition`, or remove dead `redd_area` param. Add a partial-overlap test.
- 6.8 `src/instream/modules/survival.py:384-426` — remove unused `step_length` from `redd_survival_lo_temp` / `redd_survival_hi_temp` primitives.
- 6.9 `src/instream/modules/spawning.py:448-451` — log/count dropped eggs when `trout_state` capacity is full.

**Spatial:**
- 6.10 `src/instream/model_init.py:117-120` — pre-check unknown reach names and raise with the list.
- 6.11 `src/instream/space/fem_mesh.py:142-162` — add `.copy()` calls in `to_cell_state` to match `PolygonMesh`.
- 6.12 `src/instream/space/fem_space.py` — document immutability contract; add optional `_mesh_version` counter.

**Calibration:**
- 6.13 `src/instream/calibration/multiphase.py:130,190` — reset `fixed_params` at `.run()` start OR document the warm-restart behavior.
- 6.14 `src/instream/calibration/surrogate.py:157-160` — replace uniform Monte-Carlo candidate search with LHS.
- 6.15 `src/instream/calibration/surrogate.py` — add `scenario_id` to `fit()` and assert at `find_optimum()`.
- 6.16 `src/instream/calibration/history.py:34` — use `datetime.now(timezone.utc)` to match `scenarios.py`.

**Scripts + housekeeping:**
- 6.17 `scripts/release.py:302` — detect current branch via `git rev-parse --abbrev-ref HEAD` instead of hardcoded `origin master`.
- 6.18 `scripts/generate_analytical_reference.py:95-96,128-129` — remove `sys.path.insert`; rely on installed package.
- 6.19 Untracked files cleanup — `.gitignore` the `scripts/_arc_*_*.csv` probe pattern; promote or delete `scripts/_fetch_curonian_lagoon_osm.py`; commit or remove `docs/superpowers/plans/2026-04-21-v041-deferred-followups.md`.

**Exit criteria:** All 19 hygiene tasks closed; suite passes; one consolidated v0.42.4 CHANGELOG entry.

---

## Cross-cutting concerns (not phased)

### Invariant tests to add (prevent "regression of a fix")

Four findings in this review were regressions of prior fixes. Add invariant-style tests that catch the whole class:

1. **Backend parity invariant** — for every public backend method in `_interface.py`, a generated test runs it on all installed backends and asserts numerical equality within tolerance. Covers C1, the JAX multi-species trap, and any future backend drift.
2. **Species-params sync invariant** — `params_from_config(cfg)` produces a `SpeciesParams` whose every `*_m` / `*_cm` / `*_days` field is self-consistent with `cfg.species[...]`. Covers C5 and the whole Arc E class.
3. **Deck.gl camelCase invariant** — a test that greps `app/` for `get_(fill_color|line_color|...)` and fails if any match. Covers H1 + prevents future repetition.
4. **Life-stage transition invariant** — a property test that for every (from_stage, to_stage) transition, the transition function preserves agent count (no ghost agents, no dupes). Would have caught the ghost-smolt and natal-recruitment-gap bugs from project memory.

These go into Phase 4 tasks 4.8+ as the structural hardening layer.

---

## Sequencing notes

- Phase 1 must land first (it stabilizes the scientific outputs everyone else depends on).
- Phases 2, 3, 4 can run in parallel after Phase 1 lands (independent files/subsystems). Phase 3 and Phase 4 have the smallest blast radius, so they're the best parallel candidates for a second engineer.
- Phase 5 (docs) can ship anytime after Phase 1.
- Phase 6 (hygiene) is a follow-up sweep; don't block a release on it.

## Review links

- Full review conducted 2026-04-23 in session.
- 51 findings: 5 CRITICAL, 16 HIGH, 20 MEDIUM, 10 LOW.
- See `2026-04-23-phase1-critical-correctness.md` for the TDD-structured first plan.
