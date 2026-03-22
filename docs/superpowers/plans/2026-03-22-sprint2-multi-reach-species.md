# Sprint 2: Multi-Reach + Multi-Species Support

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all hardcoded `[0]` indices from model.py so the simulation supports multiple reaches and multiple species, validated with Example B (3 reaches x 3 species).

**Architecture:** Incremental refactoring — each task replaces one category of `[0]` indices with per-reach or per-species dispatch. Example A (single-reach, single-species) must continue passing after every task. Example B integration test added at the end.

**Tech Stack:** Python 3.11+, NumPy, Mesa 3.x, Pydantic, pytest

**Spec reference:** `docs/NETLOGO_PARITY_ROADMAP.md` Sprint 2

---

## Prerequisites

Before starting, generate the Example B YAML config from the NLS parameters file. This is a one-time conversion.

---

### Task 0: Generate Example B YAML config

**Files:**
- Create: `configs/example_b.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Convert Example B NLS to YAML**

```python
# Run in Python REPL or script:
from instream.io.config import nls_to_yaml
nls_to_yaml(
    "tests/fixtures/example_b/parameters-ExampleB.nls",
    "configs/example_b.yaml"
)
```

- [ ] **Step 2: Verify the YAML loads**

```python
from instream.io.config import load_config
config = load_config("configs/example_b.yaml")
assert len(config.species) == 3  # Chinook-Fall, Chinook-Spring, Rainbow
assert len(config.reaches) == 3  # Upstream, Middle, Downstream
```

- [ ] **Step 3: Fix any path issues in the YAML**

The YAML's `spatial.mesh_file`, `reaches.*.depth_file`, etc. will reference Example B paths. Verify they resolve relative to `tests/fixtures/example_b/`.

- [ ] **Step 4: Commit**

Commit: "config: generate Example B YAML (3 reaches x 3 species)"

---

## Phase 1: Multi-Reach Hydraulics + Light + Resources

### Task 1: Per-reach hydraulic table loading

Currently `model.py:111` loads only the first reach's depth/velocity tables. All cells get the same flow.

**Files:**
- Modify: `src/instream/model.py:98-118` (__init__ hydraulic loading)
- Test: `tests/test_model.py`

- [ ] **Step 1: Write failing test**

```python
def test_multi_reach_model_initializes():
    """Model with 3 reaches should load all hydraulic tables."""
    from pathlib import Path
    from instream.model import InSTREAMModel
    CONFIGS = Path(__file__).parent.parent / "configs"
    FIXTURES = Path(__file__).parent / "fixtures" / "example_b"
    model = InSTREAMModel(CONFIGS / "example_b.yaml", data_dir=FIXTURES)
    assert len(model.reach_order) == 3
    assert model.fem_space.num_cells > 0
```

- [ ] **Step 2: Refactor hydraulic loading to iterate over reaches**

Replace the single-reach loading block with a loop over all reaches. Each reach has its own depth/velocity CSV. The PolygonMesh already assigns `reach_idx` per cell, so cells know which reach they belong to.

Key design: Store per-reach hydraulic tables, then in `update_hydraulics`, apply each reach's flow to that reach's cells only.

- [ ] **Step 3: Run Example A tests (must still pass), commit**

Commit: "feat: load hydraulic tables for all reaches"

---

### Task 2: Per-reach hydraulic updates in step()

Currently `model.py:285` uses `self.reach_state.flow[0]` for all cells.

**Files:**
- Modify: `src/instream/model.py:285-286` (step hydraulic update)
- Modify: `src/instream/space/fem_space.py` (per-reach update method)
- Test: `tests/test_model.py`

- [ ] **Step 1: Add `update_hydraulics_per_reach` to FEMSpace**

```python
def update_hydraulics_per_reach(self, reach_flows, reach_indices, backend):
    """Update hydraulics per-reach: each reach's cells use that reach's flow."""
    for r_idx, flow in enumerate(reach_flows):
        cells = np.where(self.cell_state.reach_idx == r_idx)[0]
        if len(cells) == 0:
            continue
        # Interpolate only for this reach's cells
        depths, vels = backend.update_hydraulics(
            float(flow),
            self.cell_state.depth_table_flows,
            self.cell_state.depth_table_values[cells],
            self.cell_state.vel_table_values[cells],
        )
        self.cell_state.depth[cells] = depths
        self.cell_state.velocity[cells] = vels
```

- [ ] **Step 2: Update model.step() to call per-reach**

Replace `flow = float(self.reach_state.flow[0])` + `self.fem_space.update_hydraulics(flow, ...)` with:

```python
        self.fem_space.update_hydraulics_per_reach(
            self.reach_state.flow,
            self.cell_state.reach_idx,
            self.backend,
        )
```

- [ ] **Step 3: Run tests, commit**

Commit: "feat: per-reach hydraulic updates in model.step()"

---

### Task 3: Per-reach light computation

Currently `model.py:290-310` uses reach[0]'s shading, turbidity, and light_turbid_coef.

**Files:**
- Modify: `src/instream/model.py:288-310`

- [ ] **Step 1: Replace hardcoded reach[0] with per-reach loop**

```python
        for r_idx, rname in enumerate(self.reach_order):
            reach_cfg = self.config.reaches[rname]
            cells = np.where(self.fem_space.cell_state.reach_idx == r_idx)[0]
            if len(cells) == 0:
                continue
            jd = self.time_manager.julian_date
            day_length, twilight_length, irradiance = self.backend.compute_light(
                jd, self._light_cfg.latitude, self._light_cfg.light_correction,
                reach_cfg.shading, self._light_cfg.light_at_night,
                self._light_cfg.twilight_angle,
            )
            cell_light = self.backend.compute_cell_light(
                self.fem_space.cell_state.depth[cells], irradiance,
                reach_cfg.light_turbid_coef,
                float(self.reach_state.turbidity[r_idx]),
                self._light_cfg.light_at_night,
            )
            self.fem_space.cell_state.light[cells] = cell_light
```

- [ ] **Step 2: Run tests, commit**

Commit: "feat: per-reach light computation"

---

### Task 4: Per-reach resource reset

Currently `model.py:310-315` uses reach[0]'s drift_conc and search_prod for all cells.

**Files:**
- Modify: `src/instream/model.py:310-315`

- [ ] **Step 1: Replace with per-reach resource parameters**

```python
        for r_idx, rname in enumerate(self.reach_order):
            rp = self.reach_params[rname]
            cells = np.where(cs.reach_idx == r_idx)[0]
            cs.available_drift[cells] = rp.drift_conc * cs.area[cells] * cs.depth[cells]
            cs.available_search[cells] = rp.search_prod * cs.area[cells]
            cs.available_vel_shelter[cells] = cs.frac_vel_shelter[cells] * cs.area[cells]
        cs.available_hiding_places[:] = self.mesh.num_hiding_places.copy()
```

- [ ] **Step 2: Run tests, commit**

Commit: "feat: per-reach resource reset"

---

## Phase 2: Per-Fish Species + Reach Dispatch

### Task 5: Per-fish temperature and turbidity in habitat selection

Currently `model.py:318-319` uses `reach_state.temperature[0]` and `turbidity[0]` for ALL fish. Fish should use their own reach's temperature.

**Files:**
- Modify: `src/instream/model.py:317-350` (habitat selection call)

- [ ] **Step 1: Pass per-reach arrays instead of scalars**

The habitat selection `params` dict currently passes scalar `temperature` and `turbidity`. For multi-reach, these need to be per-reach arrays, and the inner loop must look up the fish's reach:

```python
            temperature=self.reach_state.temperature,  # array, shape (num_reaches,)
            turbidity=self.reach_state.turbidity,        # array
```

Then in `select_habitat_and_activity`, the per-fish invariant block needs to do:

```python
        _fish_reach = int(trout_state.reach_idx[i])
        _temperature = float(temperature_arr[_fish_reach])
        _turbidity = float(turbidity_arr[_fish_reach])
```

This is a significant change to behavior.py — the pre-extracted `_temperature` and `_turbidity` become per-fish, not per-step.

- [ ] **Step 2: Update reach_state intermediate indexing**

Replace `max_swim_temp_term[0, 0]` and `resp_temp_term[0, 0]` with per-fish lookup:
```python
        _max_swim_temp_term = float(self.reach_state.max_swim_temp_term[_fish_reach, _species_idx])
        _resp_temp_term = float(self.reach_state.resp_temp_term[_fish_reach, _species_idx])
```

- [ ] **Step 3: Run Example A tests (should pass — single reach means [0] everywhere), commit**

Commit: "feat: per-fish reach-based temperature and turbidity lookup"

---

### Task 6: Per-fish species parameter dispatch

Currently all fish use `species_order[0]`'s parameters. Fish have `species_idx` in TroutState but it's always 0.

**Files:**
- Modify: `src/instream/model.py` (habitat selection, survival, spawning)
- Modify: `src/instream/modules/behavior.py` (parameter dispatch)

- [ ] **Step 1: Create species parameter lookup arrays**

In model.__init__, pre-build arrays for per-species dispatch:

```python
        # Pre-build species parameter arrays for fast per-fish lookup
        n_sp = len(self.species_order)
        self._sp_cmax_A = np.array([self.config.species[s].cmax_A for s in self.species_order])
        self._sp_cmax_B = np.array([self.config.species[s].cmax_B for s in self.species_order])
        self._sp_weight_A = np.array([self.config.species[s].weight_A for s in self.species_order])
        # ... etc for all species-level parameters used in hot paths
```

- [ ] **Step 2: Pass species arrays to habitat selection**

Instead of passing scalar `cmax_A=sp_cfg.cmax_A`, pass arrays and let the inner loop index by `trout_state.species_idx[i]`:

```python
        _cmax_A = _sp_cmax_A_arr[_species_idx]  # per-fish lookup
```

- [ ] **Step 3: Update survival and spawning similarly**

The survival loop and spawning loop need per-fish species parameter dispatch.

- [ ] **Step 4: Run Example A tests, commit**

Commit: "feat: per-fish species parameter dispatch"

---

### Task 7: Multi-species initial population loading

Currently `model.py:175-183` uses only the first species' weight_A/B and hardcodes `species_index=0`.

**Files:**
- Modify: `src/instream/model.py:170-190`
- Modify: `src/instream/io/population_reader.py`

- [ ] **Step 1: Load populations per-species**

```python
        # Build initial trout state with per-species parameters
        populations = read_initial_populations(pop_path)
        self.trout_state = TroutState.zeros(self.config.performance.trout_capacity)
        rng = np.random.default_rng(self.config.simulation.seed)
        idx = 0
        for pop in populations:
            sp_name = pop['species']
            sp_idx = self._species_name_to_idx.get(sp_name, 0)
            sp_cfg = self.config.species.get(sp_name, self.config.species[self.species_order[0]])
            n = pop['number']
            lengths = rng.triangular(pop['length_min'], pop['length_mode'], pop['length_max'], n)
            weights = sp_cfg.weight_A * lengths ** sp_cfg.weight_B
            end = idx + n
            self.trout_state.alive[idx:end] = True
            self.trout_state.species_idx[idx:end] = sp_idx
            self.trout_state.age[idx:end] = pop['age']
            self.trout_state.length[idx:end] = lengths
            self.trout_state.weight[idx:end] = weights
            self.trout_state.condition[idx:end] = 1.0
            self.trout_state.superind_rep[idx:end] = 1
            self.trout_state.sex[idx:end] = rng.integers(0, 2, size=n, dtype=np.int32)
            idx = end
```

- [ ] **Step 2: Run tests, commit**

Commit: "feat: multi-species initial population loading"

---

### Task 8: Per-reach spawning and redd development

Currently `_do_spawning` and `_do_redd_step` use reach[0] and species[0].

**Files:**
- Modify: `src/instream/model.py:513-710`

- [ ] **Step 1: Replace hardcoded indices in _do_spawning**

Each spawning fish uses its own species' spawn parameters and its own reach's flow/temperature:

```python
        for i in alive:
            sp_idx = int(self.trout_state.species_idx[i])
            sp_name = self.species_order[sp_idx]
            sp_cfg = self.config.species[sp_name]
            reach_idx = int(self.trout_state.reach_idx[i])
            rname = self.reach_order[reach_idx]
            rp = self.reach_params[rname]
            temperature = float(self.reach_state.temperature[reach_idx])
            flow = float(self.reach_state.flow[reach_idx])
            # ... rest of spawning logic using per-fish sp_cfg and rp
```

- [ ] **Step 2: Replace hardcoded indices in _do_redd_step**

Each redd uses its own species' development params and its own reach's conditions.

- [ ] **Step 3: Run tests, commit**

Commit: "feat: per-reach per-species spawning and redd development"

---

## Phase 3: Example B Integration

### Task 9: Example B integration test

**Files:**
- Create: `tests/test_example_b.py`

- [ ] **Step 1: Write integration test**

```python
def test_example_b_initializes():
    """3-reach, 3-species model should initialize."""
    from pathlib import Path
    from instream.model import InSTREAMModel
    CONFIGS = Path(__file__).parent.parent / "configs"
    FIXTURES = Path(__file__).parent / "fixtures" / "example_b"
    model = InSTREAMModel(CONFIGS / "example_b.yaml", data_dir=FIXTURES)
    assert len(model.reach_order) == 3
    assert len(model.species_order) == 3
    assert model.trout_state.num_alive() > 0
    # Should have multiple species
    species_present = set(model.trout_state.species_idx[model.trout_state.alive_indices()].tolist())
    assert len(species_present) > 1

def test_example_b_runs_30_days():
    """3-reach, 3-species model should complete 30 days."""
    from pathlib import Path
    from instream.model import InSTREAMModel
    CONFIGS = Path(__file__).parent.parent / "configs"
    FIXTURES = Path(__file__).parent / "fixtures" / "example_b"
    model = InSTREAMModel(CONFIGS / "example_b.yaml", data_dir=FIXTURES,
                          end_date_override="2011-05-01")
    while not model.time_manager.is_done():
        model.step()
    assert model.trout_state.num_alive() > 0
```

- [ ] **Step 2: Debug and fix any issues found**

The integration test will likely reveal issues with per-reach hydraulic table shapes, missing parameters, or index errors. Fix iteratively.

- [ ] **Step 3: Commit**

Commit: "test: Example B integration test (3 reaches x 3 species)"

---

## Dependency Graph

```
Task 0 (Example B YAML) ── prerequisite for all

Phase 1 (Multi-Reach):
  Task 1 (hydraulic loading) ──→ Task 2 (per-reach update) ──→ Task 3 (light) ──→ Task 4 (resources)

Phase 2 (Multi-Species):
  Task 5 (per-fish temp/turbidity) ── depends on Phase 1
  Task 6 (species params) ── depends on Task 5
  Task 7 (population loading) ── independent
  Task 8 (spawning/redd) ── depends on Tasks 5,6

Phase 3 (Integration):
  Task 9 (Example B test) ── depends on all above
```

---

## Verification Checklist

After all tasks:
- [ ] Example A: all existing tests pass (single-reach/species regression)
- [ ] Example B: initializes with 3 reaches x 3 species
- [ ] Example B: runs 30 days without crash
- [ ] Fish in different reaches see different temperatures
- [ ] Fish of different species use different growth parameters
- [ ] Spawning uses per-species season/condition thresholds
- [ ] Redd development uses per-species temperature coefficients

---

## Implementation Notes

### Key design principle: dispatch by index, not by name

Instead of `self.config.species[species_name]` in the inner loop (dict lookup), pre-build arrays indexed by species_idx for all hot-path parameters. Name-based lookup only at initialization.

### Numba kernel compatibility

The numba fitness kernel (`_evaluate_all_cells`) receives all parameters as positional scalars. Multi-species requires the caller to select the correct species' scalars before calling numba. This is done in the Python outer loop — no changes to the numba kernel itself.

### Per-reach hydraulic tables

The current design stores one set of hydraulic tables in CellState (all cells share the same flow breakpoints). Multi-reach requires either:
- (a) All reaches share the same flow breakpoints (simplest — just different values per cell)
- (b) Per-reach flow breakpoints (requires restructuring CellState)

Example B's files show the same number of flow breakpoints across reaches, so option (a) should work. If breakpoints differ, merge them with interpolation.
