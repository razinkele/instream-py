# inSTREAM-py User Manual

Version 0.1.0

---

## 1. Getting Started

### Installation

inSTREAM-py requires Python 3.11 or later. Install from the project root:

```bash
pip install -e .
```

For Numba acceleration (recommended for production runs):

```bash
pip install -e ".[numba]"
```

For development (tests, coverage):

```bash
pip install -e ".[dev]"
```

**Dependencies:** mesa, numpy, scipy, pandas, geopandas, shapely, pydantic, pyyaml.

### Running the Example A Simulation

```python
from instream.model import InSTREAMModel

model = InSTREAMModel(
    config_path="configs/example_a.yaml",
    data_dir="path/to/Example-Project-A_1Reach-1Species",
)
model.run()
```

Or with an early stop for testing:

```python
model = InSTREAMModel(
    config_path="configs/example_a.yaml",
    data_dir="path/to/data",
    end_date_override="2011-05-01",
)
model.run()
```

From the command line:

```bash
instream configs/example_a.yaml
```

### Inspecting Output

After running, access simulation state directly:

```python
# Population count
print(f"Alive trout: {model.trout_state.num_alive()}")
print(f"Active redds: {model.redd_state.num_alive()}")

# Current date
print(f"Date: {model.time_manager.formatted_time()}")

# Fish lengths
alive = model.trout_state.alive_indices()
lengths = model.trout_state.length[alive]
print(f"Mean length: {lengths.mean():.1f} cm")
```

---

## 2. Preparing Input Data

Each simulation requires four types of input files: a shapefile for spatial geometry, hydraulic depth and velocity tables, a time-series CSV, and an initial population CSV.

### Shapefile (.shp)

The shapefile defines habitat cell polygons. Each polygon represents one modeled habitat cell.

**Required attribute fields:**

| Field | Default Name | Description |
|-------|-------------|-------------|
| Cell ID | `ID_TEXT` | Unique text identifier for each cell |
| Reach name | `REACH_NAME` | Which reach this cell belongs to |
| Area | `AREA` | Polygon area in m^2 |
| Distance to escape | `M_TO_ESC` | Distance to nearest escape cover (cm) |
| Hiding places | `NUM_HIDING` | Number of hiding places (integer) |
| Velocity shelter fraction | `FRACVSHL` | Fraction of cell with velocity shelter (0-1) |
| Spawnable fraction | `FRACSPWN` | Fraction of cell with spawning gravel (0-1) |

**Requirements:**
- Polygon geometry (not points or lines)
- Projected CRS with units in meters (e.g., UTM). This is required for correct distance calculations and KD-tree radius queries
- Field names are configurable via `spatial.gis_properties` in YAML

**Configuration mapping example:**

```yaml
spatial:
  gis_properties:
    cell_id: "ID_TEXT"
    reach_name: "REACH_NAME"
    area: "AREA"
    dist_escape: "M_TO_ESC"
    num_hiding_places: "NUM_HIDING"
    frac_vel_shelter: "FRACVSHL"
    frac_spawn: "FRACSPWN"
```

### Depth Table CSV

Hydraulic lookup table mapping discharge to water depth at each cell.

**Format:**

```
; Comment lines start with semicolon
26,Number of flows in table
,0.28,0.42,0.56,...,28.3
C1,0.12,0.18,0.22,...,1.45
C2,0.08,0.14,0.19,...,1.32
...
```

**Structure:**
- Lines starting with `;` or `"` are comments (skipped)
- First data line: number of flow breakpoints, followed by descriptive text
- Second data line: empty first column, then flow values (m^3/s) in ascending order
- Remaining lines: cell ID in first column, then depth values (in meters) at each flow breakpoint
- One row per cell, columns match flow breakpoints exactly

**Units:** Input in meters, converted to centimeters internally (multiplied by 100).

### Velocity Table CSV

Same format as the depth table, but values represent water velocity.

**Units:** Input in m/s, converted to cm/s internally (multiplied by 100).

### Time Series CSV

Daily environmental conditions for each reach.

**Format:**

```
; inSTREAM time-series input file
; Comment lines start with semicolon
Date,temperature,flow,turbidity
10/1/2010 12:00,12.5,2.83,3.0
10/2/2010 12:00,12.3,2.75,2.8
10/3/2010 12:00,11.8,3.01,4.2
...
```

**Structure:**
- Lines starting with `;` are comments (skipped)
- Header row: `Date,temperature,flow,turbidity`
- Date format: `M/d/YYYY HH:MM` (e.g., `10/1/2010 12:00`)
- Daily or sub-daily entries
- Must cover the entire simulation period (start_date through end_date)

**Column definitions:**

| Column | Unit | Description |
|--------|------|-------------|
| `Date` | datetime | Timestamp for this record |
| `temperature` | Celsius | Water temperature |
| `flow` | m^3/s | Discharge |
| `turbidity` | NTU | Turbidity |

**Notes:**
- The reader uses nearest-date matching (within 1.5 days), so exact midnight timestamps are not required
- Column names must match exactly (`temperature`, `flow`, `turbidity`)

### Initial Populations CSV

Defines the starting fish population.

**Format:**

```
; Initial population specification
; Species, Reach, Age, Number, Length min, Length mode, Length max
Chinook-Spring,ExampleA,0,300,4,6.1,7
Chinook-Spring,ExampleA,1,150,10,12.5,15
Chinook-Spring,ExampleA,2,50,18,22,26
```

**Structure:**
- Lines starting with `;` are comments (skipped)
- No header row (data only)
- Comma-separated: Species, Reach, Age, Number, Length min, Length mode, Length max

**Column definitions:**

| Column | Type | Description |
|--------|------|-------------|
| Species | string | Species name (must match a key in `species:` config) |
| Reach | string | Reach name (must match a key in `reaches:` config) |
| Age | integer | Age class in years |
| Number | integer | Number of individuals to create |
| Length min | float | Minimum fork length (cm) for triangular distribution |
| Length mode | float | Mode fork length (cm) |
| Length max | float | Maximum fork length (cm) |

Initial lengths are drawn from a triangular distribution defined by (min, mode, max). Weights are computed from the allometric relationship `W = weight_A * L^weight_B`.

---

## 3. Configuration (YAML)

The YAML configuration file controls all simulation parameters. Below is a fully annotated example based on Example A.

```yaml
# ============================================================
# Simulation timing and output
# ============================================================
simulation:
  start_date: "2011-04-01"       # ISO date: YYYY-MM-DD
  end_date: "2013-09-30"
  output_frequency: 1            # Write output every N steps
  output_units: "days"
  seed: 0                        # RNG seed (0 = default)
  census_days:                   # Snapshot dates as "MM-dd"
    - "06-15"
    - "09-30"
  census_years_to_skip: 0        # Suppress census for N years from start
  population_file: ""            # Path to population CSV (auto-detect if empty)

# ============================================================
# Performance tuning
# ============================================================
performance:
  backend: "numpy"               # "numpy", "numba", or "jax"
  device: "cpu"
  trout_capacity: 2000           # Max trout array slots
  redd_capacity: 500             # Max redd array slots
  jit_warmup: false              # Pre-compile JIT on init

# ============================================================
# Spatial mesh configuration
# ============================================================
spatial:
  backend: "shapefile"
  mesh_file: "Shapefile/ExampleA.shp"  # Relative to data_dir
  gis_properties:                # Map internal names -> shapefile columns
    cell_id: "ID_TEXT"
    reach_name: "REACH_NAME"
    area: "AREA"
    dist_escape: "M_TO_ESC"
    num_hiding_places: "NUM_HIDING"
    frac_vel_shelter: "FRACVSHL"
    frac_spawn: "FRACSPWN"

# ============================================================
# Light and photoperiod
# ============================================================
light:
  latitude: 41                   # Degrees north
  light_correction: 0.7          # Multiplier for ambient light
  light_at_night: 0.9            # Minimum light level at night
  twilight_angle: 6.0            # Solar angle for civil twilight

# ============================================================
# Species parameters
# ============================================================
species:
  Chinook-Spring:
    is_anadromous: true
    display_color: "brown"

    # --- Consumption ---
    cmax_A: 0.628                # CMax allometric coefficient
    cmax_B: 0.7                  # CMax allometric exponent
    cmax_temp_table:             # Temperature -> CMax multiplier
      0.0: 0.05
      2.0: 0.05
      10.0: 0.5
      22.0: 1.0
      23.0: 0.8
      25.0: 0.5
      30.0: 0.0

    # --- Weight ---
    weight_A: 0.0041             # W = A * L^B (g, cm)
    weight_B: 3.49

    # --- Reactive distance ---
    react_dist_A: 4.0            # Intercept (cm)
    react_dist_B: 2.0            # Slope per cm body length
    turbid_threshold: 5.0        # NTU below which no effect
    turbid_min: 0.1              # Minimum turbidity multiplier
    turbid_exp: -0.116           # Turbidity decay exponent
    light_threshold: 20.0        # Light level above which no effect
    light_min: 0.5               # Minimum light multiplier
    light_exp: -0.2              # Light decay exponent

    # --- Capture success ---
    capture_R1: 1.3              # Vel ratio at logistic = 0.1
    capture_R9: 0.4              # Vel ratio at logistic = 0.9

    # --- Swimming ---
    max_speed_A: 2.8             # Length coeff (cm/s per cm)
    max_speed_B: 21.0            # Length intercept (cm/s)
    max_speed_C: -0.0029         # Temp quadratic
    max_speed_D: 0.084           # Temp linear
    max_speed_E: 0.37            # Temp constant

    # --- Respiration ---
    resp_A: 36                   # Standard resp coefficient (J/d)
    resp_B: 0.783                # Weight exponent
    resp_C: 0.0020               # Temperature: exp(C * T^2)
    resp_D: 1.4                  # Activity: exp(D * (v/vmax)^2)

    # --- Energetics ---
    energy_density: 5900         # Fish energy density (J/g)

    # --- Movement ---
    move_radius_max: 20000       # Maximum radius (CRS units, e.g., cm)
    move_radius_L1: 7            # Length at logistic = 0.1 (cm)
    move_radius_L9: 20           # Length at logistic = 0.9 (cm)
    search_area: 20000           # Search feeding area (cm^2)

    # --- Spawning ---
    spawn_start_day: "09-01"
    spawn_end_day: "10-31"
    spawn_min_age: -9            # Negative = disabled
    spawn_min_length: -9
    spawn_min_cond: -9
    spawn_min_temp: 5            # Celsius
    spawn_max_temp: 14
    spawn_prob: 0.1              # Daily probability
    spawn_fecund_mult: 690
    spawn_fecund_exp: 0.552
    spawn_egg_viability: 0.8
    spawn_wt_loss_fraction: 0.4  # 40% weight loss
    spawn_depth_table:           # Depth suitability (cm -> 0-1)
      0: 0.0
      12: 0.0
      27: 0.95
      33.5: 1.0
      204: 0.0
    spawn_vel_table:             # Velocity suitability (cm/s -> 0-1)
      0: 0.0
      2.3: 0.0
      3: 0.06
      54: 1.0
      61: 1.0
      192: 0.0

    # --- Mortality ---
    mort_high_temp_T1: 28.0      # Logistic L1 (C)
    mort_high_temp_T9: 24.0      # Logistic L9 (C)
    mort_strand_survival_when_dry: 0.5
    mort_condition_S_at_K8: 0.992
    mort_condition_S_at_K5: 0.8
    mort_fish_pred_L1: 3.0
    mort_fish_pred_L9: 6.0
    mort_fish_pred_D1: 35
    mort_fish_pred_D9: 5
    mort_fish_pred_P1: 5.0e-06
    mort_fish_pred_P9: -5.0
    mort_fish_pred_I1: 50
    mort_fish_pred_I9: -50
    mort_fish_pred_T1: 6.0
    mort_fish_pred_T9: 2.0
    mort_fish_pred_hiding_factor: 0.5
    mort_terr_pred_L1: 6.0
    mort_terr_pred_L9: 3.0
    mort_terr_pred_D1: 0.0
    mort_terr_pred_D9: 200
    mort_terr_pred_V1: 20
    mort_terr_pred_V9: 300
    mort_terr_pred_I1: 50
    mort_terr_pred_I9: -10
    mort_terr_pred_H1: 200
    mort_terr_pred_H9: -50
    mort_terr_pred_hiding_factor: 0.8
    mort_redd_lo_temp_T1: 1.7
    mort_redd_lo_temp_T9: 4.0
    mort_redd_hi_temp_T1: 23
    mort_redd_hi_temp_T9: 17.5
    mort_redd_dewater_surv: 0.9
    mort_redd_scour_depth: 20

    # --- Redd development ---
    redd_devel_A: 0.00190        # Constant
    redd_devel_B: 0.000500       # Linear temp coeff
    redd_devel_C: 0.0000360      # Quadratic temp coeff

    # --- Emergence ---
    emerge_length_min: 3.5       # cm
    emerge_length_mode: 3.8
    emerge_length_max: 4.1

    # --- Superindividuals ---
    superind_max_rep: 10
    superind_max_length: 5       # Split above this length (cm)

# ============================================================
# Reach parameters
# ============================================================
reaches:
  ExampleA:
    drift_conc: 3.2e-10          # g/cm^3
    search_prod: 8.00e-07        # g/cm^2/d
    shelter_speed_frac: 0.3      # Velocity reduction in shelter
    prey_energy_density: 2500    # J/g
    drift_regen_distance: 1000   # cm
    shading: 0.9                 # Fraction of light reaching water
    fish_pred_min: 0.97          # Min daily survival from fish pred
    terr_pred_min: 0.94          # Min daily survival from terr pred
    light_turbid_coef: 0.0017
    light_turbid_const: 0.0
    max_spawn_flow: 10           # m^3/s
    shear_A: 0.013               # Shear stress = A * flow^B
    shear_B: 0.40
    upstream_junction: 1
    downstream_junction: 2
    time_series_input_file: "ExampleA-TimeSeriesInputs.csv"
    depth_file: "ExampleA-Depths.csv"
    velocity_file: "ExampleA-Vels.csv"
```

### Converting from NetLogo NLS Format

If you have an existing inSTREAM 7 parameter file (`.nls`), use the built-in converter:

```python
from instream.io.config import nls_to_yaml

yaml_str = nls_to_yaml("path/to/parameters.nls")
with open("config.yaml", "w") as f:
    f.write(yaml_str)
```

This parses `set` assignments, `(list ...)` constructs, and `table:put` interpolation tables from the NetLogo format.

---

## 4. Running Simulations

### Single Run

```python
from instream.model import InSTREAMModel

model = InSTREAMModel("configs/example_a.yaml", data_dir="data/")
model.run()
```

### Step-by-Step Execution

```python
model = InSTREAMModel("configs/example_a.yaml", data_dir="data/")

while not model.time_manager.is_done():
    model.step()
    # Inspect state between steps
    print(f"{model.time_manager.formatted_time()}: "
          f"{model.trout_state.num_alive()} fish alive")
```

### Changing Backends

Set the backend in the YAML configuration:

```yaml
performance:
  backend: "numba"    # or "numpy" (default)
```

The Numba backend JIT-compiles the inner fitness evaluation loop, providing significant speedup (typically 3-10x) for the habitat selection phase. Requires `pip install instream[numba]`.

### Seed for Reproducibility

```yaml
simulation:
  seed: 42
```

Setting a non-zero seed ensures identical results across runs. With `seed: 0`, the default numpy RNG seed is used (effectively random).

---

## 5. Units Convention

All internal computations use CGS-like units. Input files use SI where noted, and conversions happen automatically during loading.

| Quantity | Internal Unit | Input Unit | Conversion |
|----------|--------------|------------|------------|
| Fish length | cm | cm | none |
| Fish weight | g | g | none |
| Cell area | cm^2 | m^2 (shapefile) | x 10,000 |
| Water depth | cm | m (CSV) | x 100 |
| Water velocity | cm/s | m/s (CSV) | x 100 |
| Temperature | C | C | none |
| Flow (discharge) | m^3/s | m^3/s | none |
| Turbidity | NTU | NTU | none |
| Distance to escape | cm | cm (shapefile) | none |
| Search area | cm^2 | cm^2 (config) | none |
| Drift concentration | g/cm^3 | g/cm^3 (config) | none |
| Energy density | J/g | J/g (config) | none |
| Respiration | J/d | - | computed |
| Growth rate | g/d | - | computed |
| Time step | days (fraction) | - | from TimeManager |
| Movement radius | CRS units | CRS units (config) | none |
| Centroid coordinates | CRS units | CRS units (shapefile) | none |

**Note on CRS units:** Movement radius and centroid coordinates are in whatever units the shapefile CRS uses. For projected coordinate systems (e.g., UTM), this is meters. The KD-tree spatial queries use the same units, so `move_radius_max: 20000` means 20,000 CRS units (20 km in UTM).

---

## 6. Output and Analysis

### Accessing TroutState Arrays

All state is accessible as numpy arrays through the model object:

```python
ts = model.trout_state
alive = ts.alive_indices()

# Basic population stats
print(f"Total alive: {ts.num_alive()}")
print(f"Mean length: {ts.length[alive].mean():.2f} cm")
print(f"Mean weight: {ts.weight[alive].mean():.2f} g")
print(f"Mean condition: {ts.condition[alive].mean():.3f}")
```

### Population Counts Over Time

```python
import numpy as np

model = InSTREAMModel("configs/example_a.yaml", data_dir="data/")
dates = []
counts = []

while not model.time_manager.is_done():
    model.step()
    dates.append(model.time_manager.current_date)
    counts.append(model.trout_state.num_alive())

# Plot or analyze
import matplotlib.pyplot as plt
plt.plot(dates, counts)
plt.xlabel("Date")
plt.ylabel("Population")
plt.title("Trout Population Over Time")
plt.show()
```

### Spatial Distribution

```python
alive = model.trout_state.alive_indices()
cell_indices = model.trout_state.cell_idx[alive]
cs = model.fem_space.cell_state

# Fish positions (centroid of their cell)
x = cs.centroid_x[cell_indices]
y = cs.centroid_y[cell_indices]

# Fish per cell
unique_cells, fish_per_cell = np.unique(cell_indices, return_counts=True)
```

### Growth and Survival Tracking

```python
alive = model.trout_state.alive_indices()

# Growth rates from most recent step
growth_rates = model.trout_state.last_growth_rate[alive]

# Activity distribution
activities = model.trout_state.activity[alive]
n_drift = np.sum(activities == 0)
n_search = np.sum(activities == 1)
n_hide = np.sum(activities == 2)
print(f"Drift: {n_drift}, Search: {n_search}, Hide: {n_hide}")

# Age structure
ages = model.trout_state.age[alive]
for age in sorted(np.unique(ages)):
    n = np.sum(ages == age)
    print(f"Age {age}: {n} fish")
```

### Redd Tracking

```python
rs = model.redd_state
alive_redds = np.where(rs.alive)[0]

for i in alive_redds:
    print(f"Redd {i}: {rs.num_eggs[i]} eggs, "
          f"{rs.frac_developed[i]:.2%} developed, "
          f"cell {rs.cell_idx[i]}")

# Egg mortality breakdown
total_initial = rs.eggs_initial[alive_redds].sum()
lost_lo = rs.eggs_lo_temp[alive_redds].sum()
lost_hi = rs.eggs_hi_temp[alive_redds].sum()
lost_dw = rs.eggs_dewatering[alive_redds].sum()
lost_sc = rs.eggs_scour[alive_redds].sum()
print(f"Initial: {total_initial}, Lost to: lo_temp={lost_lo}, "
      f"hi_temp={lost_hi}, dewater={lost_dw}, scour={lost_sc}")
```

### Environmental Conditions

```python
# Current reach conditions
print(f"Flow: {model.reach_state.flow[0]:.2f} m^3/s")
print(f"Temp: {model.reach_state.temperature[0]:.1f} C")
print(f"Turbidity: {model.reach_state.turbidity[0]:.1f} NTU")

# Cell hydraulics
cs = model.fem_space.cell_state
print(f"Depth range: {cs.depth.min():.1f} - {cs.depth.max():.1f} cm")
print(f"Velocity range: {cs.velocity.min():.1f} - {cs.velocity.max():.1f} cm/s")
```
