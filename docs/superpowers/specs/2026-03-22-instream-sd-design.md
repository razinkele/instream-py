# InSTREAM-SD Sub-Daily Scheduling Design Spec

**Date:** 2026-03-22
**Status:** Approved
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
- Exposes `is_day_boundary` flag (True when the NEXT advance would be a new calendar day)
- Falls back to daily mode when input has 1 row per day
- Tracks `substep_index` within day (0, 1, 2, ...) for memory array indexing

### 2. Model.step() modifications

| Operation | Sub-step behavior | Day boundary behavior |
|-----------|-------------------|----------------------|
| Flow/temp/turbidity | Update from current time-series row | Same |
| Hydraulics | Recalculate per reach (flow changed) | Same |
| Light | Compute once per day (skip if not day boundary) | Compute |
| Resource repletion | Partial: `available += production * step_length` | Full reset |
| Habitat selection | Run (fish re-evaluate) | Run |
| Growth | Accumulate in `growth_memory[fish, substep]` | Apply accumulated growth to weight/length/condition, reset memory |
| Survival | Apply immediately (fish can die mid-day) | Same |
| Spawning | Check only at day boundary | Run |
| Redd development | Only at day boundary | Run |
| Age increment | Only at Jan 1 day boundary | Check |
| Census | Only at day boundary | Check |

### 3. Memory management (existing TroutState arrays)

- `consumption_memory[fish, substep]`: food eaten per sub-step (for CStepMax limiting)
- `growth_memory[fish, substep]`: growth rate per sub-step (accumulated, applied at day boundary)
- Reset both arrays to zero at day boundary
- `survival_memory`: not used (survival applied immediately)
- `max_steps_per_day`: currently defaults to 4; auto-sized from detected input frequency

## Data flow per sub-step

```
advance() → step_length, is_day_boundary, substep_index
  │
  ├─ Update flow/temp/turbidity from time-series
  ├─ Recalculate hydraulics (depths/velocities from new flow)
  ├─ Light: skip if substep_index > 0 (same day)
  ├─ Resource repletion: partial (add production * step_length)
  ├─ Habitat selection (full re-evaluation)
  ├─ Store growth in growth_memory[fish, substep_index]
  ├─ Store consumption in consumption_memory[fish, substep_index]
  ├─ Apply survival immediately (stochastic mortality)
  │
  └─ If is_day_boundary:
       ├─ Apply accumulated growth (sum of growth_memory) to weight/length/condition
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
    """
    timestamps = time_series_df.index
    if len(timestamps) < 2:
        return 1
    # Compute median interval
    intervals = np.diff(timestamps.values).astype('timedelta64[m]').astype(float)
    median_minutes = np.median(intervals)
    steps_per_day = max(1, round(1440.0 / median_minutes))  # 1440 min/day
    return steps_per_day
```

## Resource repletion formula

Between sub-steps (NOT at day boundary):
```python
# Partial regeneration proportional to step_length
cs.available_drift[cells] += rp.drift_conc * cs.area[cells] * cs.depth[cells] * step_length
cs.available_search[cells] += rp.search_prod * cs.area[cells] * step_length
# Cap at daily maximum
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

## CStepMax with memory

The consumption memory tracks food eaten across sub-steps:
```python
# In growth computation per sub-step:
prev_consumption = float(np.sum(consumption_memory[fish, :substep_index]))
cstepmax = c_stepmax(cmax_wt_term, cmax_temp, prev_consumption, step_length)
# After eating:
consumption_memory[fish, substep_index] = actual_intake
```

## Backward compatibility

Daily input (1 row per day) → `steps_per_day=1`, `step_length=1.0`, `is_day_boundary=True` every step. Model behavior identical to v0.6.0. No config changes required.

## Test strategy

### Unit tests (synthetic data)
- `test_detect_frequency_hourly` → returns 24
- `test_detect_frequency_daily` → returns 1
- `test_sub_daily_step_lengths_sum_to_one`
- `test_resource_partial_repletion`
- `test_growth_memory_accumulates`
- `test_growth_applied_at_day_boundary`
- `test_survival_applied_each_substep`
- `test_daily_input_backward_compatible`

### Integration tests (ClearCreek peaking data)
- `test_peaking_flow_changes_within_day`
- `test_hydraulics_update_each_substep`
- `test_4_substeps_per_day`

### Regression
- Example A daily: must produce identical fish populations (seed-deterministic)

## Test data

- **Synthetic**: Generate from Example A daily data (repeat/interpolate to hourly)
- **Real**: Extract `TestHourlyInput.csv` and `PeakingInput_Hours-4-Ratio-6.csv` from `InSTREAM-7.4-SD_2026-02-11.zip`

## Files affected

| File | Changes |
|------|---------|
| `src/instream/io/time_manager.py` | Add SubDailyScheduler, modify TimeManager to delegate |
| `src/instream/model.py` | Restructure step() for sub-step vs day-boundary logic |
| `src/instream/state/trout_state.py` | Dynamic max_steps_per_day sizing |
| `tests/test_time.py` | Sub-daily scheduler unit tests |
| `tests/test_subdaily.py` | NEW: integration tests for sub-daily mode |
| `tests/fixtures/subdaily/` | NEW: synthetic hourly + real peaking CSVs |
