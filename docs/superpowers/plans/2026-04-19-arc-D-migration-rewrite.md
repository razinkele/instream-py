# Arc D: Migration Architecture Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 21× outmigrant deficit against NetLogo InSALMO 7.3 example_a by rewriting migration's habitat-fitness comparator and the FRY→PARR promotion gate, without changing the `migration_fitness` logistic itself (which already matches NetLogo).

**Architecture:** Three coordinated changes. (1) Introduce a **bounded per-tick habitat fitness** `(daily_survival × mean_starv_survival)^time_horizon` matching NetLogo's `fitness-for` at `InSALMO7.3:2798-2827`; store its per-fish maximum on `TroutState.best_habitat_fitness` after habitat selection. (2) Replace `should_migrate`'s `fitness_memory` comparator with `best_habitat_fitness`, putting both sides of the comparison on the same [0,1] probability scale. (3) Replace the `julian_date == 1` FRY→PARR gate with a continuous size/age rule (anadromous FRY with length ≥ parr_min_length OR age ≥ 1 → PARR) so emergence-year fish can outmigrate in their first season.

**Tech Stack:** NumPy (per-fish vectors on `TroutState`), Numba-compiled fitness evaluator (extend `backends/numba_backend/fitness.py`), pytest (TDD), existing `tests/test_run_level_parity.py::TestExampleARunVsNetLogo` as the integration-level success signal.

**Out of scope (parallel track):** Juvenile growth calibration (~32% length shortfall). Addressed in a separate session — Arc D is expected to *reduce* the outmigrant gap but not fully close it until growth is corrected. The `spawn_defense_area` cm-vs-cm² semantic is also deferred.

**Scope check:** Single subsystem (migration + habitat selection comparator). No split needed.

---

## File Structure

**New files:**
- `src/instream/modules/habitat_fitness.py` — pure-Python reference implementation of `expected_fitness(daily_survival, daily_growth, length, time_horizon, fitness_length)`, mirroring NetLogo 2813-2840. One responsibility: translate per-cell survival+growth into the bounded [0,1] fitness measure used for activity selection.
- `tests/test_habitat_fitness.py` — unit tests against hand-computed NetLogo expected outputs.
- `tests/test_arc_d_migration.py` — behavioral tests (FRY migrates, scale-consistent comparator, continuous promotion).

**Modified files:**
- `src/instream/state/trout_state.py` — add `best_habitat_fitness: float64[n]` array, zero-initialized; mirror the grow/reset pattern of `fitness_memory`.
- `src/instream/modules/behavior.py` — in the per-fish habitat-selection loop, after `_evaluate_all_cells` picks the best cell, also record that cell's `expected_fitness` on `TroutState.best_habitat_fitness[i]`.
- `src/instream/backends/numba_backend/fitness.py` — extend `_evaluate_all_cells` / `batch_select_habitat` to additionally return/write the per-fish best `expected_fitness` value. Keep the existing hab-selection decision intact.
- `src/instream/modules/migration.py:23-27` — `should_migrate` reads the caller-supplied `best_habitat_fit` argument unchanged, but the docstring clarifies it now expects the per-tick bounded fitness, not the EMA.
- `src/instream/model_day_boundary.py:482` — replace the `julian_date == 1` gate with the continuous size/age rule. Preserve the anadromous-only guard.
- `src/instream/model_day_boundary.py:599` — loosen the PARR-only filter in `_do_migration` so anadromous FRY with sufficient length also evaluate migration.
- `src/instream/model.py:108-115` — leave `fitness_memory` EMA alone (still used for survival/starvation logic); just stop using it as the migration comparator.
- `src/instream/io/config.py` (outmigration_min_length default) — lower from 8.0 to 4.0 cm for anadromous species where NetLogo's `FishEventsOut-r1_*.csv` confirms 3.6-4.0 cm fish migrate. Document the change in `docs/calibration-notes.md`.

---

## Task 1: Expected-fitness reference implementation (NetLogo `fitness-for` port)

**Files:**
- Create: `src/instream/modules/habitat_fitness.py`
- Test: `tests/test_habitat_fitness.py`

**Why first:** Pure function, no state, exact translation of NetLogo 2813-2840. Lands the [0,1] bounded measure that every subsequent task depends on. Unit-testable against hand-computed NetLogo values.

- [ ] **Step 1: Write the failing unit tests**

```python
# tests/test_habitat_fitness.py
"""Reference-implementation tests for habitat_fitness.expected_fitness.

Targets NetLogo InSALMO 7.3 fitness-for (lines 2798-2840). The formula:

    fitness = (daily_survival * mean_starv_survival_to_horizon) ^ time_horizon
    if length < fitness_length:
        fitness *= min(1.0, length_at_horizon / fitness_length)

Hand-computed expected values assume mean_starv_survival=1.0 unless
otherwise stated — starvation survival is its own module.
"""
import math

import pytest


class TestExpectedFitness:
    def test_perfect_survival_no_growth_penalty(self):
        """Survival=1, length>=fitness_length → fitness=1."""
        from instream.modules.habitat_fitness import expected_fitness

        f = expected_fitness(
            daily_survival=1.0,
            mean_starv_survival=1.0,
            length=10.0,
            daily_growth=0.1,
            time_horizon=90,
            fitness_length=6.0,
        )
        assert f == pytest.approx(1.0)

    def test_survival_power_horizon(self):
        """fitness = survival^horizon when starv_survival=1 and length>=fit_length."""
        from instream.modules.habitat_fitness import expected_fitness

        f = expected_fitness(
            daily_survival=0.99,
            mean_starv_survival=1.0,
            length=10.0,
            daily_growth=0.0,
            time_horizon=90,
            fitness_length=6.0,
        )
        assert f == pytest.approx(0.99 ** 90, rel=1e-9)

    def test_undersized_fish_length_penalty(self):
        """If length < fitness_length, fitness scales by length_at_horizon/fitness_length."""
        from instream.modules.habitat_fitness import expected_fitness

        # daily_growth small → length_at_horizon < fitness_length → penalty applies
        f = expected_fitness(
            daily_survival=1.0,
            mean_starv_survival=1.0,
            length=3.0,
            daily_growth=0.01,
            time_horizon=90,
            fitness_length=6.0,
        )
        # Expected: fitness = 1 * (3 + 90*0.01) / 6 = 3.9 / 6 = 0.65
        assert f == pytest.approx(3.9 / 6.0, rel=1e-6)

    def test_bounded_0_1(self):
        """fitness must be in [0, 1] for any plausible inputs."""
        from instream.modules.habitat_fitness import expected_fitness

        for ds in [0.1, 0.5, 0.99, 1.0]:
            for ss in [0.1, 0.5, 1.0]:
                for L in [3.0, 6.0, 12.0]:
                    for g in [0.0, 0.01, 0.1]:
                        f = expected_fitness(ds, ss, L, g, 90, 6.0)
                        assert 0.0 <= f <= 1.0, (ds, ss, L, g, f)

    def test_zero_survival_zero_fitness(self):
        from instream.modules.habitat_fitness import expected_fitness

        f = expected_fitness(0.0, 1.0, 10.0, 0.1, 90, 6.0)
        assert f == 0.0

    def test_starv_survival_multiplies(self):
        from instream.modules.habitat_fitness import expected_fitness

        f = expected_fitness(
            daily_survival=1.0,
            mean_starv_survival=0.5,
            length=10.0,
            daily_growth=0.1,
            time_horizon=10,
            fitness_length=6.0,
        )
        # (1 * 0.5)^10 = 0.5^10
        assert f == pytest.approx(0.5 ** 10, rel=1e-9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `micromamba run -n shiny python -m pytest tests/test_habitat_fitness.py -v`
Expected: ModuleNotFoundError — `instream.modules.habitat_fitness` does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
# src/instream/modules/habitat_fitness.py
"""Expected-fitness translation of NetLogo InSALMO 7.3 fitness-for (2798-2840).

NetLogo computes, per candidate cell × activity:

    fitness = (daily_survival * mean_starv_survival_to_horizon) ** time_horizon

If the fish's expected length at horizon is below species-level
trout-fitness-length, fitness is additionally multiplied by
(length_at_horizon / fitness_length) — i.e. undersized fish can't
claim full fitness even in a survivable cell.

Output is always in [0, 1], making it directly comparable against
migration_fitness (a size-only logistic in [0.1, 0.9]) on the same
probability scale.
"""
from __future__ import annotations


def expected_fitness(
    daily_survival: float,
    mean_starv_survival: float,
    length: float,
    daily_growth: float,
    time_horizon: int,
    fitness_length: float,
) -> float:
    """Return expected fitness in [0, 1] for one fish-cell-activity triple."""
    base = (daily_survival * mean_starv_survival) ** time_horizon
    if length >= fitness_length or fitness_length <= 0.0:
        return max(0.0, min(1.0, base))
    length_at_horizon = length + daily_growth * time_horizon
    if length_at_horizon < fitness_length:
        base *= length_at_horizon / fitness_length
    # else fish will exceed fitness-length — no penalty
    return max(0.0, min(1.0, base))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_habitat_fitness.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/instream/modules/habitat_fitness.py tests/test_habitat_fitness.py
git commit -m "feat(migration): add expected_fitness port of NetLogo fitness-for"
```

---

## Task 2: Add `best_habitat_fitness` to TroutState

**Files:**
- Modify: `src/instream/state/trout_state.py` (add array, initializer, grow hook)
- Test: `tests/test_arc_d_migration.py`

**Why now:** Every downstream step writes/reads this array. Schema first.

- [ ] **Step 1: Write the failing schema test**

```python
# tests/test_arc_d_migration.py
"""Arc D migration architecture rewrite — behavioral tests."""
import numpy as np
import pytest


class TestTroutStateBestHabitatFitness:
    def test_array_exists_and_is_float64(self):
        from instream.state.trout_state import TroutState

        ts = TroutState(n=10)
        assert hasattr(ts, "best_habitat_fitness")
        assert ts.best_habitat_fitness.dtype == np.float64
        assert ts.best_habitat_fitness.shape == (10,)

    def test_initial_value_zero(self):
        from instream.state.trout_state import TroutState

        ts = TroutState(n=10)
        assert np.all(ts.best_habitat_fitness == 0.0)

    def test_grow_preserves_values(self):
        """When TroutState grows its arrays, existing best_habitat_fitness
        values survive and new entries are zero-filled."""
        from instream.state.trout_state import TroutState

        ts = TroutState(n=3)
        ts.best_habitat_fitness[:] = [0.1, 0.5, 0.9]
        ts.grow(new_n=6)
        assert ts.best_habitat_fitness.shape == (6,)
        np.testing.assert_array_equal(
            ts.best_habitat_fitness[:3], [0.1, 0.5, 0.9]
        )
        assert np.all(ts.best_habitat_fitness[3:] == 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `micromamba run -n shiny python -m pytest tests/test_arc_d_migration.py::TestTroutStateBestHabitatFitness -v`
Expected: AttributeError — no `best_habitat_fitness` on TroutState.

- [ ] **Step 3: Add the array**

Find in `src/instream/state/trout_state.py`: the block where `fitness_memory` is declared and initialized. Add a sibling `best_habitat_fitness` array of the same shape and dtype, initialized to 0.0.

Locate the `__init__` assignment and add immediately after `self.fitness_memory = ...`:

```python
self.best_habitat_fitness = np.zeros(n, dtype=np.float64)
```

Then find the `grow()` method (or equivalent `resize`) and add the mirror line next to every existing `fitness_memory` resize/concatenate.

```python
self.best_habitat_fitness = np.concatenate(
    [self.best_habitat_fitness, np.zeros(new_n - old_n, dtype=np.float64)]
)
```

Use `Grep` to find every place `fitness_memory` is resized. Mirror each.

- [ ] **Step 4: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_arc_d_migration.py::TestTroutStateBestHabitatFitness -v`
Expected: 3 passed.

Also run the full existing suite to confirm no regression from the schema change:
Run: `micromamba run -n shiny python -m pytest tests/ -x -q`
Expected: all existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/instream/state/trout_state.py tests/test_arc_d_migration.py
git commit -m "feat(state): add TroutState.best_habitat_fitness for Arc D comparator"
```

---

## Task 3: Write per-fish `best_habitat_fitness` during habitat selection

**Files:**
- Modify: `src/instream/modules/behavior.py` (per-fish loop and batch path)
- Modify: `src/instream/backends/numba_backend/fitness.py` (add out-array for best fitness)
- Test: `tests/test_arc_d_migration.py::TestHabitatFitnessRecording`

**Goal:** After habitat selection picks a cell for fish `i`, also store the `expected_fitness` of that cell/activity on `trout_state.best_habitat_fitness[i]`.

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_arc_d_migration.py`:

```python
class TestHabitatFitnessRecording:
    """After _do_habitat_selection runs, every alive fish should have a
    best_habitat_fitness in [0, 1] recorded (not the unbounded EMA)."""

    def test_best_habitat_fitness_populated_after_selection(self):
        from tests._arc_d_helpers import build_minimal_model

        m = build_minimal_model(n_fish=5)
        m.step()  # runs one daily step including habitat selection
        alive = m.trout_state.alive_indices()
        assert len(alive) > 0
        vals = m.trout_state.best_habitat_fitness[alive]
        assert np.all(vals >= 0.0)
        assert np.all(vals <= 1.0)
        # At least one fish should have nonzero fitness (they are in viable cells)
        assert np.any(vals > 0.0)

    def test_best_habitat_fitness_differs_from_fitness_memory(self):
        """Proves the two quantities are separate — not aliased."""
        from tests._arc_d_helpers import build_minimal_model

        m = build_minimal_model(n_fish=5)
        for _ in range(3):  # run a few steps so EMA has time to drift
            m.step()
        alive = m.trout_state.alive_indices()
        # fitness_memory is not bounded in [0,1]; best_habitat_fitness is.
        # If they were aliased, they would match exactly. Assert they don't.
        assert not np.array_equal(
            m.trout_state.fitness_memory[alive],
            m.trout_state.best_habitat_fitness[alive],
        )
```

And create the helper:

```python
# tests/_arc_d_helpers.py
"""Shared minimal-model factory for Arc D tests."""
from pathlib import Path


def build_minimal_model(n_fish: int = 5):
    """Build the smallest possible single-reach Chinook model for unit testing.

    Uses the same fixture pattern as tests/test_behavioral_validation.py
    but capped at n_fish initial population. Returns a ready-to-step Model.
    """
    from instream.io.config import load_config
    from instream.model import Model

    cfg_path = Path(__file__).resolve().parent / "fixtures" / "example_a_small.yaml"
    if not cfg_path.exists():
        # Fall back to the smallest example_a-like config
        cfg_path = Path(__file__).resolve().parent.parent / "configs" / "example_a.yaml"
    cfg = load_config(cfg_path)
    # Override initial population so the test is fast
    if hasattr(cfg.simulation, "initial_population"):
        cfg.simulation.initial_population = n_fish
    return Model(cfg)
```

If `example_a_small.yaml` doesn't exist, the helper falls back to `configs/example_a.yaml` with a population override. Inspect `tests/test_behavioral_validation.py` first to use whatever factory pattern is already there — prefer reusing over inventing.

- [ ] **Step 2: Run the test and verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_arc_d_migration.py::TestHabitatFitnessRecording -v`
Expected: FAIL — `best_habitat_fitness` stays zero because nothing writes it yet.

- [ ] **Step 3: Update the Numba batch path to write best_habitat_fitness**

Read `src/instream/backends/numba_backend/fitness.py` and find `batch_select_habitat`. It currently returns the best cell indices per fish. Extend its signature so callers pass an output array `out_best_fitness: float64[n_fish]`, and the inner loop writes the max `expected_fitness` value found across candidate cells/activities.

The evaluator must receive the per-fish `daily_survival` × `mean_starv_survival` × `daily_growth` estimates and the species `fitness_length` + `fitness_horizon`, then compute `expected_fitness` inline (copy the Task 1 formula — Numba can't call the pure-Python version directly; duplicate the ~5 lines).

```python
# inside the per-fish loop in batch_select_habitat, after choosing best cell:
base = (ds * ss) ** horizon
if L < fit_len and fit_len > 0.0:
    L_at_h = L + dg * horizon
    if L_at_h < fit_len:
        base *= L_at_h / fit_len
if base > 1.0:
    base = 1.0
elif base < 0.0:
    base = 0.0
out_best_fitness[i] = base
```

- [ ] **Step 4: Update behavior.py callers to pass and consume the new array**

In `src/instream/modules/behavior.py`, find the site that calls `batch_select_habitat` (or `_evaluate_all_cells` in the per-fish path). Before the call, allocate `best_fit = np.zeros(n_fish, dtype=np.float64)`. After the call, write `trout_state.best_habitat_fitness[alive] = best_fit[:len(alive)]` (or the equivalent alive-indexed scatter already used in the module).

For the non-Numba (pure-Python) path, call `instream.modules.habitat_fitness.expected_fitness` on the chosen cell's inputs and store the result.

- [ ] **Step 5: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_arc_d_migration.py::TestHabitatFitnessRecording -v`
Expected: 2 passed.

Full suite to check no regression:
Run: `micromamba run -n shiny python -m pytest tests/ -x -q`
Expected: all passing (or the same red tests that were already red pre-Arc D — specifically `test_run_level_parity.py::TestExampleARunVsNetLogo` which stays red until Task 8).

- [ ] **Step 6: Commit**

```bash
git add src/instream/backends/numba_backend/fitness.py src/instream/modules/behavior.py tests/test_arc_d_migration.py tests/_arc_d_helpers.py
git commit -m "feat(behavior): record per-tick best_habitat_fitness alongside cell selection"
```

---

## Task 4: Continuous FRY → PARR promotion (remove annual Jan-1 gate)

**Files:**
- Modify: `src/instream/model_day_boundary.py` (the `_do_age_and_promote_fry` method around line 470-507)
- Test: `tests/test_arc_d_migration.py::TestContinuousPARRPromotion`

**Rule:** An anadromous FRY is promoted to PARR when length ≥ `parr_promotion_length` (species-level, default 4.0 cm — matches NetLogo's `anad-juve-length` threshold) OR age ≥ 1. Runs every day, not only Jan 1. Age still increments on Jan 1 as before.

- [ ] **Step 1: Write the failing behavioral tests**

Append to `tests/test_arc_d_migration.py`:

```python
class TestContinuousPARRPromotion:
    def test_fry_promoted_when_length_threshold_crossed_mid_year(self):
        """An anadromous FRY whose length crosses parr_promotion_length
        in July should become PARR on the next daily boundary — NOT wait
        for Jan 1."""
        from instream.state.life_stage import LifeStage
        from tests._arc_d_helpers import build_minimal_model

        m = build_minimal_model(n_fish=5)
        # Force all fish into FRY at a large length before stepping
        m.trout_state.life_history[:] = int(LifeStage.FRY)
        m.trout_state.length[:] = 5.0  # above default parr_promotion_length=4.0
        # Seed the date well away from Jan 1 (July)
        import pandas as pd
        m.time_manager._current_date = pd.Timestamp("2011-07-15")

        m.step()  # one daily step — day boundary should promote
        alive = m.trout_state.alive_indices()
        lh = m.trout_state.life_history[alive]
        assert (lh == int(LifeStage.PARR)).sum() == len(alive), (
            f"expected all anad FRY promoted to PARR mid-year, got {lh.tolist()}"
        )

    def test_small_fry_not_promoted(self):
        """FRY below length threshold AND age 0 stays FRY."""
        from instream.state.life_stage import LifeStage
        from tests._arc_d_helpers import build_minimal_model

        m = build_minimal_model(n_fish=5)
        m.trout_state.life_history[:] = int(LifeStage.FRY)
        m.trout_state.length[:] = 2.5  # below threshold
        m.trout_state.age[:] = 0
        import pandas as pd
        m.time_manager._current_date = pd.Timestamp("2011-07-15")

        m.step()
        alive = m.trout_state.alive_indices()
        lh = m.trout_state.life_history[alive]
        assert (lh == int(LifeStage.FRY)).all()

    def test_non_anadromous_fry_never_promoted(self):
        """Rainbow-trout-style non-anadromous FRY must not be promoted
        to PARR under any circumstances — this was the v0.16.0 bug."""
        # Skipped here if the minimal fixture is anadromous-only.
        # Add a dedicated fixture if/when a non-anadromous species is
        # available. Until then, preserve the existing test in
        # tests/test_non_anadromous.py as the guard.
        pytest.skip("non-anad fixture TBD; existing guard covers this")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `micromamba run -n shiny python -m pytest tests/test_arc_d_migration.py::TestContinuousPARRPromotion -v`
Expected: `test_fry_promoted_when_length_threshold_crossed_mid_year` FAILS — current code only promotes on Jan 1.

- [ ] **Step 3: Rewrite the promotion method**

Replace the current `_do_age_and_promote_fry` body (model_day_boundary.py around 482-507) with:

```python
def _do_age_and_promote_fry(self):
    """Advance age on Jan 1; promote anadromous FRY to PARR continuously.

    Promotion rule: FRY → PARR when species is anadromous AND
    (length >= parr_promotion_length OR age >= 1). The length branch
    lets emergence-year fish become PARR as soon as they are big enough
    to outmigrate; the age branch preserves the legacy 'overwinter'
    promotion for fish that stayed small.

    NetLogo reference: InSALMO 7.3 does not gate anad-juvenile status
    to a calendar date. Python's Jan-1-only gate (pre-Arc D) blocked
    emergence-year outmigration and was one of three root causes of
    the 21x outmigrant deficit reported in docs/validation/
    v0.30.2-netlogo-comparison.md.
    """
    alive = self.trout_state.alive_indices()
    if len(alive) == 0:
        return

    from instream.state.life_stage import LifeStage

    # 1) Age increment on Jan 1 only (unchanged semantics)
    if self.time_manager.julian_date == 1:
        self.trout_state.age[alive] += 1

    # 2) Continuous FRY -> PARR promotion for anadromous species
    anadromous_by_idx = np.array(
        [
            bool(getattr(self.config.species[name], "is_anadromous", False))
            for name in self.species_order
        ],
        dtype=bool,
    )
    if not anadromous_by_idx.any():
        return

    species = self.trout_state.species_idx[alive]
    is_anad = anadromous_by_idx[species]
    fry_mask = self.trout_state.life_history[alive] == int(LifeStage.FRY)

    parr_min_by_idx = np.array(
        [
            float(getattr(
                self.config.species[name], "parr_promotion_length", 4.0
            ))
            for name in self.species_order
        ],
        dtype=np.float64,
    )
    length_ok = self.trout_state.length[alive] >= parr_min_by_idx[species]
    age_ok = self.trout_state.age[alive] >= 1

    promote = alive[fry_mask & is_anad & (length_ok | age_ok)]
    if len(promote) > 0:
        self.trout_state.life_history[promote] = int(LifeStage.PARR)
```

- [ ] **Step 4: Ensure `parr_promotion_length` exists in config schema**

Grep for `parr_promotion_length` in `src/instream/io/config.py`. If absent, add it to the species config schema with default 4.0 (float). Default 4.0 matches the value logged in NetLogo FishEventsOut for emergence-year migration (3.6-4.0 cm). Do not set overrides in example_a.yaml unless its NetLogo counterpart sets them.

- [ ] **Step 5: Run tests to verify they pass**

Run: `micromamba run -n shiny python -m pytest tests/test_arc_d_migration.py::TestContinuousPARRPromotion tests/test_non_anadromous.py -v`
Expected: promotion tests pass; non-anadromous guard still passes.

- [ ] **Step 6: Commit**

```bash
git add src/instream/model_day_boundary.py src/instream/io/config.py tests/test_arc_d_migration.py
git commit -m "feat(lifecycle): continuous FRY->PARR promotion by length or age"
```

---

## Task 5: Switch migration comparator from `fitness_memory` → `best_habitat_fitness`

**Files:**
- Modify: `src/instream/model_day_boundary.py:599` (the line `best_hab = float(self.trout_state.fitness_memory[i])`)
- Modify: `src/instream/modules/migration.py:23-27` (docstring clarification on `should_migrate`)
- Test: `tests/test_arc_d_migration.py::TestMigrationComparatorScale`

**Why now:** Tasks 3 and 4 put the right quantity on the right array and let small fish enter the PARR stage. This task consumes it.

- [ ] **Step 1: Write the failing scale-consistency test**

Append to `tests/test_arc_d_migration.py`:

```python
class TestMigrationComparatorScale:
    def test_small_parr_migrates_when_habitat_fitness_low(self):
        """A 4cm PARR with best_habitat_fitness=0.05 should have
        migration_fit (0.1 at length=4, L1=4, L9=10) > best_habitat_fit
        → should_migrate True. Pre-Arc D this was blocked because
        fitness_memory was typically > 0.1 (scale mismatch)."""
        from instream.modules.migration import migration_fitness, should_migrate
        from instream.state.life_stage import LifeStage

        mig_fit = migration_fitness(length=4.0, L1=4.0, L9=10.0)
        assert mig_fit == pytest.approx(0.1, abs=0.02)

        assert should_migrate(
            migration_fit=mig_fit,
            best_habitat_fit=0.05,  # poor cell — survival^horizon low
            life_history=int(LifeStage.PARR),
        ) is True

    def test_parr_stays_in_good_habitat(self):
        from instream.modules.migration import migration_fitness, should_migrate
        from instream.state.life_stage import LifeStage

        mig_fit = migration_fitness(length=4.0, L1=4.0, L9=10.0)
        assert should_migrate(
            migration_fit=mig_fit,
            best_habitat_fit=0.9,  # excellent cell
            life_history=int(LifeStage.PARR),
        ) is False
```

- [ ] **Step 2: Run test to confirm it ALREADY PASSES at the function level**

Run: `micromamba run -n shiny python -m pytest tests/test_arc_d_migration.py::TestMigrationComparatorScale -v`
Expected: PASS. `should_migrate` at the function level already handles both scales — the test documents the contract. The actual bug is at the caller in `_do_migration`, not in `should_migrate` itself.

- [ ] **Step 3: Update `_do_migration` to read `best_habitat_fitness` instead of `fitness_memory`**

In `src/instream/model_day_boundary.py` `_do_migration`, change line 599:

```python
# BEFORE:
best_hab = float(self.trout_state.fitness_memory[i])

# AFTER:
best_hab = float(self.trout_state.best_habitat_fitness[i])
```

Same change in the supplementary path (around line 617, `outmigration_probability(best_hab, ...)`) — use `best_habitat_fitness` there too for a consistent comparator.

- [ ] **Step 4: Update the migration.py docstring**

In `src/instream/modules/migration.py`, expand the `should_migrate` docstring to clarify the expected comparator:

```python
def should_migrate(migration_fit, best_habitat_fit, life_history):
    """Decide if a fish should migrate downstream.

    Both arguments must be on the same [0, 1] probability scale.
    `best_habitat_fit` should be the per-tick expected fitness of
    the fish's chosen cell/activity (see modules.habitat_fitness,
    mirroring NetLogo InSALMO 7.3 fitness-for). Passing the
    `fitness_memory` EMA here is a scale bug — see Arc D report.

    Only anadromous juveniles (PARR) may migrate.
    """
    if life_history != LifeStage.PARR:
        return False
    return migration_fit > best_habitat_fit
```

- [ ] **Step 5: Run the migration behavioral suite**

Run: `micromamba run -n shiny python -m pytest tests/test_migration.py tests/test_outmigration.py tests/test_arc_d_migration.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/instream/model_day_boundary.py src/instream/modules/migration.py tests/test_arc_d_migration.py
git commit -m "fix(migration): compare migration_fitness to per-tick best_habitat_fitness"
```

---

## Task 6: Allow anadromous FRY to evaluate migration

**Files:**
- Modify: `src/instream/modules/migration.py` (`should_migrate` signature) OR
- Modify: `src/instream/model_day_boundary.py:_do_migration` (widen the filter)
- Test: `tests/test_arc_d_migration.py::TestFryCanMigrate`

**Design note:** Task 4's continuous promotion already turns FRY into PARR when they cross the length threshold. So in practice, by the time a fish is big enough to consider outmigration, it has already been promoted. Task 6 is a belt-and-suspenders safety net: before migration evaluation, if an anadromous FRY slipped through with length ≥ `parr_promotion_length`, promote in-place.

- [ ] **Step 1: Write the test**

```python
class TestFryCanMigrate:
    def test_anad_fry_above_promotion_length_gets_promoted_before_migration(self):
        """If the promotion pass somehow missed an anad FRY with
        length >= parr_promotion_length, _do_migration should promote
        in-place rather than silently blocking migration."""
        # Implementation-dependent — see Task 6 decision below.
        pytest.skip(
            "Implement once Task 6 decides belt-and-suspenders vs single-path"
        )
```

- [ ] **Step 2: Decide implementation**

Read the tail of `_do_migration` to confirm Task 4's promotion runs BEFORE migration each day. If it does, Task 6 is a one-line assertion in `_do_migration`: `assert lh != LifeStage.FRY` for anadromous fish with length ≥ threshold (only fires in debug). Mark the test xfail with a note pointing at Task 4 as the de facto fix.

- [ ] **Step 3: Commit**

```bash
git add tests/test_arc_d_migration.py
git commit -m "test(migration): document Task 4 is the FRY-migration fix"
```

---

## Task 7: Lower `outmigration_min_length` default for anadromous species

**Files:**
- Modify: `src/instream/io/config.py:321` (default value)
- Modify: `docs/calibration-notes.md` (document the change and NetLogo citation)
- Test: no new test — this is a default-value change; existing supplementary-path test in `tests/test_outmigration.py` covers it.

**Why:** The supplementary probabilistic path at `_do_migration:617-634` is gated by species `outmigration_min_length`, default 8.0 cm. NetLogo `FishEventsOut-r1_*.csv` shows 3.6-4.0 cm fish migrating. Change the default to 4.0 cm. Per-species YAMLs can still override.

- [ ] **Step 1: Change the default**

```python
# src/instream/io/config.py: SpeciesConfig (or wherever outmigration_min_length is declared)
outmigration_min_length: float = 4.0  # was 8.0 pre-Arc D
```

- [ ] **Step 2: Run the full suite**

Run: `micromamba run -n shiny python -m pytest tests/ -x -q`
Expected: pass — this is just a default-value change. If a test explicitly assumed 8.0, fix the test to pass the value explicitly.

- [ ] **Step 3: Document in calibration-notes.md**

Add section "Arc D: outmigration_min_length default 8.0 → 4.0 cm. NetLogo FishEventsOut-r1 logs confirm 3.6-4.0 cm outmigration in InSALMO 7.3 example_a. See docs/validation/v0.30.2-netlogo-comparison.md for full context."

- [ ] **Step 4: Commit**

```bash
git add src/instream/io/config.py docs/calibration-notes.md
git commit -m "tune(migration): lower outmigration_min_length default to 4.0 cm"
```

---

## Task 8: Re-run the run-level parity test and document drift reduction

**Files:**
- Run: `tests/test_run_level_parity.py::TestExampleARunVsNetLogo`
- Create: `docs/validation/v0.31.0-arc-D-netlogo-comparison.md`

**Goal:** Measure the impact of Tasks 1-7 on the 3 failing metrics. Expectation (based on the memory analysis):

- Outmigrant total: 1,943 → several thousand (still short of 41,146 because the ~32% growth calibration gap is untouched)
- Juvenile length @ 2012-09-30: unchanged (growth calibration, not migration)
- Adult peak: should improve (more fish survive to outmigrate → more return as adults)

Even a 3× outmigrant improvement validates the architecture fix; the remaining gap is the growth calibration track.

- [ ] **Step 1: Run the parity test and capture metrics**

```bash
micromamba run -n shiny python -m pytest tests/test_run_level_parity.py::TestExampleARunVsNetLogo -v -m slow
```

Expected runtime: ~25 min. Record actual metric values printed by the test (it logs each metric even on failure).

- [ ] **Step 2: Write the comparison report**

Create `docs/validation/v0.31.0-arc-D-netlogo-comparison.md` with the same table structure as `v0.30.2-netlogo-comparison.md`, adding a new column "Post-Arc D" showing the new Python values and the residual delta. If the outmigrant total improved by ≥2× call the architecture fix successful; if not, re-read Task 3 (the Numba batch path may not have written `best_habitat_fitness` for all fish).

Document the remaining gap and point to growth-calibration as the next arc (Arc E, future session).

- [ ] **Step 3: Update CHANGELOG**

Add an entry under `## [Unreleased]` (or the next version):

```markdown
### Changed
- **Migration architecture (Arc D)**: Migration decisions now compare
  `migration_fitness` against a per-tick `best_habitat_fitness` computed
  as `(daily_survival * mean_starv_survival)^time_horizon` (matching
  NetLogo InSALMO 7.3 `fitness-for`), replacing the scale-inconsistent
  `fitness_memory` EMA comparator. FRY→PARR promotion is now continuous
  (length ≥ parr_promotion_length OR age ≥ 1) instead of Jan-1-only.
  Default `outmigration_min_length` lowered 8.0→4.0 cm. Reduces Python
  outmigrant deficit against the cached NetLogo example_a reference
  from 21× to [N×, filled in from Task 2 output].
```

- [ ] **Step 4: Commit**

```bash
git add docs/validation/v0.31.0-arc-D-netlogo-comparison.md CHANGELOG.md
git commit -m "docs: report Arc D migration rewrite parity improvement"
```

---

## Self-Review (completed 2026-04-19)

**1. Spec coverage:**
- (a) `migration_fitness` habitat context → Tasks 1-3 (per-tick expected_fitness + best_habitat_fitness recording + comparator swap in Task 5). ✅
- (b) FRY→PARR annual gate → Task 4 (continuous promotion). ✅
- (c) `fitness_memory` vs `migration_fitness` scale mismatch → Task 5 (switch comparator). ✅
- (d) Growth calibration (#1) → **explicitly out of scope**, flagged in Arc E. ✅
- (e) Supplementary outmigration path (`outmigration_min_length` default) → Task 7. ✅

**2. Placeholder scan:** One skip in Task 6 (non-anadromous fixture) with explicit justification (existing test in `tests/test_non_anadromous.py` covers it). All other steps have concrete code or exact file paths.

**3. Type consistency:**
- `best_habitat_fitness`: `np.float64[n]` declared Task 2, read Task 3, written Task 3, consumed Task 5. Consistent.
- `expected_fitness`: same signature in Task 1 reference impl and Task 3 Numba duplicate. Consistent.
- `parr_promotion_length`: added Task 4, default 4.0 float, read via `getattr(..., default=4.0)` for backward compat. Consistent.
- `should_migrate` signature: unchanged; only docstring updated. Backward compatible.

**4. Success criteria:**
- Unit tests (Tasks 1-7) all green.
- `test_run_level_parity.py::TestExampleARunVsNetLogo` outmigrant_total metric improves by ≥2×. Full closure requires Arc E (growth calibration), documented as known limitation.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-04-19-arc-D-migration-rewrite.md`.

Per project CLAUDE.md (non-interactive, automated workflow), execute inline via `superpowers:executing-plans` when ready — do not pause for approval. Recommended order: Tasks 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Tasks 1, 2, 4, 7 are independent and could be parallelized via `superpowers:dispatching-parallel-agents`, but Tasks 3, 5, 6, 8 form a serial chain.
