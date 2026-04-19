# inSTREAM-py

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-green)](LICENSE)
[![CI](https://github.com/razinkele/instream-py/actions/workflows/ci.yml/badge.svg)](https://github.com/razinkele/instream-py/actions/workflows/ci.yml)
[![docs](https://github.com/razinkele/instream-py/actions/workflows/docs.yml/badge.svg)](https://github.com/razinkele/instream-py/actions/workflows/docs.yml)
[![PyPI](https://img.shields.io/pypi/v/instream)](https://pypi.org/project/instream/)
[![Tests](https://img.shields.io/badge/tests-920%2B-brightgreen)](https://github.com/razinkele/instream-py/actions/workflows/ci.yml)
[![Release](https://img.shields.io/badge/release-v0.30.2-blue)](https://github.com/razinkele/instream-py/releases)

A high-performance Python conversion of the **inSTREAM/inSALMO 7.4**
individual-based salmonid model — with 350-1290× the throughput of the
original Java implementation, a Mesa-based architecture, real-world case
studies (Baltic salmon in the Nemunas/Curonian Lagoon system), and an
interactive Shiny web app for exploration.

---

## Contents

- [What it does](#what-it-does)
- [Quick Start](#quick-start)
- [Case Studies](#case-studies)
- [Features](#features)
- [Architecture](#architecture)
- [Performance](#performance)
- [Installation](#installation)
- [Configuration](#configuration)
- [Testing](#testing)
- [Interactive Shiny App](#interactive-shiny-app)
- [Documentation](#documentation)
- [Citation](#citation)
- [License](#license)

---

## What it does

Individual-based simulation of salmonid populations across a hydrodynamic
landscape. Each fish has its own state (position, length, weight, condition,
life stage) and makes daily decisions about habitat, feeding, movement, and
reproduction. The model is designed for:

- **Management & conservation**: test how flow regimes, temperature shifts,
  or predator pressure propagate to population outcomes
- **Climate scenarios**: decadal projections under alternative hydrology or
  thermal forcing
- **Anadromous lifecycle**: full egg → fry → parr → smolt → ocean → return →
  spawn cycle with iteroparous kelt survival
- **Cross-boundary systems**: rivers that drain into lagoons, estuaries, and
  coastal seas — see the [Baltic case study](docs/case-studies/baltic-workflow.md)
- **Calibration**: automated sensitivity analysis (Morris) and parameter
  fitting against ICES Smolt-to-Adult-Return bands

Translation fidelity is validated against **NetLogo 7.4** reference runs
(17/17 cross-validation tests pass).

---

## Quick Start

```bash
# Install (NumPy backend, 350× speedup over pure Python)
pip install -e ".[dev]"

# Run Example A (single reach, Chinook salmon)
instream configs/example_a.yaml --output-dir results/ --end-date 2012-01-01

# Run the Baltic case study (9 reaches incl. Atmata, real coastline-clipped marine domain)
instream configs/example_baltic.yaml -o results_baltic/ --end-date 2013-04-01
```

```python
from instream.model import InSTREAMModel

model = InSTREAMModel("configs/example_baltic.yaml")
for _ in range(365):
    model.step()

ts = model.trout_state
alive = ts.alive_indices()
print(f"Day {model.time_manager.day_of_simulation}: "
      f"{len(alive)} live fish, mean length {ts.length[alive].mean():.1f} cm")
```

---

## Case Studies

Three configured and tested simulation scenarios ship with the repository:

### `example_a` — Chinook salmon, single California stream

The canonical inSTREAM 7.4 reference case: one reach, one species, ~300 cells.
Used for regression testing against NetLogo reference runs.

- Config: [`configs/example_a.yaml`](configs/example_a.yaml)
- Fixtures: `tests/fixtures/example_a/`
- Runtime: ~44 s for 912 days (Numba JIT)

### `example_b` — Multi-reach, multi-species system

3 reaches × 3 species (Chinook, Steelhead, Rainbow), ~1,000 cells. Exercises
the junction network and inter-species interactions.

- Config: [`configs/example_b.yaml`](configs/example_b.yaml)
- Fixtures: `tests/fixtures/example_b/`

### `example_baltic` — Nemunas / Curonian Lagoon / Baltic coast

The **real-data case study**: 9 reaches modeled on actual OSM geometry for
the Nemunas basin, delta branches across the Lithuania–Kaliningrad border,
the real Curonian Lagoon polygon, and a coastline-clipped Baltic nearshore
reach opening at the Klaipėda strait. Marine reaches sample real bathymetry
from **EMODnet** (1/16 arc-minute DTM).

- Config: [`configs/example_baltic.yaml`](configs/example_baltic.yaml)
- Full workflow reference: [`docs/case-studies/baltic-workflow.md`](docs/case-studies/baltic-workflow.md)
- Regeneration script: [`scripts/generate_baltic_example.py`](scripts/generate_baltic_example.py)
- Reaches: `Nemunas`, `Atmata` (main N distributary, primary salmon route),
  `Minija`, `Sysa` (Šyša), `Skirvyte` (Skirvytė), `Leite` (Leitė),
  `Gilija` (Матросовка from the Kaliningrad PBF), `CuronianLagoon`,
  `BalticCoast` — 1,591 cells total
- Marine domain: Estuary → Coastal → Baltic Proper zones with smolt exit
  and adult return transitions

Use the Baltic case study as a template when building a similar simulation
for a new salmon-bearing system (Daugava, Vistula, Scottish coast, Norwegian
fjord, etc.) — see the workflow doc's "Adapting to a different salmon
system" section.

---

## Features

| Category | Capability |
|---|---|
| **Bioenergetics** | Wisconsin model — temperature-dependent consumption, respiration, growth |
| **Survival** | 5 mortality sources (high temp, stranding, condition, fish predation, terrestrial predation) + redd survival |
| **Behavior** | Fitness-based habitat selection via expected-maturity / survival-integrated fitness |
| **Reproduction** | Redd creation, egg development, fry emergence, iteroparous kelt survival |
| **Multi-species** | Arbitrary species/reach combinations via YAML config |
| **Compute backends** | NumPy (default), Numba JIT (60×+ speedup), JAX (GPU-ready) |
| **Marine domain** | Baltic Sea zone transitions, smolt exit, adult return with SAR calibration |
| **Fishing** | Angler harvest with size selectivity, bag limits, catch-and-release |
| **Sensitivity analysis** | Morris method for one-at-a-time parameter screening |
| **Sub-daily scheduling** | Hourly + peaking flow via the inSTREAM-SD integration |
| **Real geography** | OSM PBF fetcher for rivers (any Geofabrik region), EMODnet bathymetry for marine cells, Marine Regions WFS for named water bodies |
| **Interactive exploration** | Shiny web app with deck.gl maps, live population + spatial views, Create Model panel |

---

## Architecture

```
InSTREAMModel (Mesa Model) — 108 lines, 3 mixin classes
  │
  ├── TimeManager        # date progression, season tracking
  ├── FEMSpace           # polygon mesh + KD-tree spatial queries
  ├── ReachState         # per-reach hydraulics, daily conditions
  ├── CellState          # per-cell depth, velocity, food, shelter
  ├── TroutState (SoA)   # contiguous arrays: x, y, length, weight, alive, …
  ├── ReddState (SoA)    # contiguous arrays: x, y, eggs, development, …
  ├── MarineDomain       # Baltic zones, smolt/adult transitions
  │
  └── Modules:
      ├── growth         # Wisconsin bioenergetics
      ├── survival       # 5 mortality sources + redd survival
      ├── behavior       # fitness-based habitat selection
      ├── spawning       # redd creation, egg development, emergence
      ├── migration      # inter-reach movement
      └── harvest        # angler fishing mortality
```

**Key design decisions**:

- **Structure-of-Arrays (SoA)** — all individuals stored in contiguous NumPy
  arrays for vectorized operations and cache locality. Enables 60–1000×
  speedups vs object-based models.
- **Pluggable backends** — NumPy (readable, correct), Numba (JIT-compiled
  hot path, ~48 ms/step), JAX (experimental, GPU-ready). Swapping backends
  requires no changes to model logic.
- **Mesa + FEMSpace** — polygon-mesh spatial structure wrapping a KD-tree.
  O(log n) nearest-cell lookups.
- **Config-driven** — one YAML file fully specifies a simulation; the
  model does not compile environment-specific code.

---

## Performance

Benchmarked on a reference 912-day run of `example_a` (single reach, Chinook):

| Backend          | Per step | 912-day run | Speedup vs Pure Python |
|------------------|---------:|------------:|-----------------------:|
| Python (pure)    | 62 s     | ~129 min    | 1×                     |
| NumPy vectorized | 179 ms   | ~2.1 min    | ~346×                  |
| Numba JIT        | 48 ms    | 44 s        | ~1,292×                |
| NetLogo 7.4      | ~5 s     | ~76 min     | ~12×                   |

For the Baltic case study (9 reaches, 1,591 cells, ~5,000 initial fish),
a 2-week window completes in **~90 s** under Numba — a useful fast-feedback
loop for calibration work.

---

## Installation

Requires **Python 3.11+**. Tested on Linux, macOS, and Windows.

```bash
# Core install (NumPy backend only)
pip install -e .

# With Numba JIT acceleration (recommended for real runs)
pip install -e ".[numba]"

# With JAX GPU backend (experimental)
pip install -e ".[jax]"

# Full development environment (tests, docs, all backends)
pip install -e ".[dev]"
```

The Baltic case study also requires the following system tools (installed
via conda-forge):

```bash
conda install -c conda-forge osmium-tool rasterio
```

- `osmium-tool` — CLI for clipping OSM PBFs to a bbox
- `rasterio` — reads EMODnet GeoTIFFs for per-cell depth sampling

---

## Configuration

Simulations are driven by a single YAML file. See the Baltic example's
[annotated config](configs/example_baltic.yaml) for a reference layout:

```yaml
simulation:      # start/end dates, output frequency, random seed
performance:     # backend choice (numpy/numba/jax), capacity limits
spatial:         # shapefile path, GIS column mappings
light:           # latitude, light correction factors
species:         # per-species biological parameters (bioenergetics, spawning)
reaches:         # per-reach environmental params + hydraulic CSV paths
marine:          # optional — zones, salinity/temp drivers, smolt/adult rules
```

For building a new case study from real geography (OSM/EMODnet/Marine
Regions), see [`docs/case-studies/baltic-workflow.md`](docs/case-studies/baltic-workflow.md).

---

## Testing

```bash
# Full suite
pytest tests/ -v

# Fast (skip simulation-heavy slow tests)
pytest tests/ -v -m "not slow"

# With coverage
pytest tests/ -v --cov=instream

# Targeted: model + all create_model + bathymetry
pytest tests/test_model.py tests/test_create_model*.py \
       tests/test_bathymetry.py tests/test_marineregions_cache.py -v
```

### End-to-end tests (Playwright)

Require a running Shiny app; see [Interactive Shiny App](#interactive-shiny-app).

```bash
# Fast smoke: widget assertions, config load, tab navigation (60 s)
pytest tests/e2e/ -v

# Opt-in integration: real fetch / simulate / export flows (~5 min total)
E2E_INTEGRATION=1 pytest tests/e2e/ -v
```

Current counts: **920+ tests** pass on the fast (non-slow) suite;
17/17 NetLogo cross-validation tests pass; 33/33 Playwright e2e pass
against a live app.

---

## Interactive Shiny App

`app/app.py` is a Shiny for Python application with interactive panels for
simulation control, spatial visualization (deck.gl), trips animation,
population/distribution/redd views, and a **Create Model** panel for
building new case studies from OSM geometry.

```bash
cd app && shiny run --port 8000 app:app
```

Panels (left sidebar):

- **Create Model** — fetch OSM rivers for any Geofabrik region, filter by
  Strahler order, click-select reaches, generate hexagonal habitat cells,
  export shapefile + YAML config
- **Setup** — load config, inspect grid / reach table / marine zones before
  running
- **Dashboard** — live population/mortality rates during simulation
- **Movement** — animated fish trails (TripsLayer) on the river network
- **Population** — per-reach stage-structured population curves
- **Spatial** — deck.gl map with color-by-variable cells (temperature,
  depth, velocity, fish count)
- **Environment** — daily temperature/flow/turbidity plots
- **Size Distribution** — length histograms per stage
- **Redds** — redd locations, development, emergence
- **Help & Tests** — inline test case explanations

---

## Documentation

- **API reference** (Sphinx, GitHub Pages): <https://razinkele.github.io/instream-py/>
- **User manual**: [`docs/user-manual.md`](docs/user-manual.md)
- **Calibration notes**: [`docs/calibration-notes.md`](docs/calibration-notes.md)
- **Baltic case study workflow**: [`docs/case-studies/baltic-workflow.md`](docs/case-studies/baltic-workflow.md)
- **NetLogo parity roadmap**: [`docs/NETLOGO_PARITY_ROADMAP.md`](docs/NETLOGO_PARITY_ROADMAP.md)
- **vs HexSim comparison**: [`docs/hexsim-vs-instream-comparison.md`](docs/hexsim-vs-instream-comparison.md)
- **Release plans** (pre-execution review artifacts): [`docs/superpowers/plans/`](docs/superpowers/plans/)

Build the Sphinx docs locally:

```bash
pip install -e ".[docs]"
sphinx-build -b html docs/source docs/_build/html
```

---

## Citation

If you use inSTREAM-py in your research, please cite both the original
inSTREAM reference and this Python implementation:

```bibtex
@techreport{railsback2009instream,
  title     = {InSTREAM: the individual-based stream trout research and
               environmental assessment model},
  author    = {Railsback, Steven F. and Harvey, Bret C. and Jackson,
               Stephen K. and Lamberson, Roland H.},
  year      = {2009},
  institution = {USDA Forest Service, Pacific Southwest Research Station},
  number    = {PSW-GTR-218},
  type      = {General Technical Report}
}

@book{railsback2020modeling,
  title     = {Modeling Populations of Adaptive Individuals},
  author    = {Railsback, Steven F. and Harvey, Bret C.},
  year      = {2020},
  publisher = {Princeton University Press},
  series    = {Monographs in Population Biology},
  number    = {63}
}

@software{instream_py,
  title   = {inSTREAM-py: High-performance Python individual-based
             salmonid model},
  author  = {Razinkovas-Baziukas, Artūras and contributors},
  year    = {2026},
  url     = {https://github.com/razinkele/instream-py},
  version = {0.30.2}
}
```

---

## License

**GNU General Public License v3.0 or later** (GPL-3.0-or-later). See
[LICENSE](LICENSE) for the full text.

---

## Acknowledgements

- Original **inSTREAM** model: Railsback, Harvey & colleagues at the USDA
  Forest Service Pacific Southwest Research Station
- **NetLogo 7.4** reference implementation used for cross-validation
- **OpenStreetMap** contributors (river and water-body geometry via Geofabrik)
- **EMODnet Bathymetry Consortium** for the Baltic DTM
  (<https://emodnet.ec.europa.eu/en/bathymetry>)
- **Marine Regions / VLIZ** for the named-water-body gazetteer
  (<https://marineregions.org/>)
- **HORIZON EUROPE** funding supporting the Baltic case study work
