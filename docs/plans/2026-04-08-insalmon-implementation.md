# inSALMON Implementation Plan (v2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand inSTREAM-py into inSALMON in two milestones: (1) inSALMO parity — freshwater anadromous features testable against NetLogo 7.4 reference data, then (2) novel marine lifecycle extension.

**Architecture:** Domain-dispatched step — `FreshwaterDomain` and `MarineDomain` share a single `TroutState` SoA. A `LifeStage` IntEnum replaces all magic numbers.

**Tech Stack:** Python 3.11+, Mesa, NumPy, Pydantic v2, SciPy, pytest, hypothesis

**Design doc:** `docs/plans/2026-04-08-insalmon-design.md`

**Test command:** `micromamba run -n shiny python -m pytest tests/ -v --tb=short`

**Project root:** `C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py`

---

## Milestone Overview

| Milestone | Phases | What it delivers | Validation |
|-----------|--------|-----------------|------------|
| **M1: inSALMO parity** | 1-3 | Freshwater anadromous salmon features matching inSALMO 7.4 | NetLogo reference data via `@netlogo-oracle` skill |
| **M2: Marine extension** | 4-8 | Full Baltic lifecycle with ocean phases, fishing, environmental coupling | ICES WGBAST empirical targets |

**M1 must be complete and validated before starting M2.**

---

# MILESTONE 1: inSALMO PARITY

## Phase 1: Foundation

### Task 1: LifeStage IntEnum

**Files:**
- Create: `src/instream/agents/life_stage.py`
- Test: `tests/test_life_stage.py`

**Step 1: Write the failing test**

```python
# tests/test_life_stage.py
from instream.agents.life_stage import LifeStage

def test_life_stage_values():
    assert LifeStage.FRY == 0
    assert LifeStage.PARR == 1
    assert LifeStage.SPAWNER == 2
    assert LifeStage.SMOLT == 3
    assert LifeStage.OCEAN_JUVENILE == 4
    assert LifeStage.OCEAN_ADULT == 5
    assert LifeStage.RETURNING_ADULT == 6

def test_life_stage_domain_helpers():
    assert LifeStage.FRY.is_freshwater
    assert LifeStage.PARR.is_freshwater
    assert LifeStage.SPAWNER.is_freshwater
    assert LifeStage.RETURNING_ADULT.is_freshwater
    assert LifeStage.SMOLT.is_marine
    assert LifeStage.OCEAN_JUVENILE.is_marine
    assert LifeStage.OCEAN_ADULT.is_marine
```

**Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_life_stage.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# src/instream/agents/life_stage.py
"""LifeStage enum for all salmon life history stages."""
from enum import IntEnum

class LifeStage(IntEnum):
    FRY = 0              # freshwater: post-emergence juvenile / resident
    PARR = 1             # freshwater: anadromous juvenile, pre-smolt
    SPAWNER = 2          # freshwater: active spawner
    SMOLT = 3            # marine: estuary transition
    OCEAN_JUVENILE = 4   # marine: open Baltic feeding
    OCEAN_ADULT = 5      # marine: mature, pre-return
    RETURNING_ADULT = 6  # freshwater: migrating upstream

    @property
    def is_freshwater(self) -> bool:
        return self in (LifeStage.FRY, LifeStage.PARR,
                        LifeStage.SPAWNER, LifeStage.RETURNING_ADULT)

    @property
    def is_marine(self) -> bool:
        return self in (LifeStage.SMOLT, LifeStage.OCEAN_JUVENILE,
                        LifeStage.OCEAN_ADULT)
```

**Step 4: Run test to verify it passes**

Run: `micromamba run -n shiny python -m pytest tests/test_life_stage.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/instream/agents/life_stage.py tests/test_life_stage.py
git commit -m "feat: add LifeStage IntEnum for salmon lifecycle stages"
```

---

### Task 2: Replace magic numbers with LifeStage across codebase

**Files:**
- Modify: `src/instream/model.py` (lines ~750, ~1184, ~1325)
- Modify: `src/instream/modules/migration.py` (line 24)
- Modify: `src/instream/modules/spawning.py`
- Modify: `app/simulation.py` (line ~399, `_LIFE_HISTORY_COLORS`)

**Step 1: Run existing tests as baseline**

Run: `micromamba run -n shiny python -m pytest tests/ -v --tb=short -q`
Expected: All existing tests PASS. Record the count.

**Step 2: Replace magic numbers in model.py**

Add `from instream.agents.life_stage import LifeStage` to imports.

- `life_history[i] == 2` (post-spawn death, ~line 750) -> `life_history[i] == LifeStage.SPAWNER`
- `life_history != 1` in migration check -> `life_history != LifeStage.PARR`
- `lh_val = 2` in `_do_adult_arrivals` (~line 1325) -> `lh_val = int(LifeStage.SPAWNER)`

**Transitional behavior note:** During M1, adult arrivals are assigned SPAWNER (2)
directly — there is no upstream migration phase yet. This matches the CURRENT
inSTREAM behavior (adults arrive, spawn, die) and is correct for inSALMO parity.
The RETURNING_ADULT (6) -> upstream migration -> SPAWNER transition is a marine
extension feature added in M2 Task 17. M1 tests should NOT validate upstream
migration behavior — that is an M2 concern.

**Step 3: Replace in migration.py**

- `if life_history != 1:` -> `if life_history != LifeStage.PARR:`
- Add import

**Step 4: Replace in spawning.py**

Search for hardcoded `life_history = 0` or `= 2` and replace with LifeStage. Add import.

**Step 5: Extend app/simulation.py colors**

```python
_LIFE_HISTORY_COLORS = {
    0: [65, 105, 225],    # FRY: royal blue
    1: [34, 139, 34],     # PARR: forest green
    2: [220, 20, 60],     # SPAWNER: crimson
    3: [0, 206, 209],     # SMOLT: dark turquoise
    4: [0, 0, 139],       # OCEAN_JUVENILE: dark blue
    5: [25, 25, 112],     # OCEAN_ADULT: midnight blue
    6: [255, 140, 0],     # RETURNING_ADULT: dark orange
}
```

**Step 6: Run all existing tests**

Run: `micromamba run -n shiny python -m pytest tests/ -v --tb=short -q`
Expected: Same pass count as Step 1. Zero regressions.

**Step 7: Commit**

```bash
git add -u
git commit -m "refactor: replace life_history magic numbers with LifeStage enum"
```

---

## Phase 2: inSALMO Freshwater Features

These tasks close the 7 gaps between inSTREAM-py and inSALMO 7.4 (Railsback 2021).
Reference: https://www.humboldt.edu/sites/default/files/ecological-modeling/2024-09/insalmo-72description2021-05-06.pdf

### Task 3: Adult holding behavior (zero food intake)

**Gap:** inSALMO spawner adults don't feed — they select habitat purely for low predation risk and low energy cost. Current inSTREAM-py treats spawners like any other fish.

**Files:**
- Modify: `src/instream/modules/behavior.py`
- Modify: `src/instream/model.py` (habitat selection section, ~line 608)
- Test: `tests/test_adult_holding.py`

**Step 1: Write the failing test**

```python
# tests/test_adult_holding.py
import numpy as np
from instream.agents.life_stage import LifeStage

def test_spawner_consumption_is_zero():
    """Anadromous spawners should have zero food intake."""
    # Setup: fish with life_history=SPAWNER
    # After habitat selection, consumption_memory should remain 0
    # This tests that the behavior module skips food intake for spawners.
    from instream.modules.behavior import should_skip_feeding
    assert should_skip_feeding(int(LifeStage.SPAWNER), is_anadromous=True)
    assert not should_skip_feeding(int(LifeStage.SPAWNER), is_anadromous=False)
    assert not should_skip_feeding(int(LifeStage.FRY), is_anadromous=True)
    assert not should_skip_feeding(int(LifeStage.PARR), is_anadromous=True)
```

**Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_adult_holding.py -v`
Expected: FAIL — ImportError (should_skip_feeding not found)

**Step 3: Add `should_skip_feeding` to behavior.py**

```python
def should_skip_feeding(life_history, *, is_anadromous):
    """Anadromous spawners do not feed (inSALMO behavior)."""
    from instream.agents.life_stage import LifeStage
    return life_history == LifeStage.SPAWNER and is_anadromous
```

**Step 4: Wire into model.py habitat selection**

**IMPORTANT:** Simply zeroing `consumption_memory` post-hoc is NOT sufficient.
The habitat selection loop in `behavior.py` (`select_habitat_and_activity`,
~line 1068-1113) depletes shared cell resources (drift food, search food) 
immediately when a fish "eats." If a spawner enters this loop normally, it 
depletes food that downstream fish need, even though the spawner doesn't use it.

The correct fix is to EXCLUDE spawners from `select_habitat_and_activity` entirely.
Pre-assigning `activity=2` does NOT work because `select_habitat_and_activity`
unconditionally overwrites `trout_state.activity[i]` for every fish it processes
(behavior.py line 1061). The function also depletes shared resources (drift/search
food) during the loop.

**Implementation approach:** Add a `skip_indices` set parameter to
`select_habitat_and_activity`:

```python
# In behavior.py, modify select_habitat_and_activity signature:
def select_habitat_and_activity(trout_state, ..., skip_indices=None):
    ...
    for rank, i in enumerate(alive_sorted):
        if skip_indices and i in skip_indices:
            continue  # spawner — don't evaluate, don't deplete
        ...
```

In model.py, before calling `select_habitat_and_activity`, build the skip set:

```python
# Identify anadromous spawners to skip (inSALMO: zero food intake)
from instream.modules.behavior import should_skip_feeding
skip_spawners = set()
for i in alive:
    sp = int(self.trout_state.species_idx[i])
    is_anad = getattr(self.config.species[self.species_order[sp]], "is_anadromous", False)
    if should_skip_feeding(int(self.trout_state.life_history[i]), is_anadromous=is_anad):
        skip_spawners.add(int(i))
        self.trout_state.activity[i] = 2  # hide
        self.trout_state.consumption_memory[i, substep] = 0.0

# Pass skip set to habitat selection
select_habitat_and_activity(self.trout_state, ..., skip_indices=skip_spawners)
```

This ensures spawners: (a) don't enter the evaluation loop, (b) don't deplete
shared drift/search food, (c) get activity=2 (hide) which only uses hiding places,
(d) have zero consumption memory for growth calculations.

**Step 5: Run all tests, commit**

Run: `micromamba run -n shiny python -m pytest tests/ -v --tb=short -q`
Expected: All pass.

```bash
git add src/instream/modules/behavior.py src/instream/model.py tests/test_adult_holding.py
git commit -m "feat: anadromous spawners skip feeding (inSALMO adult holding behavior)"
```

---

### Task 4: Two-piece condition-survival function

**Gap:** inSALMO uses a broken-stick starvation function: survival drops sharply below condition ~0.8 (vs inSTREAM's single linear relation). This makes post-spawning adults die quickly from condition loss.

**Files:**
- Modify: `src/instream/modules/survival.py`
- Test: `tests/test_condition_survival.py`

**Step 1: Write the failing test**

```python
# tests/test_condition_survival.py
import numpy as np
from instream.modules.survival import survival_condition_two_piece

def test_two_piece_sharp_drop_below_breakpoint():
    """Below breakpoint, survival drops much faster."""
    conditions = np.array([1.0, 0.8, 0.6, 0.4, 0.2])
    surv = survival_condition_two_piece(
        conditions, breakpoint=0.8,
        S_above_K8=0.99, S_below_K5=0.5, K5=0.5,
    )
    assert surv[0] > 0.95, "Good condition = high survival"
    assert surv[2] < surv[1], "Below breakpoint = sharper drop"
    # The slope below breakpoint should be steeper
    drop_above = surv[0] - surv[1]  # 1.0->0.8
    drop_below = surv[1] - surv[3]  # 0.8->0.4
    assert drop_below > drop_above * 2, "Below breakpoint much steeper"

def test_two_piece_identical_at_breakpoint():
    conditions = np.array([0.8])
    surv = survival_condition_two_piece(
        conditions, breakpoint=0.8,
        S_above_K8=0.99, S_below_K5=0.5, K5=0.5,
    )
    assert abs(surv[0] - 0.99) < 0.01
```

**Step 2: Run test, fails. Step 3: Implement**

```python
# Add to src/instream/modules/survival.py
def survival_condition_two_piece(conditions, *, breakpoint, S_above_K8, S_below_K5, K5):
    """Two-piece condition survival (inSALMO broken-stick).

    Above breakpoint: gentle linear decline from 1.0 to S_above_K8.
    Below breakpoint: steep linear decline from S_above_K8 to S_below_K5 at K5.
    """
    surv = np.ones_like(conditions)
    # Above breakpoint
    above = conditions >= breakpoint
    surv[above] = S_above_K8 + (1.0 - S_above_K8) * (
        (conditions[above] - breakpoint) / (1.5 - breakpoint))

    # Below breakpoint
    below = conditions < breakpoint
    slope_below = (S_above_K8 - S_below_K5) / (breakpoint - K5)
    surv[below] = S_above_K8 - slope_below * (breakpoint - conditions[below])
    surv = np.clip(surv, 0.0, 1.0)
    return surv
```

**Step 4: Wire into the codebase**

The existing `survival_condition` (scalar) is called from `fitness_for` in
`behavior.py` (line ~354) as `surv_cond_fn(condition, S_at_K5, S_at_K8)`.
This is threaded through `select_habitat_and_activity`.

Add `use_two_piece_condition: bool = False` to `SpeciesConfig` in `io/config.py`.

In `behavior.py`, where `surv_cond_fn` is assigned (~line 350), add:

```python
from instream.modules.survival import survival_condition, survival_condition_two_piece

if use_two_piece_condition:
    def surv_cond_fn(cond, S_K5, S_K8):
        return float(survival_condition_two_piece(
            np.array([cond]), breakpoint=S_K8_breakpoint,
            S_above_K8=S_K8, S_below_K5=S_K5, K5=0.5)[0])
else:
    surv_cond_fn = survival_condition  # existing scalar function
```

Thread `use_two_piece_condition` from the species config through
`select_habitat_and_activity` via the existing `**params` kwargs.

**Step 5: Run all tests, commit**

```bash
git add src/instream/modules/survival.py src/instream/modules/behavior.py src/instream/io/config.py tests/test_condition_survival.py
git commit -m "feat: add two-piece condition-survival function (inSALMO broken-stick)"
```

---

### Task 5: Stochastic outmigration probability

**Gap:** inSALMO uses daily stochastic outmigration (length-logistic probability) instead of inSTREAM's deterministic fitness comparison.

**Files:**
- Modify: `src/instream/modules/migration.py`
- Modify: `src/instream/model.py` (_do_migration)
- Test: `tests/test_stochastic_migration.py`

**Step 1: Write the failing test**

```python
# tests/test_stochastic_migration.py
import numpy as np
from instream.modules.migration import stochastic_should_migrate

def test_larger_fish_migrate_more():
    """Larger fish have higher daily outmigration probability."""
    rng = np.random.default_rng(42)
    n_trials = 10000
    small_count = sum(
        stochastic_should_migrate(10.0, L1=8.0, L9=15.0,
                                   life_history=1, rng=rng)
        for _ in range(n_trials))
    large_count = sum(
        stochastic_should_migrate(14.0, L1=8.0, L9=15.0,
                                   life_history=1, rng=rng)
        for _ in range(n_trials))
    assert large_count > small_count * 2, "Larger fish migrate more"

def test_non_parr_never_migrate():
    rng = np.random.default_rng(42)
    assert not stochastic_should_migrate(
        20.0, L1=8.0, L9=15.0, life_history=0, rng=rng)
```

**Step 2: Run test, fails. Step 3: Add to migration.py**

```python
def stochastic_should_migrate(length, L1, L9, life_history, rng):
    """inSALMO-style daily stochastic outmigration probability."""
    from instream.agents.life_stage import LifeStage
    if life_history != LifeStage.PARR:
        return False
    prob = evaluate_logistic(length, L1, L9)
    return rng.random() < prob
```

**Step 4: Add config flag and wire into model.py**

Add `use_stochastic_migration: bool = False` to `SpeciesConfig` in `io/config.py`.

In `model.py` `_do_migration` (~line 1172), replace the deterministic path with
a config-gated branch. The full updated `_do_migration` body:

```python
def _do_migration(self):
    from instream.modules.migration import (
        migration_fitness, should_migrate, stochastic_should_migrate,
        migrate_fish_downstream,
    )
    sp_mig_L1 = self._sp_arrays["migrate_fitness_L1"]
    sp_mig_L9 = self._sp_arrays["migrate_fitness_L9"]
    alive = self.trout_state.alive_indices()

    for i in alive:
        lh = int(self.trout_state.life_history[i])
        if lh != LifeStage.PARR:
            continue
        sp_idx = int(self.trout_state.species_idx[i])
        sp_name = self.species_order[sp_idx]
        sp_cfg = self.config.species[sp_name]

        if getattr(sp_cfg, "use_stochastic_migration", False):
            # inSALMO-style: daily stochastic probability
            do_migrate = stochastic_should_migrate(
                float(self.trout_state.length[i]),
                float(sp_mig_L1[sp_idx]), float(sp_mig_L9[sp_idx]),
                lh, self.rng)
        else:
            # inSTREAM-style: deterministic fitness comparison
            mig_fit = migration_fitness(
                float(self.trout_state.length[i]),
                float(sp_mig_L1[sp_idx]), float(sp_mig_L9[sp_idx]))
            best_hab = float(self.trout_state.fitness_memory[i])
            do_migrate = should_migrate(mig_fit, best_hab, lh)

        if do_migrate:
            out = migrate_fish_downstream(self.trout_state, i, self._reach_graph)
            self._outmigrants.extend(out)
```

**Step 5: Run all tests, commit**

```bash
git add src/instream/modules/migration.py src/instream/model.py tests/test_stochastic_migration.py
git commit -m "feat: add stochastic outmigration probability (inSALMO style, opt-in)"
```

---

### Task 6: Outmigrant date recording (virtual screw trap)

**Gap:** inSALMO tracks date of each outmigrant for virtual screw-trap output. Current code only tracks species/length/reach.

**Files:**
- Modify: `src/instream/modules/migration.py` (migrate_fish_downstream)
- Modify: `src/instream/model.py` (_do_migration, outmigrant collection)
- Test: `tests/test_outmigrant_dates.py`

**Step 1: Write the failing test**

```python
# tests/test_outmigrant_dates.py
from datetime import date

def test_outmigrant_record_has_date():
    """Outmigrant records should include the date of emigration."""
    from instream.modules.migration import migrate_fish_downstream
    from instream.state.trout_state import TroutState

    ts = TroutState.zeros(1)
    ts.alive[0] = True
    ts.life_history[0] = 1
    ts.reach_idx[0] = 0
    ts.length[0] = 15.0
    ts.species_idx[0] = 0

    reach_graph = {0: []}
    outmigrants = migrate_fish_downstream(ts, 0, reach_graph,
                                           current_date=date(2025, 5, 15))
    assert len(outmigrants) == 1
    assert outmigrants[0]["date"] == date(2025, 5, 15)
    assert outmigrants[0]["day_of_year"] == 135
```

**Step 2: Run test, fails. Step 3: Add `current_date` parameter to migrate_fish_downstream**

Add `current_date=None` kwarg. When provided, include `"date"` and `"day_of_year"` in outmigrant dict.

**Step 4: Update model.py caller to pass current date**

**Step 5: Run all tests, commit**

```bash
git add src/instream/modules/migration.py src/instream/model.py tests/test_outmigrant_dates.py
git commit -m "feat: record outmigrant date for virtual screw-trap output (inSALMO)"
```

---

### Task 7: Stochastic spawn-cell perturbation

**Gap:** inSALMO adds noise (~0.15) to spawn cell quality scores to prevent unrealistic redd clustering.

**Files:**
- Modify: `src/instream/modules/spawning.py` (select_spawn_cell)
- Test: `tests/test_spawn_perturbation.py`

**Step 1: Write the failing test**

```python
# tests/test_spawn_perturbation.py
import numpy as np

def test_spawn_cell_selection_varies_with_noise():
    """With perturbation, different fish may select different cells."""
    from instream.modules.spawning import select_spawn_cell
    rng = np.random.default_rng(42)

    # Two cells with nearly identical suitability
    suitabilities = np.array([0.90, 0.89])
    cell_indices = np.array([0, 1])

    selections = [
        select_spawn_cell(suitabilities, cell_indices, rng=rng,
                          noise_sd=0.15)
        for _ in range(100)
    ]
    unique = set(selections)
    assert len(unique) > 1, "With noise, should sometimes pick cell 1"
```

**Step 2: Run test, fails. Step 3: Add `rng` and `noise_sd` parameters to select_spawn_cell**

Current signature (spawning.py:140):
```python
def select_spawn_cell(scores, candidates, redd_cells=None,
                       centroids_x=None, centroids_y=None, defense_area=0.0):
```

Add `rng=None, noise_sd=0.0` as keyword args at the end. When `noise_sd > 0`
and `rng is not None`, add `rng.normal(0, noise_sd, len(scores))` to scores
before selecting max. Default `noise_sd=0.0` and `rng=None` ensures ALL existing
callers work unchanged without any modification.

**Step 4: Add config parameter `spawn_cell_noise: 0.15` to SpeciesConfig (default 0.0)**

**Step 5: Run all tests, commit**

```bash
git add src/instream/modules/spawning.py tests/test_spawn_perturbation.py
git commit -m "feat: add stochastic spawn-cell perturbation (inSALMO noise term)"
```

---

### Task 8: Modified growth fitness term

**Gap:** inSALMO uses `ln(1 + expectedLength/biggestLength)` to encourage growth across all sizes.

**Files:**
- Modify: `src/instream/modules/behavior.py`
- Test: `tests/test_growth_fitness.py`

**Step 1: Write the failing test**

```python
# tests/test_growth_fitness.py
import math
from instream.modules.behavior import insalmo_growth_fitness

def test_growth_fitness_encourages_small_fish():
    """Small fish relative to biggest should still get meaningful fitness."""
    small = insalmo_growth_fitness(expected_length=5.0, biggest_length=30.0)
    big = insalmo_growth_fitness(expected_length=25.0, biggest_length=30.0)
    assert small > 0, "Small fish get positive fitness"
    assert big > small, "Bigger expected length = higher fitness"
    assert big < 1.0, "Bounded below ln(2)"

def test_growth_fitness_formula():
    result = insalmo_growth_fitness(expected_length=10.0, biggest_length=20.0)
    expected = math.log(1 + 10.0 / 20.0)
    assert abs(result - expected) < 1e-10
```

**Step 2: Run test, fails. Step 3: Implement**

```python
# Add to behavior.py
def insalmo_growth_fitness(expected_length, biggest_length):
    """inSALMO growth fitness: ln(1 + expectedLength/biggestLength)."""
    if biggest_length <= 0:
        return 0.0
    return math.log(1.0 + expected_length / biggest_length)
```

**Step 4: Add config flag `use_insalmo_growth_fitness: true` for opt-in. Wire into habitat selection.**

**Step 5: Run all tests, commit**

```bash
git add src/instream/modules/behavior.py tests/test_growth_fitness.py
git commit -m "feat: add inSALMO growth fitness term ln(1+L/Lmax)"
```

---

## Phase 3: inSALMO Validation Gate

### Task 9: inSALMO parity validation test suite

**Files:**
- Create: `tests/test_insalmo_parity.py`

Use the `@netlogo-oracle` skill to generate NetLogo 7.4 reference data for:
- Outmigrant size distribution (given identical initial populations and environmental inputs)
- Outmigrant timing (day-of-year histogram)
- Post-spawn mortality rate for anadromous adults
- Redd-to-outmigrant survival rate

**Step 1: Write validation tests**

```python
# tests/test_insalmo_parity.py
"""Validate inSTREAM-py anadromous behavior against inSALMO 7.4 reference data."""
import pytest
import numpy as np

@pytest.mark.slow
def test_outmigrant_size_distribution():
    """Outmigrant mean length should be within 10% of NetLogo reference."""
    # TODO: generate reference data with @netlogo-oracle skill
    # Run inSTREAM-py with matching config
    # Compare outmigrant mean length, SD, and count
    pass

@pytest.mark.slow
def test_outmigrant_timing():
    """Peak outmigration should fall within same 2-week window as NetLogo."""
    pass

@pytest.mark.slow
def test_spawner_mortality_rate():
    """All anadromous spawners should die post-spawn (no zero-food survivors)."""
    pass

@pytest.mark.slow
def test_spawn_cell_dispersion():
    """With perturbation, redds should be more dispersed than without."""
    pass
```

**Step 2: Use @netlogo-oracle to fill in reference values**

**Step 3: Run and iterate until tests pass**

**Step 4: Commit**

```bash
git add tests/test_insalmo_parity.py
git commit -m "test: inSALMO parity validation suite"
```

**GATE: All inSALMO parity tests must pass before proceeding to Milestone 2.**

---

# MILESTONE 2: MARINE EXTENSION

## Phase 4: Marine State & Config

### Task 10: Extend TroutState with marine fields

**Files:**
- Modify: `src/instream/state/trout_state.py`
- Test: `tests/test_trout_state_marine.py`

**Step 1: Write the failing test**

```python
# tests/test_trout_state_marine.py
import numpy as np
from instream.state.trout_state import TroutState

def test_trout_state_has_marine_fields():
    ts = TroutState.zeros(10)
    assert ts.zone_idx.shape == (10,)
    assert ts.zone_idx.dtype == np.int32
    assert np.all(ts.zone_idx == -1)
    assert ts.sea_winters.shape == (10,)
    assert np.all(ts.sea_winters == 0)
    assert ts.smolt_date.shape == (10,)
    assert ts.natal_reach_idx.shape == (10,)
    assert np.all(ts.natal_reach_idx == -1)
    assert ts.smolt_readiness.shape == (10,)
```

**Step 2: Add 5 fields to TroutState dataclass and zeros() classmethod**

```python
zone_idx=np.full(capacity, -1, dtype=np.int32),
sea_winters=np.zeros(capacity, dtype=np.int32),
smolt_date=np.zeros(capacity, dtype=np.int32),
natal_reach_idx=np.full(capacity, -1, dtype=np.int32),
smolt_readiness=np.zeros(capacity, dtype=np.float64),
```

**Step 3: Run ALL tests for regression, commit**

```bash
git add src/instream/state/trout_state.py tests/test_trout_state_marine.py
git commit -m "feat: add marine state fields to TroutState"
```

---

### Task 11: ZoneState + MarineConfig + config loader

**Files:**
- Create: `src/instream/state/zone_state.py`
- Modify: `src/instream/io/config.py` (add MarineConfig, ZoneConfig, GearConfig; add `marine` to ModelConfig; add `is_river_mouth` to ReachConfig)
- Test: `tests/test_zone_state.py`, `tests/test_marine_config.py`

Combine previous Tasks 4 and 5 from v1 plan. See v1 for full test/implementation code.

**Key fix from review:** `ModelConfig` uses Pydantic v2 default `extra='ignore'`, so the `marine` field MUST be explicitly added as `marine: Optional[MarineConfig] = None` — otherwise the YAML section is silently dropped.

**Step 1: Write tests, Step 2: Implement, Step 3: Run all tests, Step 4: Commit**

```bash
git add src/instream/state/zone_state.py src/instream/io/config.py tests/test_zone_state.py tests/test_marine_config.py
git commit -m "feat: add ZoneState, MarineConfig, and config loader update"
```

---

## Phase 5: Marine Modules

**IMPORTANT — bugs fixed from v1 review:**
- Use `evaluate_logistic_array` (not scalar `evaluate_logistic`) for numpy arrays
- CMax parameters corrected: A=0.303, B=-0.275 (Hanson et al. 1997, Fish Bioenergetics 3.0)
- Cormorant L1/L9 corrected: 15/40 (not 8/22) per Jepsen et al. 2019
- Vulnerability formula fixed: `np.power(combined, vuln)` not `np.power(combined, 1/vuln)`

### Task 12: Marine growth module

**Files:**
- Create: `src/instream/modules/marine_growth.py`
- Test: `tests/test_marine_growth.py`

**Step 1: Write the failing test**

```python
# tests/test_marine_growth.py
import numpy as np
from instream.modules.marine_growth import marine_growth_rate

def test_marine_growth_increases_weight():
    lengths = np.array([30.0, 50.0, 70.0])
    weights = np.array([300.0, 1500.0, 4000.0])
    temperatures = np.array([10.0, 10.0, 10.0])
    prey_indices = np.array([0.8, 0.8, 0.8])
    conditions = np.array([1.0, 1.0, 1.0])

    growth = marine_growth_rate(
        lengths, weights, temperatures, prey_indices, conditions,
        cmax_A=0.303, cmax_B=-0.275, growth_efficiency=0.50,
        resp_A=0.03, resp_B=-0.25, temp_opt=12.0, temp_max=24.0,
    )
    assert growth.shape == (3,)
    assert np.all(growth > 0)

def test_marine_growth_zero_prey():
    lengths = np.array([50.0])
    weights = np.array([1500.0])
    temperatures = np.array([10.0])
    prey_indices = np.array([0.0])
    conditions = np.array([1.0])

    growth = marine_growth_rate(
        lengths, weights, temperatures, prey_indices, conditions,
        cmax_A=0.303, cmax_B=-0.275, growth_efficiency=0.50,
        resp_A=0.03, resp_B=-0.25, temp_opt=12.0, temp_max=24.0,
    )
    assert np.all(growth < 0), "No prey means weight loss"

def test_marine_growth_temperature_optimum():
    """Growth should be highest near temp_opt."""
    weights = np.array([1500.0, 1500.0, 1500.0])
    lengths = np.array([50.0, 50.0, 50.0])
    temps = np.array([5.0, 12.0, 22.0])
    prey = np.array([0.8, 0.8, 0.8])
    cond = np.array([1.0, 1.0, 1.0])

    growth = marine_growth_rate(
        lengths, weights, temps, prey, cond,
        cmax_A=0.303, cmax_B=-0.275, growth_efficiency=0.50,
        resp_A=0.03, resp_B=-0.25, temp_opt=12.0, temp_max=24.0,
    )
    assert growth[1] > growth[0], "Optimum > cold"
    assert growth[1] > growth[2], "Optimum > warm"

def test_marine_growth_zero_at_freezing():
    """Growth should be near zero at 0°C (cold-water cutoff)."""
    weights = np.array([1500.0])
    lengths = np.array([50.0])
    temps = np.array([0.5])  # below temp_min=1.0
    prey = np.array([0.8])
    cond = np.array([1.0])

    growth = marine_growth_rate(
        lengths, weights, temps, prey, cond,
        cmax_A=0.303, cmax_B=-0.275, growth_efficiency=0.50,
        resp_A=0.03, resp_B=-0.25, temp_opt=12.0, temp_max=24.0,
    )
    assert growth[0] <= 0, "No positive growth near freezing"
```

**Step 2: Run test, fails. Step 3: Implement**

```python
# src/instream/modules/marine_growth.py
"""Marine growth — simplified bioenergetics for ocean phase.

Parameters from Hanson et al. (1997) Fish Bioenergetics 3.0,
adapted for Atlantic salmon. Uses Thornton-Lessem style
temperature function.
"""
import numpy as np

def _temp_dependence(temperatures, temp_opt, temp_max, temp_min=1.0):
    """Temperature dependence for consumption (modified O'Neill 1986 form).

    Returns fraction 0-1, peaking at temp_opt, zero at temp_max and temp_min.
    Uses separate rising and falling limbs to handle cold-water cutoff.

    Rising limb (temp_min to temp_opt): linear ramp, zero below temp_min.
    Falling limb (temp_opt to temp_max): O'Neill form V^X * exp(X*(1-V)).

    The cold-water cutoff prevents unrealistic consumption at 0-1°C.
    Atlantic salmon consumption approaches zero below ~1°C (Elliott 1976).
    """
    x = np.asarray(temperatures, dtype=np.float64)
    frac = np.zeros_like(x)

    # Rising limb: linear from temp_min to temp_opt
    rising = (x >= temp_min) & (x <= temp_opt)
    if temp_opt > temp_min:
        frac[rising] = (x[rising] - temp_min) / (temp_opt - temp_min)

    # Falling limb: O'Neill form from temp_opt to temp_max
    falling = (x > temp_opt) & (x < temp_max)
    V = (temp_max - x[falling]) / (temp_max - temp_opt)
    X = 2.0  # shape parameter for salmonids
    frac[falling] = np.power(V, X) * np.exp(X * (1.0 - V))

    # Below temp_min or above temp_max: already zero
    return np.clip(frac, 0, 1)

def marine_growth_rate(
    lengths, weights, temperatures, prey_indices, conditions,
    *, cmax_A, cmax_B, growth_efficiency, resp_A, resp_B,
    temp_opt, temp_max,
):
    """Daily weight change (grams) for marine fish.

    CMax parameters: A=0.303, B=-0.275 (Hanson et al. 1997)
    """
    # CMax: allometric * temperature function
    cmax_wt = cmax_A * np.power(weights, cmax_B)
    temp_frac = _temp_dependence(temperatures, temp_opt, temp_max)
    cmax = cmax_wt * temp_frac * weights  # grams/day

    consumption = cmax * prey_indices * np.clip(conditions, 0.1, 1.5)

    # Respiration: allometric * temperature
    resp_wt = resp_A * np.power(weights, resp_B)
    resp = resp_wt * temperatures * weights / temp_opt

    daily_growth = (consumption - resp) * growth_efficiency
    return daily_growth
```

**Step 4: Run test, commit**

```bash
git add src/instream/modules/marine_growth.py tests/test_marine_growth.py
git commit -m "feat: add marine growth module (Hanson et al. bioenergetics)"
```

---

### Task 13: Marine survival module (7 mortality sources)

**Files:**
- Create: `src/instream/modules/marine_survival.py`
- Test: `tests/test_marine_survival.py`

**CRITICAL FIX from v1:** Use `evaluate_logistic_array` not `evaluate_logistic`. Fix vulnerability formula: `np.power(combined, vuln)` not `1/vuln`. Cormorant L1=15, L9=40.

**Step 1: Write the failing test**

```python
# tests/test_marine_survival.py
import numpy as np
from instream.modules.marine_survival import (
    seal_predation, cormorant_predation, background_mortality,
    temperature_mortality, m74_mortality, post_smolt_vulnerability,
    combined_marine_survival,
)

def test_seal_predation_increases_with_size():
    lengths = np.array([30.0, 50.0, 70.0, 90.0])
    surv = seal_predation(lengths, L1=40.0, L9=80.0)
    assert np.all((surv >= 0) & (surv <= 1))
    assert surv[0] > surv[-1]

def test_cormorant_targets_small_fish_in_estuary():
    lengths = np.array([12.0, 20.0, 35.0, 60.0])
    zones = np.array([0, 0, 0, 0])
    surv = cormorant_predation(lengths, zones, L1=15.0, L9=40.0,
                                active_zones=[0, 1], max_daily_rate=0.03)
    assert surv[0] < surv[-1], "Small fish more vulnerable"
    # Verify realistic daily mortality rates (1-3% for small smolts)
    assert surv[0] > 0.95, "Daily survival should be >95% even for smallest"
    assert surv[0] < 1.0, "Some mortality expected"

def test_cormorant_inactive_offshore():
    lengths = np.array([12.0])
    zones = np.array([3])  # central baltic
    surv = cormorant_predation(lengths, zones, L1=15.0, L9=40.0,
                                active_zones=[0, 1])
    assert surv[0] == 1.0

def test_vulnerability_amplifies_mortality():
    """Post-smolt vulnerability should LOWER survival (not raise it)."""
    base_survival = np.array([0.95])
    vuln_new = post_smolt_vulnerability(np.array([1]), window=30)  # day 1
    vuln_old = post_smolt_vulnerability(np.array([60]), window=30)  # day 60
    assert vuln_new > vuln_old, "New smolts have higher vulnerability"
    # Applying: survival^vuln should be LOWER for new smolts
    surv_new = np.power(base_survival, vuln_new)
    surv_old = np.power(base_survival, vuln_old)
    assert surv_new[0] < surv_old[0], "New smolts have lower survival"

def test_combined_survival_in_range():
    lengths = np.array([50.0])
    weights = np.array([1500.0])
    conditions = np.array([1.0])
    temps = np.array([10.0])
    pred_risks = np.array([0.3])
    zones = np.array([0])
    days_ocean = np.array([5])
    rng = np.random.default_rng(42)

    surv = combined_marine_survival(
        lengths, weights, conditions, temps, pred_risks, zones,
        days_ocean, rng,
        seal_L1=40.0, seal_L9=80.0,
        cormorant_L1=15.0, cormorant_L9=40.0, cormorant_zones=[0, 1],
        base_mort=0.001, temp_threshold=20.0,
        m74_prob=0.0, post_smolt_window=60,
    )
    assert 0 < surv[0] < 1
```

**Step 2: Run test, fails. Step 3: Implement**

```python
# src/instream/modules/marine_survival.py
"""Marine survival — 7 mortality sources for Baltic salmon.

Cormorant parameters: L1=15, L9=40 (Jepsen et al. 2019)
Seal parameters: L1=40, L9=80 (Lundstrom et al. 2010, Hansson et al. 2018)
"""
import numpy as np
from instream.modules.behavior import evaluate_logistic_array

def seal_predation(lengths, *, L1, L9, max_daily_rate=0.02):
    """Size-dependent seal predation. Larger fish -> higher risk.

    Scaled by max_daily_rate to produce realistic daily mortality.
    A 80cm fish gets: 0.02 * 0.9 = 1.8% daily mortality.
    A 40cm fish gets: 0.02 * 0.1 = 0.2% daily mortality.
    """
    size_vulnerability = evaluate_logistic_array(lengths, L1, L9)
    risk = max_daily_rate * size_vulnerability
    return 1.0 - risk

def cormorant_predation(lengths, zone_indices, *, L1, L9, active_zones,
                         max_daily_rate=0.03):
    """Cormorant predation on small post-smolts in estuary/coastal.

    Inverted logistic scaled by max_daily_rate to produce realistic
    daily mortality (1-3% population-level, Jepsen et al. 2019).
    Without scaling, the raw logistic gives ~94% daily mortality for
    12cm smolts, which is biologically implausible.

    Parameters
    ----------
    max_daily_rate : float
        Maximum daily mortality rate from cormorants (default 0.03 = 3%).
        A 12cm smolt gets: 0.03 * 0.94 = 2.8% daily mortality.
        A 40cm fish gets: 0.03 * 0.10 = 0.3% daily mortality.
    """
    size_vulnerability = 1.0 - evaluate_logistic_array(lengths, L1, L9)
    risk = max_daily_rate * size_vulnerability
    zone_mask = np.isin(zone_indices, active_zones)
    return np.where(zone_mask, 1.0 - risk, 1.0)

def background_mortality(n, *, daily_rate):
    return np.full(n, 1.0 - daily_rate)

def temperature_mortality(temperatures, *, threshold):
    excess = np.clip(temperatures - threshold, 0, None)
    return np.exp(-0.1 * excess)

def m74_mortality(n, *, prob, rng):
    if prob <= 0:
        return np.ones(n)
    return np.where(rng.random(n) < prob, 0.0, 1.0)

def post_smolt_vulnerability(days_since_ocean_entry, *, window):
    """Multiplier on mortality. >1 during first months at sea.
    Decays linearly from 2x to 1x over window days (default 60 days).
    Thorstad et al. 2012: critical period lasts 2-4 months."""
    return np.clip(2.0 - days_since_ocean_entry / window, 1.0, 2.0)

def combined_marine_survival(
    lengths, weights, conditions, temperatures, predation_risks,
    zone_indices, days_since_ocean_entry, rng,
    *, seal_L1, seal_L9, cormorant_L1, cormorant_L9, cormorant_zones,
    cormorant_max_daily_rate=0.03,
    base_mort, temp_threshold, m74_prob, post_smolt_window,
):
    """Combine 5 natural mortality sources. Fishing is separate."""
    n = len(lengths)
    s_seal = seal_predation(lengths, L1=seal_L1, L9=seal_L9)
    s_corm = cormorant_predation(lengths, zone_indices,
                                  L1=cormorant_L1, L9=cormorant_L9,
                                  active_zones=cormorant_zones,
                                  max_daily_rate=cormorant_max_daily_rate)
    s_back = background_mortality(n, daily_rate=base_mort)
    s_temp = temperature_mortality(temperatures, threshold=temp_threshold)
    s_m74 = m74_mortality(n, prob=m74_prob, rng=rng)

    vuln = post_smolt_vulnerability(days_since_ocean_entry,
                                     window=post_smolt_window)
    combined = s_seal * s_corm * s_back * s_temp * s_m74
    # vuln > 1 amplifies mortality: survival^2 < survival^1
    return np.power(combined, vuln)
```

**Step 4: Run test, commit**

```bash
git add src/instream/modules/marine_survival.py tests/test_marine_survival.py
git commit -m "feat: add marine survival with 7 mortality sources (corrected parameters)"
```

---

### Task 14: Marine fishing module

Same as v1 Task 8 — no bugs found. See v1 for full code.

```bash
git commit -m "feat: add marine fishing module with gear selectivity and bycatch"
```

---

### Task 15: Smoltification + maturation + zone migration

**Files:**
- Create: `src/instream/modules/smoltification.py`
- Create: `src/instream/modules/marine_migration.py`
- Test: `tests/test_smoltification.py`, `tests/test_marine_migration.py`

**Smoltification module:**

```python
# src/instream/modules/smoltification.py
"""Smoltification — photoperiod + temperature triggered transition."""
import numpy as np

def update_smolt_readiness(
    readiness, lengths, temperature, photoperiod,
    *, min_length, temp_min, temp_max, photoperiod_threshold, rate=0.02,
):
    """Update smolt readiness. Accumulates when conditions met.

    Default rate=0.02 requires ~50 qualifying days to reach readiness=1.0.
    This approximates ~350-400 degree-days at typical Baltic spring temps
    (7-8°C). For a more accurate model, use degree-day accumulation:
    rate = temperature / 400 per day (configurable via species params).

    Reference: Handeland et al. 1998 — smoltification timing in Atlantic salmon.
    """
    new = readiness.copy()
    eligible = (
        (lengths >= min_length)
        & (temperature >= temp_min)
        & (temperature <= temp_max)
        & (photoperiod >= photoperiod_threshold)
    )
    new[eligible] = np.clip(new[eligible] + rate, 0.0, 1.0)
    return new

def check_smolt_trigger(readiness, current_month, *,
                         window_start_month, window_end_month):
    """Return boolean mask of fish ready to smoltify.

    IMPORTANT: Smoltification only triggers within the seasonal window.
    Baltic salmon smolts emigrate April-June (months 4-6).
    Outside this window, readiness accumulates but does not trigger.
    """
    in_window = window_start_month <= current_month <= window_end_month
    if not in_window:
        return np.zeros(len(readiness), dtype=bool)
    return readiness >= 1.0
```

**Key test for date filtering:**

```python
def test_smolt_trigger_outside_window_blocked():
    readiness = np.array([1.0, 1.0])
    # January — outside April-June window
    triggers = check_smolt_trigger(readiness, current_month=1,
                                    window_start_month=4, window_end_month=6)
    assert not np.any(triggers), "No smoltification in January"

def test_smolt_trigger_inside_window():
    readiness = np.array([0.5, 1.0])
    triggers = check_smolt_trigger(readiness, current_month=5,
                                    window_start_month=4, window_end_month=6)
    assert not triggers[0], "Readiness < 1.0"
    assert triggers[1], "Readiness == 1.0 in May"
```

**Marine migration module** (maturation + zone movement):

```python
# src/instream/modules/marine_migration.py
"""Marine migration — zone-to-zone movement and maturation."""
import numpy as np

def check_maturation(
    lengths, conditions, sea_winters, rng,
    *, min_sea_winters, prob_by_sw, min_length, min_condition,
):
    """Return boolean mask of fish that should return to freshwater."""
    n = len(lengths)
    mature = np.zeros(n, dtype=bool)
    for i in range(n):
        sw = int(sea_winters[i])
        if sw < min_sea_winters:
            continue
        if lengths[i] < min_length or conditions[i] < min_condition:
            continue
        prob = prob_by_sw.get(sw, prob_by_sw.get(max(prob_by_sw.keys()), 0.99))
        if rng.random() < prob:
            mature[i] = True
    return mature

def seasonal_zone_movement(
    zone_indices, days_in_zone, current_month,
    *, zone_graph, max_residence,
):
    """Move fish to next zone when they exceed max residence time."""
    new_zones = zone_indices.copy()
    for i in range(len(zone_indices)):
        z = int(zone_indices[i])
        max_days = max_residence.get(z, 999999)
        if days_in_zone[i] > max_days:
            downstream = zone_graph.get(z, [])
            if downstream:
                new_zones[i] = downstream[0]
    return new_zones
```

```bash
git add src/instream/modules/smoltification.py src/instream/modules/marine_migration.py tests/test_smoltification.py tests/test_marine_migration.py
git commit -m "feat: add smoltification (with seasonal gating) and marine zone migration"
```

---

## Phase 6: Environmental Drivers

### Task 16: StaticDriver

Same as v1 Task 11 — no bugs found. See v1 for full code.

```bash
git commit -m "feat: add StaticDriver for marine zone environmental data"
```

---

## Phase 7: Domain Integration

### Task 17: MarineSpace + MarineDomain + migration.py modification

Combines v1 Tasks 12, 13, 14.

**Step 0: Create package __init__.py files**

```bash
mkdir -p src/instream/domains
touch src/instream/domains/__init__.py
mkdir -p src/instream/io/env_drivers
touch src/instream/io/env_drivers/__init__.py
```

These are required for `from instream.domains.marine import MarineDomain` and
`from instream.io.env_drivers.static_driver import StaticDriver` to resolve.

**CRITICAL FIX from review:** This task also updates `_do_adult_arrivals` in model.py:

**Step 1:** Modify `migrate_fish_downstream` to accept `is_anadromous` and `current_date` kwargs. Anadromous fish at river mouth: set `life_history=SMOLT`, `zone_idx=0`, `natal_reach_idx=current_reach`. Keep alive. Still record outmigrant with date.

**Step 2:** Update `_do_adult_arrivals` in model.py (~line 1325):
- Change `lh_val = int(LifeStage.SPAWNER)` to `lh_val = int(LifeStage.RETURNING_ADULT)`
- After assigning slot, reset marine fields:
```python
ts.zone_idx[slot] = -1
ts.sea_winters[slot] = 0
ts.smolt_date[slot] = 0
ts.natal_reach_idx[slot] = -1
ts.smolt_readiness[slot] = 0.0
```
This prevents stale marine state from a reused dead slot bleeding into the new fish.

**Step 3:** Add lifecycle transition: returning adults (life_history=6) arriving at natal reach become spawners (life_history=2) when spawning conditions are met.

**Step 3b:** Add `sea_winters` increment to `MarineDomain.daily_step`:

The design doc specifies sea_winters increments on the anniversary of `smolt_date`.
Without this, `sea_winters` stays 0 forever and `check_maturation` (which gates on
`min_sea_winters=1`) will never trigger — no fish will ever return.

Add this block inside `MarineDomain.daily_step`, after growth/survival, before
maturation check:

```python
# Increment sea_winters on anniversary of ocean entry
current_ordinal = current_date.toordinal()
for j, i in enumerate(idx):
    entry_ordinal = int(ts.smolt_date[i])
    if entry_ordinal > 0:
        days_at_sea = current_ordinal - entry_ordinal
        expected_sw = max(0, days_at_sea // 365)
        if expected_sw > ts.sea_winters[i]:
            ts.sea_winters[i] = expected_sw
```

Add a test that runs `daily_step` for 366 days and verifies `sea_winters`
increments from 0 to 1.

**Step 4:** Wire MarineDomain into model.py step():

```python
# After _do_migration (so smolts have transitioned)
# Before _do_adult_arrivals (so returning adults are freshwater)
if self.marine_domain is not None:
    self.marine_domain.update_environment(self.time_manager.current_date)
    self.marine_domain.daily_step(
        self.trout_state, self.time_manager.current_date, self.rng)
```

**Step 5: Run ALL tests, commit**

```bash
git commit -m "feat: wire MarineDomain into model, fix adult arrivals and slot reuse"
```

---

## Phase 8: End-to-End Validation

### Task 18: Full lifecycle integration test

Same as v1 Task 16 with corrected CMax parameters. See v1 for code.

```bash
git commit -m "test: full lifecycle integration test (parr -> ocean -> return)"
```

---

### Task 19: Regression + cleanup

**Step 1:** Run complete test suite: `micromamba run -n shiny python -m pytest tests/ -v --tb=short`
**Step 2:** Fix any failures
**Step 3:** Update CLAUDE.md with inSALMON architecture notes
**Step 4:** Commit

```bash
git commit -m "fix: regression fixes and CLAUDE.md update for inSALMON"
```

---

## Summary

| Phase | Tasks | Milestone | What it delivers |
|-------|-------|-----------|-----------------|
| 1: Foundation | 1-2 | M1 | LifeStage enum, magic number cleanup |
| 2: inSALMO features | 3-8 | M1 | Adult holding, condition survival, stochastic migration, outmigrant dates, spawn noise, growth fitness |
| 3: Validation gate | 9 | M1 | **inSALMO parity confirmed against NetLogo** |
| 4: Marine state | 10-11 | M2 | TroutState marine fields, ZoneState, MarineConfig |
| 5: Marine modules | 12-15 | M2 | Growth (corrected CMax), survival (7 sources), fishing, smoltification |
| 6: Drivers | 16 | M2 | StaticDriver for environmental data |
| 7: Integration | 17 | M2 | MarineDomain wiring, migration.py mod, adult arrival fix |
| 8: E2E validation | 18-19 | M2 | Full lifecycle test, regression suite |

**Total: 19 tasks across 2 milestones**

## Corrections from v1 applied

| Issue | Fix |
|-------|-----|
| Plan started with marine — no validation path | Restructured: M1 (inSALMO parity) before M2 (marine) |
| `evaluate_logistic` is scalar-only | Changed to `evaluate_logistic_array` in all marine modules |
| CMax A=0.628 not published | Corrected to A=0.303, B=-0.275 (Hanson et al. 1997) |
| Linear temp function not standard | Replaced with Thornton-Lessem style quadratic |
| Cormorant L1=8, L9=22 too small | Corrected to L1=15, L9=40 (Jepsen et al. 2019) |
| `combined^(1/vuln)` inverts mortality | Fixed to `combined^vuln` (amplifies mortality) |
| No task updates `_do_adult_arrivals` | Added to Task 17 with slot reset for marine fields |
| Missing 7 inSALMO freshwater features | Added Phase 2 (Tasks 3-8) |
| growth_efficiency=0.55 high | Adjusted to 0.50 (conservative) |
| Step ordering in model.py unspecified | Explicit: after _do_migration, before _do_adult_arrivals |

## References

- Hanson, P.C. et al. (1997). Fish Bioenergetics 3.0. University of Wisconsin Sea Grant.
- Deslauriers, D. et al. (2017). Fish Bioenergetics 4.0. Fisheries 42(11):586-596.
- Jepsen, N. et al. (2019). Cormorant predation on PIT-tagged stream-dwelling trout. Fisheries Management and Ecology 26(3):198-207.
- Lundstrom, K. et al. (2010). Grey seal diet composition in the Bothnian Sea. Fisheries Research 107(1-3):292-300.
- Hansson, S. et al. (2018). Competition for the fish. ICES JMS 76(1):284-293.
- Thorstad, E.B. et al. (2012). Critical post-smolt period. J Fish Biology 81(2):500-542.
- Railsback, S.F. (2021). inSALMO 7.2 Model Description. Cal Poly Humboldt.
