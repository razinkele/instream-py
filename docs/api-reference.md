# Salmopy API Reference

Version 0.43.3 (formerly published as `inSTREAM-py`; renamed v0.42.0)

---

## Core

### `InSTREAMModel`

```python
class InSTREAMModel(mesa.Model):
    def __init__(self, config_path, data_dir=None, end_date_override=None)
```

Main inSTREAM simulation model. Wires all modules together and runs the daily time-step loop.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `config_path` | `str` or `Path` | Path to the YAML configuration file |
| `data_dir` | `str` or `Path`, optional | Directory containing data files (shapefile, CSVs). Defaults to the config file's parent directory |
| `end_date_override` | `str`, optional | Override the end date from config (for short test runs, e.g. `"2011-05-01"`) |

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `ModelConfig` | Parsed configuration |
| `species_params` | `dict[str, SpeciesParams]` | Frozen species parameter objects keyed by name |
| `reach_params` | `dict[str, ReachParams]` | Frozen reach parameter objects keyed by name |
| `trout_state` | `TroutState` | Structure-of-arrays for all trout |
| `redd_state` | `ReddState` | Structure-of-arrays for all redds |
| `reach_state` | `ReachState` | Reach-level environmental state |
| `fem_space` | `FEMSpace` | Spatial container with KD-tree |
| `mesh` | `PolygonMesh` | Polygon mesh loaded from shapefile |
| `time_manager` | `TimeManager` | Time stepping and condition lookup |
| `rng` | `numpy.random.Generator` | Seeded random number generator |
| `backend` | `ComputeBackend` | Compute backend instance |
| `species_order` | `list[str]` | Ordered species names |
| `reach_order` | `list[str]` | Ordered reach names |

**Methods:**

```python
def step(self) -> None
```
Advance the simulation by one time step. Executes the full daily cycle: time advance, reach update, hydraulics, light, resource reset, habitat selection, growth, mortality, spawning, redd development, and Mesa agent sync.

```python
def run(self) -> None
```
Run the simulation from the current date until the end date by calling `step()` repeatedly.

---

## State Classes

### `TroutState`

```python
@dataclass
class TroutState:
    @classmethod
    def zeros(cls, capacity: int, max_steps_per_day: int = 4) -> TroutState
```

Structure-of-Arrays holding all trout agent data. All arrays have shape `(capacity,)` unless noted.

**Fields:**

| Field | dtype | Description |
|-------|-------|-------------|
| `alive` | `bool` | Whether the slot holds a living fish |
| `species_idx` | `int32` | Species identifier (0-based) |
| `length` | `float64` | Fork length (cm) |
| `weight` | `float64` | Body weight (g) |
| `condition` | `float64` | Condition factor K (weight / healthy_weight, 0-1+) |
| `age` | `int32` | Age in years (incremented on Jan 1) |
| `cell_idx` | `int32` | Current habitat cell index (-1 = unassigned) |
| `reach_idx` | `int32` | Current reach index (-1 = unassigned) |
| `activity` | `int32` | Current activity: 0=drift, 1=search, 2=hide, 3=guard, 4=hold |
| `sex` | `int32` | Sex: 0=female, 1=male |
| `superind_rep` | `int32` | Number of individuals this super-individual represents |
| `life_history` | `int32` | Life stage: 0=FRY, 1=PARR, 2=SPAWNER, 3=SMOLT, 4=OCEAN_JUVENILE, 5=OCEAN_ADULT, 6=RETURNING_ADULT, 7=KELT (see `salmopy.state.life_stage.LifeStage`) |
| `in_shelter` | `bool` | Whether fish is using velocity shelter |
| `spawned_this_season` | `bool` | Whether fish has spawned this season |
| `last_growth_rate` | `float64` | Growth rate from most recent habitat selection (g/d) |
| `growth_memory` | `float64` | Shape `(capacity, max_steps_per_day)`. Within-day growth history |
| `consumption_memory` | `float64` | Shape `(capacity, max_steps_per_day)`. Within-day consumption history |
| `survival_memory` | `float64` | Shape `(capacity, max_steps_per_day)`. Within-day survival history |
| `resp_std_wt_term` | `float64` | Cached: `resp_A * weight^resp_B` |
| `max_speed_len_term` | `float64` | Cached: `max_speed_A * length + max_speed_B` |
| `cmax_wt_term` | `float64` | Cached: `cmax_A * weight^cmax_B` |

**Methods:**

```python
def num_alive(self) -> int
```
Return the count of living fish.

```python
def alive_indices(self) -> np.ndarray
```
Return an array of integer indices where `alive == True`.

```python
def first_dead_slot(self) -> int
```
Return the index of the first dead (empty) slot, or -1 if full.

---

### `CellState`

```python
@dataclass
class CellState:
    @classmethod
    def zeros(cls, num_cells: int, num_flows: int = 1) -> CellState
```

Structure-of-Arrays for habitat cell data. All 1-D arrays have shape `(num_cells,)`.

**Static fields:**

| Field | dtype | Description |
|-------|-------|-------------|
| `area` | `float64` | Cell area (cm^2) |
| `centroid_x` | `float64` | X coordinate of cell centroid (CRS units) |
| `centroid_y` | `float64` | Y coordinate of cell centroid (CRS units) |
| `reach_idx` | `int32` | Reach index this cell belongs to |
| `num_hiding_places` | `int32` | Number of hiding places |
| `dist_escape` | `float64` | Distance to nearest escape cover (cm) |
| `frac_vel_shelter` | `float64` | Fraction of area with velocity shelter (0-1) |
| `frac_spawn` | `float64` | Fraction of area with spawning gravel (0-1) |

**Dynamic fields (updated each step):**

| Field | dtype | Description |
|-------|-------|-------------|
| `depth` | `float64` | Water depth (cm) |
| `velocity` | `float64` | Water velocity (cm/s) |
| `light` | `float64` | Light level at cell |
| `available_drift` | `float64` | Available drift food (g) |
| `available_search` | `float64` | Available search food (g) |
| `available_vel_shelter` | `float64` | Available velocity shelter area (cm^2) |
| `available_hiding_places` | `int32` | Remaining hiding places |

**Hydraulic lookup tables:**

| Field | Shape | Description |
|-------|-------|-------------|
| `depth_table_flows` | `(num_flows,)` | Flow breakpoints for depth interpolation |
| `depth_table_values` | `(num_cells, num_flows)` | Depth at each flow breakpoint per cell |
| `vel_table_flows` | `(num_flows,)` | Flow breakpoints for velocity interpolation |
| `vel_table_values` | `(num_cells, num_flows)` | Velocity at each flow breakpoint per cell |

---

### `ReddState`

```python
@dataclass
class ReddState:
    @classmethod
    def zeros(cls, capacity: int) -> ReddState
```

Structure-of-Arrays for redd (egg nest) data. Shape `(capacity,)`.

**Fields:**

| Field | dtype | Description |
|-------|-------|-------------|
| `alive` | `bool` | Whether the redd is active |
| `species_idx` | `int32` | Species identifier |
| `num_eggs` | `int32` | Current egg count |
| `frac_developed` | `float64` | Fractional development (0.0 to 1.0+) |
| `emerge_days` | `int32` | Days since emergence started |
| `cell_idx` | `int32` | Cell index where redd is located |
| `reach_idx` | `int32` | Reach index |
| `eggs_initial` | `int32` | Initial egg count at creation |
| `eggs_lo_temp` | `int32` | Cumulative eggs lost to low temperature |
| `eggs_hi_temp` | `int32` | Cumulative eggs lost to high temperature |
| `eggs_dewatering` | `int32` | Cumulative eggs lost to dewatering |
| `eggs_scour` | `int32` | Cumulative eggs lost to scour |

**Methods:**

```python
def num_alive(self) -> int
```
Return the count of active redds.

```python
def first_dead_slot(self) -> int
```
Return the index of the first inactive slot, or -1 if full.

---

### `ReachState`

```python
@dataclass
class ReachState:
    @classmethod
    def zeros(cls, num_reaches: int, num_species: int = 1) -> ReachState
```

Structure-of-Arrays for reach-level environmental state.

**Fields:**

| Field | Shape | Description |
|-------|-------|-------------|
| `flow` | `(num_reaches,)` | Discharge (m^3/s) |
| `temperature` | `(num_reaches,)` | Water temperature (C) |
| `turbidity` | `(num_reaches,)` | Turbidity (NTU) |
| `cmax_temp_func` | `(num_reaches, num_species)` | CMax temperature multiplier |
| `max_swim_temp_term` | `(num_reaches, num_species)` | Max swim speed temperature term |
| `resp_temp_term` | `(num_reaches, num_species)` | Respiration temperature term |
| `scour_param` | `(num_reaches,)` | Scour parameter |
| `is_flow_peak` | `(num_reaches,)` | Whether current flow exceeds previous |

---

### `SpeciesParams`

```python
@dataclass(frozen=True)
class SpeciesParams:
```

Immutable species parameters used at runtime. Numpy array fields are made read-only.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Species name |
| `cmax_A` | `float` | CMax allometric coefficient |
| `cmax_B` | `float` | CMax allometric exponent |
| `weight_A` | `float` | Weight allometric coefficient |
| `weight_B` | `float` | Weight allometric exponent |
| `cmax_temp_table_x` | `ndarray` | Temperature breakpoints for CMax interpolation |
| `cmax_temp_table_y` | `ndarray` | CMax multiplier values at each breakpoint |
| `max_speed_C` | `float` | Max swim speed quadratic temperature coefficient |
| `max_speed_D` | `float` | Max swim speed linear temperature coefficient |
| `max_speed_E` | `float` | Max swim speed constant term |
| `resp_C` | `float` | Respiration temperature exponent: `exp(resp_C * T^2)` |

---

### `ReachParams`

```python
@dataclass(frozen=True)
class ReachParams:
```

Immutable reach parameters used at runtime.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Reach name |
| `drift_conc` | `float` | Drift food concentration (g/cm^3) |
| `search_prod` | `float` | Search food production (g/cm^2/d) |
| `shelter_speed_frac` | `float` | Velocity reduction factor in shelter (0-1) |
| `prey_energy_density` | `float` | Prey energy density (J/g) |
| `drift_regen_distance` | `float` | Drift regeneration distance (cm) |
| `shading` | `float` | Fraction of light reaching water (0-1) |
| `fish_pred_min` | `float` | Minimum daily survival from fish predation |
| `terr_pred_min` | `float` | Minimum daily survival from terrestrial predation |
| `light_turbid_coef` | `float` | Light-turbidity coefficient |
| `light_turbid_const` | `float` | Light-turbidity constant |
| `max_spawn_flow` | `float` | Maximum flow allowing spawning (m^3/s) |
| `shear_A` | `float` | Shear stress coefficient A |
| `shear_B` | `float` | Shear stress exponent B |
| `upstream_junction` | `int` | Upstream junction node ID |
| `downstream_junction` | `int` | Downstream junction node ID |

---

## Configuration

### Config Classes

All configuration classes use Pydantic `BaseModel` for validation.

```python
class ModelConfig(BaseModel):
    simulation: SimulationConfig
    performance: PerformanceConfig = PerformanceConfig()
    spatial: SpatialConfig = SpatialConfig()
    light: LightConfig = LightConfig()
    species: Dict[str, SpeciesConfig] = {}
    reaches: Dict[str, ReachConfig] = {}
```

#### `SimulationConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `start_date` | `str` | required | Simulation start date (ISO: `"2011-04-01"`) |
| `end_date` | `str` | required | Simulation end date |
| `output_frequency` | `int` | `1` | Output every N steps |
| `output_units` | `str` | `"days"` | Output frequency units |
| `seed` | `int` | `0` | Random seed (0 = not seeded) |
| `census_days` | `list[str]` | `[]` | Census dates as `"MM-dd"` strings |
| `census_years_to_skip` | `int` | `0` | Years from start to suppress census |
| `population_file` | `str` | `""` | Path to initial population CSV |

#### `PerformanceConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backend` | `str` | `"numpy"` | Compute backend: `"numpy"`, `"numba"`, or `"jax"` |
| `device` | `str` | `"cpu"` | Device for computation |
| `trout_capacity` | `int` | `2000` | Maximum number of trout slots |
| `redd_capacity` | `int` | `500` | Maximum number of redd slots |
| `jit_warmup` | `bool` | `False` | Whether to JIT-warmup at init |

#### `SpatialConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backend` | `str` | `"shapefile"` | Spatial backend type |
| `mesh_file` | `str` | `""` | Path to shapefile (relative to data dir) |
| `gis_properties` | `Dict[str, str]` | `{}` | Mapping of internal names to shapefile column names |

#### `LightConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `latitude` | `float` | `0.0` | Site latitude (degrees) |
| `light_correction` | `float` | `1.0` | Light correction factor |
| `light_at_night` | `float` | `0.0` | Minimum light at night |
| `twilight_angle` | `float` | `6.0` | Solar angle defining twilight (degrees) |

#### `SpeciesConfig`

Pydantic model with `extra="allow"` -- accepts any parameter from the YAML.

**Consumption:**

| Field | Default | Description |
|-------|---------|-------------|
| `cmax_A` | `0.0` | CMax allometric coefficient |
| `cmax_B` | `0.0` | CMax allometric exponent |
| `cmax_temp_table` | `{}` | Temperature-to-CMax lookup `{temp: multiplier}` |

**Weight:**

| Field | Default | Description |
|-------|---------|-------------|
| `weight_A` | `0.0` | Allometric coefficient: `W = A * L^B` |
| `weight_B` | `0.0` | Allometric exponent |

**Swimming:**

| Field | Default | Description |
|-------|---------|-------------|
| `max_speed_A` | `0.0` | Length coefficient for max swim speed |
| `max_speed_B` | `0.0` | Length intercept for max swim speed |
| `max_speed_C` | `0.0` | Quadratic temperature coefficient |
| `max_speed_D` | `0.0` | Linear temperature coefficient |
| `max_speed_E` | `0.0` | Constant term |

**Movement:**

| Field | Default | Description |
|-------|---------|-------------|
| `move_radius_max` | `0.0` | Maximum movement radius (CRS units) |
| `move_radius_L1` | `0.0` | Length at logistic = 0.1 |
| `move_radius_L9` | `0.0` | Length at logistic = 0.9 |

**Spawning:**

| Field | Default | Description |
|-------|---------|-------------|
| `spawn_start_day` | `""` | Season start as `"MM-dd"` |
| `spawn_end_day` | `""` | Season end as `"MM-dd"` |
| `spawn_min_age` | `0.0` | Minimum age (negative = disabled) |
| `spawn_min_length` | `0.0` | Minimum length (negative = disabled) |
| `spawn_min_cond` | `0.0` | Minimum condition (negative = disabled) |
| `spawn_min_temp` | `0.0` | Minimum water temperature (C) |
| `spawn_max_temp` | `0.0` | Maximum water temperature (C) |
| `spawn_prob` | `0.0` | Daily spawn probability when conditions met |
| `spawn_fecund_mult` | `0.0` | Fecundity multiplier |
| `spawn_fecund_exp` | `0.0` | Fecundity exponent: `eggs = mult * weight^exp * viability` |
| `spawn_egg_viability` | `0.0` | Fraction of viable eggs (0-1) |
| `spawn_wt_loss_fraction` | `0.0` | Weight loss fraction after spawning |
| `spawn_depth_table` | `{}` | Depth suitability: `{depth_cm: suitability}` |
| `spawn_vel_table` | `{}` | Velocity suitability: `{vel_cm_s: suitability}` |

**Mortality:**

| Field | Default | Description |
|-------|---------|-------------|
| `mort_high_temp_T1` | `0.0` | High-temp logistic L1 (C) |
| `mort_high_temp_T9` | `0.0` | High-temp logistic L9 (C) |
| `mort_strand_survival_when_dry` | `0.0` | Daily survival when stranded |
| `mort_condition_S_at_K5` | `0.0` | Survival at condition = 0.5 |
| `mort_condition_S_at_K8` | `0.0` | Survival at condition = 0.8 |
| `mort_fish_pred_*` | `0.0` | Fish predation logistic params (L1/L9, D1/D9, P1/P9, I1/I9, T1/T9) |
| `mort_fish_pred_hiding_factor` | `0.0` | Risk reduction when hiding |
| `mort_terr_pred_*` | `0.0` | Terrestrial predation logistic params (L1/L9, D1/D9, V1/V9, I1/I9, H1/H9) |
| `mort_terr_pred_hiding_factor` | `0.0` | Risk reduction when hiding |
| `mort_redd_lo_temp_T1/T9` | `0.0` | Redd low-temp logistic params |
| `mort_redd_hi_temp_T1/T9` | `0.0` | Redd high-temp logistic params |
| `mort_redd_dewater_surv` | `0.0` | Redd dewatering survival |
| `mort_redd_scour_depth` | `0.0` | Redd scour depth threshold |

**Respiration:**

| Field | Default | Description |
|-------|---------|-------------|
| `resp_A` | `0.0` | Standard respiration coefficient |
| `resp_B` | `0.0` | Standard respiration weight exponent |
| `resp_C` | `0.0` | Temperature quadratic exponent |
| `resp_D` | `0.0` | Activity (swim speed ratio) exponent |

**Redd development:**

| Field | Default | Description |
|-------|---------|-------------|
| `redd_devel_A` | `0.0` | Development constant |
| `redd_devel_B` | `0.0` | Development linear temperature coefficient |
| `redd_devel_C` | `0.0` | Development quadratic temperature coefficient |

#### `ReachConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `drift_conc` | `float` | `0.0` | Drift food concentration (g/cm^3) |
| `search_prod` | `float` | `0.0` | Search food production rate (g/cm^2/d) |
| `shelter_speed_frac` | `float` | `0.0` | Velocity reduction in shelter (0-1) |
| `prey_energy_density` | `float` | `0.0` | Prey energy density (J/g) |
| `drift_regen_distance` | `float` | `0.0` | Drift regeneration distance (cm) |
| `shading` | `float` | `0.0` | Light reduction from canopy (0-1) |
| `fish_pred_min` | `float` | `0.0` | Minimum daily survival from fish predation |
| `terr_pred_min` | `float` | `0.0` | Minimum daily survival from terrestrial predation |
| `light_turbid_coef` | `float` | `0.0` | Light-turbidity coefficient |
| `light_turbid_const` | `float` | `0.0` | Light-turbidity constant |
| `max_spawn_flow` | `float` | `0.0` | Maximum flow for spawning (m^3/s) |
| `shear_A` | `float` | `0.0` | Shear stress coefficient |
| `shear_B` | `float` | `0.0` | Shear stress exponent |
| `upstream_junction` | `int` | `0` | Upstream junction ID |
| `downstream_junction` | `int` | `0` | Downstream junction ID |
| `time_series_input_file` | `str` | `""` | Path to time-series CSV |
| `depth_file` | `str` | `""` | Path to depth hydraulic table CSV |
| `velocity_file` | `str` | `""` | Path to velocity hydraulic table CSV |

### Config Functions

```python
def load_config(path: Path) -> ModelConfig
```
Load a YAML configuration file and return a validated `ModelConfig`.

**Parameters:** `path` -- Path to the YAML file.
**Returns:** `ModelConfig` instance.
**Raises:** `FileNotFoundError` if file does not exist.

```python
def params_from_config(config: ModelConfig) -> tuple[dict[str, SpeciesParams], dict[str, ReachParams]]
```
Convert a `ModelConfig` into frozen runtime parameter objects. Returns `(species_params, reach_params)` dicts keyed by name.

```python
def nls_to_yaml(nls_path: Path) -> str
```
Parse a NetLogo `.nls` parameter file and return the equivalent YAML configuration string. Useful for converting existing inSTREAM 7 setups.

---

## Modules

### `growth`

```python
def cmax_temp_function(temperature, table_x, table_y) -> float
```
CMax temperature multiplier via linear interpolation of lookup table. O(log n) scalar lookup using `bisect`.

```python
def c_stepmax(cmax_wt_term, cmax_temp, prev_consumption, step_length) -> float
```
Maximum consumption for current time step (g/d daily rate). `cmax_wt_term = cmax_A * weight^cmax_B`.

```python
def max_swim_speed(max_speed_len_term, max_swim_temp_term) -> float
```
Maximum sustainable swimming speed (cm/s). `max_speed_len_term = A * length + B`. `max_swim_temp_term = C*T^2 + D*T + E`.

```python
def drift_intake(
    length, depth, velocity, light, turbidity, drift_conc,
    max_swim_speed, c_stepmax_val, available_drift, superind_rep,
    react_dist_A, react_dist_B, turbid_threshold, turbid_min, turbid_exp,
    light_threshold, light_min, light_exp, capture_R1, capture_R9,
) -> float
```
Daily gross drift feeding intake (g/d). Computes detection distance, turbidity/light adjustments, capture geometry, and capture success via logistic function.

```python
def search_intake(
    velocity, max_swim_speed, search_prod, search_area,
    c_stepmax_val, available_search, superind_rep,
) -> float
```
Daily gross search feeding intake (g/d). Limited by CStepMax and available search food.

```python
def respiration(resp_std_wt_term, resp_temp_term, swim_speed, max_swim_speed, resp_D) -> float
```
Total respiration (J/d). Combines standard respiration with activity multiplier `exp(resp_D * (swim_speed / max_speed)^2)`.

```python
def growth_rate_for(
    activity, length, weight, depth, velocity, light, turbidity, temperature,
    drift_conc, search_prod, search_area, available_drift, available_search,
    available_shelter, shelter_speed_frac, superind_rep, prev_consumption,
    step_length, cmax_A, cmax_B, cmax_temp_table_x, cmax_temp_table_y,
    react_dist_A, react_dist_B, turbid_threshold, turbid_min, turbid_exp,
    light_threshold, light_min, light_exp, capture_R1, capture_R9,
    max_speed_A, max_speed_B, max_swim_temp_term, resp_A, resp_B, resp_D,
    resp_temp_term, prey_energy_density, fish_energy_density,
) -> float
```
Compute growth rate (g/d) for a fish at a cell with a given activity (0=drift, 1=search, 2=hide). Returns `net_energy / fish_energy_density`.

```python
def apply_growth(weight, length, condition, growth, weight_A, weight_B) -> tuple[float, float, float]
```
Update weight, length, and condition from daily growth. If new weight exceeds healthy weight, length increases; otherwise condition decreases. Returns `(new_weight, new_length, new_condition)`.

```python
def split_superindividuals(trout_state, max_length) -> None
```
Split super-individuals that exceed the length threshold. Copies all attributes to a new slot and halves the rep count. Modifies `trout_state` in place.

---

### `survival`

```python
def survival_high_temperature(temperature, T1=28.0, T9=24.0) -> float
```
Survival probability from high water temperature. Uses decreasing logistic. Returns value in [0, 1].

```python
def survival_stranding(depth, survival_when_dry=0.5) -> float
```
Survival probability from stranding. Returns `survival_when_dry` if depth <= 0, else 1.0.

```python
def survival_condition(condition, S_at_K5=0.8, S_at_K8=0.992) -> float
```
Survival based on body condition. Two-piece linear from (0.5, S_at_K5) through (0.8, S_at_K8) to (1.0, 1.0). Clamped to [0, 1].

```python
def survival_fish_predation(
    length, depth, light, pisciv_density, temperature, activity,
    min_surv, L1, L9, D1, D9, P1, P9, I1, I9, T1, T9, hiding_factor,
) -> float
```
Survival from piscivorous fish predation. Product of logistic risk terms for length, depth, piscivore density, light, and temperature. Hiding reduces risk by `hiding_factor`. Returns value in [min_surv, 1.0].

```python
def survival_terrestrial_predation(
    length, depth, velocity, light, dist_escape, activity,
    available_hiding, superind_rep, min_surv,
    L1, L9, D1, D9, V1, V9, I1, I9, H1, H9, hiding_factor,
) -> float
```
Survival from terrestrial predation (birds, mammals). Logistic risk terms for length, depth, velocity, light, and distance to escape. Hiding requires sufficient hiding places. Returns value in [min_surv, 1.0].

```python
def non_starve_survival(s_high_temp, s_stranding, s_fish_pred, s_terr_pred) -> float
```
Combined non-starvation survival as product of independent mortality sources. Condition survival is handled separately.

```python
def apply_mortality(alive, survival_probs, rng) -> None
```
Apply stochastic mortality in place. For each alive fish, draw uniform random; if `draw >= survival_prob`, fish dies.

```python
def apply_redd_survival(
    num_eggs, frac_developed, temperatures, depths, flows, is_peak, *,
    step_length=1.0, lo_T1=1.7, lo_T9=4.0, hi_T1=23.0, hi_T9=17.5,
    dewater_surv=0.9, shear_A=0.013, shear_B=0.40, scour_depth=20.0,
) -> tuple[ndarray, ndarray, ndarray, ndarray, ndarray]
```
Apply all redd survival components (low-temp, high-temp, dewatering, scour). Returns `(new_eggs, lo_deaths, hi_deaths, dw_deaths, sc_deaths)`.

---

### `behavior`

```python
def evaluate_logistic(x, L1, L9) -> float
```
Evaluate logistic function where `f(L1) = 0.1` and `f(L9) = 0.9`. Pure Python scalar version.

```python
def evaluate_logistic_array(x, L1, L9) -> np.ndarray
```
Vectorized logistic function over a numpy array.

```python
def movement_radius(length, move_radius_max, move_radius_L1, move_radius_L9) -> float
```
Calculate habitat selection radius (CRS units). Returns `move_radius_max * logistic(length)`.

```python
def build_candidate_mask(trout_state, fem_space, move_radius_max, move_radius_L1, move_radius_L9) -> np.ndarray
```
Build boolean mask of shape `(capacity, num_cells)`. True = fish can consider that cell. Uses KD-tree radius query plus direct neighbors. Excludes dry cells.

```python
def fitness_for(
    activity, length, weight, depth, velocity, light, turbidity, temperature,
    drift_conc, search_prod, search_area, ..., **survival_params,
) -> float
```
Compute fitness for a fish at a cell with given activity. Fitness = `growth * step_length * non_starve_survival * condition_survival`. Penalizes cells with high predation risk, extreme temperature, or stranding.

```python
def select_habitat_and_activity(trout_state, fem_space, **params) -> None
```
Main habitat selection. For each alive fish (sorted largest-first), evaluate all candidate cells and three activities (drift, search, hide), pick the combination with highest fitness, move the fish, and deplete resources immediately. Modifies `trout_state` in place. Supports optional Numba fast path.

---

### `spawning`

```python
def ready_to_spawn(
    sex, age, length, condition, temperature, flow, spawned_this_season,
    day_of_year, spawn_min_age, spawn_min_length, spawn_min_cond,
    spawn_min_temp, spawn_max_temp, spawn_prob, max_spawn_flow,
    spawn_start_doy, spawn_end_doy, rng,
) -> bool
```
Check whether a fish is ready to spawn. Checks sex (female only), season window, age/length/condition thresholds (negative = disabled), temperature window, flow limit, and probabilistic test.

```python
def spawn_suitability(
    depth, velocity, frac_spawn, area,
    depth_table_x, depth_table_y, vel_table_x, vel_table_y,
) -> float
```
Compute spawn suitability score for a cell. Interpolates depth and velocity suitability from lookup tables, multiplied by spawnable fraction and area.

```python
def select_spawn_cell(scores, candidates) -> int
```
Select the cell with the highest suitability score. Returns cell index.

```python
def create_redd(
    redd_state, species_idx, cell_idx, reach_idx,
    weight, fecund_mult, fecund_exp, egg_viability,
) -> bool
```
Create a new redd in the first available slot. Egg count = `fecund_mult * weight^fecund_exp * egg_viability`. Returns True if created, False if no slot available.

```python
def apply_spawner_weight_loss(weight, wt_loss_fraction) -> float
```
Apply post-spawning weight loss. Returns `weight * (1.0 - wt_loss_fraction)`.

```python
def develop_eggs(frac_developed, temperature, step_length, devel_A, devel_B, devel_C) -> float
```
Advance egg fractional development. Increment = `(A + B*T + C*T^2) * step_length`. Returns updated fraction.

```python
def redd_emergence(
    redd_state, trout_state, rng,
    emerge_length_min, emerge_length_mode, emerge_length_max,
    weight_A, weight_B, species_index,
) -> None
```
Hatch eggs from fully-developed redds (frac_developed >= 1.0). New fry fill dead trout slots with triangular-distributed lengths. Modifies both state objects in place.

---

### `reach`

```python
def update_reach_state(
    reach_state, conditions, reach_names, species_params, backend,
    species_order=None,
) -> None
```
Update reach state from current time-series conditions. Sets flow, temperature, turbidity for each reach. Computes species-dependent intermediates: `cmax_temp_func`, `max_swim_temp_term = C*T^2 + D*T + E`, `resp_temp_term = exp(resp_C * T^2)`.

---

### `migration`

```python
def build_reach_graph(upstream_junctions, downstream_junctions) -> dict[int, list[int]]
```
Build reach connectivity from junction arrays. Returns dict mapping reach index to list of downstream reach indices.

```python
def migration_fitness(length, L1, L9) -> float
```
Migration fitness for a fish (logistic of length).

```python
def should_migrate(migration_fit, best_habitat_fit, life_history) -> bool
```
Decide if a fish should migrate downstream. Only anadromous juveniles (`life_history == 1`) migrate, and only when `migration_fit > best_habitat_fit`.

```python
def migrate_fish_downstream(trout_state, fish_idx, reach_graph) -> list[dict]
```
Move a fish to the downstream reach. If no downstream reach exists, fish becomes an outmigrant (removed from simulation). Returns list of outmigrant records.

---

## Backends

### `ComputeBackend` (Protocol)

```python
@runtime_checkable
class ComputeBackend(Protocol):
    def update_hydraulics(self, flow, table_flows, depth_values, vel_values) -> tuple[ndarray, ndarray]: ...
    def compute_light(self, julian_date, latitude, light_correction, shading, light_at_night, twilight_angle) -> tuple[float, float, float]: ...
    def compute_cell_light(self, depths, irradiance, turbid_coef, turbidity, light_at_night) -> ndarray: ...
    def growth_rate(self, lengths, weights, temperatures, velocities, depths, **params) -> ndarray: ...
    def survival(self, lengths, weights, conditions, temperatures, depths, **params) -> ndarray: ...
    def fitness_all(self, trout_arrays, cell_arrays, candidates, **params) -> tuple[ndarray, ndarray]: ...
    def deplete_resources(self, fish_order, chosen_cells, available_drift, available_search, **params) -> tuple[ndarray, ndarray]: ...
    def spawn_suitability(self, depths, velocities, frac_spawn, **params) -> ndarray: ...
    def evaluate_logistic(self, x, L1, L9) -> ndarray: ...
    def interp1d(self, x, table_x, table_y) -> ndarray: ...
```

### `get_backend`

```python
def get_backend(name: str) -> ComputeBackend
```
Factory function. Returns backend instance for `"numpy"`, `"numba"`, or `"jax"` (not yet implemented).

### `NumpyBackend`

Pure NumPy implementation. No compilation overhead. Used by default.

### `NumbaBackend`

Numba JIT-compiled implementation. Requires `numba >= 0.59`. Install with `pip install instream[numba]`. Provides significant speedup for the inner fitness evaluation loop.

---

## I/O

```python
def read_time_series(path: str | Path) -> pd.DataFrame
```
Read an inSTREAM time-series CSV file. Skips `;`-prefixed comment lines. Returns DataFrame with `DatetimeIndex` and numeric columns (e.g. `temperature`, `flow`, `turbidity`).

```python
def read_initial_populations(path: Path) -> list[dict[str, Any]]
```
Read initial populations CSV. Skips `;`-prefixed comment lines. Returns list of dicts with keys: `species`, `reach`, `age`, `number`, `length_min`, `length_mode`, `length_max`.

```python
def read_depth_table(path, return_cell_ids=False) -> tuple
```
Read a depth hydraulic table CSV. Returns `(flows, values)` where flows is shape `(num_flows,)` and values is shape `(num_cells, num_flows)`. If `return_cell_ids=True`, also returns cell ID strings.

```python
def read_velocity_table(path, return_cell_ids=False) -> tuple
```
Read a velocity hydraulic table CSV. Same format as depth table.

### `TimeManager`

```python
class TimeManager:
    def __init__(self, start_date: str, end_date: str, time_series: dict[str, pd.DataFrame])
```

Manages simulation time advancement and environmental condition lookup.

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `current_date` | `pd.Timestamp` | Current simulation date |
| `julian_date` | `int` | Day of year (1-366) |

**Methods:**

```python
def advance(self) -> float
```
Advance by one day. Returns step length (1.0).

```python
def get_conditions(self, reach_name: str) -> dict[str, float]
```
Look up environmental conditions for a reach at the current date using nearest-date matching. Returns dict with keys like `flow`, `temperature`, `turbidity`.

```python
def is_done(self) -> bool
```
Return True when simulation has passed the end date.

```python
def formatted_time(self) -> str
```
Return current date as `"YYYY-MM-DD"` string.

### `is_census`

```python
def is_census(date, census_days, years_to_skip, start_date) -> bool
```
Check whether a date is a census day. Census days are specified as `"month/day"` strings. Census is suppressed for the first `years_to_skip` years.

---

## Spatial

### `PolygonMesh`

```python
class PolygonMesh:
    def __init__(
        self, shapefile_path, *,
        id_field, reach_field, area_field, dist_escape_field,
        hiding_field, shelter_field, spawn_field,
    )
```

Reads an ESRI shapefile of habitat cell polygons. Extracts cell attributes, centroids, and spatial adjacency.

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `shapefile_path` | Path to `.shp` file |
| `id_field` | Column name for cell IDs (e.g. `"ID_TEXT"`) |
| `reach_field` | Column name for reach names (e.g. `"REACH_NAME"`) |
| `area_field` | Column name for cell areas in m^2 (e.g. `"AREA"`) |
| `dist_escape_field` | Column name for distance to escape (e.g. `"M_TO_ESC"`) |
| `hiding_field` | Column for hiding places (e.g. `"NUM_HIDING"`) |
| `shelter_field` | Column for velocity shelter fraction (e.g. `"FRACVSHL"`) |
| `spawn_field` | Column for spawnable fraction (e.g. `"FRACSPWN"`) |

**Properties:** `num_cells`, `areas`, `centroids_x`, `centroids_y`, `reach_names`, `cell_ids`, `frac_spawn`, `frac_vel_shelter`, `num_hiding_places`, `dist_escape`, `neighbor_indices`.

```python
def to_cell_state(self, depth_flows, depth_values, vel_flows, vel_values) -> CellState
```
Create a `CellState` from this mesh and hydraulic lookup tables. Areas are converted from m^2 to cm^2 during mesh loading.

---

### `FEMSpace`

```python
class FEMSpace:
    def __init__(self, cell_state: CellState, neighbor_indices: np.ndarray)
```

Spatial container wrapping cell state with KD-tree indexing. Accepts any mesh backend output.

**Attributes:** `cell_state`, `neighbor_indices`, `num_cells`.

```python
def cells_in_radius(self, cell_idx: int, radius: float) -> np.ndarray
```
Return indices of all cells within `radius` of the given cell (CRS units, typically meters).

```python
def get_neighbor_indices(self, cell_idx: int) -> np.ndarray
```
Return neighbor indices for given cell (padded with -1).

```python
def update_hydraulics(self, flow: float, backend) -> None
```
Update depth and velocity for all cells at the given flow by interpolating hydraulic tables via the compute backend.

---

## WGBAST Roadmap APIs (v0.34.0 → v0.41.0)

Public APIs added by Arcs K through Q. All are **opt-in** — they activate
only when their corresponding config fields or kwargs are set; defaults
preserve v0.33.0 behavior and NetLogo InSALMO 7.3 parity.

### Arc K — PSPC output

```python
def write_smolt_production_by_reach(
    outmigrants,
    reach_names,
    reach_pspc,
    year,
    output_dir,
    filename=None,
) -> Path
```
Located in `instream.io.output`. Groups outmigrant records by
`natal_reach_idx` and emits a per-year CSV with columns `year`,
`reach_idx`, `reach_name`, `smolts_produced`, `pspc_smolts_per_year`,
`pspc_achieved_pct`. Non-natal reaches (PSPC is None) emit blank
pct/pspc but still report `smolts_produced`.

Activated automatically by `write_outputs()` when any
`ReachConfig.pspc_smolts_per_year` is set. Default filename:
`smolt_production_by_reach_{year}.csv`.

### Arc L — M74 YSFM forcing

```python
def load_m74_forcing(path: Path | str) -> Dict[Tuple[int, str], float]
def ysfm_for_year_river(series, year: int, river: str) -> float
```
Located in `instream.io.m74_forcing`. Loads per-(year, river) YSFM
fractions; returns 0.0 for unknown tuples (fail-safe).

```python
def apply_m74_cull(
    n_fry: int, year: int, river: str,
    forcing_csv: Path | str | None,
    rng: np.random.Generator,
) -> int
```
Located in `instream.modules.egg_emergence_m74`. Binomial
`p_survive = 1 - ysfm_fraction`; no-op when `forcing_csv` is None.
Applied at egg→fry emergence via `redd_emergence(..., m74_forcing_csv,
current_year, river_name_by_reach_idx)`.

### Arc N — Post-smolt survival forcing

```python
def load_post_smolt_forcing(path) -> Dict[Tuple[int, str], float]
def annual_survival_for_year(series, year, stock_unit) -> Optional[float]
def daily_hazard_multiplier(annual_survival, days_per_year=365) -> float
```
Located in `instream.marine.survival_forcing`. `daily_hazard_multiplier`
inverts `(1 - h)^365 = S_annual` exactly.

`marine_survival` accepts a new `current_year: int | None = None`
kwarg. When `MarineConfig.post_smolt_survival_forcing_csv` is set AND
`current_year` is provided, fish with `days_since_ocean_entry < 365`
have `background_hazard` replaced by the per-(smolt-year, stock-unit)
value. Smolt year is derived as
`current_year - (days_since_ocean_entry // 365)`.

### Arc O — Straying + MSA matrix

```python
# MarineConfig additions
stray_fraction: float = 0.0  # 0 = perfect homing
```

`check_adult_return` accepts a new `config=None` kwarg. When
`config.stray_fraction > 0`, a returning adult's spawning `reach_idx`
is reassigned (with prob `stray_fraction`) to a random non-natal
freshwater reach. `natal_reach_idx` stays fixed (genetic property).

```python
def write_spawner_origin_matrix(
    spawners, reach_names, year, output_dir, filename=None,
) -> Path
```
Located in `instream.io.output`. Emits a natal × spawning-reach matrix
(rep-weighted). Row index `natal_reach`; columns are spawning reaches.
Diagonal under perfect homing; off-diagonals populate with straying.

### Arc P — HELCOM grey-seal scaling

```python
def load_seal_abundance(path) -> Dict[Tuple[int, str], float]
def abundance_for_year(series, year, sub_basin) -> Optional[float]
def seal_hazard_multiplier(
    abundance: float,
    reference_abundance: float = 30000.0,
    saturation_k_half: float = 2.0,
) -> float
```
Located in `instream.marine.seal_forcing`. Holling Type II saturating
multiplier anchored at `reference` so `mult(reference) = 1.0`.
Asymptotes at `k_half + 1 = 3.0` for default `k_half = 2.0`.

`seal_hazard` accepts a new `current_year: int | None = None` kwarg.
When `MarineConfig.seal_abundance_csv` is set AND `current_year` is
provided, the length-logistic base hazard is multiplied by the HELCOM
abundance-driven Type II factor.

### Arc Q — Bayesian wrapper

`instream.bayesian` public API:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Prior:
    name: str
    lower: float
    upper: float
    shape: str = "uniform"  # {"uniform", "log_uniform", "beta"}

    def sample(self, rng: np.random.Generator, n: int = 1) -> np.ndarray
```

```python
BALTIC_SALMON_PRIORS: List[Prior]
```
Default Baltic salmon prior set: `post_smolt_survival` U(0.02, 0.18),
`m74_baseline` U(0, 0.30), `stray_fraction` U(0, 0.25),
`fecundity_mult` U(500, 900).

```python
def log_likelihood_smolt_trap(
    simulated_smolts: float,
    observed_count: int,
    trap_efficiency: float,
) -> float

def log_likelihood_spawner_counter(
    simulated_spawners: float,
    observed_count: int,
    detection_probability: float,
    overdispersion_k: float = 50.0,
) -> float
```
Poisson + negative-binomial likelihoods. NB default `k=50` matches
Orell & Erkinaro 2007 video-counter inter-observer agreement
(CV ≈ 15 % at µ=100).

```python
def run_smc(
    priors: Sequence[Prior],
    run_model_fn: Callable[[Dict[str, float], int], Dict],
    observations: List[Dict],
    n_particles: int = 500,
    n_temperature_steps: int = 10,
    rng: np.random.Generator | None = None,
) -> Dict
```
ABC-SMC with tempered log-likelihood and ESS-triggered resampling.
Returns a dict with keys `particles`, `weights`,
`log_marginal_likelihood`, `param_names`.

Each observation dict must contain `metric_name`, `observed`, `ll_fn`,
and optionally `ll_kwargs`. See `tests/test_bayesian.py` for a
self-contained example.

### Config fields added across Arcs K-Q

| Config class | Field | Arc | Default |
|--------------|-------|-----|---------|
| `ReachConfig` | `pspc_smolts_per_year: float \| None` | K | None |
| `ReachConfig` | `river_name: str \| None` | L | None |
| `ReachParams` | `river_name: str \| None` | L | None |
| `SimulationConfig` | `m74_forcing_csv: str \| None` | L | None |
| `MarineConfig` | `post_smolt_survival_forcing_csv: str \| None` | N | None |
| `MarineConfig` | `stock_unit: str \| None` | N | `"sal.27.22-31"` |
| `MarineConfig` | `stray_fraction: float` | O | 0.0 |
| `MarineConfig` | `seal_abundance_csv: str \| None` | P | None |
| `MarineConfig` | `seal_reference_abundance: float` | P | 30000.0 |
| `MarineConfig` | `seal_sub_basin: str` | P | `"main_basin"` |
| `MarineConfig` | `seal_saturation_k_half: float` | P | 2.0 |

### Shipped forcing CSVs

All under `data/wgbast/` or `data/helcom/`. Schema:
`Dict[Tuple[int, str], float]` in-memory, comment-tolerant CSV on disk.

| File | Arc | Keys |
|------|-----|------|
| `data/wgbast/m74_ysfm_series.csv` | L | (year, river) |
| `data/wgbast/post_smolt_survival_baltic.csv` | N | (year, stock_unit) |
| `data/wgbast/observations/smolt_trap_counts.csv` | Q | (year, river) |
| `data/helcom/grey_seal_abundance_baltic.csv` | P | (year, sub_basin) |

See `docs/validation/wgbast-roadmap-complete.md` for the cross-arc
narrative and `docs/releases/v0.34-to-v0.41-wgbast-summary.md` for
user-facing release notes.
