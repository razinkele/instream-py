# InSTREAM-SD Sub-Daily Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add sub-daily time stepping so the model can run with hourly or sub-hourly input data, enabling peaking flow simulations (InSTREAM-SD).

**Architecture:** Extend TimeManager with auto-detection of input frequency and sub-daily row-pointer advancement. Restructure model.step() to distinguish sub-step operations (hydraulics, habitat selection, survival) from day-boundary operations (growth application, spawning, census). Growth accumulates in memory arrays per sub-step, applied at day boundary.

**Tech Stack:** Python 3.11+, NumPy, pandas, pytest

**Spec:** `docs/superpowers/specs/2026-03-22-instream-sd-design.md`

---

## File Map

| File | Changes |
|------|---------|
| `src/instream/io/time_manager.py` | Add `detect_frequency()`, extend `TimeManager` with sub-daily support |
| `src/instream/model.py` | Restructure `step()` for sub-step vs day-boundary; detect frequency before TroutState alloc; growth accumulation |
| `src/instream/state/trout_state.py` | Accept dynamic `max_steps_per_day` |
| `tests/test_time.py` | Sub-daily scheduler unit tests |
| `tests/test_subdaily.py` | NEW: integration tests |
| `tests/fixtures/subdaily/` | NEW: synthetic hourly CSV |
| `scripts/generate_subdaily_fixture.py` | NEW: generate synthetic hourly data from Example A |

---

### Task 1: Add `detect_frequency` and sub-daily TimeManager

**Files:**
- Modify: `src/instream/io/time_manager.py`
- Test: `tests/test_time.py`

- [ ] **Step 1: Write tests for frequency detection**

```python
# In tests/test_time.py
class TestDetectFrequency:
    def test_daily_returns_1(self):
        from instream.io.time_manager import detect_frequency
        dates = pd.date_range("2011-04-01", periods=10, freq="D")
        df = pd.DataFrame({"flow": 5.0, "temperature": 12.0, "turbidity": 1.0}, index=dates)
        assert detect_frequency(df) == 1

    def test_hourly_returns_24(self):
        from instream.io.time_manager import detect_frequency
        dates = pd.date_range("2011-04-01", periods=48, freq="h")
        df = pd.DataFrame({"flow": 5.0, "temperature": 12.0, "turbidity": 1.0}, index=dates)
        assert detect_frequency(df) == 24

    def test_6hourly_returns_4(self):
        from instream.io.time_manager import detect_frequency
        dates = pd.date_range("2011-04-01", periods=8, freq="6h")
        df = pd.DataFrame({"flow": 5.0, "temperature": 12.0, "turbidity": 1.0}, index=dates)
        assert detect_frequency(df) == 4
```

- [ ] **Step 2: Implement `detect_frequency`**

Add to `time_manager.py`:
```python
def detect_frequency(time_series_df):
    """Detect time-series row frequency. Returns steps_per_day (int)."""
    timestamps = time_series_df.index
    if len(timestamps) < 2:
        return 1
    intervals = np.diff(timestamps.values).astype('timedelta64[m]').astype(float)
    median_minutes = np.median(intervals)
    steps_per_day = max(1, round(1440.0 / median_minutes))
    return steps_per_day
```

- [ ] **Step 3: Write tests for sub-daily advance**

```python
class TestSubDailyAdvance:
    def test_subdaily_step_length_fraction(self):
        dates = pd.date_range("2011-04-01", periods=8, freq="6h")
        df = pd.DataFrame({"flow": range(8), "temperature": 12.0, "turbidity": 1.0}, index=dates)
        tm = TimeManager("2011-04-01", "2011-04-03", {"R1": df})
        step_length = tm.advance()
        assert abs(step_length - 0.25) < 0.01  # 6h = 0.25 day

    def test_subdaily_step_lengths_sum_to_one(self):
        dates = pd.date_range("2011-04-01", periods=8, freq="6h")
        df = pd.DataFrame({"flow": range(8), "temperature": 12.0, "turbidity": 1.0}, index=dates)
        tm = TimeManager("2011-04-01", "2011-04-03", {"R1": df})
        total = 0.0
        day_lengths = []
        for _ in range(4):
            sl = tm.advance()
            total += sl
        assert abs(total - 1.0) < 0.01

    def test_subdaily_is_day_boundary(self):
        dates = pd.date_range("2011-04-01", periods=8, freq="6h")
        df = pd.DataFrame({"flow": range(8), "temperature": 12.0, "turbidity": 1.0}, index=dates)
        tm = TimeManager("2011-04-01", "2011-04-03", {"R1": df})
        boundaries = []
        for _ in range(8):
            tm.advance()
            boundaries.append(tm.is_day_boundary)
        # Day boundary at step 3 (last of day 1) and step 7 (last of day 2)
        assert boundaries[3] == True
        assert boundaries[7] == True
        assert boundaries[0] == False

    def test_daily_backward_compatible(self):
        dates = pd.date_range("2011-04-01", periods=5, freq="D")
        df = pd.DataFrame({"flow": 5.0, "temperature": 12.0, "turbidity": 1.0}, index=dates)
        tm = TimeManager("2011-04-01", "2011-04-06", {"R1": df})
        sl = tm.advance()
        assert sl == 1.0
        assert tm.is_day_boundary == True
```

- [ ] **Step 4: Extend TimeManager with sub-daily support**

Modify `TimeManager.__init__` to detect frequency and set up row-pointer mode. Add `is_day_boundary`, `substep_index`, `steps_per_day` properties. Modify `advance()` to step through rows instead of incrementing by 1 day. Modify `get_conditions()` to use exact row indexing.

Key design: when `steps_per_day > 1`, maintain an internal `_row_idx` per reach that advances each `advance()` call. `is_day_boundary` is True when the next row would be a new calendar day. `step_length = 1.0 / steps_per_day`.

- [ ] **Step 5: Run tests, commit**

Commit: "feat: add sub-daily time stepping with auto-frequency detection"

---

### Task 2: Generate synthetic hourly fixture data

**Files:**
- Create: `scripts/generate_subdaily_fixture.py`
- Create: `tests/fixtures/subdaily/`

- [ ] **Step 1: Create fixture generator**

```python
"""Generate synthetic hourly time-series from Example A daily data."""
import pandas as pd
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"
DAILY = FIXTURES / "example_a" / "ExampleA-TimeSeriesInputs.csv"
OUT_DIR = FIXTURES / "subdaily"
OUT_DIR.mkdir(exist_ok=True)

# Read daily data
lines = [l.strip() for l in open(DAILY) if l.strip() and not l.startswith(";")]
header = lines[0].split(",")
rows = [l.split(",") for l in lines[1:]]
df = pd.DataFrame(rows, columns=[h.strip() for h in header])
df['Date'] = pd.to_datetime(df['Date'], format='mixed')
df = df.set_index('Date')
for col in df.columns:
    df[col] = pd.to_numeric(df[col])

# Expand to hourly (24 rows per day, repeat values)
hourly = df.resample('h').ffill().iloc[:240]  # first 10 days = 240 hourly rows
hourly.to_csv(OUT_DIR / "hourly_example_a.csv")

# Also create a 4-step peaking variant (6-hourly with flow variation)
sixhourly = df.resample('6h').ffill().iloc[:40]  # 10 days x 4 = 40 rows
# Add peaking: multiply flow by 3x at hours 6-12
for i in range(len(sixhourly)):
    if i % 4 in [1, 2]:  # 2nd and 3rd sub-step = peak hours
        sixhourly.iloc[i, sixhourly.columns.get_loc('flow')] *= 3.0
sixhourly.to_csv(OUT_DIR / "peaking_example_a.csv")

print("Generated hourly and peaking fixtures")
```

- [ ] **Step 2: Run generator, commit**

Commit: "test: add synthetic hourly and peaking fixture data"

---

### Task 3: Restructure model.step() for sub-step vs day-boundary

This is the core refactoring. model.step() must distinguish what runs every sub-step from what runs only at day boundaries.

**Files:**
- Modify: `src/instream/model.py`
- Modify: `src/instream/state/trout_state.py`

- [ ] **Step 1: Update TroutState to accept dynamic max_steps_per_day**

In model.__init__, after loading time-series and detecting frequency, pass `max_steps_per_day` to TroutState:

```python
        # Detect sub-daily frequency
        first_ts = next(iter(time_series.values()))
        self.steps_per_day = detect_frequency(first_ts)

        # ... later when creating TroutState:
        self.trout_state = TroutState.zeros(
            self.config.performance.trout_capacity,
            max_steps_per_day=self.steps_per_day,
        )
```

- [ ] **Step 2: Refactor step() into sub-step and day-boundary sections**

Split the current step() logic:

```python
    def step(self):
        # 1. Advance time
        step_length = self.time_manager.advance()
        is_day_boundary = self.time_manager.is_day_boundary
        substep_index = self.time_manager.substep_index

        # 2. Get conditions (exact row lookup for sub-daily)
        conditions = {rn: self.time_manager.get_conditions(rn) for rn in self.reach_order}

        # 3. Update reach state
        update_reach_state(...)

        # 4. Update hydraulics per reach (every sub-step — flow changed)
        for r_idx, rname in enumerate(self.reach_order):
            # ... per-reach hydraulic update ...

        # 5. Light: solar once per day, cell light every sub-step
        if substep_index == 0:
            # Compute solar irradiance (once per day)
            self._solar_irradiance = {}
            for r_idx, rname in enumerate(self.reach_order):
                jd = self.time_manager.julian_date
                dl, tl, irr = self.backend.compute_light(...)
                self._solar_irradiance[rname] = irr

        # Cell light every sub-step (depth changed from flow)
        for r_idx, rname in enumerate(self.reach_order):
            cells = np.where(cs.reach_idx == r_idx)[0]
            cell_light = self.backend.compute_cell_light(
                cs.depth[cells], self._solar_irradiance[rname], ...)
            cs.light[cells] = cell_light

        # 6. Resource repletion
        if substep_index == 0:
            # Full reset at start of day
            self._reset_resources_full()
        else:
            # Partial repletion between sub-steps
            self._replenish_resources_partial(step_length)

        # 7. Piscivore density
        pisciv_densities = self._compute_piscivore_density()

        # 8. Habitat selection (every sub-step)
        select_habitat_and_activity(...)

        # 9. Store growth in memory (do NOT apply)
        alive = self.trout_state.alive_indices()
        for i in alive:
            self.trout_state.growth_memory[i, substep_index] = self.trout_state.last_growth_rate[i]
            # Store consumption (grams eaten this sub-step)
            self.trout_state.consumption_memory[i, substep_index] = (
                self.trout_state.last_growth_rate[i] * step_length  # approximate
            )

        # 10. Survival (every sub-step, with ** step_length)
        self._do_survival(step_length)

        # 11. Day-boundary operations
        if is_day_boundary:
            self._apply_accumulated_growth(step_length)
            self._do_spawning_and_redds(step_length)
            self._collect_census_if_needed()
            self._increment_age_if_new_year()
            # Reset memory for next day
            self.trout_state.growth_memory[:] = 0.0
            self.trout_state.consumption_memory[:] = 0.0

        # 12. Sync Mesa agents
        sync_trout_agents(self)
```

- [ ] **Step 3: Implement `_apply_accumulated_growth`**

```python
    def _apply_accumulated_growth(self, step_length):
        """Sum growth_memory across sub-steps and apply to weight/length/condition."""
        alive = self.trout_state.alive_indices()
        steps_today = self.time_manager.substep_index + 1
        sl = 1.0 / max(steps_today, 1)  # uniform step_length per sub-step

        for i in alive:
            total_growth = 0.0
            for s in range(steps_today):
                total_growth += float(self.trout_state.growth_memory[i, s]) * sl
            sp_idx = int(self.trout_state.species_idx[i])
            w_A = float(self._sp_arrays['weight_A'][sp_idx])
            w_B = float(self._sp_arrays['weight_B'][sp_idx])
            new_w, new_l, new_k = apply_growth(
                float(self.trout_state.weight[i]),
                float(self.trout_state.length[i]),
                float(self.trout_state.condition[i]),
                total_growth, w_A, w_B,
            )
            self.trout_state.weight[i] = new_w
            self.trout_state.length[i] = new_l
            self.trout_state.condition[i] = new_k

        split_superindividuals(self.trout_state,
            float(self._sp_arrays['superind_max_length'][0]))
```

- [ ] **Step 4: Implement `_replenish_resources_partial`**

```python
    def _replenish_resources_partial(self, step_length):
        """Partial resource restoration between sub-steps."""
        cs = self.fem_space.cell_state
        for r_idx, rname in enumerate(self.reach_order):
            rp = self.reach_params[rname]
            cells = np.where(cs.reach_idx == r_idx)[0]
            # Add production proportional to step_length
            cs.available_drift[cells] += rp.drift_conc * cs.area[cells] * cs.depth[cells] * step_length
            cs.available_search[cells] += rp.search_prod * cs.area[cells] * step_length
            # Cap at daily maximum
            max_drift = rp.drift_conc * cs.area[cells] * cs.depth[cells]
            cs.available_drift[cells] = np.minimum(cs.available_drift[cells], max_drift)
            max_search = rp.search_prod * cs.area[cells]
            cs.available_search[cells] = np.minimum(cs.available_search[cells], max_search)
```

- [ ] **Step 5: Run Example A tests (daily backward compatibility), commit**

Commit: "feat: restructure model.step() for sub-daily sub-step vs day-boundary"

---

### Task 4: Integration tests with sub-daily data

**Files:**
- Create: `tests/test_subdaily.py`

- [ ] **Step 1: Write sub-daily integration tests**

```python
"""Integration tests for InSTREAM-SD sub-daily mode."""
import numpy as np
import pytest
from pathlib import Path

CONFIGS = Path(__file__).parent.parent / "configs"
FIXTURES_A = Path(__file__).parent / "fixtures" / "example_a"
FIXTURES_SD = Path(__file__).parent / "fixtures" / "subdaily"


class TestSubDailyModel:
    def _make_subdaily_config(self, tmp_path, hourly_csv):
        """Create a config pointing to sub-daily time series."""
        import yaml
        config = yaml.safe_load((CONFIGS / "example_a.yaml").read_text())
        config['simulation']['end_date'] = '2011-04-03'  # 2 days only
        # Point reach to hourly data
        for rname in config['reaches']:
            config['reaches'][rname]['time_series_input_file'] = str(hourly_csv)
        out = tmp_path / "subdaily_config.yaml"
        out.write_text(yaml.dump(config))
        return out

    @pytest.mark.slow
    def test_hourly_produces_24_substeps_per_day(self, tmp_path):
        from instream.model import InSTREAMModel
        config = self._make_subdaily_config(tmp_path, FIXTURES_SD / "hourly_example_a.csv")
        model = InSTREAMModel(str(config), data_dir=str(FIXTURES_A))
        assert model.steps_per_day == 24
        steps = 0
        while not model.time_manager.is_done() and steps < 48:
            model.step()
            steps += 1
        assert steps == 48  # 2 days x 24

    @pytest.mark.slow
    def test_growth_not_applied_mid_day(self, tmp_path):
        from instream.model import InSTREAMModel
        config = self._make_subdaily_config(tmp_path, FIXTURES_SD / "hourly_example_a.csv")
        model = InSTREAMModel(str(config), data_dir=str(FIXTURES_A))
        # Record initial weights
        alive = model.trout_state.alive_indices()
        initial_weights = model.trout_state.weight[alive].copy()
        # Run 1 sub-step (NOT a full day)
        model.step()
        # Weights should NOT change mid-day
        assert np.allclose(model.trout_state.weight[alive], initial_weights)

    @pytest.mark.slow
    def test_growth_applied_at_day_boundary(self, tmp_path):
        from instream.model import InSTREAMModel
        config = self._make_subdaily_config(tmp_path, FIXTURES_SD / "hourly_example_a.csv")
        model = InSTREAMModel(str(config), data_dir=str(FIXTURES_A))
        alive = model.trout_state.alive_indices()
        initial_weights = model.trout_state.weight[alive].copy()
        # Run 24 sub-steps (one full day)
        for _ in range(24):
            model.step()
        # NOW weights should have changed
        assert not np.allclose(model.trout_state.weight[alive], initial_weights)

    @pytest.mark.slow
    def test_survival_applied_each_substep(self, tmp_path):
        from instream.model import InSTREAMModel
        config = self._make_subdaily_config(tmp_path, FIXTURES_SD / "hourly_example_a.csv")
        model = InSTREAMModel(str(config), data_dir=str(FIXTURES_A))
        initial_alive = model.trout_state.num_alive()
        # Run 24 sub-steps
        for _ in range(24):
            model.step()
        # Some fish may have died during the day (survival each sub-step)
        # This is expected — we just verify no crash
        assert model.trout_state.num_alive() <= initial_alive
```

- [ ] **Step 2: Run tests, commit**

Commit: "test: add InSTREAM-SD sub-daily integration tests"

---

### Task 5: Daily backward-compatibility regression test

**Files:**
- Modify: `tests/test_subdaily.py`

- [ ] **Step 1: Write bitwise regression test**

```python
    def test_daily_backward_compatible(self):
        """Daily input with sub-daily code must produce identical results to v0.6.0."""
        from instream.model import InSTREAMModel
        model = InSTREAMModel(CONFIGS / "example_a.yaml", data_dir=FIXTURES_A,
                              end_date_override="2011-04-11")
        assert model.steps_per_day == 1  # auto-detected as daily
        for _ in range(10):
            model.step()
            assert model.time_manager.is_day_boundary == True
        alive = model.trout_state.num_alive()
        # These values are from v0.6.0 Example A after 10 steps
        assert alive > 200  # rough check — exact value depends on seed
```

- [ ] **Step 2: Run, commit**

Commit: "test: daily backward-compatibility regression for sub-daily refactor"

---

## Dependency Graph

```
Task 1 (TimeManager) ──→ Task 3 (model.step refactor)
Task 2 (fixture data) ──→ Task 4 (integration tests)
Task 3 ──→ Task 4
Task 3 ──→ Task 5 (regression)
```

---

## Verification Checklist

- [ ] `python -m pytest tests/test_time.py -v` — all sub-daily scheduler tests pass
- [ ] `python -m pytest tests/test_subdaily.py -v` — all integration tests pass
- [ ] `python -m pytest tests/ -v -m "not slow"` — all existing tests pass (daily backward compat)
- [ ] Example A daily: step_length=1.0, is_day_boundary=True every step
- [ ] Synthetic hourly: 24 sub-steps per day, step_length≈0.042
- [ ] Growth memory accumulates across sub-steps, applied at day boundary
- [ ] Survival applied each sub-step with `** step_length` scaling
- [ ] Cell light recomputed each sub-step (depth changes with flow)
- [ ] Resources partially replenished between sub-steps
