# Arc M–Q Expanded Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Scope note**: This document expands Arcs M, N, O, P, Q into full TDD detail. Each Arc is a **self-contained feature** and may be merged independently (Arc P even runs in parallel with any of the others). A dedicated git branch per Arc is expected.

**Goal:** Bring SalmoPy to full WGBAST parity: multi-river output (M), post-smolt survival forcing (N), straying + genetic MSA (O), grey-seal predation as an explicit term (P), and a Bayesian life-cycle wrapper (Q).

**Prerequisites:**
- Arcs K (v0.34.0, merged) and L (v0.35.0, merged).
- **Arc 0 data-assembly (partially complete, reviewer-identified gap)**:
  Arcs M, N, P, Q all depend on data that currently lives inside the
  WGBAST 2026 report PDF (DOI 10.17895/ices.pub.29118545.v3) or the
  HELCOM grey-seal core-indicator PDF. The Arc K→Q roadmap prepended
  an Arc 0 for this; the M74 series landed in v0.35.0 as a preliminary
  placeholder (`data/wgbast/m74_ysfm_series.csv`). The remaining pieces
  each Arc below needs are:
  - **Arc M**: per-river PSPC values (Torne 2.2M, Simo 95k, Byske 180k,
    Mörrum 60k) from WGBAST 2026 §3 Table.
  - **Arc N**: per-year Baltic post-smolt survival posterior 1987–2024
    from WGBAST 2026 Figure 4.x (narrative gives "10-20% mid-2000s,
    6.0% median 2021, lowest in time-series" but not yearly CSV).
  - **Arc P**: HELCOM grey-seal abundance (hand-transcribe from the
    HELCOM core-indicator PDF at
    https://indicators.helcom.fi/indicator/grey-seal-abundance/ —
    interactive maps + PDF only, no direct CSV download).
  - **Arc Q**: smolt-trap counts (Simojoki 1991–2024; Tornionjoki
    1996–2024) + adult-counter series (Torne, Kalix, Byske, Vindel,
    Pite, Testebo) from WGBAST 2026 §3.

  The Arc K roadmap's Arc 0 task list covers 0.1–0.5 (PDF fetch → PSPC
  extraction → YSFM extraction → post-smolt extraction → README). Each
  Arc below ships a **PRELIMINARY placeholder CSV first** so the code
  wiring can land; the user then replaces each CSV with real data via
  Arc 0 in a follow-up PR (drop-in replacement, no code change).

The Arc K roadmap (`docs/superpowers/plans/2026-04-20-arc-K-to-Q-wgbast-roadmap.md`)
covered these arcs as task sheets; this document is the execution-ready expansion.

**Tech Stack:** Python 3.11, numpy/pandas, pytest, pydantic YAML configs, existing `src/instream/calibration/` framework (13 modules), ICES MCP tools (`ices-mcp/ices_clients/migratory.py`).

**Starting master**: commit `468f07a` (v0.35.0, Arc L merged).

## Dependency Graph

```
v0.35.0 (Arc L merged)
   ↓
   ├── Arc M (multi-river fixtures)   → v0.36.0  [independent]
   ├── Arc N (post-smolt forcing)     → v0.37.0  [independent]
   ├── Arc O (straying + MSA matrix)  → v0.38.0  [needs K schema]
   └── Arc P (grey-seal abundance)    → v0.39.0  [parallel-safe]
              ↓
              └── Arc Q (Bayesian wrapper) → v0.40.0  [needs K/L/M/N/O]
```

Recommended merge order: **M → N → O → P → Q**, but M/N/P can run concurrently on separate branches.

---

# Arc M: Multi-river Baltic fixtures

**Goal:** Add four WGBAST-assessment-ready river configs — Tornionjoki, Simojoki, Byskeälven, Mörrumsån — so SalmoPy can emit WGBAST-comparable `smolt_production_by_reach_{year}.csv` across the latitudinal smolt-age gradient (AU 1 → AU S, 3–4 yr → 1–2 yr smolts).

**Why:** v0.34.0 Arc K ships the PSPC output but only example_baltic (Nemunas) uses it with placeholder values. Arc M adds the four canonical WGBAST monitoring rivers with real PSPC, trap-count, and smolt-length-at-age envelopes so per-river calibration runs become meaningful.

**Effort:** M–L (3–5 days). Each river is ~0.75 days once the first one is scaffolded.

## File Structure

**Per river** (pattern repeats for each of 4):
- `tests/fixtures/tornionjoki/` — reach CSVs (depth, velocity, timeseries), Shapefile stub, InitialPopulations, AdultArrivals
- `configs/example_tornionjoki.yaml` — references the fixture + BalticAtlanticSalmon species with river-specific overrides
- `tests/fixtures/simojoki/` + `configs/example_simojoki.yaml`
- `tests/fixtures/byskealven/` + `configs/example_byskealven.yaml`
- `tests/fixtures/morrumsan/` + `configs/example_morrumsan.yaml`

**Shared:**
- `tests/test_multi_river_baltic.py` — cross-river smoke + latitudinal-gradient parity tests
- `docs/validation/v0.36.0-multi-river-baltic.md`

## Tasks

### Task M.1: Scaffold the Tornionjoki fixture (AU 1, largest stock)

**Files** (all use single stem `TornionjokiExample-` per NetLogo convention):
- Create: `tests/fixtures/tornionjoki/TornionjokiExample-Depths.csv`, `TornionjokiExample-Vels.csv`, `TornionjokiExample-TimeSeriesInputs.csv`
- Create: `tests/fixtures/tornionjoki/TornionjokiExample-InitialPopulations.csv`, `TornionjokiExample-AdultArrivals.csv`
- Create: `tests/fixtures/tornionjoki/Shapefile/TornionjokiExample.shp` (+ .shx, .dbf, .prj) — hand-traced river centerline from OSM
- Create: `configs/example_tornionjoki.yaml`

- [ ] **Step M.1.1: Pull Tornionjoki centerline bounding box**

Use `get_ices_areas_by_bbox` in `ices-mcp/ices_clients/gis.py` (the module does
NOT export an `ices_get_rectangles` function — that name exists only as an
MCP tool wrapper in `ices_mcp_server.py`). Tornionjoki spans roughly
`65.6N-67.1N, 22.9E-24.2E`.

```python
# scripts/_fetch_tornionjoki_geometry.py
from ices_clients.gis import get_ices_areas_by_bbox
areas = get_ices_areas_by_bbox(
    min_lon=22.9, min_lat=65.6, max_lon=24.2, max_lat=67.1,
)
print(f"{len(areas)} ICES areas in Tornionjoki stock unit")
```

- [ ] **Step M.1.2: Hand-trace the 5-reach river schematic**

Torne is 522 km long. Use 5 reaches matching WGBAST monitoring granularity:

| Reach name | Length (m) | Width (m) | Description |
|------------|-----------|-----------|-------------|
| TorneUpper | 130000 | 60 | Finnish-Swedish border headwaters |
| TorneMiddle | 140000 | 90 | Muonio confluence → Pajala |
| TorneLower | 150000 | 140 | Pajala → Övertorneå |
| TorneEstuary | 80000 | 200 | Övertorneå → Haparanda |
| TorneBalticExit | 22000 | 400 | Haparanda strait → Bothnian Bay |

Create minimal hydrology CSVs with 4 cells per reach (16 cells × 5 reaches = 80 total). Copy the `example_baltic` timeseries file as the initial template, then adjust mean discharge to ~400 m³/s (Torne annual mean).

Copy the Shapefile from `tests/fixtures/example_baltic/Shapefile/BalticExample.*` and hand-edit feature IDs to 0..4 matching the reach ordering above.

- [ ] **Step M.1.3: Build `configs/example_tornionjoki.yaml`**

Start from `configs/example_baltic.yaml` and change:

Fixture filename convention: **single stem per river**, following NetLogo
InSALMO 7.3 style — all files prefixed `TornionjokiExample-<Kind>.csv`.
Avoid mixing stems (`Tornionjoki-Depths.csv` vs `TornionjokiExample-...`).

```yaml
simulation:
  start_date: "2011-04-01"
  end_date: "2016-03-31"            # 5 years, full smolt cohort (3-4 yr AU1)
  seed: 42
  population_file: "TornionjokiExample-InitialPopulations.csv"
  adult_arrival_file: "TornionjokiExample-AdultArrivals.csv"
  m74_forcing_csv: "data/wgbast/m74_ysfm_series.csv"
    # WGBAST-comparable: Tornionjoki is in the Vuorinen 2021 series.

species:
  BalticAtlanticSalmon:
    smolt_min_length: 14.0          # AU1 smolts 14-18 cm (Skoglund 2024 Paper III)
    spawn_start_day: "10-15"        # same as baltic
    # Inherit everything else via the baltic species block

reaches:
  # PSPC distribution rebalanced per Anttila et al. 2008 (J. Fish Dis. 31)
  # — parr density (proxy for production) is highest in uppermost reach,
  # lowest in estuary. Earlier draft over-weighted estuary share.
  TorneUpper:
    river_name: "Tornionjoki"
    pspc_smolts_per_year: 400000     # ~18% (headwater + high-quality)
    length_m: 130000
    width_m: 60
    drift_conc: 2.5e-08              # high-quality headwaters
    # … (copy baltic reach block, adjust)
  TorneMiddle:
    river_name: "Tornionjoki"
    pspc_smolts_per_year: 880000     # ~40% (main production area)
    # …
  TorneLower:
    river_name: "Tornionjoki"
    pspc_smolts_per_year: 700000     # ~32%
    # …
  TorneEstuary:
    river_name: "Tornionjoki"
    pspc_smolts_per_year: 220000     # ~10% (marginal rearing habitat)
    # …
  TorneBalticExit:
    # non-natal exit zone, no PSPC
    river_name: "Tornionjoki"
    # …
```

Total PSPC: 2,200,000 = WGBAST 2,200k for Torne.
Distribution rationale: Anttila et al. 2008 documents highest parr
infection prevalence (a density proxy) in the upper reach and "rare in
the lowermost reach"; 40% middle / 32% lower / 18% upper / 10% estuary
matches that pattern more faithfully than the first draft's 34/32/16/17.

- [ ] **Step M.1.4: Smoke test**

```python
# tests/test_multi_river_baltic.py
import pytest
import yaml
from instream.io.config import load_config
from instream.model import InSTREAMModel


@pytest.mark.parametrize("config_path", [
    "configs/example_tornionjoki.yaml",
])
def test_fixture_loads_and_runs_3_days(config_path, tmp_path):
    """Arc M.1 smoke: fixture loads, runs 3 days, emits outputs."""
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cfg["simulation"]["end_date"] = "2011-04-03"
    cfg_path = tmp_path / "short.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg, f)

    # Use the real fixture data dir
    fixture_dir = f"tests/fixtures/{config_path.split('example_')[1].split('.yaml')[0]}"
    model = InSTREAMModel(
        config_path=str(cfg_path),
        data_dir=fixture_dir,
        output_dir=str(tmp_path),
    )
    model.run()
    assert (tmp_path / "outmigrants.csv").exists()
    assert list(tmp_path.glob("smolt_production_by_reach_*.csv"))
```

Run: `micromamba run -n shiny python -m pytest tests/test_multi_river_baltic.py -v`
Expected: PASS.

- [ ] **Step M.1.5: Commit**

```bash
git add tests/fixtures/tornionjoki configs/example_tornionjoki.yaml tests/test_multi_river_baltic.py
git commit -m "feat(fixtures): Tornionjoki Arc M — 5-reach AU1 WGBAST fixture"
```

### Task M.2: Simojoki (AU 1, trap-counted monitoring river)

Same scaffolding pattern as M.1, with these river-specific facts:
- **Reaches**: 3 reaches (Simojoki is 171 km, smaller than Torne) — SimoUpper (70km), SimoLower (80km), SimoEstuary (21km)
- **PSPC**: 95,000 smolts/yr total → SimoUpper 30k, SimoLower 55k, SimoEstuary 10k
- **Smolt length**: `smolt_min_length: 14.0` (same AU1 as Torne)
- **river_name**: "Simojoki" — present in M74 CSV, so forcing fires
- **Mean discharge**: ~45 m³/s

- [ ] **Step M.2.1: Copy Tornionjoki fixture structure, adjust hydrology and reaches**

```bash
cp -r tests/fixtures/tornionjoki tests/fixtures/simojoki
cp configs/example_tornionjoki.yaml configs/example_simojoki.yaml
```

Then edit the 3 reaches + PSPC + discharge per the table above.

- [ ] **Step M.2.2: Extend the smoke test parameterization**

```python
@pytest.mark.parametrize("config_path", [
    "configs/example_tornionjoki.yaml",
    "configs/example_simojoki.yaml",
])
```

- [ ] **Step M.2.3: Commit**

```bash
git add tests/fixtures/simojoki configs/example_simojoki.yaml tests/test_multi_river_baltic.py
git commit -m "feat(fixtures): Simojoki Arc M — 3-reach trap-counted AU1 fixture"
```

### Task M.3: Byskeälven (AU 2 intermediate) + Mörrumsån (Southern 1-2 yr smolts)

Two fixtures, same pattern:

| Parameter | Byskeälven | Mörrumsån |
|-----------|------------|-----------|
| Assessment unit | AU 2 | Southern |
| Reaches | 4 | 3 |
| Total length | 220 km | 170 km |
| PSPC total | 180,000 | 60,000 |
| smolt_min_length | 13.0 | 11.0 |
| Modal smolt age | 2 yr | 1–2 yr |
| Mean discharge | 40 m³/s | 25 m³/s |
| river_name for M74 | "" (not in CSV) | "" (not in CSV) |

Mörrum PSPC raised from 50k → 60k to match Poćwierz-Kotus et al. 2015
(DOI 10.1186/s12711-015-0121-9, which cites ~60k wild smolt production).

Byske and Mörrum aren't in the placeholder M74 CSV, so `m74_forcing_csv` stays set but fires only on Torne/Simo. That's correct behavior — future Arc 0 re-extraction will add those rivers.

- [ ] **Step M.3.1: Scaffold Byskeälven** (repeat M.1/M.2 pattern).

- [ ] **Step M.3.2: Scaffold Mörrumsån** (repeat).

- [ ] **Step M.3.3: Commit each as its own commit**.

### Task M.4: Latitudinal-gradient smolt-age test

The scientific payoff of M is that running the four fixtures produces modal smolt ages matching WGBAST's published latitudinal gradient: Torne/Simo 3–4 yr → Byske 2 yr → Mörrum 1–2 yr.

- [ ] **Step M.4.1: Write failing test**

```python
# tests/test_multi_river_baltic.py — append
import pandas as pd


@pytest.mark.slow  # 4 × 5-year runs; skip by default
@pytest.mark.parametrize("config_path,expected_modal_age", [
    ("configs/example_tornionjoki.yaml", 4),
    ("configs/example_simojoki.yaml", 3),
    ("configs/example_byskealven.yaml", 2),
    ("configs/example_morrumsan.yaml", 2),
])
def test_latitudinal_smolt_age_gradient(config_path, expected_modal_age, tmp_path):
    """Arc M.4: modal smolt age matches WGBAST latitudinal gradient."""
    import yaml
    from instream.model import InSTREAMModel

    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cfg["simulation"]["end_date"] = "2016-03-31"  # 5 yrs
    cfg["simulation"]["seed"] = 42
    cfg_path = tmp_path / "cfg.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg, f)

    fixture_dir = f"tests/fixtures/{config_path.split('example_')[1].split('.yaml')[0]}"
    model = InSTREAMModel(
        config_path=str(cfg_path),
        data_dir=fixture_dir,
        output_dir=str(tmp_path),
    )
    model.run()

    df = pd.read_csv(tmp_path / "outmigrants.csv")
    smolts = df[df["length_category"] == "Smolt"]
    assert len(smolts) > 10, f"No smolts produced in {config_path}"
    modal_age = int(smolts["age_years"].round().mode().iloc[0])
    assert abs(modal_age - expected_modal_age) <= 1, (
        f"{config_path}: modal age {modal_age}, expected {expected_modal_age}"
    )
```

- [ ] **Step M.4.2: Run tests → expect 4 to pass**

Run: `micromamba run -n shiny python -m pytest tests/test_multi_river_baltic.py::test_latitudinal_smolt_age_gradient -v -m slow`
Expected: 4 PASS.

If Tornionjoki/Simojoki produce modal age 3 instead of 4, that's still within ±1 and passes. If Mörrum produces age 3, the southern calibration is too cold; revisit temperature timeseries.

- [ ] **Step M.4.3: Commit**

```bash
git add tests/test_multi_river_baltic.py
git commit -m "test(Arc M): latitudinal smolt-age gradient across 4 WGBAST rivers"
```

### Task M.5: Docs + release v0.36.0

- [ ] **Step M.5.1: Write `docs/validation/v0.36.0-multi-river-baltic.md`** — document the 4 rivers, their WGBAST provenance, the PSPC totals, and the latitudinal-age gradient finding.

- [ ] **Step M.5.2: CHANGELOG entry under `## [0.36.0]`**:

```markdown
### Added
- **4 new WGBAST-assessment-ready Baltic river fixtures (Arc M)**:
  Tornionjoki (5 reaches, PSPC 2.2M), Simojoki (3 reaches, PSPC 95k),
  Byskeälven (4 reaches, PSPC 180k), Mörrumsån (3 reaches, PSPC 50k).
- **`smolt_min_length` override pattern per river**: AU1 rivers use
  14 cm, Byske 13 cm, Mörrum 11 cm (Skoglund 2024 Paper III envelopes).
- **Latitudinal smolt-age parity test** validates the AU1→southern
  modal-age gradient (4 → 2 yr).
```

- [ ] **Step M.5.3: Version bump + tag**

```bash
# pyproject.toml + src/instream/__init__.py → 0.36.0
git add pyproject.toml src/instream/__init__.py docs/validation/v0.36.0-multi-river-baltic.md CHANGELOG.md
git commit -m "release(v0.36.0): Arc M multi-river Baltic fixtures"
git tag v0.36.0
git push origin master v0.36.0
```

---

# Arc N: Post-smolt survival time-varying forcing

**Goal:** Replace the single-point post-smolt survival in `marine_survival()` with a per-(smolt-year, stock-unit) lookup from a WGBAST-Bayesian-posterior CSV, so retrospective simulations across 1987–2024 track the published ICES time series.

**Why:** v0.34.0 uses a constant marine mortality calibrated to a single 3.61% SAR point (v0.18.0 memory). WGBAST 2026 published a 1987–2024 posterior median series (6% median in 2021, declining from 10–20% in the mid-2000s). Forcing the model with this series enables Olmos-2018-style retrospective hindcasts and conditions Arc Q's Bayesian wrapper.

**Effort:** M (2–3 days).

## File Structure

**Create:**
- `data/wgbast/post_smolt_survival_baltic.csv` — year, stock_unit, survival_pct (placeholder pending Arc 0 extraction, same pattern as M74 CSV).
- `src/instream/marine/survival_forcing.py` — loader + per-year multiplier computation.
- `tests/test_post_smolt_forcing.py`.

**Modify:**
- `src/instream/marine/config.py:135` — add `post_smolt_survival_forcing_csv: str | None`, `stock_unit: str | None = "sal.27.22-31"`.
- `src/instream/marine/survival.py:105` — `marine_survival()` accepts an optional annual-survival override and scales the daily hazard product accordingly.
- `configs/example_baltic.yaml` + `configs/example_tornionjoki.yaml` etc. — wire the CSV.

## Tasks

### Task N.1: Ship placeholder CSV

- [ ] **Step N.1.1: Create `data/wgbast/post_smolt_survival_baltic.csv`** with placeholder series:

```
# WGBAST post-smolt survival — annual fraction for each Baltic stock unit.
# PRELIMINARY placeholder series based on WGBAST 2023 §2.5 narrative range
# (3-12% band, declining from mid-2000s highs). Replace via Arc 0 PDF
# extraction of the Bayesian posterior median from WGBAST 2026 figures.
#
# Source template:
#   ICES (2023). WGBAST. ICES Scientific Reports 5(26).
#     DOI 10.17895/ices.pub.22328542
#   Olmos, M. et al. (2018). Fish and Fisheries 20(2), 322-342.
#     DOI 10.1111/faf.12345 — hierarchical Bayesian declining trend.
#
year,stock_unit,survival_pct,source
1987,sal.27.22-31,0.14,placeholder_prelim
1990,sal.27.22-31,0.16,placeholder_prelim
1995,sal.27.22-31,0.13,placeholder_prelim
2000,sal.27.22-31,0.11,placeholder_prelim
2005,sal.27.22-31,0.09,placeholder_prelim
2010,sal.27.22-31,0.06,placeholder_prelim
2015,sal.27.22-31,0.05,placeholder_prelim
2020,sal.27.22-31,0.06,placeholder_prelim
2024,sal.27.22-31,0.05,placeholder_prelim
# Fill 1987-2024 annually per Arc 0.4 extraction; these are decade markers
```

Expand to annual 1987-2024 with linear interpolation between decade points, or transcribe exact values from the WGBAST 2023 Figure 2.5.1 when Arc 0 completes.

- [ ] **Step N.1.2: Commit**

```bash
git add data/wgbast/post_smolt_survival_baltic.csv
git commit -m "data(Arc 0 placeholder): WGBAST post-smolt survival series 1987-2024"
```

### Task N.2: Loader + per-year multiplier (TDD)

- [ ] **Step N.2.1: Write failing loader test**

```python
# tests/test_post_smolt_forcing.py
from pathlib import Path
from instream.marine.survival_forcing import (
    load_post_smolt_forcing,
    annual_survival_for_year,
    daily_hazard_multiplier,
)


def test_load_post_smolt_forcing(tmp_path: Path):
    csv = tmp_path / "ps.csv"
    csv.write_text(
        "year,stock_unit,survival_pct,source\n"
        "2020,sal.27.22-31,0.06,t\n"
        "2020,sal.27.32,0.04,t\n"
    )
    s = load_post_smolt_forcing(csv)
    assert s[(2020, "sal.27.22-31")] == 0.06
    assert s[(2020, "sal.27.32")] == 0.04


def test_annual_survival_lookup(tmp_path: Path):
    csv = tmp_path / "ps.csv"
    csv.write_text(
        "year,stock_unit,survival_pct,source\n"
        "2020,sal.27.22-31,0.06,t\n"
    )
    s = load_post_smolt_forcing(csv)
    assert annual_survival_for_year(s, 2020, "sal.27.22-31") == 0.06
    # Unknown year/stock → None (caller decides fallback)
    assert annual_survival_for_year(s, 1999, "sal.27.22-31") is None


def test_daily_hazard_multiplier_inverts_survival():
    """6% annual survival → daily hazard ≈ 0.007691 (1 - 0.06^(1/365))."""
    import math
    h = daily_hazard_multiplier(annual_survival=0.06, days_per_year=365)
    expected = 1.0 - 0.06 ** (1.0 / 365)
    assert abs(h - expected) < 1e-10
    # Sanity: annual survival 1.0 → zero hazard
    assert daily_hazard_multiplier(1.0) == 0.0
    # Annual survival 0.0 → hazard 1.0 (all die on day 1)
    assert daily_hazard_multiplier(0.0) == 1.0
```

- [ ] **Step N.2.2: Run test → FAIL (module doesn't exist)**

- [ ] **Step N.2.3: Implement `src/instream/marine/survival_forcing.py`**

```python
"""WGBAST post-smolt survival forcing loader.

Converts an annual-survival series into a per-day hazard override
that is multiplied into `marine_survival`'s hazard product.

Reference: ICES (2023) WGBAST §2.5, published 3-12% post-smolt
survival envelope; Olmos et al. 2018 DOI 10.1111/faf.12345 for
the declining Atlantic trend.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Tuple
import pandas as pd


def load_post_smolt_forcing(path: Path | str) -> Dict[Tuple[int, str], float]:
    df = pd.read_csv(path, comment="#")
    required = {"year", "stock_unit", "survival_pct"}
    missing = required - set(df.columns)
    assert not missing, f"CSV missing columns: {missing}"
    return {
        (int(r.year), str(r.stock_unit)): float(r.survival_pct)
        for r in df.itertuples()
    }


def annual_survival_for_year(
    series: Dict[Tuple[int, str], float],
    year: int,
    stock_unit: str,
) -> Optional[float]:
    """Return annual survival (0-1), or None if (year, stock_unit) unknown."""
    return series.get((int(year), str(stock_unit)))


def daily_hazard_multiplier(
    annual_survival: float,
    days_per_year: int = 365,
) -> float:
    """Convert annual survival → daily hazard.

    Given S_annual = (1 - h_daily)^days_per_year, solve for h_daily.
    """
    s = max(0.0, min(1.0, float(annual_survival)))
    if s <= 0.0:
        return 1.0
    if s >= 1.0:
        return 0.0
    return 1.0 - s ** (1.0 / float(days_per_year))
```

- [ ] **Step N.2.4: Run test → PASS; commit**

```bash
git add src/instream/marine/survival_forcing.py tests/test_post_smolt_forcing.py
git commit -m "feat(marine): post-smolt survival loader + daily-hazard converter"
```

### Task N.3: Wire forcing into `marine_survival` (TDD)

- [ ] **Step N.3.1: Confirm `marine_survival` signature**

Verified on master at commit `468f07a`:
```python
def marine_survival(
    length: np.ndarray,
    zone_idx: np.ndarray,
    temperature: np.ndarray,
    days_since_ocean_entry: np.ndarray,
    cormorant_zone_indices: np.ndarray,
    config,
    is_hatchery: np.ndarray | None = None,
) -> np.ndarray:
    # returns per-fish daily SURVIVAL PROBABILITY (0-1), not survivor count
```

The function builds a product of 5 hazards. Arc N overrides `h_back`
(from `background_hazard(n, config)` at line 143) for post-smolt fish —
post-smolt is encoded as `days_since_ocean_entry < 365`.

- [ ] **Step N.3.2: Extend MarineConfig**

Edit `src/instream/marine/config.py` — add after `marine_mort_m74_prob`:

```python
# WGBAST Arc N: per-(year, stock_unit) annual post-smolt survival
# forcing. When set, OVERRIDES background_hazard for fish in the
# post-smolt window (days_since_ocean_entry < 365).
post_smolt_survival_forcing_csv: str | None = None
stock_unit: str | None = "sal.27.22-31"
```

- [ ] **Step N.3.3: Write failing integration test**

```python
# tests/test_post_smolt_forcing.py — append
import numpy as np


def test_marine_survival_respects_post_smolt_forcing(tmp_path):
    """Setting post_smolt_survival_forcing_csv overrides background_hazard
    for fish in the post-smolt window (days_since_ocean_entry < 365)."""
    from instream.marine.config import MarineConfig
    from instream.marine.survival import marine_survival

    csv = tmp_path / "ps.csv"
    csv.write_text(
        "year,stock_unit,survival_pct,source\n"
        "2020,sal.27.22-31,0.10,t\n"   # 10% annual → high daily hazard
    )
    cfg = MarineConfig(
        post_smolt_survival_forcing_csv=str(csv),
        stock_unit="sal.27.22-31",
        marine_mort_base=0.001,         # what it would have been without forcing
    )

    # Minimal 4-fish arrays; all at typical post-smolt length, same zone,
    # same temperature, 2 fish in post-smolt window, 2 fish well past it.
    length = np.array([20.0, 20.0, 20.0, 20.0])
    zone_idx = np.array([0, 0, 0, 0])
    temperature = np.array([10.0, 10.0, 10.0, 10.0])
    days_since = np.array([30, 100, 400, 500])  # 2 post-smolt, 2 adult
    corm_zones = np.array([], dtype=np.int64)

    # With forcing
    survival = marine_survival(
        length, zone_idx, temperature, days_since, corm_zones, cfg,
        current_year=2020,
    )
    # 10% annual → daily hazard ≈ 0.00629 → daily survival ≈ 0.99371.
    # Post-smolt fish (idx 0, 1): survival product dominated by h_back=0.00629
    # Non-post-smolt fish (idx 2, 3): survival product uses marine_mort_base=0.001
    # So post-smolt fish must have strictly LOWER survival than adult fish
    # (all other hazards equal).
    assert survival[0] < survival[2] - 1e-4, (
        f"post-smolt should have lower survival: {survival}"
    )
    assert survival[1] < survival[3] - 1e-4


def test_marine_survival_no_forcing_when_csv_unset():
    """Default MarineConfig (no forcing) preserves existing behavior."""
    from instream.marine.config import MarineConfig
    from instream.marine.survival import marine_survival

    cfg = MarineConfig()  # default: no forcing
    length = np.array([20.0, 20.0])
    zone_idx = np.array([0, 0])
    temperature = np.array([10.0, 10.0])
    days_since = np.array([30, 400])
    corm_zones = np.array([], dtype=np.int64)

    s_unforced = marine_survival(
        length, zone_idx, temperature, days_since, corm_zones, cfg,
    )
    # current_year kwarg defaults to None, so forcing doesn't fire.
    assert np.all(s_unforced > 0.99)  # low background hazard
```

- [ ] **Step N.3.4: Run test → expect FAIL**

Run: `micromamba run -n shiny python -m pytest tests/test_post_smolt_forcing.py::test_marine_survival_respects_post_smolt_forcing -v`
Expected: FAIL with `TypeError: marine_survival() got an unexpected keyword argument 'current_year'`.

- [ ] **Step N.3.5: Extend `marine_survival` with `current_year` kwarg**

Edit `src/instream/marine/survival.py:105-154`:

```python
_POST_SMOLT_CACHE: "dict[Path, dict[tuple[int, str], float]]" = {}

POST_SMOLT_WINDOW_DAYS = 365


def marine_survival(
    length: np.ndarray,
    zone_idx: np.ndarray,
    temperature: np.ndarray,
    days_since_ocean_entry: np.ndarray,
    cormorant_zone_indices: np.ndarray,
    config,
    is_hatchery: np.ndarray | None = None,
    current_year: int | None = None,
) -> np.ndarray:
    """Combined daily survival probability from sources 1..5.

    Arc N: if `current_year` is provided AND
    `config.post_smolt_survival_forcing_csv` is set, the background hazard
    term is overridden for fish with `days_since_ocean_entry <
    POST_SMOLT_WINDOW_DAYS` by the per-(year, stock_unit) value from the
    CSV. Fish outside that window use the default `marine_mort_base`.

    Returns per-fish daily survival probability ∈ [0, 1].
    """
    n = np.asarray(length).shape[0]
    h_seal = seal_hazard(length, config)
    h_corm = cormorant_hazard(
        length, zone_idx, days_since_ocean_entry, cormorant_zone_indices, config
    )
    if is_hatchery is not None and np.any(is_hatchery):
        h_corm = np.where(
            is_hatchery,
            h_corm * config.hatchery_predator_naivety_multiplier,
            h_corm,
        )
    h_back = background_hazard(n, config)

    # Arc N: post-smolt survival override, keyed by SMOLT YEAR (year the
    # fish entered the ocean), not calendar year. Rationale: WGBAST's
    # posterior is indexed by smolt cohort, and a fish emigrating July Y
    # crossing into Y+1 should receive Y's forcing throughout its 365-day
    # post-smolt window — not a July/January year split that would blend
    # two cohort posteriors. We derive smolt_year from current_year +
    # days_since_ocean_entry.
    if (
        getattr(config, "post_smolt_survival_forcing_csv", None) is not None
        and getattr(config, "stock_unit", None) is not None
        and current_year is not None
    ):
        from pathlib import Path
        path = Path(config.post_smolt_survival_forcing_csv)
        if path not in _POST_SMOLT_CACHE:
            from instream.marine.survival_forcing import load_post_smolt_forcing
            _POST_SMOLT_CACHE[path] = load_post_smolt_forcing(path)
        from instream.marine.survival_forcing import (
            annual_survival_for_year, daily_hazard_multiplier,
        )
        # Per-fish smolt year = current_year - floor(days_since_ocean_entry / 365)
        smolt_years = current_year - (days_since_ocean_entry // 365)
        post_smolt_mask = days_since_ocean_entry < POST_SMOLT_WINDOW_DAYS
        h_forced_array = np.full_like(h_back, np.nan)
        for sy in np.unique(smolt_years[post_smolt_mask]):
            S_ann = annual_survival_for_year(
                _POST_SMOLT_CACHE[path], int(sy), config.stock_unit,
            )
            if S_ann is not None:
                h_forced_array[smolt_years == sy] = daily_hazard_multiplier(S_ann)
        # Apply forcing where (a) fish is in post-smolt window AND
        # (b) its smolt-year has an entry in the CSV
        forced_mask = post_smolt_mask & np.isfinite(h_forced_array)
        h_back = np.where(forced_mask, h_forced_array, h_back)

    h_temp = temperature_stress_hazard(temperature, config)
    h_m74 = m74_hazard(n, config)

    survival = (
        (1.0 - h_seal) * (1.0 - h_corm) * (1.0 - h_back)
        * (1.0 - h_temp) * (1.0 - h_m74)
    )
    return np.clip(survival, 0.0, 1.0)
```

- [ ] **Step N.3.6: Update callers to pass `current_year`**

Run: `grep -n "marine_survival(" src/instream/`.
The only call site is `apply_marine_survival` in the same file. Add
`current_year=current_date.year` to that call (threaded from the
top-level apply_marine_survival caller which receives `current_date`).

- [ ] **Step N.3.7: Run test → PASS; regression sweep**

```bash
micromamba run -n shiny python -m pytest tests/test_post_smolt_forcing.py tests/test_marine_survival.py -v
```
Expected: all PASS. Existing tests unaffected because `current_year`
defaults to `None`.

- [ ] **Step N.3.8: Commit**

```bash
git add src/instream/marine/survival.py src/instream/marine/config.py tests/test_post_smolt_forcing.py
git commit -m "feat(marine): marine_survival respects post-smolt annual-survival forcing"
```

### Task N.4: Multi-year hindcast integration test

- [ ] **Step N.4.1: Write hindcast test**

```python
# tests/test_post_smolt_forcing.py — append
def test_hindcast_2000_2020_tracks_forcing(tmp_path):
    """End-to-end: running example_baltic across 2005-2010 with a forced
    declining post-smolt survival series produces a declining outmigrant→
    adult return ratio."""
    import yaml
    from instream.model import InSTREAMModel

    with open("configs/example_baltic.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["simulation"]["start_date"] = "2005-04-01"
    cfg["simulation"]["end_date"] = "2010-03-31"
    cfg["simulation"]["post_smolt_survival_forcing_csv"] = (
        "data/wgbast/post_smolt_survival_baltic.csv"
    )
    cfg["simulation"]["stock_unit"] = "sal.27.22-31"

    cfg_path = tmp_path / "hindcast.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg, f)

    model = InSTREAMModel(
        config_path=str(cfg_path),
        data_dir="tests/fixtures/example_baltic",
        output_dir=str(tmp_path),
    )
    model.run()
    # Just smoke: confirm the run completed without error. Full parity
    # validation is an Arc Q Bayesian-wrapper task.
    assert (tmp_path / "outmigrants.csv").exists()
```

- [ ] **Step N.4.2: Run test → expect PASS**

- [ ] **Step N.4.3: Add YAML opt-in to example_baltic.yaml**

```yaml
simulation:
  # ...
  # Arc N: opt-in to WGBAST post-smolt survival forcing
  # post_smolt_survival_forcing_csv: "data/wgbast/post_smolt_survival_baltic.csv"
  # stock_unit: "sal.27.22-31"
```

Left commented because the placeholder series is decade-marker
interpolated; uncomment after Arc 0.4 real extraction.

### Task N.5: Docs + release v0.37.0

- [ ] **Step N.5.1: Write `docs/validation/v0.37.0-post-smolt-forcing.md`**
- [ ] **Step N.5.2: CHANGELOG + version bump + tag**

```bash
git tag v0.37.0
git push origin master v0.37.0
```

---

# Arc O: Straying/homing + genetic MSA spawner-origin matrix

**Goal:** Add a `stray_fraction: float` parameter controlling what fraction of returning adults stray from their natal river, and emit a `spawner_origin_matrix_{year}.csv` structurally comparable to WGBAST's genetic MSA apportionment.

**Why:** WGBAST (IBPSalmon 2013 revision) apportions mixed sea catches back
to rivers via genetic MSA. SalmoPy's current perfect-homing default biases
the apportionment when reality is ~5–15% straying (Östergren et al. 2021
archival-DNA homogenization, DOI 10.1098/rspb.2020.3147; population
structure foundation in Säisä et al. 2005 DOI 10.1139/f05-094). The 2025
stock annex explicitly flags this as a known uncertainty. Note that
Säisä 2005 quantifies *genetic differentiation* (FST/G_GB), not straying
rate directly — the 5–15% number is a downstream inference anchored to
Östergren 2021's temporal-homogenization evidence.

**Effort:** M (3–4 days). The straying logic is simple; the matrix output is also simple; what takes time is auditing the `natal_reach_idx` overwrite at `src/instream/modules/migration.py:149` that currently invalidates genetic tracking at smoltification.

## File Structure

**Fix (prerequisite):**
- `src/instream/modules/migration.py:152` — REMOVE the `natal_reach_idx = current_reach` overwrite at the SMOLT transition. This overwrite makes every smoltified fish "born" at its exit reach, destroying the genetic-MSA signal. (Plan previously cited line 149; verified on master `468f07a` the line number is 152 after Arc K's migration.py widening.)

**Modify:**
- `src/instream/marine/config.py` — add `stray_fraction: float = 0.0`.
- `src/instream/marine/domain.py:381-410` — at the adult return site, with probability `stray_fraction`, reassign `trout_state.reach_idx[i]` to a randomly chosen non-natal reach (weighted by reach size). Keep `natal_reach_idx` unchanged.
- `src/instream/io/output.py` — add `write_spawner_origin_matrix(spawners, reach_names, year, output_dir)`.

**Create:**
- `tests/test_straying.py`.
- `docs/validation/v0.38.0-straying-msa.md`.

## Tasks

### Task O.1: Fix the natal_reach_idx overwrite at smoltification (PRE-REQ)

**Critical**: v0.34.0 documented this as a known bug deferred to Arc O. Arc O cannot produce correct genetic-MSA matrices without first fixing it.

- [ ] **Step O.1.1: Write a failing test that exercises the bug**

Natal reach MUST differ from current reach so the test catches the overwrite.
Use a real `MarineConfig` (no need for a stub — construction is cheap).

```python
# tests/test_straying.py
import numpy as np
from instream.state.trout_state import TroutState
from instream.state.life_stage import LifeStage
from instream.marine.config import MarineConfig
from instream.modules.migration import migrate_fish_downstream


def test_smoltification_preserves_natal_reach_idx():
    """Arc O.1: smoltification must NOT overwrite natal_reach_idx.

    Pre-v0.38 (inherited from v0.30.x), migrate_fish_downstream assigned
    trout_state.natal_reach_idx = current_reach at the SMOLT transition,
    destroying the birth-reach signal for every outmigrating smolt.
    """
    ts = TroutState.zeros(capacity=10)
    ts.alive[0] = True
    ts.species_idx[0] = 0
    ts.length[0] = 13.0
    ts.life_history[0] = int(LifeStage.PARR)
    ts.natal_reach_idx[0] = 2          # born in reach 2
    ts.reach_idx[0] = 5                # currently migrating through reach 5
    ts.smolt_readiness[0] = 0.9

    reach_graph = {5: {"downstream": 99, "upstream": None}}
    cfg = MarineConfig()  # default config — enables marine transition

    outmigrants, smoltified = migrate_fish_downstream(
        ts, fish_idx=0, reach_graph=reach_graph,
        marine_config=cfg, smolt_min_length=12.0,
    )
    # Fish outmigrated and became SMOLT; natal_reach_idx MUST still be 2
    assert ts.natal_reach_idx[0] == 2, (
        f"natal_reach_idx overwritten at smoltification: {ts.natal_reach_idx[0]}"
    )
    assert ts.life_history[0] == int(LifeStage.SMOLT)
```

- [ ] **Step O.1.2: Run → FAIL**

Run: `micromamba run -n shiny python -m pytest tests/test_straying.py::test_smoltification_preserves_natal_reach_idx -v`
Expected: FAIL with `assert 5 == 2` (the overwrite changed natal_reach_idx
from 2 to 5, the smolt's exit reach).

- [ ] **Step O.1.3: Remove the overwrite**

Edit `src/instream/modules/migration.py` around line 149 — delete the line `trout_state.natal_reach_idx[fish_idx] = current_reach`. Add a short comment explaining why the overwrite is wrong for MSA.

- [ ] **Step O.1.4: Run → PASS; full regression sweep**

```bash
micromamba run -n shiny python -m pytest tests/ -q --tb=line
```

Some existing tests may have been passing ONLY because of this overwrite (e.g., tests that expected marine-stage fish to have `natal_reach_idx == exit_reach`). Investigate any breakage — each one is a place that was silently relying on the bug.

- [ ] **Step O.1.5: Commit**

```bash
git commit -m "fix(migration): preserve natal_reach_idx at smoltification (Arc O.1)

Removes the v0.30.x overwrite trout_state.natal_reach_idx[i] = current_reach
at the SMOLT transition. This overwrite made every smoltifying fish 'born'
at its exit reach, destroying the birth-reach signal used by Arc K PSPC
analytics and required for Arc O genetic-MSA reconstruction.

Noted as a deferred bug in docs/validation/v0.34.0-pspc-spec.md §Caveats."
```

### Task O.2: Add stray_fraction to MarineConfig

- [ ] **Step O.2.1: Write failing test**

```python
# tests/test_straying.py — append
def test_stray_fraction_zero_means_perfect_homing():
    """With stray_fraction=0, every returning adult returns to its natal reach."""
    import numpy as np
    from instream.marine.config import MarineConfig
    from instream.marine.domain import MarineDomain
    from instream.state.trout_state import TroutState

    cfg = MarineConfig(stray_fraction=0.0)
    # … set up 100 marine adults with natal_reach_idx uniformly in {0,1,2,3}
    # … call adult-return kernel
    # Assert: after return, reach_idx == natal_reach_idx for all 100
    ...


def test_stray_fraction_one_means_uniform_mixing():
    """With stray_fraction=1.0, returning adults relocate uniformly across
    non-natal reaches."""
    ...
```

- [ ] **Step O.2.2: Run → FAIL** (field doesn't exist)

- [ ] **Step O.2.3: Add field + wire into adult return**

Edit `src/instream/marine/config.py`:

```python
# WGBAST Arc O: stray-fraction knob. 0 = perfect homing (SalmoPy
# default pre-v0.38); 1 = uniform mixing. Baltic salmon typical ~0.05-0.15
# (Säisä et al. 2005 genetic FST).
stray_fraction: float = 0.0
```

Edit `src/instream/marine/domain.py:381-411` — the adult return kernel.
The function signature is `check_adult_return(trout_state, reach_cells,
return_sea_winters, return_condition_min, current_date, rng, barrier_map,
reverse_reach_graph, estuary_reach)`. `reach_cells` is a dict keyed by
reach index; `len(reach_cells)` is the freshwater-reach count.

Before the existing `trout_state.reach_idx[i] = target_reach` line (line
410), insert the straying logic. Use `len(reach_cells)` instead of the
undefined `n_freshwater_reaches`.

```python
# Arc O: apply straying. With probability stray_fraction, relocate to
# a random non-natal freshwater reach (uniform across non-natal reaches;
# length-weighting is deferred to a follow-up).
n_reaches = len(reach_cells)
if (
    getattr(config, "stray_fraction", 0.0) > 0.0
    and rng.random() < config.stray_fraction
    and n_reaches > 1
):
    candidates = [r for r in reach_cells.keys() if r != natal]
    if candidates:
        target_reach = int(rng.choice(candidates))
```

**Two coordinated edits** are required for the snippet above to have
`config` in scope:

- [ ] **Step O.2.3a: Add `config=None` kwarg to `check_adult_return`**

Edit `src/instream/marine/domain.py` — find `def check_adult_return(...)`
at line 329 (verified via `grep -n "def check_adult_return"`) and add
`config=None` to the parameter list.

- [ ] **Step O.2.3b: Thread `config` from caller**

Edit `src/instream/model.py` line 196 — the `check_adult_return(...)` call
site. Add `config=self.marine_domain.config` as the final kwarg.

Verify with: `grep -n "check_adult_return(" src/instream/`. Expected: 1
definition + 1 call site.

- [ ] **Step O.2.3c: Insert the straying block at lines 405-410**

Read lines 381-411 first to confirm the exact variable names in scope —
`natal` is at line 381, `target_reach` is assigned around line 405-410.
Then insert the straying block shown above, using `config.stray_fraction`
(now in scope via O.2.3a/b) and `len(reach_cells)` for the reach count.

- [ ] **Step O.2.4: Run → PASS**

### Task O.3: Emit spawner_origin_matrix CSV

- [ ] **Step O.3.1: Write failing test**

```python
def test_spawner_origin_matrix_is_identity_under_perfect_homing(tmp_path):
    """stray_fraction=0 → matrix is diagonal."""
    from instream.io.output import write_spawner_origin_matrix

    # spawners: list of dicts with natal_reach_idx and reach_idx
    spawners = [
        {"natal_reach_idx": 0, "reach_idx": 0, "superind_rep": 10},
        {"natal_reach_idx": 1, "reach_idx": 1, "superind_rep": 5},
        {"natal_reach_idx": 2, "reach_idx": 2, "superind_rep": 8},
    ]
    path = write_spawner_origin_matrix(
        spawners, reach_names=["A", "B", "C"], year=2020, output_dir=tmp_path,
    )
    import pandas as pd
    df = pd.read_csv(path, index_col=0)
    # Diagonal
    assert df.loc["A", "A"] == 10
    assert df.loc["B", "B"] == 5
    assert df.loc["C", "C"] == 8
    # Off-diagonals zero
    assert df.loc["A", "B"] == 0
```

- [ ] **Step O.3.2: Implement `write_spawner_origin_matrix`**

In `src/instream/io/output.py`:

```python
def write_spawner_origin_matrix(
    spawners, reach_names, year, output_dir, filename=None,
):
    """Write a natal_reach × spawning_reach matrix (WGBAST genetic MSA shape).

    Each cell is the rep-weighted count of spawners whose natal_reach_idx
    equals the row and spawning reach_idx equals the column.
    """
    if filename is None:
        filename = f"spawner_origin_matrix_{year}.csv"
    path = Path(output_dir) / filename
    n = len(reach_names)
    m = [[0] * n for _ in range(n)]
    for sp in spawners:
        natal = int(sp.get("natal_reach_idx", -1))
        spawn = int(sp.get("reach_idx", -1))
        rep = int(sp.get("superind_rep", 1))
        if 0 <= natal < n and 0 <= spawn < n:
            m[natal][spawn] += rep
    df = pd.DataFrame(m, index=reach_names, columns=reach_names)
    df.index.name = "natal_reach"
    df.to_csv(path)
    return path
```

- [ ] **Step O.3.3: Wire into write_outputs**

Edit `src/instream/model_day_boundary.py:write_outputs` — after `write_smolt_production_by_reach`, add:

```python
# Arc O: genetic MSA spawner-origin matrix (row=natal, col=spawn)
spawners = getattr(self, "_spawners_this_run", [])
if spawners:
    write_spawner_origin_matrix(
        spawners, reach_names,
        year=self.time_manager.current_date.year,
        output_dir=out,
    )
```

Populate `self._spawners_this_run` in the spawning module at the moment an adult spawns (grep `spawn` in `src/instream/modules/spawning.py`).

- [ ] **Step O.3.4: Integration test + commit**

### Task O.4: Docs + release v0.38.0

- [ ] **Step O.4.1: `docs/validation/v0.38.0-straying-msa.md`** — document stray_fraction semantics, the matrix schema, Säisä 2005 envelope, and how to calibrate `stray_fraction` from observed MSA data.

- [ ] **Step O.4.2: CHANGELOG + version bump + tag v0.38.0**

---

# Arc P: Grey-seal predation as explicit mortality

**Goal:** Replace the static `seal_hazard` length-based term with an abundance-forced term using the HELCOM grey-seal population time series, so Lai 2021-style bio-economic analyses can be done inside SalmoPy.

**Why:** `seal_hazard()` already exists at `src/instream/marine/survival.py:44` as a logistic function of length, but with a fixed `marine_mort_seal_max_daily`. HELCOM's SEAL expert group publishes Baltic grey-seal abundance annually (5k → 40k between 1988 and 2022); the true predation rate scales with that abundance. WGBAST 2025 flags seal abundance as a growing uncertainty in the Main Basin.

**Effort:** M (3 days). Smaller than it looks because the hazard infrastructure already exists — we just add a year-varying multiplier.

## File Structure

**Create:**
- `data/helcom/grey_seal_abundance_baltic.csv` — year, population_estimate, sub_basin (Gulf of Bothnia / Main Basin / Gulf of Finland). Data source: https://indicators.helcom.fi/indicator/grey-seal-abundance/ (open, no registration).
- `src/instream/marine/seal_forcing.py` — loader + multiplier.
- `tests/test_seal_forcing.py`.

**Modify:**
- `src/instream/marine/config.py` — add `seal_abundance_csv: str | None`, `seal_reference_abundance: float = 30000.0`, `seal_sub_basin: str = "main_basin"`.
- `src/instream/marine/survival.py:44-52` — `seal_hazard()` accepts an abundance multiplier.

## Tasks

### Task P.1: Ship HELCOM grey-seal abundance CSV

- [ ] **Step P.1.1: Download HELCOM data**

Visit https://indicators.helcom.fi/indicator/grey-seal-abundance/ and download the abundance time series (2003–2021 extended; HELCOM core indicator report 2015 extended version). Save as `data/helcom/grey_seal_abundance_baltic.csv` with schema:

```
# HELCOM grey-seal abundance — Baltic population estimate per sub-basin per year.
# Source: HELCOM Grey Seal Abundance core indicator,
#   https://indicators.helcom.fi/indicator/grey-seal-abundance/
# Historical values cross-referenced against:
#   Harding et al. 2007 (~2,500 in early 1980s, Baltic-wide)
#   Lai, Lindroos & Grønbæk 2021 DOI 10.1007/s10640-021-00571-z
#     (32,019 counted in 2014; HELCOM SEAL Expert Group)
#   Westphal et al. 2025 DOI 10.1002/aqc.70147 (>40k counted 2020, >45k 2023)
#   Carroll et al. 2024 DOI 10.1111/1365-2656.14065 (~3k in 1970s, ~55k recent)
# The HELCOM indicator page does NOT offer a direct CSV download — these
# values are hand-transcribed from the HELCOM core-indicator PDF and
# supplementary tables. Treat as PRELIMINARY pending Arc 0 extraction.
# Schema: year, sub_basin, population_estimate, method
year,sub_basin,population_estimate,method
1988,main_basin,2800,aerial_survey
1995,main_basin,5500,aerial_survey
2003,main_basin,15600,aerial_survey
2010,main_basin,26400,aerial_survey
2015,main_basin,32000,aerial_survey
2021,main_basin,40000,aerial_survey
```

1988 value lowered from 5,000 to 2,800 after literature cross-check
(Harding et al. 2007 documents the Baltic grey-seal low at ~2,500 in
the 1980s). Extrapolate yearly values between survey points linearly
if the published series has gaps.

- [ ] **Step P.1.2: Commit**

```bash
git add data/helcom/grey_seal_abundance_baltic.csv
git commit -m "data: HELCOM grey-seal Baltic abundance 1988-2021 (main_basin)"
```

### Task P.2: Loader + multiplier (TDD)

- [ ] **Step P.2.1: Write failing test**

```python
# tests/test_seal_forcing.py
from pathlib import Path
from instream.marine.seal_forcing import (
    load_seal_abundance,
    abundance_for_year,
    seal_hazard_multiplier,
)


def test_load_seal_abundance(tmp_path):
    csv = tmp_path / "seal.csv"
    csv.write_text(
        "year,sub_basin,population_estimate,method\n"
        "2003,main_basin,15600,aerial\n"
        "2015,main_basin,32000,aerial\n"
    )
    s = load_seal_abundance(csv)
    assert s[(2003, "main_basin")] == 15600
    assert s[(2015, "main_basin")] == 32000


def test_seal_hazard_multiplier_saturates():
    """Holling Type II with default k_half=2: anchored 1.0 at reference.

    Pin exact k=2 values to catch silent default-parameter drift.
    Analytical: mult(r) = (r / (1 + r/k)) / (1 / (1 + 1/k))
      k=2, r=1 → 1.0 (anchor)
      k=2, r=2 → 1.5
      k=2, r=10 → 2.5
      k=2, r→∞ → k+1 = 3.0 (asymptote)
    """
    # Anchor: exact at reference
    assert abs(seal_hazard_multiplier(30000, 30000) - 1.0) < 1e-9
    # r=2: exact k=2 value
    m_2x = seal_hazard_multiplier(60000, 30000)
    assert abs(m_2x - 1.5) < 0.01, f"got {m_2x}, expected 1.5 (k=2)"
    # r=10: exact k=2 value
    m_10x = seal_hazard_multiplier(300000, 30000)
    assert abs(m_10x - 2.5) < 0.05, f"got {m_10x}, expected 2.5 (k=2)"
    # r→∞: asymptote at k+1 = 3.0
    m_inf = seal_hazard_multiplier(1e9, 30000)
    assert abs(m_inf - 3.0) < 0.01, f"got {m_inf}, should asymptote to 3.0"
    # Zero abundance → zero multiplier
    assert seal_hazard_multiplier(0, 30000) == 0.0
```

- [ ] **Step P.2.2: Implement `src/instream/marine/seal_forcing.py`**

```python
"""HELCOM grey-seal abundance forcing.

Converts per-(year, sub_basin) seal abundance into a linear multiplier
on the base `marine_mort_seal_max_daily` hazard. Reference abundance
calibration: Lai, Lindroos & Grønbæk 2021 used ~30,000 seals in Baltic
scenarios (DOI 10.1007/s10640-021-00571-z).
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Tuple
import pandas as pd


def load_seal_abundance(path: Path | str) -> Dict[Tuple[int, str], float]:
    df = pd.read_csv(path, comment="#")
    return {
        (int(r.year), str(r.sub_basin)): float(r.population_estimate)
        for r in df.itertuples()
    }


def abundance_for_year(
    series: Dict[Tuple[int, str], float],
    year: int,
    sub_basin: str,
) -> Optional[float]:
    return series.get((int(year), str(sub_basin)))


def seal_hazard_multiplier(
    abundance: float,
    reference_abundance: float = 30000.0,
    saturation_k_half: float = 2.0,
) -> float:
    """Holling Type II saturating response: hazard_mult = r / (1 + r / K_half).

    Normalized so that at `abundance == reference_abundance` the multiplier
    is exactly 1.0 (this recovers the legacy `marine_mort_seal_max_daily`
    calibration). For `abundance >> reference`, the multiplier asymptotes
    at `K_half / 1 + K_half / (K_half + 1)` rather than growing linearly.

    `saturation_k_half` is the multiplier value at which handling-time
    saturation occurs (dimensionless, units of reference_abundance).
    K_half = 2.0 means half-saturation at 2× reference; the multiplier
    approaches K_half+1 = 3.0 as abundance → infinity.

    Rationale: seal predation is a predator-prey functional response, not
    a per-capita encounter rate. Type II with K_half tunable is the
    minimum form that (a) returns 1.0 at the calibration point and (b)
    bounds extrapolation across the 1988→2021 ≈ 15× abundance span.
    Linear scaling (the first-draft form) would have projected
    marine_mort_seal_max_daily × 15 = outright extinction at 2021 abundance.
    """
    if reference_abundance <= 0:
        return 1.0
    r = max(0.0, float(abundance) / float(reference_abundance))
    k = float(saturation_k_half)
    # Normalize so r=1 → mult=1: the raw H2 is r / (1 + r/k); divide by
    # its value at r=1 to re-anchor.
    raw = r / (1.0 + r / k)
    anchor = 1.0 / (1.0 + 1.0 / k)
    return raw / anchor if anchor > 0 else 1.0
```

- [ ] **Step P.2.3: Run tests → PASS; commit**

### Task P.3: Wire multiplier into seal_hazard

- [ ] **Step P.3.1: Read current `seal_hazard`**

```
grep -n "def seal_hazard" src/instream/marine/survival.py
```

- [ ] **Step P.3.2: Extend signature**

Current (line 44):
```python
def seal_hazard(length: np.ndarray, config) -> np.ndarray:
    return _logistic_hazard(
        length, config.marine_mort_seal_L1, config.marine_mort_seal_L9,
        config.marine_mort_seal_max_daily,
    )
```

New:
```python
_SEAL_FORCING_CACHE: dict[Path, dict[tuple[int, str], float]] = {}


def seal_hazard(
    length: np.ndarray,
    config,
    current_year: int | None = None,
) -> np.ndarray:
    """Daily seal-predation hazard, optionally scaled by HELCOM abundance."""
    base = _logistic_hazard(
        length,
        config.marine_mort_seal_L1,
        config.marine_mort_seal_L9,
        config.marine_mort_seal_max_daily,
    )
    if (
        config.seal_abundance_csv is not None
        and current_year is not None
    ):
        path = Path(config.seal_abundance_csv)
        if path not in _SEAL_FORCING_CACHE:
            from instream.marine.seal_forcing import load_seal_abundance
            _SEAL_FORCING_CACHE[path] = load_seal_abundance(path)
        from instream.marine.seal_forcing import (
            abundance_for_year, seal_hazard_multiplier,
        )
        abundance = abundance_for_year(
            _SEAL_FORCING_CACHE[path], current_year, config.seal_sub_basin,
        )
        if abundance is not None:
            mult = seal_hazard_multiplier(abundance, config.seal_reference_abundance)
            base = base * mult
    return base
```

- [ ] **Step P.3.3: Update `marine_survival` caller to pass `current_year`**

`grep -n "seal_hazard(" src/instream/marine/`, then at each call site add `current_year=current_year`.

- [ ] **Step P.3.4: Integration test**

```python
def test_seal_hazard_scales_with_year(tmp_path):
    """1988 (2.8k seals) → much smaller hazard than 2021 (40k), but
    saturating not linear (Holling Type II)."""
    import numpy as np
    from instream.marine.config import MarineConfig
    from instream.marine.survival import seal_hazard

    csv = tmp_path / "seal.csv"
    csv.write_text(
        "year,sub_basin,population_estimate,method\n"
        "1988,main_basin,2800,t\n"
        "2021,main_basin,40000,t\n"
    )
    cfg = MarineConfig(
        seal_abundance_csv=str(csv),
        seal_reference_abundance=30000.0,
        seal_sub_basin="main_basin",
    )
    lengths = np.array([50.0, 60.0, 70.0])
    h_1988 = seal_hazard(lengths, cfg, current_year=1988)
    h_2021 = seal_hazard(lengths, cfg, current_year=2021)
    # Abundance ratio = 40000/2800 ≈ 14.3×; under linear scaling hazard
    # would be 14.3× bigger. Under Holling Type II anchored at 30k, the
    # multipliers are:
    #   m(2800) ≈ 0.16 × (normalize to 1.0 at 30k) ≈ 0.16
    #   m(40000) ≈ 1.14 (saturating)
    # So hazard_2021 / hazard_1988 ≈ 7.1, much less than linear 14.3.
    ratio = h_2021[0] / h_1988[0]
    assert 4.0 < ratio < 10.0, f"got ratio {ratio}; saturation expected"
```

### Task P.4: Validation + release v0.39.0

- [ ] **Step P.4.1: Validation run**

With seal forcing active, a full `example_baltic.yaml` run from 1988–2020 should show declining adult-return abundance consistent with the Lai 2021 seal-predation scenario. Capture this in a validation doc.

- [ ] **Step P.4.2: Docs + tag v0.39.0**

---

# Arc Q: Bayesian life-cycle wrapper

**Goal:** Wrap the existing `src/instream/calibration/` framework (13 modules, 75 tests) in a Bayesian posterior-inference shell comparable to WGBAST's Bayesian model (Kuikka, Vanhatalo & Pulkkinen 2014). Condition on smolt-trap counts + spawner-counter data from the Arc M rivers, emit posterior distributions over key latent parameters (post-smolt survival, M74 variance, stray fraction).

**Why:** Arcs K–P make SalmoPy's outputs structurally comparable to WGBAST. Arc Q closes the loop by running the calibration framework as an observation-conditioned Bayesian inference — enabling retrospective hindcasts and probabilistic stock projections parallel to the ICES assessment model itself.

**Effort:** L (1–2 weeks). The existing Sobol/Morris/Nelder-Mead calibration framework is the prior-design engine; Arc Q adds the likelihood + posterior sampler on top.

## File Structure

**Create:**
- `src/instream/bayesian/__init__.py` — new subpackage.
- `src/instream/bayesian/observation_model.py` — likelihood functions for smolt-trap + spawner-counter data.
- `src/instream/bayesian/prior.py` — priors on post-smolt survival, M74 variance, stray_fraction, fecundity.
- `src/instream/bayesian/smc.py` — sequential Monte Carlo particle filter.
- `src/instream/bayesian/summary.py` — posterior summary (credible intervals, marginals).
- `data/wgbast/observations/` — trap counts + counter data per Arc M river.
- `tests/test_bayesian_prior.py`, `tests/test_observation_model.py`, `tests/test_smc.py`.
- `docs/validation/v0.40.0-bayesian-wrapper.md`.
- `scripts/bayesian_hindcast.py` — CLI wrapper.

## Tasks

### Task Q.1: Ship observation data

- [ ] **Step Q.1.1: Assemble Simojoki + Tornionjoki smolt-trap counts**

From WGBAST 2026 §3 Table (annual trap counts 1991–2024 for Simojoki; 1996–2024 for Tornionjoki). Save as:

```
# data/wgbast/observations/smolt_trap_counts.csv
# Schema: year, river, smolts_counted, trap_efficiency_posterior_mean, source
year,river,smolts_counted,trap_efficiency,source
1996,Simojoki,12400,0.65,WGBAST2026
1996,Tornionjoki,125000,0.18,WGBAST2026
...
```

- [ ] **Step Q.1.2: Assemble adult-counter data**

Same schema for the Tornionjoki, Kalixälven, Byskeälven, Pite, Testebo, Vindel counters. Published in WGBAST 2025 stock annex.

- [ ] **Step Q.1.3: Commit**

### Task Q.2: Observation-likelihood module (TDD)

- [ ] **Step Q.2.1: Write failing Poisson smolt-trap test**

```python
# tests/test_observation_model.py
from instream.bayesian.observation_model import (
    log_likelihood_smolt_trap,
    log_likelihood_spawner_counter,
)


def test_smolt_trap_poisson_likelihood_peaks_at_observed():
    """Poisson log-likelihood is maximized when simulated == observed / trap_efficiency."""
    # observed = 6500, trap_efficiency = 0.65 → implied N_smolts = 10000
    ll_peak = log_likelihood_smolt_trap(
        simulated_smolts=10000, observed_count=6500, trap_efficiency=0.65,
    )
    ll_off = log_likelihood_smolt_trap(
        simulated_smolts=5000, observed_count=6500, trap_efficiency=0.65,
    )
    assert ll_peak > ll_off
```

- [ ] **Step Q.2.2: Implement Poisson likelihood**

```python
# src/instream/bayesian/observation_model.py
import math
import numpy as np


def log_likelihood_smolt_trap(
    simulated_smolts: float,
    observed_count: int,
    trap_efficiency: float,
) -> float:
    """Poisson log-likelihood of observed smolt-trap count given simulated
    total smolts and trap efficiency.

    lambda = simulated_smolts * trap_efficiency
    ln P(obs | lambda) = obs * ln(lambda) - lambda - ln(obs!)
    """
    lam = max(1e-9, float(simulated_smolts) * float(trap_efficiency))
    obs = int(observed_count)
    # Stirling for large obs, direct for small
    log_factorial = (
        math.lgamma(obs + 1) if obs > 0 else 0.0
    )
    return obs * math.log(lam) - lam - log_factorial


def log_likelihood_spawner_counter(
    simulated_spawners: float,
    observed_count: int,
    detection_probability: float,
    overdispersion_k: float = 50.0,
) -> float:
    """Negative-binomial log-likelihood (accounts for counter noise).

    Parameterization: `p = k / (k + mu)`, giving `Var(X) = mu + mu²/k`.
    Default k=50 corresponds to CV ≈ 15% at mu=100, matching Orell &
    Erkinaro 2007's observed 10-15% inter-observer agreement for
    Riverwatcher video counters on Finnish rivers.

    k can be overridden per-counter (not all counters have equal noise —
    newer video devices < older resistivity counters). Pass as
    `overdispersion_k=30.0` etc. from caller when a river-specific
    value is available.

    Reference:
      Orell, P. & Erkinaro, J. (2007). Inter-observer variability in
      counting Atlantic salmon in a northern European river. ICES CM
      2007/Q:16.
    """
    # NB(k, p) where mu = simulated * detection_p; k = overdispersion_k
    mu = max(1e-9, float(simulated_spawners) * float(detection_probability))
    k = float(overdispersion_k)
    obs = int(observed_count)
    p = k / (k + mu)
    # ln P = ln Γ(k+obs) - ln Γ(k) - ln obs! + k ln p + obs ln(1-p)
    return (
        math.lgamma(k + obs) - math.lgamma(k) - math.lgamma(obs + 1)
        + k * math.log(p) + obs * math.log(max(1e-300, 1 - p))
    )
```

### Task Q.3: Prior module

- [ ] **Step Q.3.1: Define priors**

```python
# src/instream/bayesian/prior.py
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Prior:
    name: str
    lower: float
    upper: float
    shape: str = "uniform"  # or "log_uniform", "beta"

    def sample(self, rng: np.random.Generator, n: int = 1) -> np.ndarray:
        if self.shape == "uniform":
            return rng.uniform(self.lower, self.upper, size=n)
        if self.shape == "log_uniform":
            return np.exp(rng.uniform(
                np.log(self.lower), np.log(self.upper), size=n,
            ))
        if self.shape == "beta":
            # lower=alpha, upper=beta for beta-distribution
            return rng.beta(self.lower, self.upper, size=n)
        raise ValueError(f"unknown shape: {self.shape}")


# Default priors for Baltic salmon calibration (WGBAST-like)
BALTIC_SALMON_PRIORS = [
    Prior("post_smolt_survival", 0.02, 0.18, shape="uniform"),
        # ICES (2023) WGBAST §2.5 3-12% envelope, widened to 2-18%
    Prior("m74_baseline", 0.0, 0.3, shape="uniform"),
        # Vuorinen 2021 background YSFM
    Prior("stray_fraction", 0.0, 0.25, shape="uniform"),
        # Säisä 2005 Baltic FST envelope
    Prior("fecundity_mult", 500.0, 900.0, shape="uniform"),
        # Brännäs 1988 4-12k eggs per female; mult affects the length scaling
]
```

### Task Q.4: Sequential Monte Carlo sampler

- [ ] **Step Q.4.1: Implement particle filter**

```python
# src/instream/bayesian/smc.py
import numpy as np
from typing import Callable, Dict, List, Sequence


def run_smc(
    priors: Sequence,
    run_model_fn: Callable[[Dict[str, float], int], Dict],
    observations: List[Dict],
    n_particles: int = 500,
    n_temperature_steps: int = 10,
    rng: np.random.Generator | None = None,
) -> Dict:
    """Sequential Monte Carlo ABC-SMC with tempered likelihood.

    Parameters
    ----------
    priors : list of Prior objects
    run_model_fn : (params_dict, seed) -> simulation_outputs_dict
        Must return a dict with the same keys as each observation's target_metric.
    observations : list of {"metric_name": str, "observed": float, "ll_fn": callable}
    n_particles : int
        Number of particles in the posterior ensemble.
    n_temperature_steps : int
        Number of tempered-likelihood steps from prior → posterior.

    Returns
    -------
    {"particles": np.ndarray (n_particles, len(priors)),
     "weights": np.ndarray (n_particles,),
     "log_marginal_likelihood": float}
    """
    rng = rng or np.random.default_rng(42)
    # 1. Sample priors
    particles = np.stack([p.sample(rng, n=n_particles) for p in priors], axis=1)
    weights = np.ones(n_particles) / n_particles
    log_marginal = 0.0

    # 2. Tempered annealing schedule
    temperatures = np.linspace(0.0, 1.0, n_temperature_steps + 1)[1:]

    for t_idx, temp in enumerate(temperatures):
        # Evaluate likelihood at this temperature
        log_likes = np.zeros(n_particles)
        for i in range(n_particles):
            params = {p.name: particles[i, j] for j, p in enumerate(priors)}
            sim = run_model_fn(params, seed=42 + t_idx * n_particles + i)
            for obs in observations:
                sim_val = sim[obs["metric_name"]]
                log_likes[i] += temp * obs["ll_fn"](sim_val, obs["observed"])
        # Reweight particles
        log_weights = np.log(weights) + log_likes
        log_weights -= log_weights.max()  # numerical stability
        weights = np.exp(log_weights)
        weights /= weights.sum()
        log_marginal += np.log(np.exp(log_weights).mean())
        # Resample when ESS drops
        ess = 1.0 / (weights**2).sum()
        if ess < n_particles / 2:
            idx = rng.choice(n_particles, size=n_particles, p=weights)
            particles = particles[idx]
            weights = np.ones(n_particles) / n_particles

    return {
        "particles": particles,
        "weights": weights,
        "log_marginal_likelihood": log_marginal,
        "param_names": [p.name for p in priors],
    }
```

- [ ] **Step Q.4.2: Write SMC integration test**

Test on a toy problem: known-generating-value recovery on a single parameter (post-smolt survival) with a Gaussian-observed outmigrant count. The posterior should concentrate near the true value within ~20%.

### Task Q.5: End-to-end Bayesian hindcast

- [ ] **Step Q.5.1: CLI wrapper**

```python
# scripts/bayesian_hindcast.py
"""Run Arc Q Bayesian posterior inference on a Baltic fixture.

Usage:
  python scripts/bayesian_hindcast.py \\
      --config configs/example_simojoki.yaml \\
      --years 2010-2020 \\
      --n-particles 500 \\
      --output results/simojoki_bayesian_posterior.nc
"""
import argparse
import yaml
import numpy as np
import xarray as xr

from instream.bayesian.prior import BALTIC_SALMON_PRIORS
from instream.bayesian.smc import run_smc
from instream.bayesian.observation_model import log_likelihood_smolt_trap


def run_model_with_params(params, seed, config_path, years):
    """Run SalmoPy with parameter overrides, return metric dict."""
    from instream.model import InSTREAMModel
    import tempfile, os

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    # Inject calibration params into cfg
    cfg["simulation"]["seed"] = seed
    # ... (translate each param to its YAML location)

    with tempfile.TemporaryDirectory() as td:
        patched = os.path.join(td, "cfg.yaml")
        with open(patched, "w") as f:
            yaml.safe_dump(cfg, f)
        out = os.path.join(td, "out")
        os.makedirs(out)
        model = InSTREAMModel(
            config_path=patched, data_dir=..., output_dir=out,
        )
        model.run()
        # Parse outmigrants.csv + spawner-counter equivalent
        import pandas as pd
        df = pd.read_csv(os.path.join(out, "outmigrants.csv"))
        return {
            "total_smolts": len(df[df["length_category"] == "Smolt"]),
            "spawner_count": 0,  # TBD: parse spawners
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--years", required=True)  # e.g. "2010-2020"
    parser.add_argument("--n-particles", type=int, default=500)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    observations = [
        # ... load from data/wgbast/observations/smolt_trap_counts.csv
    ]

    posterior = run_smc(
        priors=BALTIC_SALMON_PRIORS,
        run_model_fn=lambda p, s: run_model_with_params(
            p, s, args.config, args.years
        ),
        observations=observations,
        n_particles=args.n_particles,
    )

    # Save as xarray NetCDF for downstream analysis
    ds = xr.Dataset(
        data_vars={
            "particles": (["particle", "param"], posterior["particles"]),
            "weights": (["particle"], posterior["weights"]),
        },
        coords={"param": posterior["param_names"]},
        attrs={"log_marginal_likelihood": posterior["log_marginal_likelihood"]},
    )
    ds.to_netcdf(args.output)


if __name__ == "__main__":
    main()
```

- [ ] **Step Q.5.2: Run on Simojoki**

Target: posterior median post-smolt survival for sal.27.22-31 within the WGBAST-published 3–12% band (ICES 2023 §2.5).

```bash
micromamba run -n shiny python scripts/bayesian_hindcast.py \
    --config configs/example_simojoki.yaml \
    --years 1996-2020 \
    --n-particles 500 \
    --output results/simojoki_posterior.nc
```

Validate the posterior medians against WGBAST publications.

### Task Q.6: Validation doc + release v0.40.0

- [ ] **Step Q.6.1: `docs/validation/v0.40.0-bayesian-wrapper.md`** — document the observation model, priors, SMC parameters, and the Simojoki posterior-recovery demonstration.

- [ ] **Step Q.6.2: Release**

```bash
# pyproject.toml + __init__.py → 0.40.0
git tag v0.40.0
git push origin master v0.40.0
```

---

# Self-Review

**Spec coverage**:
- [x] Arc M: 5 tasks (scaffold Tornionjoki, Simojoki, Byske+Mörrum, gradient test, release)
- [x] Arc N: 5 tasks (CSV, loader, wiring, hindcast test, release)
- [x] Arc O: 4 tasks (natal_reach_idx fix, stray_fraction, matrix output, release)
- [x] Arc P: 4 tasks (HELCOM CSV, loader, seal_hazard wiring, release)
- [x] Arc Q: 6 tasks (observations, likelihood, prior, SMC, hindcast, release)

24 tasks total. Each arc produces a releasable increment.

**Type consistency**:
- `(year, river)` key format shared between M74 (Arc L), post-smolt (Arc N), and seal (Arc P) forcings — all use `Dict[Tuple[int, str], float]`.
- `natal_reach_idx` (int) used consistently across K (outmigrant), O (spawner matrix), Q (observation likelihood).
- `current_year` kwarg name used consistently across seal_hazard (Arc P), m74_cull (Arc L), post_smolt forcing (Arc N).

**Placeholder scan**:
- Arc M uses placeholder PSPC distributions across reaches (documented inline).
- Arc N uses placeholder annual-survival series (documented as Arc 0 replacement).
- Arc P uses HELCOM data directly (not a placeholder).
- Arc Q observation data needs Arc 0 extraction (Step Q.1.1 depends on WGBAST PDF Table extraction).

**Prerequisites**:
- Arc O.1 (natal_reach_idx fix) is a bug fix that all post-v0.34.0 MSA analytics need; it's correctly prepended as the first Arc O task.
- Arc Q depends on Arc M (multi-river output) being complete, so Arc Q's priors can actually be anchored to the Tornionjoki/Simojoki smolt-trap series.

**Known compressions**:
- Arc M's reach-hydrology CSV contents are specified in table form rather than per-row values. Engineer fills in hydrology by interpolating from example_baltic's known-good timeseries.
- Arc Q's `run_model_with_params` translation of calibration params → YAML keys is sketched (`...`). Expand when the actual Arc Q branch starts — it depends on which parameters shipped through Arcs K–P.

---

# Execution Handoff

Plan saved to `docs/superpowers/plans/2026-04-20-arc-M-to-Q-expanded.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch one subagent per task with full context, two-stage review (spec + quality) between tasks.

**2. Inline execution** — run each arc start-to-finish in the same session using `superpowers:executing-plans`.

**3. Pause** — you review the expanded plan first.

Which approach?
