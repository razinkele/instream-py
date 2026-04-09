# Fix All Deep Analysis Issues — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all critical, warning, and tech-debt issues identified by the 5-agent deep codebase analysis (numerical reviewer, validation checker, performance profiler, architecture explorer, NetLogo source finder).

**Architecture:** Issues span 4 areas: (1) backend API consistency, (2) logistic function parity, (3) Numba velocity clamping, (4) performance hot-loop vectorization. All changes preserve the existing 682-test suite.

**Execution order:** Task 7 (remove `fitness_all`) must run BEFORE Tasks 1 and 2 (rewrite JAX backend methods), because Tasks 1/2 change line counts in `jax_backend/__init__.py` which would shift Task 7's target lines. Alternatively, Task 7 can use content-based deletion (search for the method text) regardless of order. All other tasks are independent.

**Tech Stack:** Python 3.11+, NumPy, Numba 0.64, JAX 0.7.2, pytest, conda env `shiny`

**Test command:** `conda run -n shiny python -m pytest tests/ -x -q --tb=short`

---

## File Map

| File | Changes |
|------|---------|
| `src/instream/backends/jax_backend/__init__.py` | Fix `survival()` and `growth_rate()` signatures to match Protocol |
| `src/instream/backends/_interface.py` | Remove phantom `fitness_all` method |
| `src/instream/backends/numpy_backend/__init__.py` | Remove `fitness_all` stub, fix logistic degenerate case |
| `src/instream/backends/numba_backend/__init__.py` | Remove `fitness_all` stub, add velocity clamping, fix logistic degenerate case |
| `src/instream/backends/numba_backend/fitness.py` | Fix `_logistic` degenerate case (0.5 → 0.9/0.1), fix `condition == 1.0` |
| `src/instream/backends/numba_backend/spatial.py` | Single-pass candidate building |
| `src/instream/modules/behavior.py` | Fix `evaluate_logistic` and `evaluate_logistic_array` degenerate case |
| `src/instream/modules/survival.py` | Fix `condition == 1.0` exact float comparison |
| `src/instream/model.py` | Add hydraulic shape assertion, vectorize `_apply_accumulated_growth`, vectorize fitness EMA |
| `tests/test_backends.py` | Add JAX signature test, logistic degenerate test, velocity clamping test |
| `tests/test_behavior.py` | Add logistic degenerate case test |
| `tests/test_survival.py` | Add condition near-1.0 test |
| `tests/test_spatial_visualization.py` | Update `test_equal_L1_L9_gives_half_max` for new 0.9 degenerate behavior |
| `tests/test_perf.py` | Add single-pass candidate benchmark assertion |

---

### Task 1: Fix JAX Backend `survival()` Signature

The JAX `survival()` takes positional args in a completely different order than the Protocol and numpy/numba backends. The model calls `self.backend.survival(lengths, weights, conditions, temps, depths, **kwargs)` (model.py:658). The JAX backend has positional args `(lengths, depths, velocities, light, temperatures, conditions, activities, ...)` — so `weights` would be received as `depths`, producing silent garbage.

**Note on condition survival:** The existing JAX code has a comment saying "Condition survival is NOT included here (handled separately)" but this is INCORRECT — both numpy and numba backends include `s_cond` in the survival product (numpy_backend line 401: `return s_ht * s_str * s_cond * s_fp * s_tp`). The fix below correctly includes condition survival to match numpy/numba behavior.

**Files:**
- Modify: `src/instream/backends/jax_backend/__init__.py:382-526`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_backends.py`:

```python
class TestJaxBackendSignature:
    """Verify JAX backend survival/growth match numpy backend signatures."""

    @pytest.fixture
    def backends(self):
        from instream.backends.numpy_backend import NumpyBackend
        try:
            from instream.backends.jax_backend import JaxBackend
        except ImportError:
            pytest.skip("JAX not installed")
        return NumpyBackend(), JaxBackend()

    def test_survival_matches_numpy(self, backends):
        np_be, jax_be = backends
        rng = np.random.default_rng(42)
        n = 5
        lengths = rng.uniform(3, 20, n)
        weights = rng.uniform(1, 100, n)
        conditions = rng.uniform(0.5, 1.0, n)
        temperatures = np.full(n, 12.0)
        depths = rng.uniform(10, 200, n)
        kwargs = dict(
            velocities=rng.uniform(5, 50, n),
            lights=rng.uniform(50, 500, n),
            activities=rng.choice([0, 1, 2], n).astype(np.int32),
            pisciv_densities=rng.uniform(0, 0.5, n),
            dist_escapes=rng.uniform(10, 100, n),
            available_hidings=rng.uniform(0, 10, n),
            superind_reps=np.ones(n, dtype=np.int32),
            sp_mort_high_temp_T1=np.full(n, 28.0),
            sp_mort_high_temp_T9=np.full(n, 24.0),
            sp_mort_strand_survival_when_dry=np.full(n, 0.5),
            sp_mort_condition_S_at_K5=np.full(n, 0.8),
            sp_mort_condition_S_at_K8=np.full(n, 0.992),
            rp_fish_pred_min=np.full(n, 0.99),
            sp_mort_fish_pred_L1=np.full(n, 10.0),
            sp_mort_fish_pred_L9=np.full(n, 3.0),
            sp_mort_fish_pred_D1=np.full(n, 50.0),
            sp_mort_fish_pred_D9=np.full(n, 10.0),
            sp_mort_fish_pred_P1=np.full(n, 0.5),
            sp_mort_fish_pred_P9=np.full(n, 0.1),
            sp_mort_fish_pred_I1=np.full(n, 200.0),
            sp_mort_fish_pred_I9=np.full(n, 50.0),
            sp_mort_fish_pred_T1=np.full(n, 25.0),
            sp_mort_fish_pred_T9=np.full(n, 15.0),
            sp_mort_fish_pred_hiding_factor=np.full(n, 0.5),
            rp_terr_pred_min=np.full(n, 0.99),
            sp_mort_terr_pred_L1=np.full(n, 15.0),
            sp_mort_terr_pred_L9=np.full(n, 5.0),
            sp_mort_terr_pred_D1=np.full(n, 50.0),
            sp_mort_terr_pred_D9=np.full(n, 10.0),
            sp_mort_terr_pred_V1=np.full(n, 50.0),
            sp_mort_terr_pred_V9=np.full(n, 10.0),
            sp_mort_terr_pred_I1=np.full(n, 200.0),
            sp_mort_terr_pred_I9=np.full(n, 50.0),
            sp_mort_terr_pred_H1=np.full(n, 50.0),
            sp_mort_terr_pred_H9=np.full(n, 10.0),
            sp_mort_terr_pred_hiding_factor=np.full(n, 0.5),
        )
        np_result = np_be.survival(lengths, weights, conditions, temperatures, depths, **kwargs)
        jax_result = jax_be.survival(lengths, weights, conditions, temperatures, depths, **kwargs)
        np.testing.assert_allclose(jax_result, np_result, rtol=1e-10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_backends.py::TestJaxBackendSignature::test_survival_matches_numpy -v`
Expected: FAIL (TypeError or wrong values — JAX positional args don't match)

- [ ] **Step 3: Rewrite JAX `survival()` to match Protocol signature**

Replace the entire `survival` method in `src/instream/backends/jax_backend/__init__.py` (lines 382-526) with a version that takes the same `(lengths, weights, conditions, temperatures, depths, **params)` signature as numpy/numba:

```python
    def survival(self, lengths, weights, conditions, temperatures, depths, **params):
        """Vectorized survival probability using JAX.

        Signature matches NumpyBackend.survival() and the ComputeBackend Protocol.
        """
        lengths = jnp.asarray(lengths)
        weights = jnp.asarray(weights)
        conditions = jnp.asarray(conditions)
        temperatures = jnp.asarray(temperatures)
        depths = jnp.asarray(depths)

        velocities = jnp.asarray(params["velocities"])
        light = jnp.asarray(params["lights"])
        activities = jnp.asarray(params["activities"], dtype=jnp.int32)
        dist_escape = jnp.asarray(params["dist_escapes"])
        available_hiding = jnp.asarray(params["available_hidings"])
        superind_rep = jnp.asarray(params["superind_reps"])
        pisciv_density = jnp.asarray(params["pisciv_densities"])

        _ln81 = jnp.log(81.0)

        def _logistic(x, L1, L9):
            midpoint = (L1 + L9) / 2.0
            degenerate = jnp.abs(L9 - L1) < 1e-15
            slope = jnp.where(degenerate, 0.0, _ln81 / jnp.where(degenerate, 1.0, L9 - L1))
            raw = 1.0 / (1.0 + jnp.exp(-slope * (x - midpoint)))
            return jnp.where(degenerate, jnp.where(x >= L1, 0.9, 0.1), raw)

        # 1. High temperature survival
        s_high_temp = _logistic(
            temperatures,
            params["sp_mort_high_temp_T1"],
            params["sp_mort_high_temp_T9"],
        )

        # 2. Stranding survival
        s_stranding = jnp.where(
            depths > 0.0, 1.0, params["sp_mort_strand_survival_when_dry"]
        )

        # 3. Condition survival (two-piece linear)
        cond = conditions
        S_at_K5 = params["sp_mort_condition_S_at_K5"]
        S_at_K8 = params["sp_mort_condition_S_at_K8"]
        slope_upper = 5.0 - 5.0 * S_at_K8
        intercept_upper = 5.0 * S_at_K8 - 4.0
        s_upper = cond * slope_upper + intercept_upper
        slope_lower = (S_at_K8 - S_at_K5) / 0.3
        intercept_lower = S_at_K5 - 0.5 * slope_lower
        s_lower = cond * slope_lower + intercept_lower
        s_cond = jnp.where(cond > 0.8, s_upper, s_lower)
        s_cond = jnp.where(cond <= 0.0, 0.0, s_cond)
        s_cond = jnp.where(cond >= 1.0, 1.0, s_cond)
        s_cond = jnp.clip(s_cond, 0.0, 1.0)

        # 4. Fish predation survival
        is_hiding = activities == 2
        hide_fp = jnp.where(
            is_hiding, params["sp_mort_fish_pred_hiding_factor"], 0.0
        )
        fp_risk = (
            (1.0 - _logistic(lengths, params["sp_mort_fish_pred_L1"], params["sp_mort_fish_pred_L9"]))
            * (1.0 - _logistic(depths, params["sp_mort_fish_pred_D1"], params["sp_mort_fish_pred_D9"]))
            * (1.0 - _logistic(pisciv_density, params["sp_mort_fish_pred_P1"], params["sp_mort_fish_pred_P9"]))
            * (1.0 - _logistic(light, params["sp_mort_fish_pred_I1"], params["sp_mort_fish_pred_I9"]))
            * (1.0 - _logistic(temperatures, params["sp_mort_fish_pred_T1"], params["sp_mort_fish_pred_T9"]))
            * (1.0 - hide_fp)
        )
        fp_min = params["rp_fish_pred_min"]
        s_fp = fp_min + (1.0 - fp_min) * (1.0 - fp_risk)

        # 5. Terrestrial predation survival
        in_hiding = is_hiding & (available_hiding >= superind_rep)
        hide_tp = jnp.where(
            in_hiding, params["sp_mort_terr_pred_hiding_factor"], 0.0
        )
        tp_risk = (
            (1.0 - _logistic(lengths, params["sp_mort_terr_pred_L1"], params["sp_mort_terr_pred_L9"]))
            * (1.0 - _logistic(depths, params["sp_mort_terr_pred_D1"], params["sp_mort_terr_pred_D9"]))
            * (1.0 - _logistic(velocities, params["sp_mort_terr_pred_V1"], params["sp_mort_terr_pred_V9"]))
            * (1.0 - _logistic(light, params["sp_mort_terr_pred_I1"], params["sp_mort_terr_pred_I9"]))
            * (1.0 - _logistic(dist_escape, params["sp_mort_terr_pred_H1"], params["sp_mort_terr_pred_H9"]))
            * (1.0 - hide_tp)
        )
        tp_min = params["rp_terr_pred_min"]
        s_tp = tp_min + (1.0 - tp_min) * (1.0 - tp_risk)

        return np.asarray(s_high_temp * s_stranding * s_cond * s_fp * s_tp)
```

- [ ] **Step 4: Update existing JAX survival tests to use new signature**

The 4 existing tests (`test_jax_survival_matches_python`, `test_jax_survival_hiding_fish`, `test_jax_survival_stranding`, `test_jax_survival_batch` at `tests/test_backends.py` lines 607-840) call `jax_b.survival(lengths=..., depths=..., velocities=..., ...)` using the OLD positional keyword names. Update them to use the new Protocol signature: `jax_b.survival(lengths, weights, conditions, temperatures, depths, velocities=..., lights=..., activities=..., pisciv_densities=..., dist_escapes=..., available_hidings=..., superind_reps=..., sp_mort_*=..., rp_*=...)`. The key renames:
- `light=` → `lights=`
- `dist_escape=` → `dist_escapes=`
- `available_hiding=` → `available_hidings=`
- `superind_rep=` → `superind_reps=`
- `pisciv_density=` → `pisciv_densities=`
- Add `weights=` and `conditions=` as positional args
- Add all `sp_mort_*` and `rp_*` keyword params that numpy backend expects

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_backends.py::TestJaxBackendSignature -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/backends/jax_backend/__init__.py tests/test_backends.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "fix: align JAX backend survival() signature with Protocol and numpy/numba backends"
```

---

### Task 2: Fix JAX Backend `growth_rate()` Signature

Same issue as survival: JAX `growth_rate()` takes `(activity, lengths, weights, depth, velocity, light, turbidity, temperature, ...)` as explicit positional args. The Protocol defines `(lengths, weights, temperatures, velocities, depths, **params)`. The model doesn't call `growth_rate()` directly (habitat selection inlines growth), but the interface mismatch prevents correct backend-polymorphic usage.

**Files:**
- Modify: `src/instream/backends/jax_backend/__init__.py:171-380`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_backends.py`:

```python
    def test_growth_rate_matches_numpy(self, backends):
        np_be, jax_be = backends
        rng = np.random.default_rng(42)
        n = 3
        lengths = rng.uniform(5, 15, n)
        weights = rng.uniform(5, 50, n)
        temperatures = np.full(n, 12.0)
        velocities = rng.uniform(5, 40, n)
        depths = rng.uniform(20, 150, n)
        kwargs = dict(
            activities=np.array([0, 1, 2], dtype=np.int32),
            lights=rng.uniform(100, 400, n),
            turbidities=np.full(n, 5.0),
            drift_concs=np.full(n, 1e-10),
            search_prods=np.full(n, 1e-7),
            search_areas=np.full(n, 5000.0),
            available_drifts=np.full(n, 1e6),
            available_searches=np.full(n, 1e6),
            available_shelters=np.full(n, 1e6),
            shelter_speed_fracs=np.full(n, 0.3),
            superind_reps=np.ones(n, dtype=np.int32),
            prev_consumptions=np.zeros(n),
            step_length=1.0,
            cmax_As=np.full(n, 0.628),
            cmax_Bs=np.full(n, -0.3),
            cmax_temp_table_xs=[np.array([0, 5, 10, 15, 20, 25, 30], dtype=np.float64)] * n,
            cmax_temp_table_ys=[np.array([0.0, 0.15, 0.5, 0.98, 1.0, 0.8, 0.0], dtype=np.float64)] * n,
            species_idxs=np.zeros(n, dtype=np.int32),
            react_dist_As=np.full(n, 0.0),
            react_dist_Bs=np.full(n, 0.1),
            turbid_thresholds=np.full(n, 10.0),
            turbid_mins=np.full(n, 0.1),
            turbid_exps=np.full(n, -0.1),
            light_thresholds=np.full(n, 100.0),
            light_mins=np.full(n, 0.1),
            light_exps=np.full(n, -0.01),
            capture_R1s=np.full(n, 0.5),
            capture_R9s=np.full(n, 0.9),
            max_speed_As=np.full(n, 2.5),
            max_speed_Bs=np.full(n, 0.0),
            max_swim_temp_terms=np.full(n, 1.0),
            resp_As=np.full(n, 0.0196),
            resp_Bs=np.full(n, -0.218),
            resp_Ds=np.full(n, 0.03),
            resp_temp_terms=np.full(n, 1.0),
            prey_energy_densities=np.full(n, 3500.0),
            fish_energy_densities=np.full(n, 5900.0),
        )
        np_result = np_be.growth_rate(lengths, weights, temperatures, velocities, depths, **kwargs)
        jax_result = jax_be.growth_rate(lengths, weights, temperatures, velocities, depths, **kwargs)
        np.testing.assert_allclose(jax_result, np_result, rtol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_backends.py::TestJaxBackendSignature::test_growth_rate_matches_numpy -v`
Expected: FAIL (TypeError — wrong positional args)

- [ ] **Step 3: Rewrite JAX `growth_rate()` to match Protocol signature**

Replace `growth_rate` in `src/instream/backends/jax_backend/__init__.py` (lines 171-380):

```python
    def growth_rate(self, lengths, weights, temperatures, velocities, depths, **params):
        """Vectorized growth rate using JAX.

        Signature matches NumpyBackend.growth_rate() and the ComputeBackend Protocol.
        """
        activity = jnp.asarray(params["activities"], dtype=jnp.int32)
        lengths = jnp.asarray(lengths)
        weights = jnp.asarray(weights)
        depth = jnp.asarray(depths)
        velocity = jnp.asarray(velocities)
        temperature = temperatures  # scalar or array
        light = jnp.asarray(params["lights"])
        turbidity = params["turbidities"]  # scalar or per-fish array

        available_drift = jnp.asarray(params["available_drifts"])
        available_search = jnp.asarray(params["available_searches"])
        available_shelter = jnp.asarray(params["available_shelters"])
        superind_rep = jnp.asarray(params["superind_reps"])
        prev_consumption = jnp.asarray(params["prev_consumptions"])
        step_length = float(params["step_length"])

        # Per-fish species params (indexed before call or passed as arrays)
        cmax_A = jnp.asarray(params["cmax_As"])
        cmax_B = jnp.asarray(params["cmax_Bs"])
        sp_idx = params["species_idxs"]
        # Use first species' temp table (all same for single-species)
        cmax_temp_table_x = jnp.asarray(params["cmax_temp_table_xs"][0])
        cmax_temp_table_y = jnp.asarray(params["cmax_temp_table_ys"][0])

        react_dist_A = jnp.asarray(params["react_dist_As"])
        react_dist_B = jnp.asarray(params["react_dist_Bs"])
        turbid_threshold = params["turbid_thresholds"]
        turbid_min = params["turbid_mins"]
        turbid_exp = params["turbid_exps"]
        light_threshold = params["light_thresholds"]
        light_min = params["light_mins"]
        light_exp = params["light_exps"]
        capture_R1 = params["capture_R1s"]
        capture_R9 = params["capture_R9s"]
        max_speed_A = jnp.asarray(params["max_speed_As"])
        max_speed_B = jnp.asarray(params["max_speed_Bs"])
        max_swim_temp_term = params["max_swim_temp_terms"]
        resp_A = jnp.asarray(params["resp_As"])
        resp_B = jnp.asarray(params["resp_Bs"])
        resp_D = params["resp_Ds"]
        resp_temp_term = params["resp_temp_terms"]
        prey_energy_density = params["prey_energy_densities"]
        fish_energy_density = params["fish_energy_densities"]
        drift_conc = params["drift_concs"]
        search_prod = params["search_prods"]
        search_area = params["search_areas"]
        shelter_speed_frac = params["shelter_speed_fracs"]

        # --- CMax ---
        cmax_wt = cmax_A * weights**cmax_B
        cmax_temp = jnp.interp(jnp.asarray(temperature, dtype=jnp.float64),
                               cmax_temp_table_x, cmax_temp_table_y)
        c_max_daily = cmax_wt * cmax_temp
        cstepmax = jnp.maximum(
            0.0, (c_max_daily - prev_consumption) / jnp.maximum(step_length, 1e-30)
        )

        # --- Max swim speed ---
        max_speed = (max_speed_A * lengths + max_speed_B) * max_swim_temp_term

        # --- Standard respiration ---
        resp_std = resp_A * weights**resp_B

        # --- Detection distance ---
        detect_dist = react_dist_A + react_dist_B * lengths
        turbid_func = jnp.where(
            turbidity <= turbid_threshold, 1.0,
            turbid_min + (1.0 - turbid_min) * jnp.exp(turbid_exp * (turbidity - turbid_threshold)),
        )
        light_func = jnp.where(
            light >= light_threshold, 1.0,
            light_min + (1.0 - light_min) * jnp.exp(light_exp * (light_threshold - light)),
        )
        detect_dist = detect_dist * turbid_func * light_func

        # --- Capture success ---
        cap_h = jnp.minimum(depth, detect_dist)
        cap_area = 2.0 * detect_dist * cap_h
        vel_ratio = jnp.where(max_speed > 0, velocity / max_speed, 999.0)
        cap_mid = (capture_R1 + capture_R9) / 2.0
        cap_slope = jnp.where(
            jnp.abs(capture_R9 - capture_R1) > 1e-15,
            jnp.log(81.0) / (capture_R9 - capture_R1), 0.0,
        )
        cap_success = 1.0 / (1.0 + jnp.exp(-cap_slope * (vel_ratio - cap_mid)))

        # --- Drift intake ---
        d_intake = cap_area * drift_conc * velocity * 86400.0 * cap_success
        d_intake = jnp.minimum(d_intake, cstepmax)
        d_intake = jnp.minimum(d_intake, available_drift / jnp.maximum(superind_rep, 1))
        d_intake = jnp.where((depth > 0) & (velocity > 0), d_intake, 0.0)

        # --- Search intake ---
        search_vel_ratio = jnp.where(max_speed > 0, (max_speed - velocity) / max_speed, 0.0)
        s_intake = search_prod * search_area * jnp.maximum(search_vel_ratio, 0.0)
        s_intake = jnp.minimum(s_intake, cstepmax)
        s_intake = jnp.minimum(s_intake, available_search / jnp.maximum(superind_rep, 1))

        # --- Swim speeds per activity ---
        shelter_ok = available_shelter > lengths**2
        drift_swim = jnp.where(shelter_ok, velocity * shelter_speed_frac, velocity)

        def _resp(swim_speed):
            ratio = jnp.where(max_speed > 0, swim_speed / max_speed, 20.0)
            ratio = jnp.minimum(ratio, 20.0)
            return resp_std * resp_temp_term * jnp.exp(resp_D * ratio**2)

        growth_drift = (d_intake * prey_energy_density - _resp(drift_swim)) / fish_energy_density
        growth_search = (s_intake * prey_energy_density - _resp(velocity)) / fish_energy_density
        growth_hide = -_resp(0.0) / fish_energy_density

        growth = jnp.where(activity == 0, growth_drift,
                           jnp.where(activity == 1, growth_search, growth_hide))

        return np.asarray(growth)
```

- [ ] **Step 4: Update existing JAX growth_rate tests to use new signature**

The 5 existing tests (`test_jax_growth_rate_drift_matches_python`, `test_jax_growth_rate_search_matches_python`, `test_jax_growth_rate_hide_matches_python`, `test_jax_growth_rate_batch`, `test_jax_growth_rate_dry_cell` at `tests/test_backends.py` lines 341-605) call `jax_b.growth_rate(activity=..., lengths=..., weights=..., depth=..., ...)` using OLD positional keyword names. Update them to use the new Protocol signature: `jax_b.growth_rate(lengths, weights, temperatures, velocities, depths, activities=..., lights=..., turbidities=..., drift_concs=..., search_prods=..., search_areas=..., available_drifts=..., available_searches=..., available_shelters=..., shelter_speed_fracs=..., superind_reps=..., prev_consumptions=..., step_length=..., cmax_As=..., cmax_Bs=..., cmax_temp_table_xs=..., cmax_temp_table_ys=..., species_idxs=..., react_dist_As=..., ...)`. The key renames:
- `activity=` → `activities=` (in `**params`)
- `depth=` → positional `depths`
- `velocity=` → positional `velocities`
- `light=` → `lights=`
- `turbidity=` → `turbidities=`
- `temperature=` → positional `temperatures`
- All scalar params become per-fish arrays in `**params`

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_backends.py::TestJaxBackendSignature::test_growth_rate_matches_numpy -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/backends/jax_backend/__init__.py tests/test_backends.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "fix: align JAX backend growth_rate() signature with Protocol"
```

---

### Task 3: Fix Logistic Degenerate Case Inconsistency

Three implementations disagree when `L1 == L9`:
- `behavior.py:evaluate_logistic` (scalar) → returns 0.5
- `numba_backend/fitness.py:_logistic` (Numba kernel) → returns 0.5
- `numpy_backend/__init__.py:evaluate_logistic` (vectorized) → returns 0.9 if x >= L1, else 0.1
- `numba_backend/__init__.py:evaluate_logistic` (vectorized) → returns 0.9 if x >= L1, else 0.1
- `jax_backend/__init__.py:evaluate_logistic` → returns 0.9 if x >= L1, else 0.1

The vectorized backends use the step-function convention (0.9/0.1) which is the correct behavior for a degenerate logistic: when L1==L9, the function should be a step at that threshold. The scalar paths returning 0.5 are wrong. The Numba fitness kernel uses the scalar `_logistic` in the hot loop for habitat selection fitness, while the numpy/numba backends use the vectorized version for mortality — causing inconsistent survival between habitat evaluation and mortality application.

**Fix:** Change scalar `evaluate_logistic` and Numba `_logistic` to match the 0.9/0.1 step-function convention.

**Files:**
- Modify: `src/instream/modules/behavior.py:38-50`
- Modify: `src/instream/backends/numba_backend/fitness.py:10-21`
- Test: `tests/test_behavior.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_behavior.py`:

```python
class TestLogisticDegenerateCase:
    """When L1 == L9, logistic should act as step function."""

    def test_scalar_logistic_degenerate_above(self):
        from instream.modules.behavior import evaluate_logistic
        result = evaluate_logistic(15.0, 10.0, 10.0)
        assert result == pytest.approx(0.9), f"Expected 0.9 for x > L1==L9, got {result}"

    def test_scalar_logistic_degenerate_below(self):
        from instream.modules.behavior import evaluate_logistic
        result = evaluate_logistic(5.0, 10.0, 10.0)
        assert result == pytest.approx(0.1), f"Expected 0.1 for x < L1==L9, got {result}"

    def test_scalar_logistic_degenerate_at(self):
        from instream.modules.behavior import evaluate_logistic
        result = evaluate_logistic(10.0, 10.0, 10.0)
        assert result == pytest.approx(0.9), f"Expected 0.9 for x == L1==L9, got {result}"

    def test_numba_logistic_degenerate(self):
        try:
            from instream.backends.numba_backend.fitness import _logistic
        except ImportError:
            pytest.skip("Numba not installed")
        assert _logistic(15.0, 10.0, 10.0) == pytest.approx(0.9)
        assert _logistic(5.0, 10.0, 10.0) == pytest.approx(0.1)
        assert _logistic(10.0, 10.0, 10.0) == pytest.approx(0.9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_behavior.py::TestLogisticDegenerateCase -v`
Expected: FAIL (returns 0.5 instead of 0.9/0.1)

- [ ] **Step 3: Fix scalar `evaluate_logistic` in behavior.py**

In `src/instream/modules/behavior.py`, replace lines 38-50:

```python
def evaluate_logistic(x, L1, L9):
    """Evaluate logistic function where f(L1)=0.1 and f(L9)=0.9. Scalar version.

    Uses pure Python math (not numpy) to avoid 0-d array dispatch overhead.
    When L1 == L9 (degenerate), acts as step function: 0.9 if x >= L1, else 0.1.
    """
    if L9 == L1:
        return 0.9 if x >= L1 else 0.1
    midpoint = (L1 + L9) * 0.5
    slope = _LN81 / (L9 - L1)
    arg = -slope * (x - midpoint)
    if arg > 500.0:
        arg = 500.0
    elif arg < -500.0:
        arg = -500.0
    return 1.0 / (1.0 + math.exp(arg))
```

- [ ] **Step 3b: Fix `evaluate_logistic_array` in behavior.py**

Also in `src/instream/modules/behavior.py`, replace `evaluate_logistic_array` (lines 53-60):

```python
def evaluate_logistic_array(x, L1, L9):
    """Evaluate logistic function on an array.

    When L1 == L9 (degenerate), acts as step function: 0.9 if x >= L1, else 0.1.
    """
    x = np.asarray(x, dtype=np.float64)
    if L9 == L1:
        return np.where(x >= L1, 0.9, 0.1)
    midpoint = (L1 + L9) / 2.0
    slope = np.log(81.0) / (L9 - L1)
    arg = -slope * (x - midpoint)
    arg = np.clip(arg, -500, 500)
    return 1.0 / (1.0 + np.exp(arg))
```

- [ ] **Step 4: Fix Numba `_logistic` in fitness.py**

In `src/instream/backends/numba_backend/fitness.py`, replace lines 10-21:

```python
@numba.njit(cache=True)
def _logistic(x, L1, L9):
    if L9 == L1:
        return 0.9 if x >= L1 else 0.1
    midpoint = (L1 + L9) * 0.5
    slope = _LN81 / (L9 - L1)
    arg = -slope * (x - midpoint)
    if arg > 500.0:
        arg = 500.0
    elif arg < -500.0:
        arg = -500.0
    return 1.0 / (1.0 + math.exp(arg))
```

- [ ] **Step 5: Clear Numba cache (the .nbi files cache old bytecode)**

Run: `find "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py\src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true`

- [ ] **Step 6: Update breaking test `test_spatial_visualization.py`**

The test `test_equal_L1_L9_gives_half_max` in `tests/test_spatial_visualization.py` expects `movement_radius` to return 100.0 (= 0.5 × 200) when L1 == L9. After the fix, the logistic returns 0.9 instead of 0.5, so the expected radius becomes 180.0 (= 0.9 × 200). Update the test:

```python
    def test_equal_L1_L9_gives_step_function(self):
        """When L1 == L9, logistic acts as step function: returns 0.9 at x >= L1."""
        r = movement_radius(
            length=10.0, move_radius_max=200.0, move_radius_L1=10.0, move_radius_L9=10.0
        )
        assert abs(r - 180.0) < 0.01
```

- [ ] **Step 7: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_behavior.py::TestLogisticDegenerateCase tests/test_spatial_visualization.py::TestMovementRadius::test_equal_L1_L9_gives_step_function -v`
Expected: PASS

- [ ] **Step 8: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 9: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/modules/behavior.py src/instream/backends/numba_backend/fitness.py tests/test_behavior.py tests/test_spatial_visualization.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "fix: align degenerate logistic (L1==L9) to step function 0.9/0.1 across all implementations"
```

---

### Task 4: Fix Numba Backend Velocity Clamping

The NumPy backend clamps all negative velocities: `vels = np.maximum(vels, 0.0)`. The Numba backend only zeroes velocity when `depth == 0.0`, not when `depth > 0` and velocity is negative from interpolation. A cell with positive depth but negative interpolated velocity would get `v < 0` in Numba but `v = 0` in NumPy.

**Files:**
- Modify: `src/instream/backends/numba_backend/__init__.py:78-102`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_backends.py`:

```python
class TestVelocityClamping:
    """Numba and numpy backends must clamp negative velocities identically."""

    def test_negative_velocity_clamped_to_zero(self):
        """When interpolation produces negative velocity at positive depth, clamp to 0."""
        from instream.backends.numpy_backend import NumpyBackend
        try:
            from instream.backends.numba_backend import NumbaBackend
        except ImportError:
            pytest.skip("Numba not installed")

        np_be = NumpyBackend()
        nb_be = NumbaBackend()

        # Construct table where interpolation at flow=1.5 produces negative velocity
        # Cell 0: vel at flow=1 is 5, vel at flow=2 is 1
        # interpolated vel at 1.5 = 5 + 0.5*(1-5) = 3.0 (positive, no issue)
        # Cell 1: vel at flow=1 is 2, vel at flow=2 is -10
        # interpolated vel at 1.5 = 2 + 0.5*(-10-2) = -4.0 (NEGATIVE — must clamp)
        table_flows = np.array([1.0, 2.0])
        depth_values = np.array([[10.0, 20.0], [15.0, 25.0]])
        vel_values = np.array([[5.0, 1.0], [2.0, -10.0]])

        np_d, np_v = np_be.update_hydraulics(1.5, table_flows, depth_values, vel_values)
        nb_d, nb_v = nb_be.update_hydraulics(1.5, table_flows, depth_values, vel_values)

        np.testing.assert_allclose(nb_d, np_d, rtol=1e-12)
        np.testing.assert_allclose(nb_v, np_v, rtol=1e-12)
        # Both should have non-negative velocity
        assert np.all(np_v >= 0.0), f"NumPy produced negative velocity: {np_v}"
        assert np.all(nb_v >= 0.0), f"Numba produced negative velocity: {nb_v}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_backends.py::TestVelocityClamping -v`
Expected: FAIL (Numba produces negative velocity for cell 1)

- [ ] **Step 3: Add velocity clamping to Numba `_update_hydraulics`**

In `src/instream/backends/numba_backend/__init__.py`, replace lines 95-101:

```python
        # Clamp: negative depth → 0, dry cell → zero velocity, negative vel → 0
        if d < 0.0:
            d = 0.0
        if d == 0.0:
            v = 0.0
        if v < 0.0:
            v = 0.0
        depths[i] = d
        vels[i] = v
```

- [ ] **Step 4: Clear Numba cache**

Run: `find "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py\src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true`

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_backends.py::TestVelocityClamping -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/backends/numba_backend/__init__.py tests/test_backends.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "fix: clamp negative velocities in Numba hydraulics backend (match numpy)"
```

---

### Task 5: Fix `condition == 1.0` Exact Float Comparison

In `survival.py:94` and `numba_backend/fitness.py:229`, exact `condition == 1.0` is fragile. A fish with `condition = 0.9999999999999998` would miss the early-return and compute via the two-piece linear, getting ~0.99999... instead of exactly 1.0. Low severity but easy to fix: use `condition >= 1.0`.

**Files:**
- Modify: `src/instream/modules/survival.py:92-95`
- Modify: `src/instream/backends/numba_backend/fitness.py:228-230`
- Test: `tests/test_survival.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_survival.py`:

```python
class TestConditionSurvivalNearOne:
    """Condition very close to 1.0 should give survival == 1.0."""

    def test_condition_above_one_returns_one(self):
        from instream.modules.survival import survival_condition
        # condition slightly above 1.0 (float arithmetic artifact)
        # Before fix: enters upper piece, computes s > 1.0, gets clipped to 1.0
        # This specific value demonstrates the == vs >= distinction:
        result = survival_condition(1.05)
        assert result == 1.0, f"Expected 1.0 for condition > 1.0, got {result}"

    def test_condition_exactly_one(self):
        from instream.modules.survival import survival_condition
        result = survival_condition(1.0)
        assert result == 1.0

    def test_condition_at_099(self):
        from instream.modules.survival import survival_condition
        # condition 0.99 should return something less than 1.0
        result = survival_condition(0.99)
        assert 0.99 < result < 1.0, f"Expected ~0.996 for condition=0.99, got {result}"
```

- [ ] **Step 2: Run test to verify baseline behavior**

Run: `conda run -n shiny python -m pytest tests/test_survival.py::TestConditionSurvivalNearOne -v`
Expected: All PASS (the `>= 1.0` change is defensive — existing clipping handles most cases, but the fix ensures early exit for supranormal condition values)

- [ ] **Step 3: Fix `survival_condition` in survival.py**

In `src/instream/modules/survival.py`, replace lines 92-95:

```python
    if condition <= 0.0:
        return 0.0
    if condition >= 1.0:
        return 1.0
```

- [ ] **Step 4: Fix Numba fitness kernel condition check**

In `src/instream/backends/numba_backend/fitness.py`, find the condition survival block (around line 227-229) and change:

```python
    elif fish_condition == 1.0:
```
to:
```python
    elif fish_condition >= 1.0:
```

- [ ] **Step 5: Clear Numba cache**

Run: `find "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py\src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true`

- [ ] **Step 6: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_survival.py::TestConditionSurvivalNearOne -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/modules/survival.py src/instream/backends/numba_backend/fitness.py tests/test_survival.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "fix: use condition >= 1.0 instead of == 1.0 in survival functions"
```

---

### Task 6: Add Hydraulic Shape Assertion

`model.py:508-514` assigns `backend.update_hydraulics()` output to `cs.depth[cells]`. If the hydraulic table row count doesn't match the cell count for that reach, values get assigned to wrong cells or numpy raises a shape error. Add a defensive assertion.

**Files:**
- Modify: `src/instream/model.py:508-514`
- Test: `tests/test_model.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_model.py`:

```python
def test_hydraulic_table_cell_count_mismatch():
    """Model should raise if hydraulic table rows don't match cell count for a reach."""
    from instream.model import InSTREAMModel
    model = InSTREAMModel(
        CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
    )
    # Corrupt the hydraulic data to have wrong row count
    rname = model.reach_order[0]
    hdata = model._reach_hydraulic_data[rname]
    original = hdata["depth_values"]
    hdata["depth_values"] = original[:-5]  # remove 5 rows
    with pytest.raises(ValueError, match="hydraulic table.*cell count"):
        model.step()
    # Restore
    hdata["depth_values"] = original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n shiny python -m pytest tests/test_model.py::test_hydraulic_table_cell_count_mismatch -v`
Expected: FAIL (no ValueError raised — numpy either broadcasts or raises IndexError)

- [ ] **Step 3: Add shape assertion in model.py**

In `src/instream/model.py`, after line 512 (`depths, vels = self.backend.update_hydraulics(...)`) and before line 514 (`cs.depth[cells] = depths`), add:

```python
            if len(depths) != len(cells):
                raise ValueError(
                    f"Reach '{rname}': hydraulic table has {len(depths)} rows "
                    f"but cell count is {len(cells)} — check that the hydraulic "
                    f"CSV rows match the shapefile cells for this reach"
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n shiny python -m pytest tests/test_model.py::test_hydraulic_table_cell_count_mismatch -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/model.py tests/test_model.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "fix: add shape assertion for per-reach hydraulic table vs cell count"
```

---

### Task 7: Remove Phantom `fitness_all` from Protocol and All Backends

`fitness_all` is declared in the Protocol, stubbed as `NotImplementedError` in all 3 backends, and never called anywhere. Remove it to clean up the interface.

**Files:**
- Modify: `src/instream/backends/_interface.py:59-61`
- Modify: `src/instream/backends/numpy_backend/__init__.py:403-404`
- Modify: `src/instream/backends/numba_backend/__init__.py:331-332`
- Modify: `src/instream/backends/jax_backend/__init__.py:528-536`

- [ ] **Step 1: Verify `fitness_all` is never called**

Run: `grep -r "fitness_all" "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py\src" --include="*.py" -l`

Confirm it only appears in `_interface.py`, `numpy_backend/__init__.py`, `numba_backend/__init__.py`, `jax_backend/__init__.py` — never in `model.py`, `behavior.py`, or any caller.

- [ ] **Step 2: Remove from Protocol**

In `src/instream/backends/_interface.py`, delete lines 59-61:

```python
    def fitness_all(
        self, trout_arrays: dict, cell_arrays: dict, candidates: np.ndarray, **params
    ) -> tuple[np.ndarray, np.ndarray]: ...
```

- [ ] **Step 3: Remove from numpy backend**

In `src/instream/backends/numpy_backend/__init__.py`, delete lines 403-404:

```python
    def fitness_all(self, trout_arrays, cell_arrays, candidates, **params):
        raise NotImplementedError("Phase 4")
```

- [ ] **Step 4: Remove from numba backend**

In `src/instream/backends/numba_backend/__init__.py`, delete lines 331-332:

```python
    def fitness_all(self, *args, **kwargs):
        raise NotImplementedError("Phase 4")
```

- [ ] **Step 5: Remove from JAX backend**

In `src/instream/backends/jax_backend/__init__.py`, delete lines 528-536 (the `fitness_all` method with the long docstring).

- [ ] **Step 6: Remove `test_backend_has_fitness_all` test**

In `tests/test_backends.py`, delete the test at line 38-42:

```python
    def test_backend_has_fitness_all(self):
        backend = get_backend("numpy")
        assert hasattr(backend, "fitness_all")
```

This test asserts the method exists — removing it is correct since we're deleting the method.

- [ ] **Step 7: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/backends/_interface.py src/instream/backends/numpy_backend/__init__.py src/instream/backends/numba_backend/__init__.py src/instream/backends/jax_backend/__init__.py tests/test_backends.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "refactor: remove phantom fitness_all from Protocol and all backends"
```

---

### Task 8: Single-Pass Candidate Building in Numba

`build_all_candidates_numba` in `spatial.py` runs the full O(N_fish × N_cells) brute-force distance search TWICE — once to count candidates, once to fill them. This doubles the 7 ms cost. Fix: compute radius once per fish, call `_find_candidates_single` once, and collect results directly.

**Files:**
- Modify: `src/instream/backends/numba_backend/spatial.py:65-137`

- [ ] **Step 1: Run baseline benchmark to record current timing**

Run: `conda run -n shiny python -c "import time; from instream.backends.numba_backend.spatial import build_all_candidates_numba; import numpy as np; n=400; nc=1373; alive=np.ones(n,dtype=np.bool_); ci=np.random.randint(0,nc,n).astype(np.int32); l=np.random.uniform(3,20,n); cx=np.random.uniform(0,1000,nc); cy=np.random.uniform(0,1000,nc); wet=np.ones(nc,dtype=np.bool_); nb=np.full((nc,6),-1,dtype=np.int32); build_all_candidates_numba(alive,ci,l,cx,cy,wet,nb,500.0,5.0,15.0); t0=time.perf_counter(); [build_all_candidates_numba(alive,ci,l,cx,cy,wet,nb,500.0,5.0,15.0) for _ in range(20)]; print(f'Current: {(time.perf_counter()-t0)/20*1000:.1f} ms')"`

- [ ] **Step 2: Rewrite `build_all_candidates_numba` as single-pass**

Replace the function in `src/instream/backends/numba_backend/spatial.py` (lines 65-137) with a single-pass version that pre-allocates a worst-case buffer and calls `_find_candidates_single` only once per fish:

```python
@numba.njit(cache=True)
def build_all_candidates_numba(
    alive,
    cell_idx,
    lengths,
    centroid_x,
    centroid_y,
    wet_mask,
    neighbor_indices,
    move_radius_max,
    move_radius_L1,
    move_radius_L9,
):
    """Build candidate lists for ALL fish. Returns (offsets, flat) CSR format.

    Single-pass with pre-allocated buffer sized to worst case.
    """
    LN81 = 4.394449154672439
    n_fish = alive.shape[0]
    n_cells = centroid_x.shape[0]

    # Worst case: every fish gets every cell as candidate
    # For typical meshes (1373 cells, 400 fish), this is ~2.2M int32 = ~8.8 MB
    max_total = n_fish * n_cells
    flat_buf = np.empty(max_total, dtype=np.int32)
    offsets = np.zeros(n_fish + 1, dtype=np.int64)
    pos = 0

    for i in range(n_fish):
        if not alive[i] or cell_idx[i] < 0:
            offsets[i + 1] = pos
            continue
        # Degenerate case: step function matching Task 3 logistic fix (0.9/0.1)
        if move_radius_L9 == move_radius_L1:
            frac = 0.9 if lengths[i] >= move_radius_L1 else 0.1
        else:
            mid = (move_radius_L1 + move_radius_L9) * 0.5
            slp = LN81 / (move_radius_L9 - move_radius_L1)
            arg = -slp * (lengths[i] - mid)
            if arg > 500.0:
                arg = 500.0
            elif arg < -500.0:
                arg = -500.0
            frac = 1.0 / (1.0 + math.exp(arg))
        radius = move_radius_max * frac
        cands = _find_candidates_single(
            cell_idx[i], radius, centroid_x, centroid_y, wet_mask, neighbor_indices
        )
        n_cands = len(cands)
        for k in range(n_cands):
            flat_buf[pos + k] = cands[k]
        pos += n_cands
        offsets[i + 1] = pos

    # Trim to actual size
    flat = flat_buf[:pos].copy()
    return offsets, flat
```

- [ ] **Step 3: Clear Numba cache**

Run: `find "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py\src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true`

- [ ] **Step 4: Run full test suite to verify correctness**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 5: Run timing comparison**

Run same benchmark as Step 1, verify improvement.

- [ ] **Step 6: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/backends/numba_backend/spatial.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "perf: single-pass candidate building in Numba spatial search"
```

---

### Task 9: Vectorize `_apply_accumulated_growth` in model.py

The method uses a Python for-loop over alive indices and nested loop over sub-steps. This is fully vectorizable with numpy.

**Files:**
- Modify: `src/instream/model.py` (the `_apply_accumulated_growth` method)

- [ ] **Step 1: Read current implementation**

Read `src/instream/model.py` to find `_apply_accumulated_growth` and its current loop structure.

- [ ] **Step 2: Write regression test**

Add to `tests/test_model.py`:

```python
def test_apply_accumulated_growth_deterministic():
    """Growth application should produce identical results before/after vectorization."""
    from instream.model import InSTREAMModel
    model = InSTREAMModel(
        CONFIGS_DIR / "example_a.yaml", data_dir=FIXTURES_DIR / "example_a"
    )
    model.step()
    # Snapshot weights and lengths after step
    alive = np.where(model.trout_state.alive)[0]
    weights = model.trout_state.weight[alive].copy()
    lengths = model.trout_state.length[alive].copy()
    conditions = model.trout_state.condition[alive].copy()
    # All must be finite and positive
    assert np.all(np.isfinite(weights))
    assert np.all(weights > 0)
    assert np.all(np.isfinite(lengths))
    assert np.all(lengths > 0)
    assert np.all(np.isfinite(conditions))
```

- [ ] **Step 3: Run test to verify baseline**

Run: `conda run -n shiny python -m pytest tests/test_model.py::test_apply_accumulated_growth_deterministic -v`
Expected: PASS (before refactoring)

- [ ] **Step 4: Vectorize `_apply_accumulated_growth`**

Replace the method at `model.py:836-868`. The current implementation loops per-fish with a nested sub-step loop. Vectorize using numpy:

```python
    def _apply_accumulated_growth(self):
        """Sum growth_memory across sub-steps and apply to weight/length/condition."""
        alive = self.trout_state.alive_indices()
        if len(alive) == 0:
            return
        steps = self.steps_per_day
        sl = 1.0 / max(self.steps_per_day, 1)

        _wA = self._sp_arrays["weight_A"]
        _wB = self._sp_arrays["weight_B"]

        # Vectorized: sum growth across sub-steps for all alive fish at once
        total_growth = self.trout_state.growth_memory[alive, :steps].sum(axis=1) * sl

        # Filter out fish with invalid cells
        cell_idx = self.trout_state.cell_idx[alive]
        valid = (cell_idx >= 0) & (cell_idx < self.fem_space.num_cells)
        valid_alive = alive[valid]
        valid_growth = total_growth[valid]

        if len(valid_alive) == 0:
            return

        # Per-fish species weight params
        sp_idx = self.trout_state.species_idx[valid_alive]
        wA = _wA[sp_idx]
        wB = _wB[sp_idx]

        # Apply growth: still uses scalar apply_growth per fish because
        # the length-never-decreases rule and allometric back-calculation
        # have conditional logic that's hard to vectorize correctly.
        for j in range(len(valid_alive)):
            i = valid_alive[j]
            new_w, new_l, new_k = apply_growth(
                float(self.trout_state.weight[i]),
                float(self.trout_state.length[i]),
                float(self.trout_state.condition[i]),
                float(valid_growth[j]),
                float(wA[j]),
                float(wB[j]),
            )
            self.trout_state.weight[i] = new_w
            self.trout_state.length[i] = new_l
            self.trout_state.condition[i] = new_k
```

The key improvement is vectorizing the growth memory summation (eliminates nested sub-step loop) and the cell validity check. The `apply_growth` call remains scalar because it has conditional allometric back-calculation that's not trivially vectorizable.

- [ ] **Step 5: Run test to verify correctness preserved**

Run: `conda run -n shiny python -m pytest tests/test_model.py::test_apply_accumulated_growth_deterministic -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/model.py tests/test_model.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "perf: vectorize _apply_accumulated_growth (eliminate Python per-fish loop)"
```

---

### Task 10: Mark JAX Backend as Experimental

The JAX backend is incomplete — 5 of 9 Protocol methods raise NotImplementedError. A user selecting `backend: jax` in config will get a crash on the first growth computation. Add a clear warning at init time.

**Files:**
- Modify: `src/instream/backends/jax_backend/__init__.py:13-18`

- [ ] **Step 1: Add warning to `__init__`**

Add an `__init__` method to `JaxBackend`:

```python
class JaxBackend:
    """JAX compute backend with vmap vectorization and GPU support.

    WARNING: This backend is EXPERIMENTAL. Only hydraulics, light, logistic,
    and interpolation are implemented. Growth and survival now work but
    fitness_all, deplete_resources are not yet vectorized.
    """

    def __init__(self):
        import warnings
        warnings.warn(
            "JaxBackend is experimental: deplete_resources and spawn_suitability "
            "use NumPy fallbacks. Full JAX vectorization is pending.",
            stacklevel=2,
        )
```

- [ ] **Step 2: Run full test suite**

Run: `conda run -n shiny python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass (warning doesn't break anything)

- [ ] **Step 3: Commit**

```bash
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" add src/instream/backends/jax_backend/__init__.py
git -C "C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py" commit -m "docs: mark JAX backend as experimental with init warning"
```

---

## Summary of All Tasks

| Task | Type | Severity | Files |
|------|------|----------|-------|
| 1. Fix JAX `survival()` signature | Bug fix | CRITICAL | jax_backend, test_backends |
| 2. Fix JAX `growth_rate()` signature | Bug fix | CRITICAL | jax_backend, test_backends |
| 3. Fix logistic degenerate case | Bug fix | CRITICAL | behavior.py, fitness.py, test_behavior |
| 4. Fix Numba velocity clamping | Bug fix | WARNING | numba_backend, test_backends |
| 5. Fix `condition == 1.0` float comparison | Bug fix | WARNING | survival.py, fitness.py, test_survival |
| 6. Add hydraulic shape assertion | Defensive | WARNING | model.py, test_model |
| 7. Remove phantom `fitness_all` | Cleanup | LOW | _interface.py, all backends |
| 8. Single-pass candidate building | Performance | MEDIUM | spatial.py |
| 9. Vectorize `_apply_accumulated_growth` | Performance | MEDIUM | model.py, test_model |
| 10. Mark JAX as experimental | Documentation | LOW | jax_backend |
