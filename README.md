# PySALMO

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-green)
![Status: In Development](https://img.shields.io/badge/status-in%20development-orange)

## Overview

**PySALMO** is a full-lifecycle individual-based model for Baltic Atlantic
salmon (*Salmo salar*), extending the
[inSTREAM/inSALMO 7.4](https://www.fs.usda.gov/research/treesearch/56100)
freshwater framework with novel marine phases. Built in Python using:

- **Mesa 3.x** for agent-based model orchestration
- **NumPy structured-of-arrays (SoA)** state containers for cache-friendly
  batch operations
- **Numba JIT** compilation for compute-intensive kernels
- An optional **JAX** backend for GPU-accelerated vectorized kernels
- **Domain-dispatched architecture** — freshwater and marine domains share
  state, coupled to EMODnet/HELCOM oceanographic data

The model simulates the complete anadromous salmon lifecycle: freshwater
growth, survival, habitat selection, smoltification, ocean migration,
marine growth and mortality (including gear-specific fishing), maturation,
adult return, spawning, and post-spawn death — all within spatially explicit
stream reaches and configurable marine zones.

For background on the inSTREAM modelling framework, see:

- Railsback, S.F., Harvey, B.C., et al. (2009). *inSTREAM: the individual-based
  stream trout research and environmental assessment model.* Gen. Tech. Rep.
  PSW-GTR-218.
- Railsback, S.F. & Harvey, B.C. (2020). *Modeling populations of adaptive
  individuals.* Princeton University Press.

## Features

### Freshwater (inSTREAM/inSALMO parity)

- **Wisconsin bioenergetics** -- temperature-dependent consumption, respiration,
  and growth
- **Five survival sources** -- high temperature, stranding, poor condition, fish
  predation, and terrestrial predation
- **Fitness-based habitat selection** -- expected maturity via survival-integrated
  fitness function
- **Spawning and redd lifecycle** -- redd creation, egg development,
  fry emergence with density-dependent capacity
- **Multi-species, multi-reach architecture** -- arbitrary number of species and
  stream reaches connected by a junction network
- **inSALMO features** -- adult holding (zero food intake), two-piece
  condition-survival, stochastic outmigration, spawn-cell perturbation,
  modified growth fitness
- **Angler harvest** -- size-selective fishing mortality with bag limits

### Marine (novel PySALMO extension)

- **7 life stages** -- fry, parr, spawner, smolt, ocean juvenile, ocean adult,
  returning adult (LifeStage IntEnum)
- **Domain-dispatched step** -- FreshwaterDomain and MarineDomain share state,
  fish transition by changing life_history
- **Marine growth** -- O'Neill (1986) temperature function, Hanson et al.
  bioenergetics (CMax A=0.303, B=-0.275)
- **7 marine mortality sources** -- seal predation, cormorant predation,
  background, temperature stress, M74 syndrome, fishing harvest, bycatch
- **Gear-specific fishing** -- logistic/normal selectivity curves, 4 gear types
  (trap net, drift net, longline, trolling), seasonal/zone closures, bycatch
- **Smoltification** -- photoperiod + temperature triggered, seasonal window
- **Environmental coupling** -- StaticDriver (YAML), planned NetCDF/WMS drivers
  for EMODnet/HELCOM data

### Performance

- **Numba JIT backend** -- critical inner loops compiled to machine code
- **Pluggable compute backends** -- NumPy (default), Numba, and JAX
- **Sensitivity analysis** -- Morris one-at-a-time parameter screening
- **Habitat restoration** -- config-driven cell property changes at scheduled dates

## Quick Start

```bash
# Clone the repository
git clone https://github.com/razinkele/pysalmo.git
cd pysalmo

# Install in development mode
pip install -e ".[dev]"

# Run Example A simulation
pysalmo configs/example_a.yaml --output-dir results/ --end-date 2012-01-01

# Run Example B (3 reaches x 3 species)
pysalmo configs/example_b.yaml --data-dir tests/fixtures/example_b/ -o results_b/

# Run with marine domain enabled (add marine: section to YAML)
pysalmo configs/baltic_salmon.yaml --output-dir results/
```

## Installation

Requires **Python 3.11** or later.

```bash
# Core install (NumPy backend only)
pip install -e .

# With Numba JIT acceleration
pip install -e ".[numba]"

# With JAX GPU backend (experimental)
pip install -e ".[jax]"

# Full development environment (tests, Numba, Hypothesis)
pip install -e ".[dev]"
```

### Dependencies

| Package    | Version  | Purpose                        |
|------------|----------|--------------------------------|
| mesa       | >= 3.1   | Agent-based model framework    |
| numpy      | >= 1.24  | Array computation              |
| scipy      | >= 1.11  | Spatial queries (KD-tree)      |
| pandas     | >= 2.0   | Time series and data I/O       |
| geopandas  | >= 0.14  | Shapefile reading              |
| shapely    | >= 2.0   | Polygon geometry               |
| pydantic   | >= 2.0   | Configuration validation       |
| pyyaml     | >= 6.0   | YAML parsing                   |

## Usage

```python
from instream.model import InSTREAMModel

# Create and run a simulation
model = InSTREAMModel("configs/example_a.yaml")

# Step through time
for _ in range(365):
    model.step()

# Access state arrays
trout = model.trout_state
print(f"Live fish: {trout.alive.sum()}")
print(f"Mean length: {trout.length[trout.alive].mean():.1f} cm")
print(f"Mean weight: {trout.weight[trout.alive].mean():.2f} g")

# Access redd state
redds = model.redd_state
print(f"Active redds: {redds.alive.sum()}")
```

## Configuration

Simulations are configured through a single YAML file. See
[`configs/example_a.yaml`](configs/example_a.yaml) for a complete example.

Top-level sections:

```yaml
simulation:      # start/end dates, output frequency, random seed
performance:     # backend choice (numpy/numba/jax), capacity limits
spatial:         # shapefile path, GIS column mappings
light:           # latitude, light correction factors
species:         # per-species biological parameters (bioenergetics,
                 # survival, spawning, movement)
reaches:         # per-reach environmental parameters, file paths
```

Species parameters include Wisconsin bioenergetics coefficients, survival
logistic parameters, spawning schedules, and movement rules. Reach parameters
specify drift food concentration, predation minimums, and paths to hydraulic
input files.

## Data Requirements

Each reach requires the following input files:

| File                   | Format    | Description                                                    |
|------------------------|-----------|----------------------------------------------------------------|
| Shapefile (`.shp`)     | ESRI shp  | Polygon mesh defining cells with attributes: cell ID, reach name, area, distance to escape cover, hiding places, velocity shelter fraction, spawning fraction |
| Depths CSV             | CSV       | Columns: `flow` + one column per cell ID. Depth (cm) at each flow level |
| Velocities CSV         | CSV       | Columns: `flow` + one column per cell ID. Velocity (cm/s) at each flow level |
| Time series CSV        | CSV       | Daily records: date, flow (m^3/s), temperature (C), turbidity (NTU), daylight hours |
| Population file        | CSV       | Optional. Initial population: species, age, length per individual |

All file paths in the YAML configuration are relative to the config file's
parent directory.

## Performance

Benchmark results (912-day simulation, Intel i7-11800H, 64 GB RAM):

| Example | Fish | Cells | Step Time | Full Run | vs NetLogo |
|---------|------|-------|-----------|----------|------------|
| A (1 reach, 1 species) | 360 | 1,373 | 48 ms | 44 sec | AT PARITY |
| B (3 reaches, 3 species) | 63 | 5,631 | 22 ms | 24 sec | 5-9x FASTER |

| Backend          | Full step | 912-day run | vs Pure Python |
|------------------|-----------|-------------|----------------|
| Python (pure)    | 62 s      | ~129 min    | 1x             |
| NumPy vectorized | 179 ms    | ~2.1 min    | ~346x          |
| Numba JIT        | 48 ms     | 44 sec      | ~1292x         |
| NetLogo 7.4      | ~5 s      | ~76 min     | ~12x           |

*Measured on Intel i7-11800H, 64 GB RAM. Numba times exclude JIT warmup.*

## Architecture

```
InSTREAMModel (Mesa Model)
  |
  +-- TimeManager              # date progression, season tracking
  +-- FreshwaterDomain
  |    +-- FEMSpace            # polygon mesh, KD-tree spatial queries
  |    +-- ReachState          # per-reach hydraulics, daily conditions
  |    +-- CellState           # per-cell depth, velocity, food, shelter
  |    +-- Modules: reach, growth, survival, behavior, spawning,
  |                 migration, harvest, smoltification
  |
  +-- MarineDomain (optional)
  |    +-- MarineSpace         # zone graph, connectivity
  |    +-- ZoneState           # per-zone temperature, prey, predation
  |    +-- StaticDriver        # environmental data from YAML
  |    +-- Modules: marine_growth, marine_survival, marine_fishing,
  |                 marine_migration
  |
  +-- TroutState (SoA)        # shared: length, weight, life_history,
  |                            #   zone_idx, sea_winters, natal_reach, ...
  +-- ReddState (SoA)         # eggs, development, emergence
  +-- LifeStage IntEnum       # FRY=0 .. RETURNING_ADULT=6
```

**Key design decisions:**

- **SoA state containers** store all individuals of a type in contiguous NumPy
  arrays, enabling vectorized operations and good cache locality.
- **FEMSpace** wraps a polygon mesh with a KD-tree for fast nearest-cell
  lookups and neighbor queries.
- **Pluggable backends** allow swapping NumPy for Numba or JAX without changing
  model logic. Backend selection is controlled via the `performance.backend`
  config key.

## Testing

```bash
# Run the full test suite
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=instream --cov-report=term-missing

# Skip slow tests
pytest tests/ -v -m "not slow"

# Run only property-based tests
pytest tests/test_properties.py -v
```

The test suite includes unit tests, integration tests, Hypothesis
property-based tests, and performance regression tests.

## Project Status

**v1.0.0** -- PySALMO: Full anadromous lifecycle with marine domain (April 2026).

### Current Metrics

| Metric          | Value                          |
|-----------------|--------------------------------|
| Tests           | 694                            |
| Validation      | 11/11 NetLogo reference tests  |
| Step time       | 48 ms (Example A, Numba JIT)   |
| Species         | Multi-species support          |
| Reaches         | Multi-reach support            |
| Sub-daily       | InSTREAM-SD hourly + peaking   |
| Output          | 7 file types + CLI             |
| Example B       | 3 reaches x 3 species working  |

### Completed

- Core model infrastructure (Mesa orchestration, SoA state, FEMSpace)
- YAML configuration with NLS parameter conversion
- Wisconsin bioenergetics (growth, consumption, respiration)
- Five survival sources with logistic functions
- Fitness-based habitat selection with survival integration
- Spawning, egg development, and redd emergence
- Multi-reach migration with junction network routing
- Multi-species support (Example B: 3 reaches x 3 species)
- Output system (7 file types: population, habitat, individual, redd, mortality, spatial, growth report)
- CLI interface (`instream` command)
- NumPy, Numba, and JAX compute backends (survival vectorized across all 3)
- InSTREAM-SD sub-daily scheduling (hourly + peaking flow)
- Growth accumulation with day-boundary application
- 11/11 NetLogo validation tests passing
- 674 unit, integration, property-based, and validation tests
- JAX GPU backend with vectorized growth/survival kernels
- FEM mesh reader (River2D/GMSH via meshio)
- Shiny for Python frontend (configure, run, explore simulations)
- Deploy skill for laguna.ku.lt Shiny Server
- Angler harvest module with size-selective mortality and bag limits
- Morris sensitivity analysis (one-at-a-time parameter screening)
- Config-driven habitat restoration scenarios
- Fitness memory (EMA), drift regen distance, spawn defense area
- Per-species migration params, superindividual split thresholds
- Anadromous adult life history with post-spawn mortality
- Daily-integral solar irradiance (replaces noon-elevation approximation)
- YearShuffler for stochastic multi-year input remapping

### Planned

- Scenario comparison (side-by-side simulation runs)
- Full Numba JIT compilation of fitness_all inner loop
- Sphinx documentation build

## License

This project is licensed under the **GNU General Public License v3.0 or later**
(GPL-3.0-or-later). See [LICENSE](LICENSE) for the full text.

## Citation

If you use PySALMO in your research, please cite:

> Railsback, S.F., Harvey, B.C., Hayse, J.W., & LaGory, K.E. (2005).
> Tests of theory for diel variation in salmonid feeding activity and habitat
> use. *Ecology*, 86(4), 947-959.

> Railsback, S.F., Harvey, B.C., Jackson, S.K., & Lamberson, R.H. (2009).
> InSTREAM: the individual-based stream trout research and environmental
> assessment model. Gen. Tech. Rep. PSW-GTR-218. Albany, CA: USDA Forest
> Service, Pacific Southwest Research Station.

> Railsback, S.F. & Harvey, B.C. (2020). *Modeling populations of adaptive
> individuals.* Monographs in Population Biology 63. Princeton University Press.
