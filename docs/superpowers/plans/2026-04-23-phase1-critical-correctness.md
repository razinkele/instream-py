# Phase 1 — v0.41.15 Critical Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 CRITICAL findings plus one companion HIGH (movement_panel deck.gl), shipping a v0.41.15 patch release that restores scientific correctness of inSTREAM-py simulations, outputs, and fresh-install compatibility.

**Architecture:** Nine independent bug fixes, each a separate commit with its own regression test. The nine commits are not ordered by dependency — each can be developed independently in any order — but they ship as one release to minimize version churn.

**Tech Stack:** Python 3.11+, pytest, NumPy, Pydantic v2, Numba (optional), Shiny + deck.gl (frontend).

---

## Orientation for the engineer

**Working directory:** `C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py`

**Environment:** Use micromamba `shiny` environment per project CLAUDE.md. Every command below is wrapped with `micromamba run -n shiny`.

**Test conventions:** Tests live under `tests/`, use pytest, import from `instream.*`. Fixtures live under `tests/fixtures/example_a/` (small Chinook mesh) and `tests/fixtures/example_baltic/` (Baltic salmon, multi-reach).

**Pytest invocation for all tasks below:**
```bash
micromamba run -n shiny python -m pytest tests/ -v
```

**Project memory:** Several of these fixes close "regression-of-a-fix" bugs — a correct fix was applied historically, then a later refactor silently shadowed it. See `memory/feedback_deckgl_camelcase.md`, `memory/project_v017_status.md`, and the Arc E entries.

---

## Task 1: Fix `behavior.py` fallback loop indentation (C1)

**Problem:** In `src/salmopy/modules/behavior.py` the `for i in range(n_fish):` at line 211 is at 4-space indentation and sits OUTSIDE the `else:` block. Every Numba-computed candidate list gets overwritten by the Python KD-tree scan, silently wasting the Numba hot path and replacing its result when the two algorithms differ at boundary cases.

**Files:**
- Modify: `src/salmopy/modules/behavior.py:208-227`
- Create: `tests/test_behavior_numba_fallback.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_behavior_numba_fallback.py`:

```python
"""Regression test for behavior.py:211 indentation bug.

When Numba is available, the Python KD-tree fallback must NOT run —
its result would overwrite the Numba-computed candidate lists.
"""
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_numba_path_does_not_invoke_python_fallback(monkeypatch):
    from salmopy.modules import behavior

    if not behavior._HAS_NUMBA_SPATIAL:
        pytest.skip("numba not installed")

    from salmopy.model import SalmopyModel
    model = SalmopyModel(
        config_path=str(CONFIGS_DIR / "example_a.yaml"),
        data_dir=str(FIXTURES_DIR / "example_a"),
    )
    assert hasattr(model.fem_space, "_geo_offsets"), (
        "Expected Numba geo-cache to be built; test precondition failed"
    )

    def tripwire(*args, **kwargs):
        raise AssertionError(
            "fem_space.cells_in_radius was called — Python fallback ran "
            "despite Numba being available. The `for i in range(n_fish)` "
            "loop in behavior.py must be indented under `else:`."
        )
    monkeypatch.setattr(model.fem_space, "cells_in_radius", tripwire)

    sp_cfg = model.config.species[model.species_order[0]]
    candidate_lists = behavior.build_candidate_lists(
        trout_state=model.trout_state,
        fem_space=model.fem_space,
        move_radius_max=sp_cfg.move_radius_max,
        move_radius_L1=sp_cfg.move_radius_L1,
        move_radius_L9=sp_cfg.move_radius_L9,
        reach_allowed=None,
    )
    assert len(candidate_lists) == model.trout_state.alive.shape[0]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_behavior_numba_fallback.py -v
```

Expected: FAIL with `AssertionError: fem_space.cells_in_radius was called — Python fallback ran despite Numba being available.`

- [ ] **Step 3: Apply the fix (indent the fallback loop under `else:`)**

In `src/salmopy/modules/behavior.py` lines 208-227, the structure is currently:

```python
    else:
        # Python fallback: KD-tree queries + vectorized wet filter
        candidate_lists = [None] * n_fish
    for i in range(n_fish):
        if not trout_state.alive[i]:
            continue
        current_cell = trout_state.cell_idx[i]
        if current_cell < 0:
            continue
        radius = movement_radius(
            trout_state.length[i], move_radius_max, move_radius_L1, move_radius_L9
        )
        candidates = fem_space.cells_in_radius(current_cell, radius)
        neighbors = fem_space.get_neighbor_indices(current_cell)
        neighbors = neighbors[neighbors >= 0]
        all_c = np.unique(
            np.concatenate([candidates, neighbors, np.array([current_cell])])
        )
        # Vectorized wet filter (replaces Python for-loop)
        candidate_lists[i] = all_c[wet_mask[all_c]].astype(np.int32)
```

Change it to (note: everything from the `for` onward becomes indented by one level):

```python
    else:
        # Python fallback: KD-tree queries + vectorized wet filter
        candidate_lists = [None] * n_fish
        for i in range(n_fish):
            if not trout_state.alive[i]:
                continue
            current_cell = trout_state.cell_idx[i]
            if current_cell < 0:
                continue
            radius = movement_radius(
                trout_state.length[i], move_radius_max, move_radius_L1, move_radius_L9
            )
            candidates = fem_space.cells_in_radius(current_cell, radius)
            neighbors = fem_space.get_neighbor_indices(current_cell)
            neighbors = neighbors[neighbors >= 0]
            all_c = np.unique(
                np.concatenate([candidates, neighbors, np.array([current_cell])])
            )
            # Vectorized wet filter (replaces Python for-loop)
            candidate_lists[i] = all_c[wet_mask[all_c]].astype(np.int32)
```

- [ ] **Step 4: Run the regression test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_behavior_numba_fallback.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite to verify no other test regresses**

```bash
micromamba run -n shiny python -m pytest tests/ -v -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

Expected: all tests PASS (existing skip/xfail counts unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/salmopy/modules/behavior.py tests/test_behavior_numba_fallback.py
git commit -m "fix(behavior): indent Python KD-tree fallback under else: branch

The for-loop at line 211 was at 4-space indentation, running unconditionally
after the Numba branches and overwriting every Numba-computed candidate list
with a KD-tree scan. This silently reverted the v0.29.0 batch-Numba speedup
and replaced Numba results with Python results when the two differ.

Regression test asserts cells_in_radius is not invoked when Numba is available."
```

---

## Task 2: Initialize `max_lifetime_weight` for initial population (C2)

**Problem:** In `src/salmopy/model_init.py:347` the initial-population builder writes `weight[idx:end]` but never writes `max_lifetime_weight`, which stays at the `zeros(capacity)` default from `TroutState.zeros()`. The `survival_mass_floor` function returns `1.0` (exempt from starvation) when `max_lifetime_weight <= 0.0`, so starvation is silently disabled for initial-population fish. Hatchery stocking and adult arrivals handle this correctly — only the initial population is broken.

**Files:**
- Modify: `src/salmopy/model_init.py:342-353`
- Modify: `tests/test_initialization.py` (append a new test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_initialization.py`. If `CONFIGS_DIR` is not already defined at module level in that file, add it alongside the existing `FIXTURES_DIR` constant (top of file, after imports):

```python
# At top of file, next to FIXTURES_DIR:
CONFIGS_DIR = Path(__file__).parent.parent / "configs"
```

Then append the test class:

```python
class TestInitialPopulationMaxLifetimeWeight:
    """Regression: initial population must have max_lifetime_weight > 0 so
    survival_mass_floor correctly applies starvation mortality."""

    def test_max_lifetime_weight_matches_initial_weight(self):
        import numpy as np
        from salmopy.model import SalmopyModel

        model = SalmopyModel(
            config_path=str(CONFIGS_DIR / "example_a.yaml"),
            data_dir=str(FIXTURES_DIR / "example_a"),
        )
        alive = model.trout_state.alive
        n_alive = int(alive.sum())
        assert n_alive > 0, "fixture must seed some alive fish"
        mlw = model.trout_state.max_lifetime_weight[:n_alive]
        w = model.trout_state.weight[:n_alive]
        assert (mlw > 0).all(), (
            f"max_lifetime_weight has zeros at indices "
            f"{np.where(mlw == 0)[0].tolist()[:5]}; starvation logic disabled"
        )
        np.testing.assert_array_equal(mlw, w)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_initialization.py::TestInitialPopulationMaxLifetimeWeight -v
```

Expected: FAIL with `AssertionError: max_lifetime_weight has zeros at indices ...`

- [ ] **Step 3: Apply the fix**

In `src/salmopy/model_init.py`, after the existing line `self.trout_state.weight[idx:end] = weights` (currently line 347), add:

```python
            self.trout_state.max_lifetime_weight[idx:end] = weights
```

So the block (lines 341-349) becomes:

```python
            end = idx + n
            self.trout_state.alive[idx:end] = True
            self.trout_state.species_idx[idx:end] = sp_idx
            self.trout_state.age[idx:end] = pop["age"]
            self.trout_state.length[idx:end] = lengths
            self.trout_state.initial_length[idx:end] = lengths
            self.trout_state.weight[idx:end] = weights
            self.trout_state.max_lifetime_weight[idx:end] = weights
            self.trout_state.condition[idx:end] = 1.0
            self.trout_state.superind_rep[idx:end] = 1
```

- [ ] **Step 4: Run the regression test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_initialization.py::TestInitialPopulationMaxLifetimeWeight -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite to verify no regression**

```bash
micromamba run -n shiny python -m pytest tests/ -v -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 6: Commit**

```bash
git add src/salmopy/model_init.py tests/test_initialization.py
git commit -m "fix(init): initialize max_lifetime_weight for initial population

Initial-population fish had max_lifetime_weight left at the zeros default,
which made survival_mass_floor return 1.0 (starvation-exempt) for every
pre-seeded fish. Hatchery stocking and adult arrivals set this correctly;
only the initial population was broken.

Regression test asserts max_lifetime_weight == weight for all pre-seeded fish."
```

---

## Task 3: Remove RETURNING_ADULT bulk promotion at spawn-season open (C3)

**Problem:** In `src/salmopy/model_day_boundary.py:252-255`, RETURNING_ADULT fish are bulk-promoted to SPAWNER as soon as the spawn season opens — before any per-fish readiness check and before any redd deposit. This shadows the v0.17.0 fix at line 369 (`if int(self.trout_state.life_history[i]) == int(LifeStage.RETURNING_ADULT): ...`) which becomes dead code because the bulk promotion has already set every RETURNING_ADULT to SPAWNER. The net effect: fish that fail readiness are promoted anyway and may be exposed to the post-spawn death block incorrectly.

**Files:**
- Modify: `src/salmopy/model_day_boundary.py:252-255`
- Create: `tests/test_returning_adult_promotion.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_returning_adult_promotion.py`:

```python
"""Regression for model_day_boundary.py:252-255.

A RETURNING_ADULT fish that fails readiness (e.g. temperature outside
spawn range) must remain RETURNING_ADULT — not be bulk-promoted to SPAWNER
at season-open. Per v0.17.0: promotion only on actual redd deposit.
"""
import numpy as np
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_returning_adult_not_promoted_without_redd_deposit(monkeypatch):
    from salmopy.model import SalmopyModel
    from salmopy.state.life_stage import LifeStage

    model = SalmopyModel(
        config_path=str(CONFIGS_DIR / "example_a.yaml"),
        data_dir=str(FIXTURES_DIR / "example_a"),
    )

    # Pick an alive fish and mark it RETURNING_ADULT
    alive = np.where(model.trout_state.alive)[0]
    assert len(alive) > 0, "fixture must seed alive fish"
    fish_i = int(alive[0])
    model.trout_state.life_history[fish_i] = int(LifeStage.RETURNING_ADULT)

    # Force temperature outside spawn range so ready_to_spawn will return False
    sp_name = model.species_order[0]
    sp_cfg = model.config.species[sp_name]
    r_idx = int(model.trout_state.reach_idx[fish_i])
    model.reach_state.temperature[r_idx] = sp_cfg.spawn_min_temp - 5.0

    # Force julian_date into the spawn window. Parse directly from the
    # config (NOT from model._spawn_doy_cache — that is lazy-initialized
    # on first call to _do_spawning). Example_a's Chinook-Spring has
    # spawn_start_day: "09-01" → DOY 244.
    import pandas as pd
    month, day = sp_cfg.spawn_start_day.split("-")
    spawn_start_doy = int(
        pd.Timestamp(f"2000-{month}-{day}").day_of_year
    )
    monkeypatch.setattr(
        type(model.time_manager),
        "julian_date",
        property(lambda self: spawn_start_doy),
    )

    model._do_spawning(step_length=1.0)

    assert int(model.trout_state.life_history[fish_i]) == int(LifeStage.RETURNING_ADULT), (
        "Fish was promoted to SPAWNER without depositing a redd — bulk promotion "
        "at model_day_boundary.py:252-255 is shadowing the v0.17.0 per-fish fix."
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_returning_adult_promotion.py -v
```

Expected: FAIL with `AssertionError: Fish was promoted to SPAWNER without depositing a redd`.

- [ ] **Step 3: Apply the fix (delete the bulk promotion block)**

In `src/salmopy/model_day_boundary.py`, delete lines 252-255 (the four lines ending with `self.trout_state.life_history[alive[ra_mask]] = int(LifeStage.SPAWNER)`). The surrounding code becomes:

```python
        alive = self.trout_state.alive_indices()
        # Filter to freshwater fish only (zone_idx == -1)
        marine_domain = getattr(self, '_marine_domain', None)
        if marine_domain is not None:
            fw_mask = self.trout_state.zone_idx[alive] == -1
            alive = alive[fw_mask]
        cs = self.fem_space.cell_state

        for i in alive:
```

The per-fish promotion at line 369 (inside the redd-deposit block) is preserved and becomes the sole promotion path — exactly as v0.17.0 intended.

- [ ] **Step 4: Run the regression test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_returning_adult_promotion.py -v
```

Expected: PASS.

- [ ] **Step 5: Run related existing tests**

```bash
micromamba run -n shiny python -m pytest tests/test_spawning.py tests/test_kelt_survival.py tests/test_marine_e2e.py -v
```

Expected: all PASS. If any test relied on the bulk promotion to work, it is the test that is wrong — fix the test to set up RETURNING_ADULTs that pass ready_to_spawn.

- [ ] **Step 6: Run full suite**

```bash
micromamba run -n shiny python -m pytest tests/ -v -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 7: Commit**

```bash
git add src/salmopy/model_day_boundary.py tests/test_returning_adult_promotion.py
git commit -m "fix(spawning): remove RETURNING_ADULT bulk promotion at season open

The bulk promotion at model_day_boundary.py:252-255 shadowed the v0.17.0
per-fish-on-redd-deposit fix (line 369 became dead code). A fish that
failed ready_to_spawn was still promoted to SPAWNER and could then be
incorrectly exposed to the post-spawn death block.

Restores v0.17.0 semantics: RETURNING_ADULT -> SPAWNER only on redd deposit."
```

---

## Task 4: Weight PSPC counts by `superind_rep` (C4)

**Problem:** In `src/salmopy/io/output.py:219-223`, `write_smolt_production_by_reach` increments `counts[r] += 1` per outmigrant dict. Each outmigrant represents a super-individual with `superind_rep` real fish. The sibling function `write_spawner_origin_matrix` (line 288) correctly uses `rep = int(sp.get("superind_rep", 1))`. The PSPC writer is inconsistent and silently under-reports the primary ICES WGBAST scientific deliverable ("Potential Smolt Production Capacity achieved %") by a factor equal to the mean super-individual rep.

**Files:**
- Modify: `src/salmopy/io/output.py:219-223`
- Modify: `tests/test_pspc_output.py` (add a new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pspc_output.py`:

```python
def test_smolt_production_by_reach_weights_by_superind_rep(tmp_path):
    """Regression for output.py:219-223: PSPC must weight each outmigrant
    by superind_rep. Each outmigrant dict represents a super-individual."""
    outmigrants = [
        {"species_idx": 0, "natal_reach_idx": 0, "superind_rep": 100},
        {"species_idx": 0, "natal_reach_idx": 0, "superind_rep": 50},
        {"species_idx": 0, "natal_reach_idx": 1, "superind_rep": 10},
    ]
    reach_names = ["Reach_A", "Reach_B"]
    reach_pspc = [1000.0, 100.0]
    path = write_smolt_production_by_reach(
        outmigrants, reach_names, reach_pspc, year=2025, output_dir=tmp_path
    )
    df = pd.read_csv(path)
    row_a = df[df["reach_idx"] == 0].iloc[0]
    assert row_a["smolts_produced"] == 150, (
        f"Expected rep-weighted count 150 (=100+50), got {row_a['smolts_produced']}"
    )
    row_b = df[df["reach_idx"] == 1].iloc[0]
    assert row_b["smolts_produced"] == 10


def test_smolt_production_missing_superind_rep_defaults_to_one(tmp_path):
    """Legacy outmigrant dicts without superind_rep still count as 1 (current test compat)."""
    outmigrants = [
        {"species_idx": 0, "natal_reach_idx": 0, "length": 12.0, "reach_idx": 0},
        {"species_idx": 0, "natal_reach_idx": 0, "length": 11.0, "reach_idx": 0},
    ]
    reach_names = ["Only"]
    reach_pspc = [100.0]
    path = write_smolt_production_by_reach(
        outmigrants, reach_names, reach_pspc, year=2025, output_dir=tmp_path
    )
    df = pd.read_csv(path)
    assert df.iloc[0]["smolts_produced"] == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
micromamba run -n shiny python -m pytest tests/test_pspc_output.py::test_smolt_production_by_reach_weights_by_superind_rep -v
```

Expected: FAIL with `Expected rep-weighted count 150 (=100+50), got 2`.

- [ ] **Step 3: Apply the fix**

In `src/salmopy/io/output.py`, change lines 219-223 from:

```python
    counts = [0] * len(reach_names)
    for om in outmigrants:
        r = int(om.get("natal_reach_idx", -1))
        if 0 <= r < len(counts):
            counts[r] += 1
```

to:

```python
    counts = [0] * len(reach_names)
    for om in outmigrants:
        r = int(om.get("natal_reach_idx", -1))
        if 0 <= r < len(counts):
            counts[r] += int(om.get("superind_rep", 1))
```

- [ ] **Step 4: Run the regression tests to verify they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_pspc_output.py -v
```

Expected: all PASS, including the previously-existing `test_smolt_production_by_reach_csv` which uses outmigrants without `superind_rep` (defaults to 1, old behavior preserved).

- [ ] **Step 5: Verify calibration tests still pass (they read PSPC output)**

```bash
micromamba run -n shiny python -m pytest tests/test_calibration_ices.py -v -m "not slow"
```

Expected: PASS or the same skip/xfail state as before.

- [ ] **Step 6: Commit**

```bash
git add src/salmopy/io/output.py tests/test_pspc_output.py
git commit -m "fix(output): weight PSPC smolts_produced by superind_rep

write_smolt_production_by_reach counted each outmigrant as 1 fish instead
of superind_rep real fish, silently under-reporting the ICES WGBAST PSPC
achieved % metric by the mean super-individual rep factor. Sibling writer
write_spawner_origin_matrix (line 288) already weights correctly — now
consistent.

Regression tests cover both rep-weighted and legacy (no-rep) outmigrant inputs."
```

---

## Task 5: Propagate `spawn_defense_area_m` into `SpeciesParams` (C5)

**Problem:** The Arc E fix reconciled legacy `spawn_defense_area` (cm²) into the canonical `spawn_defense_area_m` (meters) on the Pydantic `SpeciesConfig` object. But `src/salmopy/state/params.py:102` still declares only `spawn_defense_area: float = 0.0` on the frozen `SpeciesParams` runtime dataclass, and `params_from_config` (`src/salmopy/io/config.py:544`) copies only the legacy cm field. The spawning code in `model_day_boundary.py:325` reads `spawn_defense_area_m` directly from `sp_cfg` (the Pydantic object) so it happens to be correct today — but any refactor that switches a caller to read `SpeciesParams.spawn_defense_area_m` silently resurrects the Arc E bug (values 100× too large, one giant redd blocking all spawn).

**Files:**
- Modify: `src/salmopy/state/params.py:102`
- Modify: `src/salmopy/io/config.py:544`
- Modify: `tests/test_config.py` (add a new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py` (inside the existing test module, alongside `TestLoadConfig`):

```python
class TestParamsFromConfigDefenseArea:
    """Regression for config.py:544 + params.py:102.

    The Pydantic SpeciesConfig stores spawn_defense_area_m (meters, the Arc E
    canonical unit). The frozen runtime SpeciesParams must expose the same
    field so callers that go through params_from_config do not silently fall
    back to the legacy cm field.
    """

    def test_species_params_has_spawn_defense_area_m_field(self):
        from salmopy.state.params import SpeciesParams
        params = SpeciesParams()
        assert hasattr(params, "spawn_defense_area_m"), (
            "SpeciesParams must expose spawn_defense_area_m to prevent "
            "Arc E regression"
        )

    def test_params_from_config_propagates_spawn_defense_area_m(self):
        from salmopy.io.config import load_config, params_from_config
        cfg = load_config(CONFIGS_DIR / "example_a.yaml")
        sp_name = next(iter(cfg.species))
        cfg.species[sp_name].spawn_defense_area_m = 3.5
        params_dict = params_from_config(cfg)
        assert params_dict[sp_name].spawn_defense_area_m == pytest.approx(3.5)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
micromamba run -n shiny python -m pytest tests/test_config.py::TestParamsFromConfigDefenseArea -v
```

Expected: FAIL with `AttributeError: 'SpeciesParams' object has no attribute 'spawn_defense_area_m'`.

- [ ] **Step 3a: Add the field to `SpeciesParams`**

In `src/salmopy/state/params.py` around line 102 (inside the `# --- Spawning ---` section), add the new field. The existing line is:

```python
    # --- Spawning ---
    spawn_defense_area: float = 0.0
    spawn_egg_viability: float = 0.0
```

Change to:

```python
    # --- Spawning ---
    spawn_defense_area: float = 0.0  # legacy cm² — kept for back-compat
    spawn_defense_area_m: float = 0.0  # Arc E canonical meters
    spawn_egg_viability: float = 0.0
```

- [ ] **Step 3b: Populate the field in `params_from_config`**

In `src/salmopy/io/config.py` around line 544, the existing line is:

```python
            # Spawning
            spawn_defense_area=sp.spawn_defense_area,
            spawn_egg_viability=sp.spawn_egg_viability,
```

Change to:

```python
            # Spawning
            spawn_defense_area=sp.spawn_defense_area,
            spawn_defense_area_m=getattr(sp, "spawn_defense_area_m", 0.0),
            spawn_egg_viability=sp.spawn_egg_viability,
```

The `getattr` default protects legacy Pydantic configs that predate the Arc E reconciliation.

- [ ] **Step 4: Run the regression tests to verify they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_config.py::TestParamsFromConfigDefenseArea -v
```

Expected: PASS.

- [ ] **Step 5: Run defense-area-related tests**

```bash
micromamba run -n shiny python -m pytest tests/test_config.py tests/test_phase3_hardening.py tests/test_spawning.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run full suite**

```bash
micromamba run -n shiny python -m pytest tests/ -v -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

- [ ] **Step 7: Commit**

```bash
git add src/salmopy/state/params.py src/salmopy/io/config.py tests/test_config.py
git commit -m "fix(params): add spawn_defense_area_m to SpeciesParams (Arc E completion)

Arc E's fix reconciled the legacy cm field into canonical meters on the
Pydantic SpeciesConfig, but the frozen runtime SpeciesParams dataclass
kept only the cm field. Any caller consuming SpeciesParams.spawn_defense_area_m
(rather than reading from the Pydantic config directly) would silently
get 0.0 — resurrecting the Arc E 'one giant redd blocks all spawn' bug.

Now SpeciesParams exposes both fields and params_from_config propagates
the canonical meters value."
```

---

## Task 6: Fix `movement_panel.py` deck.gl snake_case props (H1)

**Problem:** `app/modules/movement_panel.py:39-41` passes `get_fill_color`, `get_line_color`, `get_line_width` to `geojson_layer(...)`. Per `memory/feedback_deckgl_camelcase.md` and the comment at `app/modules/setup_panel.py:254`, deck.gl silently ignores snake_case kwargs — the water-background layer renders with no fill color and default stroke. Commit `798a03a` (2026-04-23) fixed this exact pattern in `setup_panel.py`; the matching fix in `movement_panel.py` was missed.

**Files:**
- Modify: `app/modules/movement_panel.py:37-42`
- Create: `tests/test_deckgl_camelcase.py` (invariant test to prevent future regressions)

- [ ] **Step 1: Write the failing invariant test**

Create `tests/test_deckgl_camelcase.py`:

```python
"""Invariant: deck.gl props in app/ must be camelCase.

Per memory/feedback_deckgl_camelcase.md: deck.gl's JS side silently ignores
unrecognized (snake_case) keys. A regression here produces an invisible
layer with no runtime error. Scans app/ for the known forbidden keys.
"""
import re
from pathlib import Path

FORBIDDEN_KEYS = (
    "get_fill_color",
    "get_line_color",
    "get_line_width",
    "get_position",
    "get_radius",
    "get_elevation",
    "get_text",
    "get_icon",
    "get_source_position",
    "get_target_position",
)


def test_no_snake_case_deckgl_props_in_app():
    app_dir = Path(__file__).parent.parent / "app"
    pattern = re.compile(rf"\b({'|'.join(FORBIDDEN_KEYS)})\s*=")
    offenders = []
    for py in app_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # Ignore lines that are comments about the forbidden keys (docstrings, warnings)
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            if pattern.search(line):
                offenders.append(
                    f"{py.relative_to(app_dir.parent)}:{lineno}: {stripped}"
                )
    assert not offenders, (
        "Found snake_case deck.gl props in app/ (must be camelCase — see "
        "memory/feedback_deckgl_camelcase.md):\n" + "\n".join(offenders)
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_deckgl_camelcase.py -v
```

Expected: FAIL listing `app/modules/movement_panel.py:39`, `:40`, `:41` as offenders.

- [ ] **Step 3: Apply the fix**

In `app/modules/movement_panel.py`, change lines 37-42 from:

```python
    return geojson_layer(
        id="water-bg", data=geojson,
        get_fill_color="@@=properties._fill",
        get_line_color=[100, 140, 180, 60],
        get_line_width=1, stroked=True, filled=True, pickable=False,
    )
```

to:

```python
    return geojson_layer(
        id="water-bg", data=geojson,
        getFillColor="@@=properties._fill",
        getLineColor=[100, 140, 180, 60],
        getLineWidth=1, stroked=True, filled=True, pickable=False,
    )
```

- [ ] **Step 4: Run the invariant test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_deckgl_camelcase.py -v
```

Expected: PASS.

- [ ] **Step 5: Run Shiny smoke tests**

```bash
micromamba run -n shiny python -m pytest tests/test_app_smoke.py tests/test_spatial_panel.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/modules/movement_panel.py tests/test_deckgl_camelcase.py
git commit -m "fix(movement): convert deck.gl props to camelCase

get_fill_color / get_line_color / get_line_width were silently ignored by
deck.gl, leaving the water-background layer invisible on the Movement
panel. Commit 798a03a fixed the same pattern in setup_panel yesterday;
this completes the sweep.

Adds an invariant test (tests/test_deckgl_camelcase.py) that greps app/
for known snake_case deck.gl keys and fails if any appear, preventing
future regressions of this class."
```

---

## Task 6a: Declare `meshio` as a core dependency (C6)

**Problem:** `src/salmopy/space/fem_mesh.py:7` imports `meshio` unconditionally at module top. `meshio` is not declared in `pyproject.toml` — not in core `dependencies`, not in any optional-dependency group. A user who does `pip install instream` into a clean environment will get `ImportError: No module named 'meshio'` the moment any FEM-mesh path is touched (which happens during normal model init for configs using `.2dm` / `.msh` meshes). The project currently "works" only because the `shiny` micromamba environment has `meshio` installed for unrelated reasons.

**Files:**
- Modify: `pyproject.toml:21-30`
- Create: `tests/test_dependency_manifest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dependency_manifest.py`:

```python
"""Dependency-manifest invariants.

These tests enforce that every third-party package unconditionally imported
in src/instream is declared in pyproject.toml. A gap here means `pip install
instream` into a clean env breaks at first use of the code path.
"""
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _load_pyproject():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _all_declared_packages():
    data = _load_pyproject()
    deps = list(data["project"].get("dependencies", []))
    for group in data["project"].get("optional-dependencies", {}).values():
        deps.extend(group)
    return [d.split(">=")[0].split("<")[0].split("==")[0].split("[")[0].strip().lower()
            for d in deps]


def test_meshio_declared_in_core_dependencies():
    """meshio is imported unconditionally in src/salmopy/space/fem_mesh.py;
    it must be a core dependency so fresh installs work."""
    data = _load_pyproject()
    core = data["project"]["dependencies"]
    assert any(d.lower().startswith("meshio") for d in core), (
        "meshio is imported unconditionally at src/salmopy/space/fem_mesh.py:7 "
        "but is not listed in pyproject.toml [project.dependencies]. "
        "Add 'meshio>=5.3' to the core dependencies block."
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_dependency_manifest.py::test_meshio_declared_in_core_dependencies -v
```

Expected: FAIL with `AssertionError: meshio is imported unconditionally at src/salmopy/space/fem_mesh.py:7 but is not listed...`

- [ ] **Step 3: Apply the fix**

In `pyproject.toml`, change the `dependencies` block (currently lines 21-30):

```toml
dependencies = [
    "mesa>=3.1",
    "numpy>=1.24",
    "scipy>=1.11",
    "pandas>=2.0",
    "geopandas>=0.14",
    "shapely>=2.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
]
```

to (insert `meshio>=5.3` in alphabetical order):

```toml
dependencies = [
    "geopandas>=0.14",
    "mesa>=3.1",
    "meshio>=5.3",
    "numpy>=1.24",
    "pandas>=2.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "scipy>=1.11",
    "shapely>=2.0",
]
```

(The alphabetical sort is a minor cleanliness improvement; the critical change is the addition of `meshio>=5.3`.)

- [ ] **Step 4: Run the test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_dependency_manifest.py::test_meshio_declared_in_core_dependencies -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_dependency_manifest.py
git commit -m "fix(deps): declare meshio as core dependency

fem_mesh.py imports meshio unconditionally at module load. It was not
listed in pyproject.toml under any dependency group — fresh pip install
would raise ImportError on first FEM mesh use. Discovered by the
2026-04-23 deep review.

Adds tests/test_dependency_manifest.py as an invariant-style regression
guard for the dep manifest."
```

---

## Task 6b: Declare `SALib` and `scikit-learn` in a `[calibration]` extra (C7)

**Problem:** `src/salmopy/calibration/sensitivity.py` lazily imports `SALib.sample.sobol`, `SALib.sample.morris`, `SALib.analyze.sobol`, `SALib.analyze.morris`. `src/salmopy/calibration/surrogate.py` lazily imports `sklearn.gaussian_process`. Neither `SALib` nor `scikit-learn` appears in any optional-dependency group. `SensitivityAnalyzer.generate_samples()` and `SurrogateCalibrator.fit()` both raise `ModuleNotFoundError` on a clean `pip install salmopy[dev]`. The `[dev]` extra should be the canonical "everything developers need" group, and the calibration suite is a first-class feature.

**Files:**
- Modify: `pyproject.toml:36-50` (optional-dependencies block)
- Modify: `tests/test_dependency_manifest.py` (extend with new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dependency_manifest.py`:

```python
def test_calibration_extra_declares_salib_and_sklearn():
    """SALib and scikit-learn are imported in src/salmopy/calibration/;
    they must be declared in an optional-dependencies group (canonically
    a new [calibration] extra, and [dev] should depend on that extra)."""
    data = _load_pyproject()
    optional = data["project"].get("optional-dependencies", {})
    declared = []
    for group in optional.values():
        declared.extend(d.lower() for d in group)

    def has(pkg: str) -> bool:
        return any(d.startswith(pkg) for d in declared)

    assert has("salib"), (
        "SALib is imported in src/salmopy/calibration/sensitivity.py. "
        "Declare it in an optional-dependencies group (recommended: [calibration])."
    )
    assert has("scikit-learn") or has("sklearn"), (
        "scikit-learn is imported in src/salmopy/calibration/surrogate.py. "
        "Declare it in an optional-dependencies group (recommended: [calibration])."
    )


def test_dev_extra_pulls_calibration_transitively():
    """[dev] should be the 'install everything a contributor needs' group
    and must include the calibration extra so `pip install -e .[dev]` is
    enough to run the calibration tests."""
    data = _load_pyproject()
    dev = data["project"]["optional-dependencies"].get("dev", [])
    assert any("salmopy[calibration]" in d for d in dev), (
        "The [dev] extra must include 'salmopy[calibration]' so a clean "
        "dev install brings SALib + scikit-learn. Currently dev can't run "
        "the calibration tests from scratch."
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
micromamba run -n shiny python -m pytest tests/test_dependency_manifest.py -v
```

Expected: FAIL on both new tests.

- [ ] **Step 3: Apply the fix**

In `pyproject.toml`, the current `[project.optional-dependencies]` block (lines 36-60) reads:

```toml
[project.optional-dependencies]
numba = [
    "numba>=0.59",
]
jax = [
    "jax>=0.4.20",
    "jaxlib>=0.4.20",
    "interpax>=0.3",
]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "hypothesis>=6.0",
    "salmopy[numba]",
]
docs = [
    "sphinx",
    "sphinx-rtd-theme",
]
frontend = [
    "shiny>=1.0",
    "shiny-deckgl>=1.9",
    "plotly>=6.0",
    "shinyswatch>=0.9",
]
```

Add a `[calibration]` entry and make `[dev]` depend on it:

```toml
[project.optional-dependencies]
numba = [
    "numba>=0.59",
]
jax = [
    "jax>=0.4.20",
    "jaxlib>=0.4.20",
    "interpax>=0.3",
]
calibration = [
    "SALib>=1.4",
    "scikit-learn>=1.3",
]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "hypothesis>=6.0",
    "salmopy[numba]",
    "salmopy[calibration]",
]
docs = [
    "sphinx",
    "sphinx-rtd-theme",
]
frontend = [
    "shiny>=1.0",
    "shiny-deckgl>=1.9",
    "plotly>=6.0",
    "shinyswatch>=0.9",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_dependency_manifest.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_dependency_manifest.py
git commit -m "fix(deps): add [calibration] extra declaring SALib + scikit-learn

calibration/sensitivity.py imports SALib (Sobol + Morris analyzers);
calibration/surrogate.py imports sklearn.gaussian_process. Neither was
declared in any dependency group, so a clean pip install salmopy[dev]
raised ModuleNotFoundError on first SensitivityAnalyzer.generate_samples()
or SurrogateCalibrator.fit() call.

New [calibration] extra. [dev] now transitively includes it."
```

---

## Task 6c: Remove silent `except Exception: pass` around marine species-weight propagation (C8)

**Problem:** `src/salmopy/model_init.py:516-528` wraps the propagation of `species_weight_A` / `species_weight_B` from config onto `self._marine_domain` in a bare `try: ... except Exception: pass`. The comment on the block explicitly says this assignment is **required for Arc P seal-predation (Holling-II) to fire** — without it, the seal-hazard computation silently returns zero mortality because the species-weight length-at-weight table isn't populated. A misspelled species name in `species_order`, a numpy shape mismatch, or any AttributeError silently disables seal predation with no diagnostic in logs or output.

**Files:**
- Modify: `src/salmopy/model_init.py:515-528`
- Create: `tests/test_marine_species_weights.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_marine_species_weights.py`:

```python
"""Regression for model_init.py:516-528.

The try/except:pass around species_weight_A / species_weight_B propagation
silently disabled Arc P seal predation on any config error. After the fix,
(a) the happy path still populates both attributes, and (b) a deliberately
broken config surfaces a real error rather than a silent zero-mortality.
"""
import numpy as np
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_marine_domain_has_species_weights_populated():
    """Happy path: a well-formed Baltic config must end init with
    species_weight_A and species_weight_B populated on the marine domain."""
    from salmopy.model import SalmopyModel
    model = SalmopyModel(
        config_path=str(CONFIGS_DIR / "example_baltic.yaml"),
        data_dir=str(FIXTURES_DIR / "example_baltic"),
    )
    md = getattr(model, "_marine_domain", None)
    if md is None:
        pytest.skip("config has no marine domain")
    assert hasattr(md, "species_weight_A"), (
        "species_weight_A missing on marine domain — Arc P seal predation "
        "would silently return zero mortality"
    )
    assert hasattr(md, "species_weight_B")
    assert md.species_weight_A is not None
    assert len(md.species_weight_A) == len(model.species_order)
    assert (np.asarray(md.species_weight_A) > 0).all()


def test_bad_species_order_surfaces_keyerror_not_silent_failure(monkeypatch):
    """Bad path: if species_order references a species absent from
    config.species, model init must raise — not silently disable predation.

    Before the fix, the try/except:pass swallowed the KeyError and left
    species_weight_A unset, yielding zero seal mortality with no diagnostic.
    """
    from salmopy.model import SalmopyModel
    from salmopy import model_init as mi

    orig = mi.SalmopyModel._build_model

    def break_species_order_after_build(self):
        orig(self)
        # Inject a mismatch and re-run the propagation block conceptually:
        # we cannot easily replay just the block, so instead we verify the
        # try/except wrapper is gone by reading the source.

    import inspect
    src = inspect.getsource(mi)
    # Look for the specific except clause around species_weight propagation.
    # After the fix, the block is a plain if/hasattr guard.
    assert "species_weight_A" in src
    # Narrow assertion: there must be no `except Exception: pass` within
    # 8 lines after the species_weight_A assignment. The assignment line
    # currently reads `self._marine_domain.species_weight_A = sp_weight_A`.
    needle = "self._marine_domain.species_weight_A = sp_weight_A"
    assert needle in src, (
        f"Expected assignment `{needle}` not found in model_init.py — "
        "the plan's target line has moved or been renamed."
    )
    idx = src.index(needle)
    window = src[idx:idx + 400]
    assert "except Exception" not in window, (
        "try/except:pass still wraps the species_weight_A assignment block "
        "at model_init.py:516-528. Silent Arc P seal-predation failure "
        "would persist."
    )
```

- [ ] **Step 2: Run the tests to verify the structural assertion fails**

```bash
micromamba run -n shiny python -m pytest tests/test_marine_species_weights.py -v
```

Expected: `test_bad_species_order_surfaces_keyerror_not_silent_failure` FAILS with `AssertionError: try/except:pass still wraps ...`. The happy-path test may pass today.

- [ ] **Step 3: Apply the fix**

In `src/salmopy/model_init.py` lines 515-528, the current block is:

```python
            # seal predation — with L1=40 cm — never activates).
            try:
                sp_weight_A = np.array(
                    [self.config.species[n].weight_A for n in self.species_order],
                    dtype=np.float64,
                )
                sp_weight_B = np.array(
                    [self.config.species[n].weight_B for n in self.species_order],
                    dtype=np.float64,
                )
                self._marine_domain.species_weight_A = sp_weight_A
                self._marine_domain.species_weight_B = sp_weight_B
            except Exception:
                pass
```

Replace with:

```python
            # seal predation — with L1=40 cm — never activates).
            if hasattr(self._marine_domain, "species_weight_A"):
                sp_weight_A = np.array(
                    [self.config.species[n].weight_A for n in self.species_order],
                    dtype=np.float64,
                )
                sp_weight_B = np.array(
                    [self.config.species[n].weight_B for n in self.species_order],
                    dtype=np.float64,
                )
                self._marine_domain.species_weight_A = sp_weight_A
                self._marine_domain.species_weight_B = sp_weight_B
```

The `hasattr` guard handles the one legitimate scenario the `try/except` was defending: a legacy `MarineDomain` dataclass predating the `species_weight_A` attribute. Any other failure (KeyError on species_order, numpy shape mismatch, config loading error) now propagates with a real traceback.

- [ ] **Step 4: Run both tests to verify they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_marine_species_weights.py -v
```

Expected: both PASS.

- [ ] **Step 5: Run the full marine suite**

```bash
micromamba run -n shiny python -m pytest tests/test_marine*.py tests/test_seal_forcing.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/salmopy/model_init.py tests/test_marine_species_weights.py
git commit -m "fix(init): remove silent except Exception: pass around marine species-weight

The try/except:pass at model_init.py:516-528 silently disabled Arc P seal
predation (Holling-II) on any config error — a misspelled species name or
any shape mismatch produced zero seal mortality with no diagnostic. The
comment on the block said this assignment is 'required for seal predation
to fire.'

Replaced with an explicit hasattr() guard covering the one legitimate
compatibility case (legacy MarineDomain without the attribute). Real
errors now propagate."
```

---

## Task 7: Version bump + CHANGELOG entry + release

**Files:**
- Modify: `pyproject.toml:7`
- Modify: `src/salmopy/__init__.py:3`
- Modify: `CHANGELOG.md`

Note: per memory, `src/salmopy/__init__.py` already declares `__version__ = "0.41.14"` while `pyproject.toml` is at `0.41.13`. We bump both to `0.41.15` in one atomic commit so the version index is consistent.

- [ ] **Step 1: Bump version in `pyproject.toml`**

Change `pyproject.toml:7` from:

```toml
version = "0.41.13"
```

to:

```toml
version = "0.41.15"
```

- [ ] **Step 2: Bump version in `src/salmopy/__init__.py`**

Change `src/salmopy/__init__.py:3` from:

```python
__version__ = "0.41.14"
```

to:

```python
__version__ = "0.41.15"
```

- [ ] **Step 3: Write CHANGELOG entry**

Prepend to `CHANGELOG.md` above the current top entry:

```markdown
## [0.41.15] — 2026-04-23

### Fixed — critical correctness patch

- **behavior.py** indentation bug at line 211 (Numba candidate lists silently overwritten by Python KD-tree fallback). Restores v0.29.0 batch-Numba hot path and eliminates silent algorithm substitution.
- **model_init.py**: initial-population `max_lifetime_weight` not initialized, silently disabling starvation mortality for all pre-seeded fish.
- **model_day_boundary.py**: remove RETURNING_ADULT→SPAWNER bulk promotion at spawn-season open; v0.17.0 per-fish-on-redd-deposit semantics restored.
- **output.py `write_smolt_production_by_reach`**: PSPC `smolts_produced` now weighted by `superind_rep` (was counting super-individuals as single fish, under-reporting ICES WGBAST PSPC achieved % by the mean rep factor).
- **state/params.py + io/config.py**: add `spawn_defense_area_m` to `SpeciesParams` and propagate in `params_from_config`; closes a latent Arc E regression path.
- **app/modules/movement_panel.py**: deck.gl props converted to camelCase (water-background layer was invisible on the Movement panel).
- **pyproject.toml**: `meshio>=5.3` added to core dependencies (previously imported unconditionally in `space/fem_mesh.py` but undeclared — fresh `pip install` raised ImportError on first FEM-mesh use).
- **pyproject.toml**: new `[calibration]` extra declaring `SALib>=1.4` and `scikit-learn>=1.3`; `[dev]` now transitively includes it.
- **model_init.py**: removed silent `except Exception: pass` around marine `species_weight_A`/`species_weight_B` propagation — any config error here silently disabled Arc P Holling-II seal predation.

### Added

- Invariant test `tests/test_deckgl_camelcase.py` prevents snake_case deck.gl regressions.
- Invariant test `tests/test_dependency_manifest.py` prevents undeclared top-level imports.
- Regression tests: `tests/test_behavior_numba_fallback.py`, `tests/test_returning_adult_promotion.py`, `tests/test_marine_species_weights.py`, `tests/test_pspc_output.py::test_smolt_production_by_reach_weights_by_superind_rep`, `tests/test_config.py::TestParamsFromConfigDefenseArea`, `tests/test_initialization.py::TestInitialPopulationMaxLifetimeWeight`.

```

Also add a missing `[0.41.14]` entry ABOVE `[0.41.13]` documenting the silent bump (memory says v0.41.14 was the UX-phase closure; grep `git log v0.41.13..v0.41.14 --oneline` for exact commits and summarize).

- [ ] **Step 4: Run full test suite one final time**

```bash
micromamba run -n shiny python -m pytest tests/ -v -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py
```

Expected: all PASS.

- [ ] **Step 5: Run ruff**

```bash
micromamba run -n shiny ruff check src/ tests/ --select E,F,W --ignore E501
```

Expected: no violations.

- [ ] **Step 6: Commit version bump**

```bash
git add pyproject.toml src/salmopy/__init__.py CHANGELOG.md
git commit -m "release(v0.41.15): critical correctness patch

See CHANGELOG.md entry for v0.41.15 — 9 fixes closing findings from the
2026-04-23 deep review: behavior.py Numba indentation, max_lifetime_weight
init, RETURNING_ADULT bulk promotion, PSPC rep-weighting, SpeciesParams
defense_area_m, meshio core dependency, [calibration] extra declaring
SALib + scikit-learn, silent except-pass around marine species-weights,
movement_panel deck.gl camelCase.

Invariant tests added for deck.gl camelCase discipline and dependency
manifest declarations."

# Note: we bypass scripts/release.py for this patch because (a) we must
# bump pyproject.toml from 0.41.13 AND __init__.py from 0.41.14 in a
# single atomic commit, which the release script does not support; and
# (b) the release script's shield-badge regex bug is itself addressed
# in Phase 5 Task 5.1.
```

- [ ] **Step 7: Tag and push**

```bash
git tag -a v0.41.15 -m "v0.41.15: critical correctness patch"
git push origin master --tags
```

---

## Post-Phase-1 verification checklist

- [ ] All 9 new regression/invariant tests pass (6 originally planned + 3 from the dependency/marine additions)
- [ ] Existing test suite's skip/xfail count is unchanged from pre-Phase-1
- [ ] `ruff check` is clean
- [ ] `pyproject.toml` and `src/salmopy/__init__.py` agree on version string `0.41.15`
- [ ] CHANGELOG.md top entry is `[0.41.15]` with a `[0.41.14]` entry right below documenting the previously-unlogged diff
- [ ] `git tag v0.41.15` exists and pushed
- [ ] Manual smoke: `pip install -e .` in a clean Python env succeeds (verifies C6 meshio declaration holds)
- [ ] Manual smoke: `pip install -e ".[dev]"` installs SALib + scikit-learn (verifies C7)
- [ ] Manual smoke: start the Shiny app, open Movement panel — water-background layer is visible (previously invisible)
