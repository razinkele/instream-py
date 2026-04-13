# Performance Optimizations — Habitat Selection Hot Path

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce per-step time in `select_habitat_and_activity` by targeting the Numba kernel (35ms) and spatial search (5ms), aiming for 30-50% step time reduction.

**Architecture:** The hot path spends ~46ms per step: ~35ms inside the batch Numba kernel (`batch_select_habitat`), ~5ms in Numba spatial search (`build_candidate_lists`), and ~3ms in Python overhead (CSR construction, array packing, result unpacking). cProfile cannot see inside Numba — all 35ms appears as self-time of `select_habitat_and_activity`.

**Tech Stack:** Python, NumPy, Numba (JIT, `@njit`, `prange`), Mesa framework

**Evidence base:** cProfile of 10 steps on example_a (351 fish, 1373 cells):
- `select_habitat_and_activity`: 454ms cumulative (45.4ms/step), 396ms self (includes Numba kernel)
- `build_candidate_lists`: 53ms (5.3ms/step) — Numba spatial kernel, NOT Python
- Step median: 46.1ms
- Numba batch path: active (`_HAS_NUMBA_BATCH = True`)
- Resource depletion: handled inside Numba kernel (fitness.py:835-890), not in Python

**Reviewed 2026-04-13:** Two independent code reviews found original plan overstated Python overhead (2-3ms, not 10ms). Plan revised to target Numba kernel parallelization and spatial search algorithm.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/instream/backends/numba_backend/fitness.py:653` | Modify | Two-pass parallel Numba kernel |
| `src/instream/backends/numba_backend/spatial.py` | Modify | KD-tree spatial candidate search |
| `src/instream/modules/behavior.py:648-659` | Modify | CSR construction vectorization |
| `src/instream/modules/behavior.py:896-908` | Modify | Result unpacking vectorization |
| `tests/test_perf.py` | Modify | Step-level timing regression test |
| `tests/test_behavior.py` | Verify | Existing tests must continue to pass |

---

### Task 1: Baseline Measurement and Micro-Profiling

**Files:**
- Read: `benchmarks/bench_full.py`, `.benchmarks/baseline.txt`

- [ ] **Step 1: Run benchmark and record baseline**

```bash
micromamba run -n shiny python benchmarks/bench_full.py 2>&1 | tee /tmp/bench_before.txt
```

Record "Steps 11-40 median" as the primary metric.

- [ ] **Step 2: Add time.perf_counter instrumentation around each phase**

To measure the actual Python vs Numba split (cProfile can't), temporarily instrument `select_habitat_and_activity` with `time.perf_counter()` around:
- `build_candidate_lists` call (line 492)
- CSR construction block (lines 648-659)
- Array packing block (lines 661-811)
- `_numba_batch()` call (line 818)
- Result unpacking block (lines 896-908)

Run 10 steps, print per-phase median. This gives the true breakdown.

- [ ] **Step 3: Run test suite to confirm green**

```bash
micromamba run -n shiny python -m pytest tests/ -q --tb=short
```

- [ ] **Step 4: Remove instrumentation, commit baseline measurement**

---

### Task 2: Two-Pass Parallel Numba Kernel (High Impact)

The `batch_select_habitat` kernel at fitness.py:749 iterates fish **sequentially** (`for fi in range(n_fish)`) because resource depletion requires dominance ordering (large fish first). However, fitness evaluation (the expensive part) is independent per fish — only depletion creates serial dependency.

**Approach:** Split into two passes:
- **Pass 1 (parallel):** Evaluate fitness for all fish × cells × activities using `numba.prange`. Write results to per-fish arrays. No depletion.
- **Pass 2 (sequential):** Iterate fish in dominance order, commit best choices, apply depletion. When a fish's best cell has been depleted below threshold by a prior fish, fall back to its second-best choice.

**Files:**
- Modify: `src/instream/backends/numba_backend/fitness.py:653-891`
- Test: `tests/test_behavior.py`, `tests/test_backends.py`

- [ ] **Step 1: Write test for parallel vs sequential parity**

Add to `tests/test_backends.py`:

```python
def test_batch_select_parallel_parity():
    """Two-pass parallel kernel produces same results as sequential."""
    from instream.model import InSTREAMModel
    from pathlib import Path
    import copy

    PROJECT = Path(__file__).resolve().parent.parent
    config = str(PROJECT / "configs" / "example_a.yaml")
    data = str(PROJECT / "tests" / "fixtures" / "example_a")

    model_seq = InSTREAMModel(config, data_dir=data)
    model_seq.step()  # warm up

    # Snapshot state before habitat selection
    # Run sequential path, record results
    # Run parallel path on same snapshot, compare
    # (Implementation depends on how the kernel is refactored)
```

- [ ] **Step 2: Implement Pass 1 — parallel fitness evaluation**

In `fitness.py`, create a new function `_evaluate_fitness_parallel` that uses `numba.prange`:

```python
@numba.njit(parallel=True, cache=True)
def _evaluate_fitness_parallel(
    n_fish, offsets, cand_flat,
    # ... all cell and param arrays ...
):
    """Evaluate fitness for all fish × candidate cells × 3 activities.

    Returns per-fish arrays of (best_cell, best_act, best_growth, top_k_cells, top_k_fitness).
    No resource depletion — pure evaluation.
    """
    best_cells = np.empty(n_fish, dtype=np.int32)
    best_acts = np.empty(n_fish, dtype=np.int32)
    best_growths = np.empty(n_fish, dtype=np.float64)

    for fi in numba.prange(n_fish):
        # ... same fitness evaluation loop as current kernel, but without depletion ...
        # Store best cell/activity/growth for this fish
```

- [ ] **Step 3: Implement Pass 2 — sequential depletion with fallback**

```python
@numba.njit(cache=True)
def _commit_choices_sequential(
    n_fish, dominance_order, best_cells, best_acts, best_growths,
    cell_avail_drift, cell_avail_search, cell_avail_shelter, cell_avail_hiding,
    fish_lengths, fish_reps, step_length,
):
    """Commit choices in dominance order, applying resource depletion."""
    final_cells = np.empty(n_fish, dtype=np.int32)
    final_acts = np.empty(n_fish, dtype=np.int32)
    final_growths = np.empty(n_fish, dtype=np.float64)
    got_shelter = np.zeros(n_fish, dtype=np.int32)

    for rank in range(n_fish):
        fi = dominance_order[rank]
        bc = best_cells[fi]
        ba = best_acts[fi]
        # Apply depletion (same logic as current lines 835-890)
        # If resource depleted below threshold, keep choice but record reduced intake
        final_cells[fi] = bc
        final_acts[fi] = ba
        final_growths[fi] = best_growths[fi]
    return final_cells, final_acts, final_growths, got_shelter
```

- [ ] **Step 4: Wire into `batch_select_habitat` as the new default**

Replace the sequential `for fi in range(n_fish)` loop with calls to `_evaluate_fitness_parallel` then `_commit_choices_sequential`.

- [ ] **Step 5: Run tests and benchmark**

```bash
micromamba run -n shiny python -m pytest tests/ -q --tb=short
micromamba run -n shiny python benchmarks/bench_full.py
```

Compare step median before/after. Expected: 20-40% reduction on the Numba kernel time (multi-core speedup on the 35ms evaluation pass).

- [ ] **Step 6: Commit**

```bash
git add src/instream/backends/numba_backend/fitness.py tests/test_backends.py
git commit -m "perf: two-pass parallel Numba kernel for habitat selection"
```

---

### Task 3: Vectorize Python Overhead (CSR + Unpack)

Small but clean wins on the Python side (~1-2ms total).

**Files:**
- Modify: `src/instream/modules/behavior.py:648-659, 896-908`

- [ ] **Step 1: Vectorize CSR construction (lines 648-659)**

Replace:
```python
        cand_flat_parts = []
        offsets = np.empty(n_batch + 1, dtype=np.int64)
        offsets[0] = 0
        for fi_local in range(n_batch):
            i = normal_idx[fi_local]
            cands = candidate_lists[i]
            if cands.dtype != np.int32:
                cands = cands.astype(np.int32)
            cand_flat_parts.append(cands)
            offsets[fi_local + 1] = offsets[fi_local] + len(cands)
        cand_flat = np.concatenate(cand_flat_parts) if cand_flat_parts else np.empty(0, dtype=np.int32)
```

With:
```python
        _cand_arrays = [candidate_lists[i] for i in normal_idx]
        _cand_lens = np.array([len(c) for c in _cand_arrays], dtype=np.int64)
        offsets = np.empty(n_batch + 1, dtype=np.int64)
        offsets[0] = 0
        np.cumsum(_cand_lens, out=offsets[1:])
        total_cands = int(offsets[-1])
        if total_cands > 0:
            cand_flat = np.empty(total_cands, dtype=np.int32)
            for fi_local in range(n_batch):
                cand_flat[int(offsets[fi_local]):int(offsets[fi_local + 1])] = _cand_arrays[fi_local]
        else:
            cand_flat = np.empty(0, dtype=np.int32)
```

Note: dtype check removed — Numba spatial path guarantees int32.

- [ ] **Step 2: Vectorize result unpacking (lines 896-908)**

Replace:
```python
        for fi_local in range(n_batch):
            i = normal_idx[fi_local]
            bc = int(b_cells[fi_local])
            ba = int(b_acts[fi_local])
            best_cells[i] = bc
            best_activities[i] = ba
            trout_state.cell_idx[i] = bc
            trout_state.activity[i] = ba
            trout_state.reach_idx[i] = cs.reach_idx[bc]
            trout_state.last_growth_rate[i] = b_growths[fi_local]
            if b_shelter[fi_local]:
                trout_state.in_shelter[i] = True
```

With:
```python
        best_cells[normal_idx] = b_cells
        best_activities[normal_idx] = b_acts
        trout_state.cell_idx[normal_idx] = b_cells
        trout_state.activity[normal_idx] = b_acts
        trout_state.reach_idx[normal_idx] = cs.reach_idx[b_cells]
        trout_state.last_growth_rate[normal_idx] = b_growths
        _shelter_mask = b_shelter.astype(bool)
        if np.any(_shelter_mask):
            trout_state.in_shelter[normal_idx[_shelter_mask]] = True
```

- [ ] **Step 3: Run tests**

```bash
micromamba run -n shiny python -m pytest tests/test_behavior.py tests/test_perf.py -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add src/instream/modules/behavior.py
git commit -m "perf: vectorize CSR construction and result unpacking in habitat selection"
```

---

### Task 4: Add Step-Level Performance Regression Test

**Files:**
- Modify: `tests/test_perf.py`

- [ ] **Step 1: Add timing regression test**

```python
def test_select_habitat_step_time():
    """Step time must not regress beyond 60ms (example_a, ~350 fish)."""
    import time
    from pathlib import Path
    from instream.model import InSTREAMModel

    PROJECT = Path(__file__).resolve().parent.parent
    config = str(PROJECT / "configs" / "example_a.yaml")
    data = str(PROJECT / "tests" / "fixtures" / "example_a")
    model = InSTREAMModel(config, data_dir=data)

    for _ in range(5):
        model.step()

    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        model.step()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    median = times[len(times) // 2]
    assert median < 60.0, f"Step median {median:.1f}ms exceeds 60ms threshold"
```

- [ ] **Step 2: Run test, commit**

```bash
micromamba run -n shiny python -m pytest tests/test_perf.py -v
git add tests/test_perf.py
git commit -m "test: add step-level timing regression test (60ms threshold)"
```

---

### Task 5: Final Measurement and Baseline Update

- [ ] **Step 1: Run benchmark**

```bash
micromamba run -n shiny python benchmarks/bench_full.py 2>&1 | tee /tmp/bench_after.txt
```

- [ ] **Step 2: Compare before/after**

```
| Metric                      | Before | After | Delta | Status |
|-----------------------------|--------|-------|-------|--------|
| Step median (ms)            |        |       |       |        |
| Estimated full run (912d)   |        |       |       |        |
```

- [ ] **Step 3: Update baseline if improved**

```bash
cp /tmp/bench_after.txt .benchmarks/baseline.txt
git add .benchmarks/baseline.txt
git commit -m "perf: update baseline after parallel kernel + vectorization"
```

- [ ] **Step 4: Run full test suite**

```bash
micromamba run -n shiny python -m pytest tests/ -v --tb=short
```

---

## Future Work (Not in This Plan)

- **KD-tree spatial search** in `spatial.py` — replace brute-force O(n_fish × n_cells) with pre-built KD-tree. Would reduce `build_candidate_lists` from 5.3ms toward ~1ms.
- **Pre-allocated parameter buffers** — reuse arrays across steps instead of allocating ~60 per step. Reduces GC pressure by ~9MB/step.
- **Consumption memory cache** — maintain running `consumption_total` column instead of per-step `.sum(axis=1)`.
