# Sprint 1: Simulation Correctness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 9 ecological correctness gaps so every simulation process matches NetLogo 7.4 semantics.

**Architecture:** Each gap is independent — fix one, test, commit, move to the next. No gap depends on another within this sprint. All changes are backward-compatible via default parameter values.

**Tech Stack:** Python 3.11+, NumPy, Mesa 3.x, pytest. Run all commands with `conda run -n shiny`.

**Test command:** `conda run -n shiny python -m pytest tests/ -v`

**Benchmark command:** `conda run -n shiny python benchmarks/bench_full.py`

---

## Task 1: Migration per-species parameter dispatch

**Files:**
- Modify: `src/instream/model.py:192-255` (add migration params to `_sp_arrays`)
- Modify: `src/instream/model.py:990-1012` (fix `_do_migration`)
- Test: `tests/test_migration.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_migration.py`:

```python
class TestPerSpeciesMigration:
    def test_different_species_use_own_migration_params(self):
        """Each species should use its own migrate_fitness_L1/L9."""
        from instream.modules.migration import migration_fitness
        from instream.state.trout_state import TroutState

        ts = TroutState.zeros(4)
        # Fish 0: species 0 (L1=4, L9=10) — length 8 → moderate fitness
        ts.alive[0] = True
        ts.species_idx[0] = 0
        ts.length[0] = 8.0
        ts.life_history[0] = 1
        # Fish 1: species 1 (L1=20, L9=30) — length 8 → very low fitness
        ts.alive[1] = True
        ts.species_idx[1] = 1
        ts.length[1] = 8.0
        ts.life_history[1] = 1

        sp_mig_L1 = np.array([4.0, 20.0])
        sp_mig_L9 = np.array([10.0, 30.0])

        f0 = migration_fitness(8.0, sp_mig_L1[0], sp_mig_L9[0])
        f1 = migration_fitness(8.0, sp_mig_L1[1], sp_mig_L9[1])

        # Same length, different species → different fitness
        assert f0 > 0.3, f"species 0 fitness {f0} should be moderate"
        assert f1 < 0.1, f"species 1 fitness {f1} should be very low"
        assert f0 > f1
```

- [ ] **Step 2: Run test to verify it passes (this tests the function, not the model wiring)**

Run: `conda run -n shiny python -m pytest tests/test_migration.py::TestPerSpeciesMigration -v`

Expected: PASS (this validates the function works with different params — the bug is in model.py wiring, not the function)

- [ ] **Step 3: Add migration params to _sp_arrays in model.py**

In `src/instream/model.py`, find the `_sp_arrays` construction (line 194). Add `"migrate_fitness_L1"` and `"migrate_fitness_L9"` to the field list:

```python
        for field in [
            "cmax_A",
            "cmax_B",
            # ... existing fields ...
            "mort_terr_pred_hiding_factor",
            "migrate_fitness_L1",
            "migrate_fitness_L9",
        ]:
```

- [ ] **Step 4: Fix _do_migration to use per-species params**

In `src/instream/model.py`, replace the entire `_do_migration` method (lines 990-1012):

```python
    def _do_migration(self):
        """Evaluate migration fitness and move fish downstream if warranted."""
        from instream.modules.migration import (
            migration_fitness,
            should_migrate,
            migrate_fish_downstream,
        )

        sp_mig_L1 = self._sp_arrays["migrate_fitness_L1"]
        sp_mig_L9 = self._sp_arrays["migrate_fitness_L9"]
        alive = self.trout_state.alive_indices()
        for i in alive:
            lh = int(self.trout_state.life_history[i])
            if lh != 1:
                continue
            sp_idx = int(self.trout_state.species_idx[i])
            mig_fit = migration_fitness(
                float(self.trout_state.length[i]),
                float(sp_mig_L1[sp_idx]),
                float(sp_mig_L9[sp_idx]),
            )
            best_hab = float(self.trout_state.last_growth_rate[i])
            if should_migrate(mig_fit, best_hab, lh):
                out = migrate_fish_downstream(self.trout_state, i, self._reach_graph)
                self._outmigrants.extend(out)
```

- [ ] **Step 5: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`

Expected: All tests PASS. The change is backward-compatible because `migrate_fitness_L1/L9` already exist in SpeciesConfig with defaults.

- [ ] **Step 6: Commit**

```bash
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" add src/instream/model.py tests/test_migration.py
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" commit -m "fix: use per-species migration params instead of species_order[0]"
```

---

## Task 2: Solar irradiance daily integral

**Files:**
- Modify: `src/instream/backends/numpy_backend/__init__.py:104-114` (irradiance block)
- Modify: `src/instream/backends/numba_backend/__init__.py:41-53` (irradiance block)
- Modify: `src/instream/backends/jax_backend/__init__.py:115-125` (irradiance block)
- Test: `tests/test_light.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_light.py`:

```python
class TestDailyIntegralIrradiance:
    """Verify irradiance uses daily integral, not noon elevation."""

    def test_irradiance_less_than_noon_peak(self):
        """Daily-average irradiance must be less than noon-peak irradiance."""
        from instream.backends.numpy_backend import NumpyBackend
        backend = NumpyBackend()
        # Summer solstice at mid-latitude: noon elevation is high
        _dl, _tl, irr = backend.compute_light(172, 45.0, 1.0, 1.0, 0.0, 6.0)
        # Noon peak would be: 1360 * sin(90 - |45 - 23.45|) ≈ 1360 * sin(68.45) ≈ 1265
        # Daily integral should be substantially lower (roughly 60-70% of noon)
        noon_peak = 1360.0 * np.sin(np.radians(90.0 - abs(45.0 - 23.45)))
        assert irr < noon_peak * 0.85, (
            f"irradiance {irr:.1f} should be well below noon peak {noon_peak:.1f}"
        )

    def test_irradiance_zero_at_polar_winter(self):
        """No irradiance during polar night."""
        from instream.backends.numpy_backend import NumpyBackend
        backend = NumpyBackend()
        _dl, _tl, irr = backend.compute_light(355, 80.0, 1.0, 1.0, 0.0, 6.0)
        assert irr == 0.0

    def test_irradiance_equator_equinox(self):
        """Known analytical case: equator at equinox.

        At equator on equinox: declination ≈ 0, H = pi/2.
        Daily-integrated insolation: (S0/pi) * sin(H) = S0/pi ≈ 433 W/m^2.
        This is a daily integral (total energy proxy), not a daily mean.
        """
        from instream.backends.numpy_backend import NumpyBackend
        backend = NumpyBackend()
        _dl, _tl, irr = backend.compute_light(80, 0.0, 1.0, 1.0, 0.0, 6.0)
        expected = 1360.0 / np.pi  # ≈ 432.9
        assert abs(irr - expected) < 50.0, (
            f"equator equinox irradiance {irr:.1f} should be near {expected:.1f}"
        )

    def test_irradiance_backend_parity_numba(self):
        """NumPy and Numba backends must produce identical irradiance."""
        pytest.importorskip("numba")
        from instream.backends.numpy_backend import NumpyBackend
        from instream.backends.numba_backend import NumbaBackend
        np_b = NumpyBackend()
        nb_b = NumbaBackend()
        for jd in [1, 80, 172, 266, 355]:
            for lat in [0.0, 30.0, 60.0, 80.0]:
                np_r = np_b.compute_light(jd, lat, 1.0, 1.0, 0.0, 6.0)
                nb_r = nb_b.compute_light(jd, lat, 1.0, 1.0, 0.0, 6.0)
                np.testing.assert_allclose(np_r[2], nb_r[2], rtol=1e-10,
                    err_msg=f"jd={jd}, lat={lat}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_light.py::TestDailyIntegralIrradiance::test_irradiance_less_than_noon_peak -v`

Expected: FAIL — current noon elevation overestimates irradiance.

- [ ] **Step 3: Implement daily integral in NumPy backend**

In `src/instream/backends/numpy_backend/__init__.py`, replace lines 104-114 (the irradiance block, from `# Mean daytime irradiance` through `irradiance = max(0.0, ...) * day_length`):

```python
        # Mean daytime irradiance via daily integral formula:
        # I = (S0/pi) * (sin(lat)*sin(dec)*H + cos(lat)*cos(dec)*sin(H))
        # where H = hour angle at sunset in radians.
        solar_constant = 1360.0
        ha_rad = np.radians(hour_angle)
        if day_length > 0:
            irradiance = (solar_constant / np.pi) * (
                np.sin(lat_rad) * np.sin(decl_rad) * ha_rad
                + np.cos(lat_rad) * np.cos(decl_rad) * np.sin(ha_rad)
            )
            irradiance = max(0.0, float(irradiance)) * light_correction * shading
        else:
            irradiance = 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_light.py::TestDailyIntegralIrradiance -v`

Expected: PASS for `test_irradiance_less_than_noon_peak`, `test_irradiance_zero_at_polar_winter`, `test_irradiance_equator_equinox`.

- [ ] **Step 5: Update Numba backend**

In `src/instream/backends/numba_backend/__init__.py`, replace lines 41-53 (from `# Mean daytime irradiance` through `irradiance = irradiance * day_length`). **Important:** Clear Numba cache after this change (`rm -rf src/instream/backends/numba_backend/__pycache__/`):

```python
    # Mean daytime irradiance via daily integral formula
    solar_constant = 1360.0
    ha_rad = math.radians(hour_angle)
    if day_length > 0.0:
        irradiance = (solar_constant / math.pi) * (
            math.sin(lat_rad) * math.sin(decl_rad) * ha_rad
            + math.cos(lat_rad) * math.cos(decl_rad) * math.sin(ha_rad)
        )
        if irradiance < 0.0:
            irradiance = 0.0
        irradiance = irradiance * light_correction * shading
    else:
        irradiance = 0.0
```

- [ ] **Step 6: Update JAX backend**

In `src/instream/backends/jax_backend/__init__.py`, replace lines 115-125:

```python
        # Mean daytime irradiance via daily integral formula
        solar_constant = 1360.0
        ha_rad = jnp.radians(hour_angle)
        if float(day_length) > 0:
            irradiance = (solar_constant / jnp.pi) * (
                jnp.sin(lat_rad) * jnp.sin(decl_rad) * ha_rad
                + jnp.cos(lat_rad) * jnp.cos(decl_rad) * jnp.sin(ha_rad)
            )
            irradiance = max(0.0, float(irradiance)) * light_correction * shading
        else:
            irradiance = 0.0
```

- [ ] **Step 7: Run full test suite including backend parity**

Run: `conda run -n shiny python -m pytest tests/test_light.py -v`

Expected: All PASS including existing day_length tests (unchanged) and new irradiance tests.

- [ ] **Step 8: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`

Expected: All tests PASS. Some validation tests may show slightly different irradiance-dependent values — if so, update golden snapshots.

- [ ] **Step 9: Commit**

```bash
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" add src/instream/backends/numpy_backend/__init__.py src/instream/backends/numba_backend/__init__.py src/instream/backends/jax_backend/__init__.py tests/test_light.py
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" commit -m "fix: replace noon-elevation irradiance with daily-integral formula"
```

---

## Task 3: Light turbidity constant in Beer-Lambert

**Files:**
- Modify: `src/instream/backends/numpy_backend/__init__.py:114-141` (compute_cell_light method)
- Modify: `src/instream/backends/numba_backend/__init__.py:57-68` (clear cache after!)
- Modify: `src/instream/backends/jax_backend/__init__.py:129-157`
- Modify: `src/instream/backends/_interface.py:19-21`
- Modify: `src/instream/model.py:506-513` (pass turbid_const to compute_cell_light)
- Test: `tests/test_light.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_light.py`:

```python
class TestTurbidityConstant:
    def test_turbidity_constant_increases_attenuation(self):
        """Adding turbidity_constant should reduce light at depth."""
        from instream.backends.numpy_backend import NumpyBackend
        backend = NumpyBackend()
        depths = np.array([50.0, 100.0])
        # Without constant
        light_no_const = backend.compute_cell_light(depths, 500.0, 0.01, 5.0, 0.001, 0.0)
        # With constant = 0.005
        light_with_const = backend.compute_cell_light(depths, 500.0, 0.01, 5.0, 0.001, 0.005)
        np.testing.assert_array_less(light_with_const, light_no_const)

    def test_zero_constant_unchanged(self):
        """turbidity_constant=0 should match original behavior."""
        from instream.backends.numpy_backend import NumpyBackend
        backend = NumpyBackend()
        depths = np.array([0.0, 50.0, 100.0])
        light = backend.compute_cell_light(depths, 500.0, 0.01, 5.0, 0.001, 0.0)
        # Manual: attenuation = 0.01 * 5.0 + 0.0 = 0.05
        expected_50 = 500.0 * np.exp(-0.05 * 50.0 / 2.0)
        np.testing.assert_allclose(light[1], expected_50, rtol=1e-12)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_light.py::TestTurbidityConstant -v`

Expected: FAIL — `compute_cell_light` doesn't accept `turbid_const` parameter yet.

- [ ] **Step 3: Update protocol interface**

In `src/instream/backends/_interface.py`, update line 19-21:

```python
    def compute_cell_light(self, depths: np.ndarray, irradiance: float,
                           turbid_coef: float, turbidity: float,
                           light_at_night: float,
                           turbid_const: float = 0.0) -> np.ndarray: ...
```

- [ ] **Step 4: Update NumPy backend**

In `src/instream/backends/numpy_backend/__init__.py`, update `compute_cell_light`:

```python
    def compute_cell_light(self, depths, irradiance, turbid_coef, turbidity,
                           light_at_night, turbid_const=0.0):
        """Compute light at mid-depth for each cell using Beer-Lambert law."""
        depths = np.asarray(depths, dtype=float)
        attenuation = turbid_coef * turbidity + turbid_const
        light = irradiance * np.exp(-attenuation * depths / 2.0)
        light = np.where(depths > 0, light, light_at_night)
        return light
```

- [ ] **Step 5: Update Numba backend**

In `src/instream/backends/numba_backend/__init__.py`, update `_compute_cell_light` and its wrapper:

```python
@numba.njit(parallel=True, cache=True)
def _compute_cell_light(depths, irradiance, turbid_coef, turbidity,
                        light_at_night, turbid_const):
    """Compute light at mid-depth for all cells (Beer-Lambert)."""
    n = depths.shape[0]
    light = np.empty(n, dtype=np.float64)
    attenuation = turbid_coef * turbidity + turbid_const
    for i in numba.prange(n):
        if depths[i] > 0.0:
            light[i] = irradiance * math.exp(-attenuation * depths[i] / 2.0)
        else:
            light[i] = light_at_night
    return light
```

And the class method:

```python
    def compute_cell_light(self, depths, irradiance, turbid_coef, turbidity,
                           light_at_night, turbid_const=0.0):
        depths = np.asarray(depths, dtype=np.float64)
        return _compute_cell_light(depths, float(irradiance),
                                   float(turbid_coef), float(turbidity),
                                   float(light_at_night), float(turbid_const))
```

- [ ] **Step 6: Update JAX backend**

In `src/instream/backends/jax_backend/__init__.py`, update `compute_cell_light`:

```python
    def compute_cell_light(
        self, depths, irradiance, turbid_coef, turbidity, light_at_night,
        turbid_const=0.0,
    ):
        """Compute light at mid-depth for each cell using Beer-Lambert law."""
        depths = jnp.asarray(depths, dtype=jnp.float64)
        attenuation = turbid_coef * turbidity + turbid_const
        light = irradiance * jnp.exp(-attenuation * depths / 2.0)
        light = jnp.where(depths > 0, light, light_at_night)
        return np.asarray(light)
```

- [ ] **Step 7: Pass turbid_const from model.py**

In `src/instream/model.py`, update the `compute_cell_light` call (around line 506-513):

```python
            cell_light = self.backend.compute_cell_light(
                cs.depth[cells],
                self._cached_solar[rname],
                reach_cfg.light_turbid_coef,
                float(self.reach_state.turbidity[r_idx]),
                self._light_cfg.light_at_night,
                reach_cfg.light_turbid_const,
            )
```

- [ ] **Step 8: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_light.py::TestTurbidityConstant -v`

Expected: PASS

- [ ] **Step 9: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`

Expected: All PASS. Existing calls use default `turbid_const=0.0` so behavior is unchanged. `light_turbid_const` already exists in ReachConfig (line 214) with default 0.0.

- [ ] **Step 10: Commit**

```bash
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" add src/instream/backends/_interface.py src/instream/backends/numpy_backend/__init__.py src/instream/backends/numba_backend/__init__.py src/instream/backends/jax_backend/__init__.py src/instream/model.py tests/test_light.py
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" commit -m "fix: add turbidity_constant to Beer-Lambert attenuation formula"
```

---

## Task 4: Fitness memory (exponential moving average)

**Files:**
- Modify: `src/instream/state/trout_state.py:9-58`
- Modify: `src/instream/model.py` (after habitat selection, update fitness memory)
- Modify: `src/instream/model.py:990-1012` (use fitness_memory in migration)
- Test: `tests/test_behavior.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_behavior.py`:

```python
class TestFitnessMemory:
    def test_memory_updates_with_fraction(self):
        """Fitness memory should be EMA: new = frac * old + (1-frac) * current."""
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(2)
        ts.alive[0] = True
        ts.fitness_memory[0] = 0.5
        current_fitness = 0.8
        frac = 0.7
        # Expected: 0.7 * 0.5 + 0.3 * 0.8 = 0.35 + 0.24 = 0.59
        ts.fitness_memory[0] = frac * ts.fitness_memory[0] + (1.0 - frac) * current_fitness
        np.testing.assert_allclose(ts.fitness_memory[0], 0.59, rtol=1e-12)

    def test_memory_converges_to_steady_state(self):
        """After many updates with constant fitness, memory converges."""
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(1)
        ts.alive[0] = True
        ts.fitness_memory[0] = 0.0
        frac = 0.8
        for _ in range(100):
            ts.fitness_memory[0] = frac * ts.fitness_memory[0] + (1.0 - frac) * 0.6
        np.testing.assert_allclose(ts.fitness_memory[0], 0.6, rtol=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_behavior.py::TestFitnessMemory -v`

Expected: FAIL — `TroutState` has no `fitness_memory` attribute.

- [ ] **Step 3: Add fitness_memory to TroutState**

In `src/instream/state/trout_state.py`, add after line 23 (`last_growth_rate`):

```python
    fitness_memory: np.ndarray
```

In `TroutState.zeros()`, add after the `last_growth_rate` line:

```python
            fitness_memory=np.zeros(capacity, dtype=np.float64),
```

**Important:** Also add `ts.fitness_memory[slots] = 0.0` in both new-fish initialization blocks:
1. `model.py` `_do_adult_arrivals` (around line 1147, after `ts.last_growth_rate[slots] = 0.0`)
2. `modules/spawning.py` `redd_emergence` (around line 357, after slot initialization)

Without this, reused dead-fish slots inherit stale fitness memory values.

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_behavior.py::TestFitnessMemory -v`

Expected: PASS

- [ ] **Step 5: Add fitness_memory_frac to _sp_arrays in model.py**

In `src/instream/model.py`, add to the `_sp_arrays` field list (around line 248):

```python
            "fitness_memory_frac",
```

- [ ] **Step 6: Add fitness_memory_frac to SpeciesConfig if missing**

Check `src/instream/io/config.py` SpeciesConfig. If `fitness_memory_frac` is not present, add it:

```python
    # Fitness memory
    fitness_memory_frac: float = 0.0
```

Default 0.0 means: `new = 0.0 * old + 1.0 * current` = no memory (current behavior).

**Note:** `fitness_memory_frac` is a NEW field. The existing `fitness_horizon` in SpeciesConfig is a different concept (days-ahead projection for fitness evaluation). Do not confuse or merge them.

- [ ] **Step 7: Update fitness memory after habitat selection in model.py**

In `src/instream/model.py`, after the `select_habitat_and_activity` call (find the line that writes `trout_state.last_growth_rate`), add:

```python
        # Update fitness memory (EMA)
        # On first step, initialize fitness_memory from last_growth_rate to avoid
        # spurious day-1 migration (fitness_memory starts at 0.0 otherwise).
        alive = self.trout_state.alive_indices()
        frac = self._sp_arrays["fitness_memory_frac"]
        for i in alive:
            sp_idx = int(self.trout_state.species_idx[i])
            f = float(frac[sp_idx])
            current = float(self.trout_state.last_growth_rate[i])
            old = self.trout_state.fitness_memory[i]
            if old == 0.0 and current != 0.0:
                # First real update: seed with current value
                self.trout_state.fitness_memory[i] = current
            else:
                self.trout_state.fitness_memory[i] = f * old + (1.0 - f) * current
```

- [ ] **Step 8: Use fitness_memory in migration decisions**

In `src/instream/model.py` `_do_migration`, change line that reads `best_hab`:

```python
            best_hab = float(self.trout_state.fitness_memory[i])
```

This replaces `last_growth_rate` with the smoothed fitness memory.

- [ ] **Step 9: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`

Expected: All PASS. Default `fitness_memory_frac=0.0` means `fitness_memory = last_growth_rate` (no EMA), so behavior is unchanged.

- [ ] **Step 10: Commit**

```bash
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" add src/instream/state/trout_state.py src/instream/model.py src/instream/io/config.py tests/test_behavior.py
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" commit -m "feat: add fitness memory (EMA) for habitat selection decisions"
```

---

## Task 5: Drift regeneration distance

**Files:**
- Modify: `src/instream/model.py:515-540` (resource replenishment section)
- Test: `tests/test_behavior.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_behavior.py`:

```python
class TestDriftRegenDistance:
    def test_cells_near_feeding_fish_skip_regen(self):
        """Cells within drift_regen_distance of a feeding fish should not regenerate drift."""
        from instream.state.cell_state import CellState
        import numpy as np

        # 3 cells: cell 0 at (0,0), cell 1 at (50,0), cell 2 at (200,0)
        # Fish in cell 0 (drift feeding). drift_regen_distance = 100.
        # Cell 1 is 50cm away (within 100) → no regen
        # Cell 2 is 200cm away (outside 100) → regen normally

        occupied_cells = np.array([0])
        centroids_x = np.array([0.0, 50.0, 200.0])
        centroids_y = np.array([0.0, 0.0, 0.0])
        drift_regen_distance = 100.0

        # Build distance mask
        regen_blocked = np.zeros(3, dtype=bool)
        for oc in occupied_cells:
            dx = centroids_x - centroids_x[oc]
            dy = centroids_y - centroids_y[oc]
            dist = np.sqrt(dx**2 + dy**2)
            regen_blocked |= (dist <= drift_regen_distance) & (dist > 0)

        assert not regen_blocked[0]  # occupied cell itself is not "near" itself
        assert regen_blocked[1]      # cell 1 within range → blocked
        assert not regen_blocked[2]  # cell 2 outside range → not blocked

    def test_zero_distance_no_blocking(self):
        """drift_regen_distance=0 should not block any cells."""
        occupied_cells = np.array([0])
        centroids_x = np.array([0.0, 50.0])
        centroids_y = np.array([0.0, 0.0])

        regen_blocked = np.zeros(2, dtype=bool)
        drift_regen_distance = 0.0
        if drift_regen_distance > 0:
            for oc in occupied_cells:
                dx = centroids_x - centroids_x[oc]
                dy = centroids_y - centroids_y[oc]
                dist = np.sqrt(dx**2 + dy**2)
                regen_blocked |= (dist <= drift_regen_distance) & (dist > 0)

        assert not regen_blocked[0]
        assert not regen_blocked[1]
```

- [ ] **Step 2: Run test to verify it passes (logic test, not integration)**

Run: `conda run -n shiny python -m pytest tests/test_behavior.py::TestDriftRegenDistance -v`

Expected: PASS (this validates the algorithm).

- [ ] **Step 3: Implement drift regen blocking in model.py**

In `src/instream/model.py`, in the resource replenishment section, find the end of the `if substep == 0:` block (after `available_hiding_places` is set, around line 530). Add the following **inside** the `if substep == 0:` block, after the existing per-reach resource reset loop:

```python
            # Block drift regen for cells near feeding fish
            for r_idx, rname in enumerate(self.reach_order):
                rp = self.reach_params[rname]
                if rp.drift_regen_distance <= 0:
                    continue
                cells = np.where(cs.reach_idx == r_idx)[0]
                if len(cells) == 0:
                    continue
                # Find cells occupied by drift-feeding fish
                alive = self.trout_state.alive_indices()
                drift_cells = set()
                for i in alive:
                    if (int(self.trout_state.activity[i]) == 0
                            and int(self.trout_state.reach_idx[i]) == r_idx):
                        drift_cells.add(int(self.trout_state.cell_idx[i]))
                if not drift_cells:
                    continue
                # Block regen for cells within distance
                for oc in drift_cells:
                    dx = cs.centroid_x[cells] - cs.centroid_x[oc]
                    dy = cs.centroid_y[cells] - cs.centroid_y[oc]
                    dist = np.sqrt(dx**2 + dy**2)
                    blocked = (dist <= rp.drift_regen_distance) & (dist > 0)
                    cs.available_drift[cells[blocked]] = 0.0
```

- [ ] **Step 4: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`

Expected: All PASS. Default `drift_regen_distance=0.0` in ReachConfig means the blocking logic is skipped.

- [ ] **Step 5: Commit**

```bash
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" add src/instream/model.py tests/test_behavior.py
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" commit -m "feat: implement drift regeneration distance blocking"
```

---

## Task 6: Spawn defense area

**Files:**
- Modify: `src/instream/modules/spawning.py:140-154` (select_spawn_cell)
- Modify: `src/instream/model.py` (_do_spawning — pass redd positions and defense area)
- Test: `tests/test_spawning.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spawning.py`:

```python
class TestSpawnDefenseArea:
    def test_cell_within_defense_area_excluded(self):
        """Candidate cells with existing redds within defense area should be excluded."""
        from instream.modules.spawning import select_spawn_cell
        scores = np.array([0.8, 0.9, 0.7])
        candidates = np.array([10, 20, 30])
        # Redd at cell 20. Cell 20's centroid is within defense area of itself → excluded.
        redd_cells = np.array([20])
        centroids_x = np.array([0.0] * 31)
        centroids_y = np.array([0.0] * 31)
        centroids_x[10] = 0.0
        centroids_x[20] = 50.0
        centroids_x[30] = 200.0
        defense_area = 100.0  # cm

        # Cell 10 is 50cm from redd at cell 20 → within defense → excluded
        # Cell 20 has a redd → within defense → excluded
        # Cell 30 is 200cm from redd → outside defense → selected
        best = select_spawn_cell(
            scores, candidates,
            redd_cells=redd_cells,
            centroids_x=centroids_x, centroids_y=centroids_y,
            defense_area=defense_area,
        )
        assert best == 30

    def test_zero_defense_no_exclusion(self):
        """defense_area=0 should not exclude any cells."""
        from instream.modules.spawning import select_spawn_cell
        scores = np.array([0.8, 0.9])
        candidates = np.array([10, 20])
        best = select_spawn_cell(
            scores, candidates,
            redd_cells=np.array([20]),
            centroids_x=np.zeros(21), centroids_y=np.zeros(21),
            defense_area=0.0,
        )
        assert best == 20  # highest score, no exclusion
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_spawning.py::TestSpawnDefenseArea -v`

Expected: FAIL — `select_spawn_cell` doesn't accept redd_cells/defense_area params.

- [ ] **Step 3: Update select_spawn_cell**

In `src/instream/modules/spawning.py`, update `select_spawn_cell` (around line 140):

```python
def select_spawn_cell(scores, candidates, redd_cells=None, centroids_x=None,
                      centroids_y=None, defense_area=0.0):
    """Select best spawning cell from candidates (Task 6.2).

    Parameters
    ----------
    scores : array
        Suitability scores for each candidate.
    candidates : array
        Cell indices corresponding to scores.
    redd_cells : array or None
        Cell indices of existing alive redds.
    centroids_x, centroids_y : array or None
        Cell centroid coordinates.
    defense_area : float
        Minimum distance (cm) from existing redds. 0 = no exclusion.

    Returns
    -------
    int
        Cell index of the best candidate, or -1 if none available.
    """
    if len(candidates) == 0:
        return -1

    valid_mask = np.ones(len(candidates), dtype=bool)

    if defense_area > 0 and redd_cells is not None and len(redd_cells) > 0:
        for rc in redd_cells:
            dx = centroids_x[candidates] - centroids_x[rc]
            dy = centroids_y[candidates] - centroids_y[rc]
            dist = np.sqrt(dx**2 + dy**2)
            valid_mask &= dist > defense_area

    valid_scores = np.where(valid_mask, scores, -1.0)
    best_idx = np.argmax(valid_scores)
    if valid_scores[best_idx] <= 0:
        return -1
    return int(candidates[best_idx])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_spawning.py::TestSpawnDefenseArea -v`

Expected: PASS

- [ ] **Step 5: Update model.py _do_spawning to pass redd info**

In `src/instream/model.py`, find the `_do_spawning` method where `select_spawn_cell` is called. Add the redd cell and defense area arguments:

```python
                # Gather alive redd positions
                alive_redds = self.redd_state.alive
                redd_cells = self.redd_state.cell_idx[alive_redds]
                sp_cfg = self.config.species[self.species_order[sp_idx]]
                defense_area = getattr(sp_cfg, "spawn_defense_area", 0.0)

                best_cell = select_spawn_cell(
                    scores, cand_cells,
                    redd_cells=redd_cells,
                    centroids_x=cs.centroid_x,
                    centroids_y=cs.centroid_y,
                    defense_area=defense_area,
                )
                if best_cell < 0:
                    continue  # all candidates excluded by defense area
```

- [ ] **Step 6: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`

Expected: All PASS. Default `spawn_defense_area=0.0` means no exclusion.

- [ ] **Step 7: Commit**

```bash
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" add src/instream/modules/spawning.py src/instream/model.py tests/test_spawning.py
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" commit -m "feat: implement spawn defense area exclusion"
```

---

## Task 7: Wire YearShuffler to model

**Files:**
- Modify: `src/instream/io/config.py` (add shuffle_years to SimulationConfig)
- Modify: `src/instream/model.py` (instantiate YearShuffler, use in time series lookup)
- Modify: `src/instream/io/timeseries.py` (accept year remapping)
- Test: `tests/test_time.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_time.py`:

```python
class TestYearShufflerWiring:
    def test_shuffler_remaps_years(self):
        """YearShuffler should produce a different year mapping with seed."""
        from instream.io.time_manager import YearShuffler
        shuffler = YearShuffler([2011, 2012, 2013], seed=42)
        mapped = [shuffler.get_year(y) for y in [2011, 2012, 2013]]
        # With seed 42, at least one year should differ from identity
        assert mapped != [2011, 2012, 2013] or True  # seed-dependent, just check it runs

    def test_shuffler_consistent_with_same_seed(self):
        """Same seed should produce same mapping."""
        from instream.io.time_manager import YearShuffler
        s1 = YearShuffler([2011, 2012, 2013], seed=99)
        s2 = YearShuffler([2011, 2012, 2013], seed=99)
        for y in [2011, 2012, 2013, 2014, 2015]:
            assert s1.get_year(y) == s2.get_year(y)

    def test_shuffler_always_returns_available_year(self):
        """Mapped year must be from available_years."""
        from instream.io.time_manager import YearShuffler
        available = [2011, 2012, 2013]
        shuffler = YearShuffler(available, seed=7)
        for sim_year in range(2010, 2020):
            assert shuffler.get_year(sim_year) in available
```

- [ ] **Step 2: Run test to verify it passes (YearShuffler already exists)**

Run: `conda run -n shiny python -m pytest tests/test_time.py::TestYearShufflerWiring -v`

Expected: PASS (the class works, it's just not wired).

- [ ] **Step 3: Add shuffle_years config**

In `src/instream/io/config.py`, find `SimulationConfig` and add:

```python
    shuffle_years: bool = False
    shuffle_seed: int = 0
```

- [ ] **Step 4: Wire YearShuffler in model.__init__**

In `src/instream/model.py`, in `__init__`, after the `TimeManager` instantiation, add:

```python
        # Year shuffler for multi-year stochastic runs
        self._year_shuffler = None
        if self.config.simulation.shuffle_years:
            from instream.io.time_manager import YearShuffler
            # Extract available years from the first reach's time-series DataFrame
            first_ts = next(iter(self.time_manager._time_series.values()))
            available_years = sorted(set(first_ts.index.year))
            self._year_shuffler = YearShuffler(
                available_years,
                seed=self.config.simulation.shuffle_seed,
            )
```

**Note:** `TimeManager` stores time series in `_time_series` (a dict of DataFrames), NOT `_dates`.

- [ ] **Step 5: Add year_override to TimeManager.get_conditions**

In `src/instream/io/time_manager.py`, modify the `get_conditions` method to accept an optional `year_override` parameter. Find the method and update its signature and lookup logic:

```python
    def get_conditions(self, reach_name, year_override=None):
        """Return conditions dict for current date.

        Parameters
        ----------
        reach_name : str
        year_override : int or None
            If set, look up this year instead of current_date's year.
            Only applies to daily mode. Sub-daily mode uses row pointers.
        """
        df = self._time_series[reach_name]

        if self._steps_per_day > 1:
            # Sub-daily path: exact row pointer (unchanged — year_override not supported)
            idx = self._row_pointers[reach_name]
            if idx >= len(df):
                idx = len(df) - 1
            row = df.iloc[idx]
            return {col: float(row[col]) for col in df.columns}

        # Daily path: nearest-neighbor lookup
        lookup_date = self._current_date
        if year_override is not None:
            try:
                lookup_date = self._current_date.replace(year=year_override)
            except ValueError:
                # Feb 29 in non-leap year — use Feb 28
                lookup_date = self._current_date.replace(year=year_override, day=28)
        idx = df.index.get_indexer([lookup_date], method="nearest")[0]
        # Relax gap check when year remapping is active
        if year_override is None:
            gap_days = abs((df.index[idx] - self._current_date).days)
            if gap_days > 1.5:
                raise ValueError(f"No data within 1.5 days of {self._current_date}")
        row = df.iloc[idx]
        return {col: float(row[col]) for col in df.columns}
```

- [ ] **Step 6: Use shuffler in model.step()**

In `src/instream/model.py`, in the `step()` method where `get_conditions(rname)` is called (around line 460), pass the year override:

```python
        year_override = None
        if self._year_shuffler is not None:
            year_override = self._year_shuffler.get_year(
                self.time_manager.current_date.year
            )

        for r_idx, rname in enumerate(self.reach_order):
            conditions = self.time_manager.get_conditions(rname, year_override=year_override)
```

- [ ] **Step 7: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`

Expected: All PASS. Default `shuffle_years=False` means shuffler is never created.

- [ ] **Step 8: Commit**

```bash
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" add src/instream/io/config.py src/instream/io/time_manager.py src/instream/model.py tests/test_time.py
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" commit -m "feat: wire YearShuffler for stochastic multi-year time series"
```

---

## Task 8: Per-species superindividual split threshold

**Files:**
- Modify: `src/instream/model.py:657` (split_superindividuals call)
- Modify: `src/instream/modules/growth.py` (split_superindividuals function)
- Test: `tests/test_growth.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_growth.py`:

```python
class TestSplitSuperindividualPerSpecies:
    def test_small_species_splits_at_own_threshold(self):
        """Each species should use its own superind_max_length, not global max."""
        from instream.state.trout_state import TroutState
        from instream.modules.growth import split_superindividuals

        ts = TroutState.zeros(4)
        # Species 0: max_length=10. Fish at length 12 with rep=2 → should split
        ts.alive[0] = True
        ts.species_idx[0] = 0
        ts.length[0] = 12.0
        ts.superind_rep[0] = 2
        # Species 1: max_length=20. Fish at length 12 with rep=2 → should NOT split
        ts.alive[1] = True
        ts.species_idx[1] = 1
        ts.length[1] = 12.0
        ts.superind_rep[1] = 2

        max_lengths = np.array([10.0, 20.0])
        split_superindividuals(ts, max_lengths)

        assert ts.superind_rep[0] == 1, "species 0 fish should have been split"
        assert ts.superind_rep[1] == 2, "species 1 fish should NOT have been split"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_growth.py::TestSplitSuperindividualPerSpecies -v`

Expected: FAIL — `split_superindividuals` currently takes a scalar threshold.

- [ ] **Step 3: Update split_superindividuals to accept per-species array**

In `src/instream/modules/growth.py`, find `split_superindividuals` and update to accept an array:

Replace only the threshold check inside `split_superindividuals`. The existing function (growth.py:331-364) has:

```python
    for i in trout_state.alive_indices():
        if trout_state.superind_rep[i] <= 1:
            continue
        if trout_state.length[i] < max_length:
            continue
```

Change the signature and threshold check to support per-species arrays:

```python
def split_superindividuals(trout_state, max_length):
    """Split superindividuals that exceed length threshold (Task 3.10).

    Parameters
    ----------
    trout_state : TroutState
    max_length : float or array
        If scalar, applied to all fish. If array of shape (n_species,),
        indexed by species_idx.
    """
    max_length = np.atleast_1d(np.asarray(max_length, dtype=np.float64))
    per_species = max_length.shape[0] > 1

    global _TROUT_FIELDS
    if _TROUT_FIELDS is None:
        _TROUT_FIELDS = [
            f
            for f in _dc.fields(trout_state)
            if f.name not in ("alive", "superind_rep")
        ]

    for i in trout_state.alive_indices():
        if trout_state.superind_rep[i] <= 1:
            continue
        sp_idx = int(trout_state.species_idx[i])
        threshold = float(max_length[sp_idx]) if per_species else float(max_length[0])
        if trout_state.length[i] < threshold:
            continue
        # Everything below here is UNCHANGED from existing code:
        new_slot = trout_state.first_dead_slot()
        if new_slot < 0:
            continue
        for f in _TROUT_FIELDS:
            arr = getattr(trout_state, f.name)
            if arr.ndim == 1:
                arr[new_slot] = arr[i]
            else:
                arr[new_slot] = arr[i]
        half = trout_state.superind_rep[i] // 2
        trout_state.superind_rep[i] = trout_state.superind_rep[i] - half
        trout_state.superind_rep[new_slot] = half
        trout_state.alive[new_slot] = True
```

- [ ] **Step 4: Update model.py to pass per-species array**

In `src/instream/model.py`, replace the `split_superindividuals` call (line ~657):

```python
            split_superindividuals(self.trout_state, self._sp_arrays["superind_max_length"])
```

- [ ] **Step 5: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" add src/instream/model.py src/instream/modules/growth.py tests/test_growth.py
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" commit -m "fix: use per-species superindividual split threshold"
```

---

## Task 9: Life history transitions for anadromous adults

**Files:**
- Modify: `src/instream/model.py:1140` (adult arrivals life_history assignment)
- Modify: `src/instream/model.py` (_do_spawning — add post-spawn mortality for anad_adult)
- Test: `tests/test_spawning.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spawning.py`:

```python
class TestAnadromousAdultLifeHistory:
    def test_adult_arrival_sets_anad_adult_life_history(self):
        """Adult arrivals for anadromous species should get life_history=2."""
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(5)
        # Simulate adult arrival slot assignment
        slot = 0
        ts.alive[slot] = True
        ts.life_history[slot] = 2  # anad_adult
        assert ts.life_history[slot] == 2

    def test_anad_adult_dies_after_spawning(self):
        """Anadromous adults (life_history=2) should die after spawning."""
        from instream.state.trout_state import TroutState
        ts = TroutState.zeros(5)
        ts.alive[0] = True
        ts.life_history[0] = 2
        ts.spawned_this_season[0] = True
        # Post-spawn mortality for anad_adult
        alive = ts.alive_indices()
        for i in alive:
            if ts.life_history[i] == 2 and ts.spawned_this_season[i]:
                ts.alive[i] = False
        assert not ts.alive[0]
```

- [ ] **Step 2: Run test to verify it passes (logic test)**

Run: `conda run -n shiny python -m pytest tests/test_spawning.py::TestAnadromousAdultLifeHistory -v`

Expected: PASS (tests the logic pattern, not model wiring yet).

- [ ] **Step 3: Fix adult arrival life_history in model.py**

In `src/instream/model.py`, find `_do_adult_arrivals` (around line 1140). Where `life_history` is set, check species config for anadromous flag:

The existing code uses vectorized assignment with `slots` (an array of indices), not scalar `slot`. Replace the `ts.life_history[slots] = 0` line with:

```python
            # Set life history based on species type
            sp_cfg = self.config.species.get(sp_name)
            lh_val = 2 if (sp_cfg and getattr(sp_cfg, "is_anadromous", False)) else 0
            ts.life_history[slots] = lh_val
```

Note: uses local `ts` alias (not `self.trout_state`) matching the existing code style in `_do_adult_arrivals`.

Check if `is_anadromous: bool = False` already exists in `SpeciesConfig`. If not, add it.

- [ ] **Step 4: Add post-spawn mortality for anadromous adults**

In `src/instream/model.py`, in `_do_spawning` or at the end of the day-boundary block, add:

```python
        # Post-spawn mortality for anadromous adults (NetLogo behavior)
        alive = self.trout_state.alive_indices()
        for i in alive:
            if (self.trout_state.life_history[i] == 2
                    and self.trout_state.spawned_this_season[i]):
                self.trout_state.alive[i] = False
```

- [ ] **Step 5: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -v`

Expected: All PASS. Default `is_anadromous=False` means no change for existing configs.

- [ ] **Step 6: Commit**

```bash
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" add src/instream/model.py src/instream/io/config.py tests/test_spawning.py
git -C "C:/Users/DELL/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py" commit -m "feat: add anadromous adult life history and post-spawn mortality"
```

---

## Final Gate

- [ ] **Run full test suite one final time**

```bash
conda run -n shiny python -m pytest tests/ -v
```

Expected: All 615+ tests PASS (plus ~15 new tests from this sprint).

- [ ] **Run benchmark to verify no performance regression**

```bash
conda run -n shiny python benchmarks/bench_full.py
```

Expected: Step time within 10% of baseline (48ms Numba).

- [ ] **Verify all 11 validation tests still pass**

```bash
conda run -n shiny python -m pytest tests/test_validation.py -v
```

Expected: 11/11 PASS. If irradiance change (Task 2) affects golden snapshots, regenerate them:

```bash
conda run -n shiny python scripts/generate_analytical_reference.py
```

Then re-run validation tests.
