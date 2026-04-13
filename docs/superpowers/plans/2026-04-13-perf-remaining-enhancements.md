# Performance Remaining Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate remaining Python overhead across 4 independent micro-optimizations, targeting a cumulative 2-4ms/step reduction (20ms → ~16-18ms).

**Architecture:** Four independent tasks that each target a different subsystem: reach-cell caching, growth vectorization, Numba cache dir, and a tighter step-time regression threshold. All tasks are independent and can be implemented in any order. Each produces a self-contained, testable change.

**Tech Stack:** Python, NumPy, Numba, pandas, Mesa

**Evidence base:** Post-optimization profile (example_a, ~340 fish, 1373 cells, step median 20ms):
- Numba kernel: 11.4ms (45%) — at algorithmic limit
- Candidate lookup: 3ms (12%) — just optimized with geometry cache
- Python overhead (CSR/pack/unpack): 3.4ms (13%)
- Day boundary: 2.8ms (11%)
- Environment update: 0.9ms + pandas 3.4ms cumtime
- Everything else: ~2ms

**Dropped from earlier draft (review 2026-04-13):**
- ~~Cache `get_conditions` per day~~ — `get_conditions` is called exactly once per `(reach_name, date)` per step with unique keys each time; a memoization cache would never hit. Zero performance benefit.
- ~~Eliminate CSR double-pack~~ — `candidate_lists[i]` entries are already views into the Numba CSR flat buffer, so re-packing them "directly from CSR" saves near-zero time (both paths end with `np.concatenate` of the same slices). The API change (`build_candidate_lists` returning a 3-tuple) would break 14 test call sites across `test_behavior.py` (5) and `test_spatial_visualization.py` (9) for negligible gain.

---

## File Map

| File | Tasks | Action |
|------|-------|--------|
| `src/instream/model_init.py` | 1 | Add `_reach_cells` cache after FEMSpace init |
| `src/instream/model_environment.py` | 1 | Replace 6× `np.where` with cache lookup |
| `src/instream/model_day_boundary.py` | 1, 2 | Replace `np.where` + vectorize growth loop |
| `src/instream/modules/growth.py` | 2 | Add `import numpy as np` + `apply_growth_vectorized` function |
| `src/instream/backends/numba_backend/__init__.py` | 3 | Set NUMBA_CACHE_DIR |
| `tests/test_perf.py` | 4 | Tighten step threshold |
| `tests/test_growth.py` | 2 | Test vectorized growth parity |

---

### Task 1: Cache Reach-Cell Indices at Init

Six `np.where(cs.reach_idx == r_idx)[0]` calls in `model_environment.py` execute per step per reach (6×N for N reaches), scanning the full cell array (1373 cells) each time. `reach_idx` never changes after init (verified: no assignments post-init). Pre-compute once.

Note: `io/output.py:190` also has `np.where(cell_state.reach_idx == r_idx)[0]`, but it's a standalone CSV-export function (not a model method, no access to `self._reach_cells`, not called per step). Excluded intentionally.

**Files:**
- Modify: `src/instream/model_init.py:123`
- Modify: `src/instream/model_environment.py:51,93,110,125,149,281`
- Modify: `src/instream/model_day_boundary.py:111,764`

- [ ] **Step 1: Add `_reach_cells` dict to model init**

In `src/instream/model_init.py`, after `self.fem_space = FEMSpace(...)` is created (around line 123), add:

```python
        # Pre-compute per-reach cell indices (reach_idx never changes)
        self._reach_cells = {}
        for r_idx in range(len(self.reach_order)):
            self._reach_cells[r_idx] = np.where(
                self.fem_space.cell_state.reach_idx == r_idx
            )[0]
```

- [ ] **Step 2: Replace all `np.where(cs.reach_idx == r_idx)` in model_environment.py**

In `src/instream/model_environment.py`, replace each occurrence:

Line 51: `cells = np.where(cs.reach_idx == r_idx)[0]` → `cells = self._reach_cells[r_idx]`
Line 93: same replacement
Line 110: same replacement
Line 125: same replacement
Line 149: same replacement
Line 281: same replacement

- [ ] **Step 3: Replace occurrences in model_day_boundary.py**

Line 111: `cells = np.where(cs.reach_idx == r_idx)[0]` → `cells = self._reach_cells[r_idx]`
Line 764: `reach_cells = np.where(self.fem_space.cell_state.reach_idx == r_idx)[0]` → `reach_cells = self._reach_cells.get(r_idx, np.arange(n_cells))`

- [ ] **Step 4: Run tests**

```bash
micromamba run -n shiny python -m pytest tests/test_model.py tests/test_perf.py tests/test_hatchery.py -q --tb=short
```

Note: `test_hatchery.py` is required to cover the stocking path at `model_day_boundary.py:764`. `test_model.py` exercises `_update_environment` (via `model.step()`) but does not cover hatchery stocking.

- [ ] **Step 5: Commit**

```bash
git add src/instream/model_init.py src/instream/model_environment.py src/instream/model_day_boundary.py
git commit -m "perf: cache reach-cell indices at init, eliminate 6x np.where per step"
```

---

### Task 2: Vectorize `_apply_accumulated_growth`

The per-fish Python loop (lines 185-215 of `model_day_boundary.py`) calls scalar `apply_growth` for each alive fish. Replace with vectorized NumPy operations.

**Files:**
- Modify: `src/instream/modules/growth.py` (add numpy import + vectorized function)
- Modify: `src/instream/model_day_boundary.py:185-215`
- Test: `tests/test_growth.py`

- [ ] **Step 1: Add `import numpy as np` to growth.py**

`src/instream/modules/growth.py` currently imports only `bisect` and `math`. Add `import numpy as np` at the top of the file, after the existing imports:

```python
import bisect
import dataclasses as _dc
import math

import numpy as np
```

- [ ] **Step 2: Write test for vectorized growth parity**

Add to `tests/test_growth.py`:

```python
def test_apply_growth_vectorized_matches_scalar():
    """Vectorized apply_growth must match scalar version exactly."""
    import numpy as np
    from instream.modules.growth import apply_growth, apply_growth_vectorized

    rng = np.random.default_rng(42)
    n = 100
    weights = rng.uniform(5, 50, n)
    lengths = rng.uniform(5, 30, n)
    conditions = rng.uniform(0.5, 1.2, n)
    growths = rng.uniform(-2, 5, n)
    wA = np.full(n, 0.000247)
    wB = np.full(n, 2.9)

    # Scalar reference
    ref_w, ref_l, ref_k = np.empty(n), np.empty(n), np.empty(n)
    for i in range(n):
        ref_w[i], ref_l[i], ref_k[i] = apply_growth(
            weights[i], lengths[i], conditions[i], growths[i], wA[i], wB[i]
        )

    # Vectorized
    vec_w, vec_l, vec_k = apply_growth_vectorized(
        weights, lengths, conditions, growths, wA, wB
    )

    np.testing.assert_allclose(vec_w, ref_w, rtol=1e-12)
    np.testing.assert_allclose(vec_l, ref_l, rtol=1e-12)
    np.testing.assert_allclose(vec_k, ref_k, rtol=1e-12)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_growth.py::test_apply_growth_vectorized_matches_scalar -v
```

Expected: FAIL — `apply_growth_vectorized` not defined.

- [ ] **Step 4: Implement `apply_growth_vectorized` in growth.py**

Add after the scalar `apply_growth` function (after line 325):

```python
def apply_growth_vectorized(weights, lengths, conditions, growths, weight_A, weight_B):
    """Vectorized version of apply_growth over arrays of fish.

    Returns (new_weights, new_lengths, new_conditions) as numpy arrays.
    """
    new_weights = np.maximum(weights + growths, 0.0)
    healthy_weights = weight_A * lengths ** weight_B
    grew = new_weights > healthy_weights
    new_lengths = np.where(grew, (new_weights / weight_A) ** (1.0 / weight_B), lengths)
    new_conditions = np.where(
        grew,
        1.0,
        np.where(healthy_weights > 0, new_weights / healthy_weights, 0.0),
    )
    return new_weights, new_lengths, new_conditions
```

Note: If `weight_A == 0`, both scalar `length_for_weight` and this vectorized path produce division-by-zero → inf. This matches the scalar behavior exactly — the edge case is pre-existing, not introduced by vectorization. In practice, `weight_A` is a biological allometric constant (e.g. 0.000247) and is never zero.

- [ ] **Step 5: Run test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_growth.py::test_apply_growth_vectorized_matches_scalar -v
```

- [ ] **Step 6: Replace the per-fish loop in `_apply_accumulated_growth`**

In `src/instream/model_day_boundary.py`, replace lines 185-215:

```python
        # Fasting clamp for RETURNING_ADULT and KELT
        lh = self.trout_state.life_history[valid_alive]
        _RA = int(LifeStage.RETURNING_ADULT)
        _KELT = int(LifeStage.KELT)
        fasting_mask = ((lh == _RA) | (lh == _KELT)) & (valid_growth < 0.0)
        valid_growth = np.where(fasting_mask, 0.0, valid_growth)

        from instream.modules.growth import apply_growth_vectorized
        new_w, new_l, new_k = apply_growth_vectorized(
            self.trout_state.weight[valid_alive].astype(np.float64),
            self.trout_state.length[valid_alive].astype(np.float64),
            self.trout_state.condition[valid_alive].astype(np.float64),
            valid_growth.astype(np.float64),
            wA.astype(np.float64),
            wB.astype(np.float64),
        )
        self.trout_state.weight[valid_alive] = new_w
        self.trout_state.length[valid_alive] = new_l
        self.trout_state.condition[valid_alive] = new_k
```

- [ ] **Step 7: Run full test suite**

```bash
micromamba run -n shiny python -m pytest tests/ -q --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add src/instream/modules/growth.py src/instream/model_day_boundary.py tests/test_growth.py
git commit -m "perf: vectorize apply_growth, eliminate per-fish Python loop in day boundary"
```

---

### Task 3: Set NUMBA_CACHE_DIR Off OneDrive

The project lives on OneDrive. Numba's cache files can get corrupted by sync conflicts, causing unnecessary JIT recompilation (~2s per function). Set `NUMBA_CACHE_DIR` to a local temp path.

**Files:**
- Modify: `src/instream/backends/numba_backend/__init__.py`

- [ ] **Step 1: Add NUMBA_CACHE_DIR at module load**

At the top of `src/instream/backends/numba_backend/__init__.py`, **before** the existing `import numba` at line 5:

```python
import os
from pathlib import Path

# Avoid Numba cache corruption from OneDrive sync conflicts
if "NUMBA_CACHE_DIR" not in os.environ:
    _cache = Path.home() / ".instream_numba_cache"
    _cache.mkdir(exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(_cache)
```

Then the existing imports follow:

```python
import math
import numpy as np
import numba
```

Import order is safe: `behavior.py` imports from `numba_backend.fitness` / `.spatial` at module level, but Python resolves the package `__init__.py` first, so `NUMBA_CACHE_DIR` is always set before `import numba` runs anywhere. The env var is process-global, but only inSTREAM uses Numba in this process (verified: no other Numba users in `src/instream/`).

- [ ] **Step 2: Run tests**

```bash
micromamba run -n shiny python -m pytest tests/test_perf.py -q --tb=short
```

- [ ] **Step 3: Commit**

```bash
git add src/instream/backends/numba_backend/__init__.py
git commit -m "perf: set NUMBA_CACHE_DIR off OneDrive to prevent cache corruption"
```

---

### Task 4: Tighten Step-Time Regression Threshold

With Tasks 1-3 applied, update the regression test threshold. **The new value must be validated empirically** — run the benchmark first and set the threshold at 1.5× the observed median to avoid flaky CI.

**Files:**
- Modify: `tests/test_perf.py`

- [ ] **Step 1: Run benchmark to measure current step median**

```bash
micromamba run -n shiny python benchmarks/bench_full.py 2>&1 | grep "Steps 11-40 median"
```

Record the value. Expected: ~17-20ms after Tasks 1-3.

- [ ] **Step 2: Compute threshold**

Set threshold = ceil(observed_median × 1.5). Example: if median is 18ms → threshold = 27ms. If median is 16ms → threshold = 24ms. This gives CI headroom on slower machines.

- [ ] **Step 3: Update threshold in test**

In `tests/test_perf.py`, update the `test_select_habitat_step_time` assertion (currently at line 89, threshold = 40ms):

```python
    assert median < NEW_THRESHOLD, f"Step median {median:.1f}ms exceeds {NEW_THRESHOLD}ms threshold"
```

Replace `NEW_THRESHOLD` with the value computed in Step 2.

- [ ] **Step 4: Run test to confirm it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_perf.py::test_select_habitat_step_time -v
```

- [ ] **Step 5: Update baseline and commit**

```bash
micromamba run -n shiny python benchmarks/bench_full.py > .benchmarks/baseline.txt 2>&1
git add tests/test_perf.py .benchmarks/baseline.txt
git commit -m "perf: tighten step-time regression threshold to Xms after optimizations"
```

---

## Self-Review Checklist

1. **Coverage:** All 4 optimization targets have a corresponding task. Two original tasks (conditions cache, CSR pass-through) were dropped during review with documented rationale.
2. **No placeholders:** All code blocks show complete implementations, except Task 4's threshold which must be filled from benchmark output (by design — empirical validation required).
3. **Type consistency:** `_reach_cells` is `dict[int, np.ndarray]`, used consistently. `apply_growth_vectorized` signature matches test. `growth.py` gets `import numpy as np` (was missing in earlier draft).
4. **Independence:** Tasks 1-3 modify different files (except Task 1 and 2 both touch `model_day_boundary.py` — Task 1 changes line 111/764, Task 2 changes lines 185-215, no overlap). Task 4 depends on Tasks 1-3 being complete (threshold is validated against their combined effect).
5. **No test breakage:** No public API return types are changed. All modifications are internal.
6. **Mutation safety (verified):** `cell_state.reach_idx` is never assigned after init (line 121). The `_reach_cells` cache cannot serve stale data.
7. **Completeness (verified):** `io/output.py:190` also uses `np.where(cell_state.reach_idx == r_idx)` but is a standalone CSV-export function with no `self` access — excluded intentionally.
8. **Import order (verified):** Python resolves `numba_backend/__init__.py` before submodules (`fitness.py`, `spatial.py`), so `NUMBA_CACHE_DIR` is set before `import numba` runs anywhere in the process.
9. **Vectorization equivalence (verified):** `apply_growth_vectorized` matches scalar `apply_growth` for all inputs including edge cases. The `weight_A == 0` division-by-zero is pre-existing in both paths.
10. **Array mutation safety (verified):** All 8 replacement sites use `cells` only as a read index (`cs.depth[cells]`, `cs.area[cells]`, etc.). No site mutates `cells` in-place, so sharing cached arrays without copying is safe.
11. **Variable scoping (verified):** The Task 2 replacement code uses `wA`, `wB` (line 182-183), `valid_growth` (line 176), `valid_alive` (line 175), and `LifeStage` (line 19 import) — all confirmed in scope at line 185.
12. **Test coverage (verified):** Task 1 test command includes `test_hatchery.py` to cover the stocking path at line 764, which `test_model.py` does not exercise.
