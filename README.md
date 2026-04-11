# inSTREAM-py

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-green)](LICENSE)
[![CI](https://github.com/razinkele/instream-py/actions/workflows/ci.yml/badge.svg)](https://github.com/razinkele/instream-py/actions/workflows/ci.yml)
[![docs](https://github.com/razinkele/instream-py/actions/workflows/docs.yml/badge.svg)](https://github.com/razinkele/instream-py/actions/workflows/docs.yml)
[![PyPI](https://img.shields.io/pypi/v/instream)](https://pypi.org/project/instream/)

**Python conversion of the inSTREAM/inSALMO 7.4 individual-based salmonid model.**

## Quick Start

```bash
pip install -e ".[dev]"

# Run Example A simulation
instream configs/example_a.yaml --output-dir results/ --end-date 2012-01-01

# Run Example B (3 reaches x 3 species)
instream configs/example_b.yaml --data-dir tests/fixtures/example_b/ -o results_b/
```

```python
from instream.model import InSTREAMModel

model = InSTREAMModel("configs/example_a.yaml")
for _ in range(365):
    model.step()

trout = model.trout_state
print(f"Live fish: {trout.alive.sum()}, Mean length: {trout.length[trout.alive].mean():.1f} cm")
```

## Features

- **Wisconsin bioenergetics** -- temperature-dependent consumption, respiration, and growth
- **Five survival sources** -- high temperature, stranding, poor condition, fish predation, terrestrial predation
- **Fitness-based habitat selection** -- expected maturity via survival-integrated fitness function
- **Spawning and redd lifecycle** -- redd creation, egg development, fry emergence
- **Multi-species, multi-reach architecture** -- arbitrary species/reaches connected by junction network
- **Pluggable compute backends** -- NumPy (default), Numba JIT (60x+), JAX GPU
- **Marine domain** -- Baltic Sea zone transitions, smolt exit, adult return
- **Angler harvest** -- size-selective fishing mortality with bag limits
- **Morris sensitivity analysis** -- one-at-a-time parameter screening
- **Sub-daily scheduling** -- hourly + peaking flow (InSTREAM-SD)

## Architecture

```
InSTREAMModel (Mesa Model) -- 108 lines, decomposed into 3 mixin classes
  |
  +-- TimeManager          # date progression, season tracking
  +-- FEMSpace             # polygon mesh, KD-tree spatial queries
  +-- ReachState           # per-reach hydraulics, daily conditions
  +-- CellState            # per-cell depth, velocity, food, shelter
  +-- TroutState (SoA)     # arrays: x, y, length, weight, alive, ...
  +-- ReddState (SoA)      # arrays: x, y, eggs, development, ...
  +-- MarineDomain         # Baltic Sea zones, smolt/adult transitions
  |
  +-- Modules:
       +-- growth          # Wisconsin bioenergetics
       +-- survival        # 5 mortality sources + redd survival
       +-- behavior        # fitness-based habitat selection
       +-- spawning        # redd creation, egg development, emergence
       +-- migration       # inter-reach movement
       +-- harvest         # angler fishing mortality
```

Key design decisions:

- **SoA state containers** store all individuals in contiguous NumPy arrays for vectorized operations and cache locality.
- **FEMSpace** wraps a polygon mesh with a KD-tree for fast nearest-cell lookups.
- **Pluggable backends** allow swapping NumPy for Numba or JAX without changing model logic.

## Current Metrics

| Metric          | Value                                          |
|-----------------|------------------------------------------------|
| Version         | **v0.18.0**                                    |
| Tests           | 876+                                           |
| Validation      | 17/17 (11 original + 6 NetLogo cross-val)      |
| Marine ecology  | Hanson bioenergetics, 5-source survival, fishing |
| Marine domain   | Baltic Sea zones, smolt exit, adult return     |
| model.py        | 108 lines (decomposed into 3 mixin classes)    |
| Step time       | 48 ms (Example A, Numba JIT)                   |

## Performance

| Backend          | Full step | 912-day run | vs Pure Python |
|------------------|-----------|-------------|----------------|
| Python (pure)    | 62 s      | ~129 min    | 1x             |
| NumPy vectorized | 179 ms    | ~2.1 min    | ~346x          |
| Numba JIT        | 48 ms     | 44 sec      | ~1292x         |
| NetLogo 7.4      | ~5 s      | ~76 min     | ~12x           |

## Installation

Requires **Python 3.11** or later.

```bash
# Core install (NumPy backend only)
pip install -e .

# With Numba JIT acceleration
pip install -e ".[numba]"

# With JAX GPU backend (experimental)
pip install -e ".[jax]"

# Full development environment
pip install -e ".[dev]"
```

## Configuration

Simulations are configured through a single YAML file. See
[`configs/example_a.yaml`](configs/example_a.yaml) for a complete example.

```yaml
simulation:      # start/end dates, output frequency, random seed
performance:     # backend choice (numpy/numba/jax), capacity limits
spatial:         # shapefile path, GIS column mappings
light:           # latitude, light correction factors
species:         # per-species biological parameters
reaches:         # per-reach environmental parameters, file paths
```

## Documentation

API documentation is built with Sphinx and deployed to GitHub Pages:
https://razinkele.github.io/instream-py/

To build locally:

```bash
pip install -e ".[docs]"
sphinx-build -b html docs/source docs/_build/html
```

## Testing

```bash
pytest tests/ -v                         # full suite
pytest tests/ -v -m "not slow"           # skip slow tests
pytest tests/ -v --cov=instream          # with coverage
```

## Citation

If you use inSTREAM-py in your research, please cite:

```bibtex
@techreport{railsback2009instream,
  title     = {InSTREAM: the individual-based stream trout research and
               environmental assessment model},
  author    = {Railsback, Steven F and Harvey, Bret C and Jackson, Stephen K
               and Lamberson, Roland H},
  year      = {2009},
  institution = {USDA Forest Service, Pacific Southwest Research Station},
  number    = {PSW-GTR-218},
  type      = {General Technical Report}
}

@book{railsback2020modeling,
  title     = {Modeling populations of adaptive individuals},
  author    = {Railsback, Steven F and Harvey, Bret C},
  year      = {2020},
  publisher = {Princeton University Press},
  series    = {Monographs in Population Biology},
  number    = {63}
}
```

## License

This project is licensed under the **GNU General Public License v3.0 or later**
(GPL-3.0-or-later). See [LICENSE](LICENSE) for the full text.
