# InSTREAM-SD Sub-Daily Scheduling Design Spec

**Date:** 2026-03-22
**Status:** Approved (rev 2 — reviewer fixes applied)
**Scope:** Sub-daily time stepping, resource repletion, memory accumulation, peaking flow support

---

## Overview

InSTREAM-SD extends the simulation from daily to sub-daily time steps (hourly or finer). Fish re-evaluate habitat each sub-step, resources partially regenerate between sub-steps, and flow/temperature can vary within a single day (peaking hydropower scenarios).

## Architecture

Three components modified:

### 1. SubDailyScheduler (new class in `time_manager.py`)

- Auto-detects input frequency by examining timestamp intervals in time-series CSV
- Groups rows by calendar day
- `advance()` returns fractional `step_length` (e.g., 0.042 for hourly, 0.25 for 6-hourly, 1.0 for daily)
- Exposes `is_day_boundary` flag (True when the current sub-step is the LAST of the calendar day)
- Falls back to daily mode when input has 1 row per day
- Tracks `substep_index` within day (0, 1, 2, ...) for memory array indexing
- Maintains an internal **row pointer** into the time-series DataFrame; `get_conditions()` returns the row at the current pointer (exact indexing, NOT nearest-neighbor interpolation)

**Initialization ordering:** Frequency detection happens BEFORE TroutState allocation so `max_steps_per_day` can be sized correctly:
```
1. Load time-series CSVs
2. Detect frequency → steps_per_day
3. Create TimeManager/SubDailyScheduler with steps_per_day
4. Allocate TroutState.zeros(capacity, max_steps_per_day=steps_per_day)
```

**Irregular intervals:** If a day has fewer rows than `steps_per_day` (gaps, DST transitions), the scheduler logs a warning and uses available rows. `substep_index` never exceeds `max_steps_per_day - 1`; excess sub-steps within a day are clamped.

### 2. Model.step() modifications

| Operation | Sub-step behavior | Day boundary behavior |
|-----------|-------------------|----------------------|
| Flow/temp/turbidity | Update from current time-series row | Same |
| Hydraulics | Recalculate per reach (flow changed) | Same |
| Solar irradiance | Compute once per day (skip if substep_index > 0) | Compute |
| **Cell light** | **Recompute each sub-step** (depends on depth which changes with flow) | Same |
| Resource repletion | Partial: `available += production * step_length` (capped) | Full reset |
| Habitat selection | Run (fish re-evaluate) | Run |
| Growth | **Store growth rate (g/d) in `growth_memory[fish, substep_index]`; do NOT call apply_growth** | **Sum growth_memory entries, multiply by step_lengths, call apply_growth with total weight change; reset memory** |
| Survival | Apply immediately with `daily_surv ** step_length` scaling | Same |
| Spawning | Check only at day boundary | Run |
| Redd development | Only at day boundary | Run |
| Age increment | Only at Jan 1 day boundary | Check |
| Census | Only at day boundary | Check |

### 3. Memory management (existing TroutState arrays)

**Units are critical:**

| Array | Unit | What it stores |
|-------|------|---------------|
| `consumption_memory[fish, substep]` | **grams** | Mass of food consumed during this sub-step (NOT a rate) |
| `growth_memory[fish, substep]` | **g/d** (daily rate) | Growth rate from `growth_rate_for()` for this sub-step |

- Reset both arrays to zero at day boundary
- `survival_memory`: kept for diagnostic purposes but not used in computation (survival applied immediately with `** step_length` scaling)
- `max_steps_per_day`: auto-sized from detected input frequency BEFORE TroutState allocation

**Growth application at day boundary:**
```python
# At day boundary, compute total weight change:
total_growth = 0.0
for s in range(steps_this_day):
    total_growth += growth_memory[fish, s] * step_lengths[s]  # g/d * fraction_of_day = grams
# growth_memory stores daily rates; multiply by each sub-step's step_length to get grams
new_weight, new_length, new_condition = apply_growth(weight, length, condition,
                                                       total_growth, weight_A, weight_B)
```

## Data flow per sub-step

```
advance() → step_length, is_day_boundary, substep_index
  │
  ├─ Update flow/temp/turbidity from time-series (exact row lookup)
  ├─ Recalculate hydraulics (depths/velocities from new flow)
  ├─ Solar irradiance: skip if substep_index > 0
  ├─ Cell light: ALWAYS recompute (depth changed → Beer-Lambert changes)
  ├─ Resource repletion: partial (add production * step_length, cap at daily max)
  ├─ Habitat selection (full re-evaluation with current conditions)
  ├─ Store growth rate (g/d) in growth_memory[fish, substep_index]
  ├─ Store consumption (grams) in consumption_memory[fish, substep_index]
  ├─ Apply survival immediately: daily_surv ** step_length (stochastic mortality)
  │
  └─ If is_day_boundary:
       ├─ Apply accumulated growth: sum(growth_memory * step_lengths) → apply_growth
       ├─ Reset growth_memory and consumption_memory to zero
       ├─ Full resource reset (start of new day)
       ├─ Spawning check
       ├─ Redd development + emergence
       ├─ Census check
       └─ Age increment check (Jan 1)
```

## Auto-detection logic

```python
def detect_frequency(time_series_df):
    """Detect time-series row frequency.

    Returns steps_per_day (int). 1 = daily, 24 = hourly, etc.
    Validates that most days have the expected number of rows.
    """
    timestamps = time_series_df.index
    if len(timestamps) < 2:
        return 1
    # Compute median interval
    intervals = np.diff(timestamps.values).astype('timedelta64[m]').astype(float)
    median_minutes = np.median(intervals)
    steps_per_day = max(1, round(1440.0 / median_minutes))  # 1440 min/day

    # Validate: check that most days have the expected count
    day_counts = time_series_df.groupby(time_series_df.index.date).size()
    expected = steps_per_day
    mismatches = (day_counts != expected).sum()
    if mismatches > 0:
        import logging
        logging.getLogger(__name__).warning(
            "%d of %d days have != %d rows (irregular input)",
            mismatches, len(day_counts), expected,
        )

    return steps_per_day
```

## Resource repletion formula

Between sub-steps (NOT at day boundary):
```python
# Partial regeneration proportional to step_length
# NOTE: depth may have changed from peaking flow — use CURRENT depth for production
cs.available_drift[cells] += rp.drift_conc * cs.area[cells] * cs.depth[cells] * step_length
cs.available_search[cells] += rp.search_prod * cs.area[cells] * step_length
# Cap at daily maximum using CURRENT depth (flow-dependent)
daily_max_drift = rp.drift_conc * cs.area[cells] * cs.depth[cells]
cs.available_drift[cells] = np.minimum(cs.available_drift[cells], daily_max_drift)
daily_max_search = rp.search_prod * cs.area[cells]
cs.available_search[cells] = np.minimum(cs.available_search[cells], daily_max_search)
# Shelter and hiding: no repletion (fixed per day)
```

At day boundary:
```python
# Full reset (same as current daily code)
cs.available_drift[cells] = rp.drift_conc * cs.area[cells] * cs.depth[cells]
cs.available_search[cells] = rp.search_prod * cs.area[cells]
cs.available_vel_shelter[cells] = cs.frac_vel_shelter[cells] * cs.area[cells]
cs.available_hiding_places[:] = mesh.num_hiding_places.copy()
```

**Resource cap uses current depth:** Under peaking flows, depth changes significantly. Production and cap both use current depth, meaning drift availability tracks flow conditions naturally. A flow drop reduces both production rate and maximum capacity, which is ecologically correct (less water volume = less drift habitat).

## CStepMax with memory

The consumption memory tracks food eaten (in **grams**, not rate) across sub-steps:
```python
# In growth computation per sub-step:
# consumption_memory stores grams consumed (mass, not rate)
prev_consumption = float(np.sum(consumption_memory[fish, :substep_index]))
cstepmax = c_stepmax(cmax_wt_term, cmax_temp, prev_consumption, step_length)
# cstepmax returns a RATE (g/d) — the max intake rate for this sub-step

# After habitat selection determines actual intake rate (g/d):
actual_intake_rate = last_growth_rate_intake_component  # g/d from growth_rate_for
actual_intake_grams = actual_intake_rate * step_length  # convert rate to mass
consumption_memory[fish, substep_index] = actual_intake_grams
```

## Survival scaling

**Preserved from current code:** Survival probability is raised to `step_length` power:
```python
daily_surv = s_ht * s_str * s_cond * s_fp * s_tp
survival_probs[i] = daily_surv ** step_length  # fractional step → fractional mortality
```
This is essential for sub-daily: without it, a 4-step day would apply 4x the mortality of a 1-step day. The exponentiation ensures `(daily_surv ** 0.25) ** 4 ≈ daily_surv`.

## Backward compatibility

Daily input (1 row per day) → `steps_per_day=1`, `step_length=1.0`, `is_day_boundary=True` every step. Growth applied immediately (1 entry in memory, summed = same value). Survival: `daily_surv ** 1.0 = daily_surv`. Model behavior identical to v0.6.0. No config changes required.

**Regression tolerance:** Daily mode must produce bitwise-identical results (same RNG path, same computation order). The refactoring must not change the order of operations for the daily case.

## Temperature and other sub-daily variations

Temperature and turbidity are read directly from the time-series CSV row for each sub-step. If the CSV has sub-daily temperature variation (common in peaking scenarios where hypolimnetic releases are colder), it is automatically used. No special handling needed — `get_conditions()` returns whatever the current row contains.

## Light: solar vs cell-level

- **Solar irradiance** (day_length, twilight_length, surface irradiance): computed once per day. Depends on julian date and latitude only.
- **Cell-level light** (Beer-Lambert attenuation through water column): **recomputed each sub-step** because it depends on `depth`, which changes with flow. Formula: `light = irradiance * exp(-turbid_coef * turbidity * depth / 2)`.

Future enhancement: hour-of-day solar angle variation (dawn/dusk) is not included in this spec. The current implementation uses daily-average irradiance. Sub-daily light variation can be added later by computing solar elevation per sub-step.

## Edge cases

- **First day:** If simulation starts mid-day (input CSV starts at hour 12), the first day has fewer sub-steps. The scheduler handles this by counting actual rows for that date.
- **Last day:** If the end date falls mid-day, remaining sub-steps are not executed.
- **Leap years:** Handled by pandas datetime; no special logic needed.
- **Missing rows:** Warning logged; substep_index clamped to `max_steps_per_day - 1`.

## Test strategy

### Unit tests (synthetic data)
- `test_detect_frequency_hourly` → returns 24
- `test_detect_frequency_daily` → returns 1
- `test_detect_frequency_irregular_logs_warning`
- `test_sub_daily_step_lengths_sum_to_one`
- `test_resource_partial_repletion`
- `test_growth_memory_accumulates_rate`
- `test_growth_applied_at_day_boundary_uses_step_lengths`
- `test_survival_applied_each_substep_with_exponent`
- `test_daily_input_backward_compatible_bitwise`
- `test_substep_index_clamped_to_max`
- `test_cell_light_recomputed_each_substep`
- `test_consumption_memory_in_grams`

### Integration tests (ClearCreek peaking data)
- `test_peaking_flow_changes_within_day`
- `test_hydraulics_update_each_substep`
- `test_4_substeps_per_day`

### Regression
- Example A daily: bitwise identical fish populations to v0.6.0 (same seed, same computation order)

## Test data

- **Synthetic**: Generate from Example A daily data (repeat each day's values 24 times with timestamps)
- **Real**: Extract `TestHourlyInput.csv` and `PeakingInput_Hours-4-Ratio-6.csv` from `InSTREAM-7.4-SD_2026-02-11.zip`

## Files affected

| File | Changes |
|------|---------|
| `src/instream/io/time_manager.py` | Add SubDailyScheduler, modify TimeManager to delegate, row-pointer get_conditions |
| `src/instream/model.py` | Restructure step() for sub-step vs day-boundary; growth accumulation; detect frequency before TroutState alloc |
| `src/instream/state/trout_state.py` | Accept dynamic max_steps_per_day from detected frequency |
| `tests/test_time.py` | Sub-daily scheduler unit tests |
| `tests/test_subdaily.py` | NEW: integration tests for sub-daily mode |
| `tests/fixtures/subdaily/` | NEW: synthetic hourly + real peaking CSVs |
