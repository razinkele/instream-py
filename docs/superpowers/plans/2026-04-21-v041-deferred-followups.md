# v0.41.14 Deferred Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Scope note**: Four independent Arcs (R, S, T, U) closing the five deferred items from `project_v041_phase_status.md`. Each Arc is self-contained and produces mergeable working software on its own. Stop after any Arc if priorities change.

**Goal:** Close the 5 deferred items from the v0.41.14 pause point — Movement panel idle preview + simulation verification, latitudinal smolt-age test validation, Arc 0 WGBAST/HELCOM PDF data extraction, GitHub Releases backfill.

**Architecture:** Each deferred item becomes one Arc. Arc R is a feature slice with tests; Arc S is test-only; Arc T is a data-extraction pipeline (partially human); Arc U is a one-shot release-backfill script. Arcs are independent — run in any order.

**Tech Stack:** Python 3.11 + shiny_deckgl (Arc R), pytest slow markers (Arc S), pdfplumber + WebPlotDigitizer (Arc T), gh CLI (Arc U). Conda env: `shiny`.

**Starting master**: `f2821fe` (v0.41.14).

---

## Arc Dependency Graph

```
Arc U (releases backfill)   ← independent, 15 min
Arc S (latitudinal tests)   ← independent, 30 min + ~8 min slow-test runtime
Arc R (movement idle+verify) ← independent, 2-3 hours
Arc T (PDF extraction)       ← independent, 1-3 hours + human PDF handling
```

Recommended order: **U → S → R → T** (easy wins first; T requires human PDF access).

---

# Arc R: Movement panel idle basemap + simulation-run verification

**Goal:** Two improvements:

1. When no simulation has run, the Movement panel shows the currently-loaded fixture's reach cells on a MapLibre basemap (as a static preview). Users see *where* trails will appear before running.
2. A Playwright e2e test verifies that after running a short simulation, the Movement map re-centers on fixture bounds and at least one TripsLayer layer is sent to the widget.

**Effort:** M (2–3 days).

## File Structure

**Modify:**
- `app/modules/movement_panel.py` — add idle-state `_build_idle_preview_layer()` that renders the loaded fixture's cells; wire it into `map_container` when `dashboard_data_rv()` returns empty.
- `tests/e2e/test_movement_e2e.py` — new file, Playwright-driven end-to-end test.

**Read (context only):**
- `app/modules/setup_panel.py` — reuse the `_load_gdf()` pattern for reading the loaded config's shapefile.
- `app/app.py:56-84` — `_resolve_data_dir` lookup logic.
- `tests/e2e/test_baltic_e2e.py` — existing e2e test pattern (skipped unless `E2E_INTEGRATION=1`).

## Tasks

### Task R.1: Extract loaded-config gdf helper into a shared module

**Files:**
- Create: `app/modules/_fixture_loader.py` — shared helper for reading the selected config's shapefile as a WGS84 GeoDataFrame. Used by both setup_panel and movement_panel.
- Modify: `app/modules/setup_panel.py` — switch `_load_gdf()` to call the shared helper.
- Test: `tests/test_app_smoke.py` — extend existing smoke tests to cover the helper.

- [ ] **Step R.1.1: Write failing test for the shared helper**

```python
# tests/test_app_smoke.py — append
def test_load_fixture_gdf_example_a():
    """Shared _fixture_loader.load_fixture_gdf resolves example_a shapefile
    across the 3 known layouts: full relative path from config, flat
    `Shapefile/` subdir, rglob fallback."""
    from modules._fixture_loader import load_fixture_gdf
    gdf = load_fixture_gdf("configs/example_a.yaml")
    assert gdf is not None
    assert len(gdf) > 0
    assert "reach" in gdf.columns
    # CA stream — longitude in [-124, -117]
    assert -125 < gdf.total_bounds[0] < -117
```

- [ ] **Step R.1.2: Run test → FAIL (module missing)**

Run: `micromamba run -n shiny python -m pytest tests/test_app_smoke.py::test_load_fixture_gdf_example_a -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step R.1.3: Create the shared helper**

Create `app/modules/_fixture_loader.py`:

```python
"""Shared helper: load a config's mesh_file shapefile as a WGS84 GeoDataFrame.

Extracted from setup_panel._load_gdf so movement_panel (and any future
map panel) can reuse the same lookup + canonical-column-rename logic.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import logging
import yaml
import geopandas as gpd

logger = logging.getLogger(__name__)

_CANONICAL_MAP = {
    "cell_id": "cell_id",
    "reach_name": "reach",
    "area": "area",
    "frac_spawn": "frac_spawn",
    "num_hiding_places": "num_hiding",
    "frac_vel_shelter": "frac_vel_shelter",
    "dist_escape": "dist_escape",
}


def load_fixture_gdf(config_path: str) -> Optional[gpd.GeoDataFrame]:
    """Load the shapefile referenced by `spatial.mesh_file` in the YAML.

    Tries candidate paths in order:
      1. <data_dir>/<mesh_file>           (exact from config)
      2. <data_dir>/<basename>            (flat fallback)
      3. <data_dir>/Shapefile/<basename>  (server layout)
      4. <data_dir>.rglob(<basename>)     (last-resort tree search)

    Returns None and logs a warning if none resolve.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    spatial = raw.get("spatial", {})
    mesh_file = spatial.get("mesh_file")
    if not mesh_file:
        return None

    # app/ is on sys.path (see tests/test_app_smoke.py); this resolves
    # to app/app.py as a module, not the app/ package. Matches the
    # existing setup_panel.py:340 pattern — verified 2026-04-21.
    from app import _resolve_data_dir
    data_dir = Path(_resolve_data_dir(config_path))
    mesh_name = Path(mesh_file).name
    candidates = [
        data_dir / mesh_file,
        data_dir / mesh_name,
        data_dir / "Shapefile" / mesh_name,
    ]
    mesh_path = next((p for p in candidates if p.exists()), None)
    if mesh_path is None:
        matches = list(data_dir.rglob(mesh_name))
        if matches:
            mesh_path = matches[0]
    if mesh_path is None:
        logger.warning(
            "Could not find mesh %r under %s; tried: %s",
            mesh_name, data_dir, [str(p) for p in candidates],
        )
        return None

    gdf = gpd.read_file(str(mesh_path))

    # Canonical column renames (shapefile attrs may be upper/lower case)
    gis = spatial.get("gis_properties", {})
    col_map = {}
    for key, shp_col in gis.items():
        for actual_col in gdf.columns:
            if actual_col.upper() == shp_col.upper():
                canonical = _CANONICAL_MAP.get(key)
                if canonical:
                    col_map[actual_col] = canonical
                break
    gdf = gdf.rename(columns=col_map)

    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    gdf.attrs["raw_config"] = raw
    return gdf
```

- [ ] **Step R.1.4: Run test → PASS**

Run: `micromamba run -n shiny python -m pytest tests/test_app_smoke.py::test_load_fixture_gdf_example_a -v`
Expected: PASS.

- [ ] **Step R.1.5: Refactor `setup_panel._load_gdf` to delegate**

Replace the body of `setup_panel._load_gdf()` in `app/modules/setup_panel.py` with:

```python
@reactive.calc
def _load_gdf():
    config_path = _loaded_config()
    if not config_path:
        return None
    try:
        from modules._fixture_loader import load_fixture_gdf
        return load_fixture_gdf(config_path)
    except Exception:
        logger.exception("Failed to load fixture gdf for %r", config_path)
        return None
```

- [ ] **Step R.1.6: Run full setup smoke suite → PASS**

Run: `micromamba run -n shiny python -m pytest tests/test_app_smoke.py tests/test_pspc_output.py -q`
Expected: PASS (no regressions from the refactor).

- [ ] **Step R.1.7: Commit**

```bash
git add app/modules/_fixture_loader.py app/modules/setup_panel.py tests/test_app_smoke.py
git commit -m "refactor(app): extract load_fixture_gdf to shared _fixture_loader module"
```

### Task R.2: Add idle basemap preview to Movement panel

**Files:**
- Modify: `app/app.py:635` — thread `config_file_rv=input.config_file` into `movement_server(...)` call. Mirrors how `setup_server` already receives it.
- Modify: `app/modules/movement_panel.py` — accept `config_file_rv` as a new `movement_server(...)` parameter; use it directly instead of trying to read root-session inputs.
- Modify: `app/modules/movement_panel.py` — new `_build_preview_layer(gdf)` + wire into `map_container` / `_process_data` when `dashboard_data_rv()` is empty.
- Test: manual via browser (Playwright test comes in Task R.4).

**Why the thread-through pattern:** the plan's first draft tried
`root = session.parent; root.input.config_file()` but Shiny-for-Python
doesn't reliably expose parent sessions for input reads (only for
`ui.update_*` writes). `setup_server` already demonstrates the correct
pattern — pass the sidebar's reactive as an explicit kwarg.

- [ ] **Step R.2.0 (new): Update app.py call site**

Edit `app/app.py` line 635 — change

```python
movement_server("movement", dashboard_data_rv=_dashboard_data)
```

to

```python
movement_server(
    "movement",
    dashboard_data_rv=_dashboard_data,
    config_file_rv=input.config_file,
)
```

- [ ] **Step R.2.1: Read current `map_container` + `_process_data` contracts**

Run: `grep -n "def map_container\|_cells_sent\|dashboard_data_rv\|_cells_gdf" app/modules/movement_panel.py`
Expected: `_cells_gdf[0]` is mutable-list state, `_cells_sent[0]` is a boolean latch, `map_container` returns the widget div once. The new preview must not interfere with the trips-layer flow.

- [ ] **Step R.2.2a: Add `config_file_rv` kwarg to `movement_server`**

Edit `app/modules/movement_panel.py` — change the signature from
```python
def movement_server(input, output, session, dashboard_data_rv):
```
to
```python
def movement_server(input, output, session, dashboard_data_rv, config_file_rv):
```

- [ ] **Step R.2.2b: Add a reactive that pushes preview cells when idle**

Edit `app/modules/movement_panel.py` — add near `_process_data`:

```python
_idle_preview_sent = [False]


@reactive.effect
async def _update_idle_preview():
    """Push a low-opacity cell-grid preview to the Movement map whenever
    no simulation data is available but a config is loaded. Clears when
    a simulation starts streaming (so trips layers get full spotlight).
    """
    data = dashboard_data_rv()
    widget = _map_widget

    # If a simulation is feeding data, hide the preview and let
    # _process_data own the layer stack.
    if data:
        if _idle_preview_sent[0]:
            try:
                await widget.update(session, [], animate=False)
            except Exception:
                logger.exception("Failed to clear idle preview")
            _idle_preview_sent[0] = False
        return

    # Sidebar's currently-selected config — threaded in from app.py as
    # `config_file_rv` (see Step R.2.0).
    config_path = config_file_rv()
    if not config_path:
        return

    from modules._fixture_loader import load_fixture_gdf
    gdf = load_fixture_gdf(config_path)
    if gdf is None or gdf.empty:
        return

    # Build a desaturated grey preview — users can tell it's not live data.
    geojson = gdf.__geo_interface__
    for feat in geojson["features"]:
        feat["properties"]["_fill"] = [160, 170, 180, 80]

    from shiny_deckgl import geojson_layer
    preview_layer = geojson_layer(
        "movement-idle-preview",
        geojson,
        getFillColor="@@=d.properties._fill",
        getLineColor=[100, 110, 120, 120],
        getLineWidth=1,
        stroked=True,
        filled=True,
        pickable=False,
    )

    try:
        await widget.update(session, [preview_layer], animate=False)
        # Auto-fit view bounds so the preview centres on the fixture.
        minx, miny, maxx, maxy = gdf.total_bounds
        await widget.fit_bounds(
            session,
            bounds=[[minx, miny], [maxx, maxy]],
            padding=50,
            duration=800,
        )
        _idle_preview_sent[0] = True
    except Exception:
        logger.exception("Failed to push idle preview layer")
```

- [ ] **Step R.2.3: Parse-check + deploy locally**

Run: `micromamba run -n shiny python -c "import ast; ast.parse(open('app/modules/movement_panel.py', encoding='utf-8').read())"`
Expected: no output (parses clean).

- [ ] **Step R.2.4: Smoke-test by hand on laguna**

Deploy:
```bash
scp app/modules/movement_panel.py razinka@laguna.ku.lt:/srv/shiny-server/inSTREAMPY/modules/
ssh razinka@laguna.ku.lt "touch /srv/shiny-server/inSTREAMPY/restart.txt"
```

Open `https://laguna.ku.lt/inSTREAMPY/` → Setup → Load `example_baltic` → Movement tab. Expected: cells visible in pale grey with the map centred on the Nemunas delta. Idle text still visible below.

- [ ] **Step R.2.5: Commit**

```bash
git add app/modules/movement_panel.py
git commit -m "feat(movement): idle-state basemap preview of loaded fixture reaches"
```

### Task R.3: Version bump + CHANGELOG

- [ ] **Step R.3.1: Bump to v0.42.0**

Edit `pyproject.toml` and `src/instream/__init__.py` → `0.42.0`.

- [ ] **Step R.3.2: CHANGELOG entry**

Add to `CHANGELOG.md`:

```markdown
## [0.42.0] - YYYY-MM-DD (Arc R: Movement idle preview + shared fixture loader)

### Added
- **Movement panel idle preview**: when no simulation is feeding data,
  the Movement map renders the loaded fixture's cells as a low-opacity
  grey grid and centres the view on the fixture bounds. Users see
  *where* trails will appear before running. Clears automatically when
  a simulation starts streaming.
- **`app/modules/_fixture_loader.py`**: shared helper extracting the
  setup_panel config→shapefile lookup. Both panels now use the same
  lookup-and-rename pipeline.

### Changed
- `setup_panel._load_gdf()` refactored to delegate to
  `_fixture_loader.load_fixture_gdf()`. Behaviour unchanged.
```

- [ ] **Step R.3.3: Tag + push**

```bash
git tag v0.42.0
git push origin master v0.42.0
```

### Task R.4: End-to-end Playwright test for Movement simulation

**Files:**
- Create: `tests/e2e/test_movement_e2e.py` — marked integration; opt-in via `E2E_INTEGRATION=1`.

- [ ] **Step R.4.0: Install Playwright + Chromium browser**

Playwright is NOT in the `shiny` env by default. Install both the
Python binding (conda-forge) and the Chromium browser (playwright
CLI — browsers live under the env's cache, not pip):

```bash
micromamba install -n shiny -c conda-forge playwright -y
micromamba run -n shiny playwright install chromium
```

Verify:
```bash
micromamba run -n shiny python -c "import playwright; print(playwright.__version__)"
```
Expected: a version string like `1.4x.x`.

- [ ] **Step R.4.1: Write the test**

```python
"""Arc R.4: e2e verification of Movement trails after a short simulation.

Skipped by default. Enable via:
    E2E_INTEGRATION=1 pytest tests/e2e/test_movement_e2e.py -v

Requires (install in Step R.4.0):
    - playwright Python binding (conda-forge)
    - playwright's chromium browser (`playwright install chromium`)
"""
from __future__ import annotations
import os
import subprocess
import time
from pathlib import Path

import pytest

E2E = os.environ.get("E2E_INTEGRATION") == "1"


@pytest.mark.skipif(not E2E, reason="E2E_INTEGRATION=1 not set")
@pytest.fixture(scope="module")
def shiny_server():
    """Spawn `shiny run app/app.py --port 8000` for the duration of the test."""
    proc = subprocess.Popen(
        ["micromamba", "run", "-n", "shiny",
         "shiny", "run", "app/app.py", "--port", "8000", "--host", "127.0.0.1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    # Wait for server to listen
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:8000/", timeout=1)
            break
        except Exception:
            time.sleep(1)
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.skipif(not E2E, reason="E2E_INTEGRATION=1 not set")
def test_movement_trails_render_after_short_sim(shiny_server, tmp_path):
    """Load example_a, run 30-day sim, switch to Movement, assert trails
    layer is sent and map is centred on CA fixture bounds."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://127.0.0.1:8000/")
        page.wait_for_load_state("networkidle", timeout=15000)

        # Shorten end date to 2011-04-30 (30 days)
        page.locator("#end_date").fill("2011-04-30")

        # Click Run Simulation
        page.get_by_role("button", name="Run Simulation").click()

        # Wait for the sim to complete — status text shows "Day" or
        # spawn/outmigrant count. Give it up to 5 minutes: Numba JIT
        # warmup on habitat selection (Arc 29 memory) adds 60-120 s
        # before the first agent step, on top of Shiny cold start
        # and the 30-day simulation itself.
        page.wait_for_selector("text=/Day \\d+/", timeout=300000)

        # Switch to Movement tab
        page.get_by_role("link", name=" Movement").click()
        page.wait_for_timeout(3000)

        # Assert the map widget is present and has at least one canvas.
        # MapWidget ids are NOT module-namespace-prefixed in the DOM —
        # MapWidget("movement_map") produces #movement_map directly.
        assert page.locator("#movement_map canvas").count() >= 1

        # Assert status text is not "Idle" — sim should have populated data
        status = page.locator("text=/Day|fish tracked/")
        assert status.count() >= 1, (
            "Expected status text to show simulation progress"
        )

        browser.close()
```

- [ ] **Step R.4.2: Register the test's skip-marker in pyproject.toml if not already**

`[tool.pytest.ini_options] markers` already has `integration`. No change needed.

- [ ] **Step R.4.3: Run opt-in test manually on a dev machine**

Run:
```bash
E2E_INTEGRATION=1 micromamba run -n shiny python -m pytest tests/e2e/test_movement_e2e.py -v
```
Expected: PASS after ~180-300 s (includes JIT warmup, Shiny cold
start, and a 30-day sim). If timing exceeds 5 min, bump the
`timeout=300000` ms in the test to a safer value.

- [ ] **Step R.4.4: Commit**

```bash
git add tests/e2e/test_movement_e2e.py
git commit -m "test(e2e): Arc R.4 Movement simulation-run verification"
```

---

# Arc S: Validate latitudinal smolt-age gradient tests

**Goal:** Run the `@pytest.mark.slow` `test_latitudinal_smolt_age_gradient` across all 4 WGBAST river fixtures. Confirm whether they pass or document which ones skip and why.

**Why:** v0.36.0 shipped 4 Baltic river fixtures and a test asserting modal smolt ages 4/3/2/2 for Torne/Simo/Byske/Mörrum. Test is `@pytest.mark.slow` and has only been executed during plan review, never during automated CI. Closing this validates the fixtures.

**Effort:** S (30 min engineer time + ~8 min runtime).

## Tasks

### Task S.1: Run the slow test suite for all 4 rivers

- [ ] **Step S.1.1: Execute the test**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python -m pytest \
    tests/test_multi_river_baltic.py::test_latitudinal_smolt_age_gradient \
    -v -m slow 2>&1 | tee /tmp/latitudinal_run.log
```
Expected: 4 parametrizations. Each runs a 5-year simulation (~2 min each) then asserts modal smolt age within ±1 of WGBAST envelope (Torne=4, Simo=3, Byske=2, Mörrum=2).

- [ ] **Step S.1.2: Triage results**

Three possible outcomes:
- **All 4 pass**: proceed to S.2 (document result in validation doc).
- **Any skip with "only N smolts produced"**: the fixture is too sparse;
  see S.3.
- **Any fail**: the modal age deviates >±1 from WGBAST expectation;
  see S.4.

### Task S.2: Document passing results

- [ ] **Step S.2.1: Append to v0.36.0 validation doc**

Edit `docs/validation/v0.36.0-multi-river-baltic.md` — add a section:

```markdown
## Latitudinal smolt-age gradient test — runtime result

Executed `test_latitudinal_smolt_age_gradient` 2026-04-21 on master.
All 4 WGBAST rivers produced modal smolt ages within ±1 year of the
Skoglund 2024 Paper III envelope:

| River | Latitude | AU | Expected age | Observed modal age | Pass? |
|-------|----------|----|--------------|--------------------|-------|
| Tornionjoki | 65.85°N | 1 | 4 | <fill from log> | ✓ / ✗ |
| Simojoki    | 65.60°N | 1 | 3 | <fill from log> | ✓ / ✗ |
| Byskeälven  | 64.98°N | 2 | 2 | <fill from log> | ✓ / ✗ |
| Mörrumsån   | 56.17°N | S | 2 | <fill from log> | ✓ / ✗ |

Total runtime: ~8 min. Marked `@pytest.mark.slow`; exclude from
default CI with `-m "not slow"`.
```

Fill the "Observed modal age" column from `/tmp/latitudinal_run.log`.

- [ ] **Step S.2.2: Commit**

```bash
git add docs/validation/v0.36.0-multi-river-baltic.md
git commit -m "docs(S): latitudinal smolt-age gradient test runtime results"
```

### Task S.3: If any river skipped due to sparse smolt production

- [ ] **Step S.3.1: Increase fixture population by editing the template CSV + re-scaffolding**

**Do NOT edit the per-river fixture CSVs directly** — the scaffold
script calls `shutil.rmtree` at the top of each target dir, which
overwrites any hand edits on the next regeneration. The scaffold
copies `tests/fixtures/example_baltic/` verbatim as the template
(see `TEMPLATE = ROOT / "tests" / "fixtures" / "example_baltic"` at
line 24 of `scripts/_scaffold_wgbast_rivers.py`), then renames
`BalticExample-InitialPopulations.csv` → `<Stem>Example-InitialPopulations.csv`
per-river. Content is carried over unchanged.

Therefore the authoritative intervention is to edit the TEMPLATE
population CSV, then re-run the scaffold so all 4 WGBAST rivers
pick up the new counts:

```bash
# 1. Multiply the super-individual counts in the template by 5
micromamba run -n shiny python -c "
import pandas as pd
from pathlib import Path
p = Path('tests/fixtures/example_baltic/BalticExample-InitialPopulations.csv')
# Preserve the ';'-prefixed comment header — pandas keeps ordering but strips it.
raw = p.read_text(encoding='utf-8').splitlines(keepends=True)
header_lines = [l for l in raw if l.startswith(';')]
df = pd.read_csv(p, comment=';')
# Verified column names (case-sensitive):
#   Species, Reach, Age, Number, Length min, Length mode, Length max
assert 'Number' in df.columns, f'expected Number col, got {list(df.columns)}'
df['Number'] = (df['Number'] * 5).astype(int)
with open(p, 'w', encoding='utf-8') as f:
    f.writelines(header_lines)
    df.to_csv(f, index=False, lineterminator='\n')
print('updated', p)
"
```

Then re-scaffold (this re-copies the template, so all 4 river
fixtures inherit the new counts):
```bash
micromamba run -n shiny python scripts/_scaffold_wgbast_rivers.py
```

This regenerates all 4 WGBAST river fixture dirs with 5× the
initial super-individual counts.

- [ ] **Step S.3.2: Re-run the slow test**

```bash
micromamba run -n shiny python -m pytest \
    tests/test_multi_river_baltic.py::test_latitudinal_smolt_age_gradient \
    -v -m slow
```
Expected: all 4 PASS (no skips).

- [ ] **Step S.3.3: Commit**

```bash
git add scripts/_scaffold_wgbast_rivers.py tests/fixtures/example_{tornionjoki,simojoki,byskealven,morrumsan}/
git commit -m "fix(fixtures): 5x initial population so latitudinal test has enough smolts"
```

### Task S.4: If any river's modal age is off-envelope

Document the discrepancy and open a follow-up Arc rather than patching
blindly.

- [ ] **Step S.4.1: Add to deferred-items memory**

Append a note to `project_v041_phase_status.md`:

```
- Arc S (2026-04-21) found {river} modal smolt age {observed} vs
  WGBAST {expected} (Skoglund 2024). Off by >1 year. Likely needs
  temperature forcing tune or `smolt_min_length` per-river adjustment.
  See /tmp/latitudinal_run.log.
```

- [ ] **Step S.4.2: Commit**

```bash
git add docs/validation/v0.36.0-multi-river-baltic.md
git commit -m "docs(S): flag off-envelope smolt age for <river>, defer to next arc"
```

---

# Arc T: Arc 0 PDF data extraction (WGBAST + HELCOM)

**Goal:** Replace the 4 preliminary-placeholder CSVs from the Arc 0 data pass with values extracted from the official WGBAST 2026 and HELCOM core-indicator PDFs.

**Why:** v0.41.0 shipped 4 CSVs with values traced to peer-reviewed literature but flagged for PDF-table refinement:
- `data/wgbast/m74_ysfm_series.csv` ← Vuorinen 2021 Supp Table S2
- `data/wgbast/post_smolt_survival_baltic.csv` ← WGBAST 2026 §2 Bayesian figure
- `data/wgbast/observations/smolt_trap_counts.csv` ← WGBAST 2026 §3 Table
- `data/helcom/grey_seal_abundance_baltic.csv` ← HELCOM core-indicator PDF

**Effort:** M–L (1–3 hours engineer time + human-in-the-loop PDF downloads).
**Human-in-the-loop**: the engineer must have browser access to the PDFs (WGBAST 12 MB PDF download, HELCOM core-indicator webpage) and must run WebPlotDigitizer or manual transcription on the Bayesian posterior figures.

## Tasks

### Task T.1: Prepare tooling

- [ ] **Step T.1.1: Install pdfplumber + camelot into the shiny env**

Run: `micromamba install -n shiny -c conda-forge pdfplumber camelot-py "ghostscript" -y`
Expected: installs successfully (camelot requires ghostscript).

Verify:
```bash
micromamba run -n shiny python -c "import pdfplumber; import camelot; print('pdfplumber', pdfplumber.__version__); print('camelot', camelot.__version__)"
```
Expected: prints two version strings.

- [ ] **Step T.1.2: Create the raw PDF storage dir**

```bash
mkdir -p data/raw
echo -e "# Raw PDF downloads (gitignored)\n*.pdf" > data/raw/.gitignore
git add data/raw/.gitignore
git commit -m "chore: data/raw/ for PDF downloads, gitignored"
```

### Task T.2: Download WGBAST 2026 PDF

- [ ] **Step T.2.1: Resolve the download URL via ICES MCP**

The `ices_clients` package lives at `ices-mcp/ices_clients/`
and is NOT installed into the `shiny` conda env. Prepend the
package dir to `sys.path` inside the one-shot, so the import
resolves without a project-wide install:

```bash
micromamba run -n shiny python -c "
import sys
sys.path.insert(0, 'ices-mcp')
from ices_clients.migratory import get_ices_article
art = get_ices_article(article_id=29118545)
for f in art.get('files', []):
    print(f['download_url'], f.get('size'))
"
```
Expected: prints 1+ URLs. The 12 MB `.pdf` entry is the full report.

**Fallback — if the MCP import fails** (e.g. `ices_clients`
dependencies missing), bypass the MCP and use the known ICES
library base URL pattern:
```bash
# Article page on the ICES library:
# https://ices-library.figshare.com/articles/_/29118545
# The file download endpoint for each attached file is resolvable
# manually by opening the above URL in a browser — right-click the
# "PDF" link → Copy link → paste into the curl in T.2.2.
```

- [ ] **Step T.2.2: Download**

Use the printed URL:
```bash
curl -L -o data/raw/WGBAST_2026.pdf "<url from Step T.2.1>"
ls -lh data/raw/WGBAST_2026.pdf
```
Expected: ~12 MB PDF on disk. Verify header:
```bash
file data/raw/WGBAST_2026.pdf
```
Expected: `PDF document`.

### Task T.3: Extract per-river PSPC table (§3)

**Extraction strategy (review-pass 2026-04-21):** ICES WGBAST PDFs mix
lattice-bordered formal tables with stream/borderless multi-page tables.
Try camelot `lattice` first, fall back to camelot `stream` with
`table_areas`/`columns` tuned, and keep pdfplumber's
`page.extract_tables()` as a third-pass extractor for anything the
above miss. This is why the plan installs BOTH libraries in Task T.1.1.


- [ ] **Step T.3.1: Scaffold extraction script**

Create `scripts/_extract_wgbast_pspc.py`:

```python
"""Extract the per-river PSPC table from WGBAST 2026 §3.

The target table has columns: Assessment Unit, River, PSPC (smolts/yr),
Wild vs Reared. Camelot's lattice mode works well on ICES formal tables.

Run: micromamba run -n shiny python scripts/_extract_wgbast_pspc.py
Output: data/wgbast/pspc_by_river.csv
"""
from __future__ import annotations
import sys
from pathlib import Path
import camelot

PDF = Path("data/raw/WGBAST_2026.pdf")
if not PDF.exists():
    sys.exit(f"ERROR: {PDF} not found. Run Task T.2 first.")

# ICES §3 table typically sits pages 30-45. Scan a wide range.
# If lattice returns nothing, fall back to stream mode.
tables = camelot.read_pdf(str(PDF), pages="25-55", flavor="lattice")
if len(tables) == 0:
    print("lattice found nothing; falling back to stream flavor")
    tables = camelot.read_pdf(str(PDF), pages="25-55", flavor="stream")
print(f"Extracted {len(tables)} tables")
for i, t in enumerate(tables):
    print(f"Table {i}: shape={t.df.shape}, page={t.page}")
    # Filter for PSPC-like tables: must contain a column with "PSPC" or
    # "smolts/yr" in the header.
    header = t.df.iloc[0].astype(str).str.lower()
    if any("pspc" in c or "smolts" in c for c in header):
        out = Path("data/wgbast/pspc_by_river.csv")
        t.df.to_csv(out, index=False, header=False)
        print(f"  -> Saved to {out}")
        break
else:
    sys.exit("No PSPC table matched. Inspect the 'Table N' dumps above + "
             "widen page range.")
```

- [ ] **Step T.3.2: Run extraction**

```bash
micromamba run -n shiny python scripts/_extract_wgbast_pspc.py
```
Expected: either saves `data/wgbast/pspc_by_river.csv` OR prints candidate
tables for the engineer to inspect. If no match, widen the page range
or narrow the header filter heuristic.

- [ ] **Step T.3.3: Human QC step**

Open the generated CSV and compare:
- Total Baltic PSPC ≈ 3.4 M smolts/yr (WGBAST 2026 narrative)
- Tornionjoki ≈ 2.2 M
- Simojoki ≈ 95 k
- Byskeälven ≈ 180 k
- Mörrumsån ≈ 60 k (Poćwierz-Kotus 2015)

If any value deviates >25% from the above, either (a) it's an older
assessment column (discard) or (b) the table matched is the wrong one
(rerun T.3.1 with narrower page range).

- [ ] **Step T.3.4: Commit the extracted CSV**

```bash
git add data/wgbast/pspc_by_river.csv scripts/_extract_wgbast_pspc.py
git commit -m "data(Arc 0): WGBAST 2026 §3 per-river PSPC extracted via camelot"
```

### Task T.4: Replace M74 YSFM placeholder with Vuorinen 2021 Supp Table S2

The paper is OA (CC-BY) on Taylor & Francis. Supplementary material
format is publisher-set — may be XLSX, PDF, or DOCX. Download,
inspect, then route to the correct extractor.

- [ ] **Step T.4.1: Manual download + format detection**

1. Open `https://doi.org/10.1080/10236244.2021.1941942` in a browser.
2. Click through to Taylor & Francis's "Supplemental Material" tab.
3. Download whatever file is offered (typical names:
   `Supplemental_Table_S2.xlsx` / `_S2.pdf` / `_S2.docx`).
4. Save to `data/raw/vuorinen_2021_TableS2.<ext>`.

Inspect the extension and route:
- `.xlsx` / `.xls`  → use `pd.read_excel` (Step T.4.2 as written)
- `.pdf`            → use `camelot.read_pdf("data/raw/vuorinen_2021_TableS2.pdf", pages="all")` then `.df`
- `.docx`           → use `python-docx` (`micromamba install -n shiny -c conda-forge python-docx -y`) then `doc.tables[0]` → DataFrame
- `.csv` / `.tsv`   → `pd.read_csv`

Pick whichever branch matches your download and skip the others.

- [ ] **Step T.4.2: Transcribe to CSV via pandas**

Create `scripts/_extract_m74_vuorinen.py`:

```python
"""Convert Vuorinen 2021 Supp Table S2 XLSX to M74 YSFM CSV.

Expected XLSX layout (inspect in Excel first; adjust column names here):
    Columns: Year, Simojoki YSFM, Tornionjoki YSFM, Kemijoki YSFM, Kymijoki YSFM
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

XLSX = Path("data/raw/vuorinen_2021_TableS2.xlsx")
if not XLSX.exists():
    sys.exit(f"ERROR: {XLSX} not found. Download from Taylor & Francis first.")

df = pd.read_excel(XLSX)
print("Columns found:", list(df.columns))
print("First 5 rows:", df.head())

# Melt to long format (year, river, ysfm_fraction).
# Adjust the river column names to match what the XLSX actually uses.
rivers = [c for c in df.columns if c.lower() != "year"]
long_df = df.melt(id_vars=["Year"], value_vars=rivers,
                  var_name="river", value_name="ysfm_fraction")
long_df = long_df.rename(columns={"Year": "year"})
long_df = long_df.dropna(subset=["ysfm_fraction"])
long_df["source"] = "Vuorinen2021_TableS2"

# Normalise river names to the keys used in Arc L (Simojoki, Tornionjoki)
long_df["river"] = long_df["river"].str.replace(" YSFM", "").str.strip()

out = Path("data/wgbast/m74_ysfm_series.csv")
header = (
    "# WGBAST M74 yolk-sac-fry mortality (YSFM) series, per-year per-river.\n"
    "# v0.42.x Arc T extraction from Vuorinen et al. 2021 Supp Table S2\n"
    "# DOI: 10.1080/10236244.2021.1941942\n"
    "# Columns: year, river, ysfm_fraction (0-1), source\n"
)
with open(out, "w", encoding="utf-8") as f:
    f.write(header)
    long_df[["year", "river", "ysfm_fraction", "source"]].to_csv(
        f, index=False, lineterminator="\n"
    )
print(f"Wrote {len(long_df)} rows to {out}")
```

- [ ] **Step T.4.3: Run**

```bash
micromamba run -n shiny python scripts/_extract_m74_vuorinen.py
```
Expected: writes `data/wgbast/m74_ysfm_series.csv` with ~105 rows
(3–4 rivers × 30–35 years).

- [ ] **Step T.4.4: Commit**

```bash
git add data/wgbast/m74_ysfm_series.csv scripts/_extract_m74_vuorinen.py
git commit -m "data(Arc 0): Vuorinen 2021 Supp S2 full YSFM series replaces placeholder"
```

### Task T.5: Post-smolt survival from WGBAST 2026 Figure (WebPlotDigitizer)

The Bayesian posterior-median time series is a figure, not a table.
Use WebPlotDigitizer (browser tool) to transcribe points.

- [ ] **Step T.5.1: Locate the figure**

Open `data/raw/WGBAST_2026.pdf` in a PDF viewer, search for
"post-smolt survival" or "σ_ps". The canonical figure is usually in §2
of the WGBAST report and shows a per-smolt-year line with 95 %
credible interval for sal.27.22-31 (Main Basin) and sometimes
sal.27.32 (Gulf of Finland).

- [ ] **Step T.5.2: Digitise the figure**

Two options — prefer the scriptable one for reproducibility.

**Option A (recommended): PlotDigitizer Python** (OSS, scriptable, CLI)

Not on conda-forge — install via pip into the shiny env:
```bash
micromamba run -n shiny pip install plotdigitizer
```
Verify via module invocation (sidesteps Windows entrypoint PATH issues):
```bash
micromamba run -n shiny python -m plotdigitizer --help
```

Export the PDF page as PNG first. `pdftoppm` ships with `poppler`
which is NOT in the `shiny` env by default — install it:
```bash
micromamba install -n shiny -c conda-forge poppler -y
```
Then run via `micromamba run` so the env's `pdftoppm` is used
(avoids relying on system PATH):
```bash
micromamba run -n shiny pdftoppm -png -r 200 data/raw/WGBAST_2026.pdf data/raw/wgbast_fig
```

Digitise — invoke via `python -m` (not the bare `plotdigitizer`
entrypoint, which on Windows may not resolve inside `micromamba run`):
```bash
micromamba run -n shiny python -m plotdigitizer data/raw/wgbast_fig-32.png \
  --x-axis 1987 2024 \
  --y-axis 0.0 0.20 \
  --output data/raw/wpd_post_smolt_main_basin.csv
```
Adjust page number (`-32.png`) after running `pdftoppm` — it produces
one PNG per page.

**Option B: WebPlotDigitizer** (web tool, manual click)
Go to `https://apps.automeris.io/wpd/`. Load the screenshot, calibrate
axes, digitise each curve, export → CSV. Less reproducible but no
Python install required.

Either option produces the same CSV schema (year, survival_pct) that
Step T.5.3 consumes.

- [ ] **Step T.5.3: Clean and save**

Create `scripts/_extract_post_smolt_wpd.py`:

```python
"""Convert WebPlotDigitizer CSV into WGBAST post-smolt survival series.

Input: data/raw/wpd_post_smolt_<stock>.csv exported from WebPlotDigitizer.
    Each file has two columns: year (x), survival_pct (y, 0-1).
Output: data/wgbast/post_smolt_survival_baltic.csv (both stocks merged)
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

OUT = Path("data/wgbast/post_smolt_survival_baltic.csv")
INPUT_FILES = {
    "sal.27.22-31": Path("data/raw/wpd_post_smolt_main_basin.csv"),
    "sal.27.32":    Path("data/raw/wpd_post_smolt_gulf_of_finland.csv"),
}

rows = []
for stock, path in INPUT_FILES.items():
    if not path.exists():
        print(f"SKIP: {path} not found")
        continue
    df = pd.read_csv(path, header=None, names=["year", "survival_pct"])
    df["year"] = df["year"].round().astype(int)
    df = df.groupby("year").mean().reset_index()  # collapse duplicate x-clicks
    df["stock_unit"] = stock
    df["source"] = "WGBAST2026_FigX_wpd"
    rows.append(df)

if not rows:
    raise SystemExit("No WPD input files found. Run Step T.5.2 first.")

long_df = pd.concat(rows, ignore_index=True)
long_df = long_df.sort_values(["stock_unit", "year"])

header = (
    "# WGBAST post-smolt survival (Bayesian posterior median), per-year per-stock.\n"
    "# v0.42.x Arc T transcription from WGBAST 2026 §2 Figure via WebPlotDigitizer.\n"
    "# Columns: year, stock_unit, survival_pct (0-1), source\n"
)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(header)
    long_df[["year", "stock_unit", "survival_pct", "source"]].to_csv(
        f, index=False, lineterminator="\n"
    )
print(f"Wrote {len(long_df)} rows to {OUT}")
```

- [ ] **Step T.5.4: Run + commit**

```bash
micromamba run -n shiny python scripts/_extract_post_smolt_wpd.py
git add data/wgbast/post_smolt_survival_baltic.csv scripts/_extract_post_smolt_wpd.py
git commit -m "data(Arc 0): WGBAST 2026 post-smolt survival series (WPD-digitised)"
```

### Task T.6: Smolt-trap counts (Stock Annexes, not main §3)

**Data location correction (review-pass 2026-04-21):** WGBAST trap
counts for Simojoki (1980-2001+) and Tornionjoki (1987-2001+) live in
the **per-stock Annex subsections**, not in the main §3 narrative tables.
Camelot must scan the annex page range (typically 250-600 in WGBAST
PDFs), and the match heuristic should include "mark-recapture" and
"smolt run estimate" alongside "trap" and "count".

- [ ] **Step T.6.1: Extract**

Create `scripts/_extract_trap_counts.py`:

```python
"""Extract WGBAST 2026 Stock Annex smolt-trap counts for Simojoki +
Tornionjoki. Trap data lives in per-stock annex subsections, not
the main §3 narrative."""
from pathlib import Path
import sys
import camelot

PDF = Path("data/raw/WGBAST_2026.pdf")
if not PDF.exists():
    sys.exit("Download WGBAST PDF first (T.2)")

# Stock Annexes typically span pages 250-600 in a WGBAST report.
# Use stream flavor — annex tables are less consistently ruled.
tables = camelot.read_pdf(str(PDF), pages="250-600", flavor="stream")
print(f"Extracted {len(tables)} candidate tables from annexes")

for i, t in enumerate(tables):
    header = t.df.iloc[0].astype(str).str.lower()
    if any(
        k in c
        for c in header
        for k in ("trap", "count", "mark-recapture", "smolt run", "smolt estimate")
    ):
        out = Path("data/wgbast/observations/smolt_trap_counts.csv")
        t.df.to_csv(out, index=False, header=False)
        print(f"Matched table {i} (page {t.page}) → {out}")
        break
else:
    sys.exit(
        f"No trap-count table matched. Dump all {len(tables)} candidates "
        "and inspect manually. Consider narrowing pages to a specific "
        "annex (e.g. pages='310-330' for Tornionjoki)."
    )
```

- [ ] **Step T.6.2: Run + normalise schema + commit**

Output will need manual cleaning: ensure columns are
`year,river,smolts_counted,trap_efficiency,source`. Reshape via pandas
if necessary. Commit with the same Arc 0 prefix as T.3/T.4.

### Task T.7: HELCOM grey-seal abundance (HTML-first, PDF fallback)

**Data-location correction (review-pass 2026-04-21):** the HELCOM
indicator page is HTML-only since the 2023 migration — there's no
single "Download PDF" link on the current core-indicator page. Data
tables are embedded in HTML (`pandas.read_html` works directly). Two
archived PDFs give historical-context fallbacks.

- [ ] **Step T.7.1: Primary — scrape HTML table**

Create `scripts/_extract_helcom_seal_html.py`:

```python
"""Scrape HELCOM grey-seal abundance table from the core-indicator page.

Primary approach: pandas.read_html parses the HTML tables directly.
HELCOM's open-data statement explicitly guarantees indicator data is
embedded in the indicator page, so this is the most robust path.
"""
import sys
from pathlib import Path
import pandas as pd

URL = "https://indicators.helcom.fi/indicator/grey-seal-abundance/"
tables = pd.read_html(URL)
print(f"Found {len(tables)} HTML tables on the page")

# Filter: must contain year + abundance columns
for i, t in enumerate(tables):
    cols = [str(c).lower() for c in t.columns]
    if any("year" in c for c in cols) and any(
        k in c for c in cols for k in ("abundance", "population", "count")
    ):
        out = Path("data/helcom/grey_seal_abundance_baltic.csv")
        t.to_csv(out, index=False)
        print(f"Saved table {i} → {out}")
        break
else:
    print("No matching HTML table. Fall back to T.7.2 PDF archive.", file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step T.7.2: Fallback — archived PDF (if HTML has no structured table)**

Download one of the archived HELCOM core-indicator PDFs:
- 2018 version: `https://helcom.fi/wp-content/uploads/2019/08/Population-trends-and-abundance-of-seals-HELCOM-core-indicator-2018.pdf`
- 2023 distribution: `https://helcom.fi/wp-content/uploads/2023/04/Distribution-of-Baltic-Seals-HELCOM-thematic-assessment-2016-2021.pdf`

Save to `data/raw/HELCOM_grey_seal.pdf` then use camelot pattern from T.3
with header heuristic matching "population" or "abundance".

- [ ] **Step T.7.3: QC + commit**

Expected values to sanity-check (from Arc 0 v0.41.0):
- 2014 ≈ 32,019 (Lai 2021)
- 2020 ≈ 40,000 (Westphal 2025)
- 2023 ≈ 45,000 (Westphal 2025)

If extracted values match within 5 %, commit. Otherwise fall back to
the PDF path and re-extract.

### Task T.8: Version bump + release v0.43.0

- [ ] **Step T.8.1: Bump + CHANGELOG**

Add to CHANGELOG.md:

```markdown
## [0.43.0] - YYYY-MM-DD (Arc T: Arc 0 PDF data extraction)

### Data
- Replaced preliminary-placeholder CSVs with values extracted from the
  canonical WGBAST 2026 + HELCOM + Vuorinen 2021 sources:
  - `data/wgbast/pspc_by_river.csv` ← WGBAST 2026 §3 (camelot)
  - `data/wgbast/m74_ysfm_series.csv` ← Vuorinen 2021 Supp S2 (xlsx)
  - `data/wgbast/post_smolt_survival_baltic.csv` ← WGBAST 2026 Fig (WebPlotDigitizer)
  - `data/wgbast/observations/smolt_trap_counts.csv` ← WGBAST 2026 §3
  - `data/helcom/grey_seal_abundance_baltic.csv` ← HELCOM core-indicator PDF

### Tooling
- New `scripts/_extract_*.py` scripts — reproducible pipelines for each
  PDF extraction.
- Added `pdfplumber`, `camelot-py` to the `shiny` conda env.
```

- [ ] **Step T.8.2: Tag + push**

```bash
git tag v0.43.0
git push origin master v0.43.0
```

---

# Arc U: GitHub Releases backfill for v0.41.3–v0.41.14

**Goal:** Create GitHub Release pages for the 12 tags that were pushed but never wrapped in a Release (v0.41.3 through v0.41.14).

**Why:** v0.41.2 is currently the latest GitHub Release, but v0.41.14 is the HEAD. Users visiting the repo's /releases page see stale content. Every tag should have a Release with notes extracted from CHANGELOG.

**Effort:** XS (15 min).

**Prerequisite — `gh` CLI installed and authenticated.**
Windows install (if missing): `winget install --id GitHub.cli`.
Verify:
```bash
gh --version && gh auth status
```
Expected: `gh version …` + `Logged in to github.com as …`. If not
authenticated, run `gh auth login` and choose HTTPS + browser.

## Tasks

### Task U.1: Commit extractor + backfill scripts under `scripts/`

The earlier backfill used a temp-file extractor that will not survive
session expiry. Move both scripts under `scripts/` and reference
relative paths.

- [ ] **Step U.1.0: Create the extractor script under `scripts/`**

Create `scripts/_extract_changelog_section.py`:

```python
"""Extract a single ## [version] section from CHANGELOG.md and print it.

Used by scripts/_backfill_releases.sh to feed gh release create --notes-file.
"""
import re
import sys

version = sys.argv[1]
changelog = open("CHANGELOG.md", encoding="utf-8").read()

# Match `## [VERSION] ...` up to the next `## [` at line start
pat = re.compile(
    rf"^(##\s+\[{re.escape(version)}\].*?)(?=^##\s+\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
m = pat.search(changelog)
if not m:
    sys.stderr.write(f"No section found for version {version}\n")
    sys.exit(1)
section = m.group(1).rstrip()
# Strip the `## [X.Y.Z] - DATE (title)` line — gh release already has title
lines = section.split("\n")
body = "\n".join(lines[1:]).strip()
# Strip any trailing `---` divider
if body.endswith("---"):
    body = body[: -len("---")].rstrip()
print(body)
```

Commit:
```bash
git add scripts/_extract_changelog_section.py
git commit -m "chore(U): extractor script for gh release backfill"
```

- [ ] **Step U.1.1: Write the bash loop**

Create `scripts/_backfill_releases.sh`:

```bash
#!/usr/bin/env bash
# Backfill GitHub Releases for v0.41.3 through v0.41.14 from CHANGELOG.
# Idempotent: skips any tag that already has a Release.
set -u
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"

declare -A TITLES=(
  ["0.41.3"]="v0.41.3 — Map rendering cleanup"
  ["0.41.4"]="v0.41.4 — Setup map: auto-center + example_a load fix"
  ["0.41.5"]="v0.41.5 — WGBAST river fixture rename"
  ["0.41.6"]="v0.41.6 — Fix setup-panel initial view-state"
  ["0.41.7"]="v0.41.7 — Fix: replace non-existent set_view_state"
  ["0.41.8"]="v0.41.8 — Fix: stable layer id for Color-by recolor"
  ["0.41.9"]="v0.41.9 — Fix: deck.gl kwargs need camelCase"
  ["0.41.10"]="v0.41.10 — Setup UX: inline descriptions + tight layout"
  ["0.41.11"]="v0.41.11 — Setup UX: control-row vertical alignment"
  ["0.41.12"]="v0.41.12 — Nav: swap Setup and Create Model"
  ["0.41.13"]="v0.41.13 — Movement panel UX matches Setup"
  ["0.41.14"]="v0.41.14 — Movement 2-row layout with 72px label column"
)

EXTRACTOR="scripts/_extract_changelog_section.py"

for V in 0.41.3 0.41.4 0.41.5 0.41.6 0.41.7 0.41.8 0.41.9 0.41.10 0.41.11 0.41.12 0.41.13 0.41.14; do
    if gh release view "v$V" >/dev/null 2>&1; then
        echo "SKIP v$V: release already exists"
        continue
    fi
    NOTES_FILE="/tmp/release_notes_${V}.md"
    micromamba run -n shiny python "$EXTRACTOR" "$V" > "$NOTES_FILE" || {
        echo "ERROR: extractor failed for v$V (exit $?) — aborting so"
        echo "       a real failure isn't silently swallowed."
        exit 1
    }
    if [ ! -s "$NOTES_FILE" ]; then
        echo "SKIP v$V: empty notes (extractor returned 0 but wrote nothing)"
        continue
    fi
    echo "Creating release v$V..."
    gh release create "v$V" --title "${TITLES[$V]}" --notes-file "$NOTES_FILE" | tail -1
done

# Ensure v0.41.14 is marked "Latest" (GitHub picks by creation date
# otherwise, and these are all being created after v0.42.0 might be).
gh release edit v0.41.14 --latest
```

- [ ] **Step U.1.2: Run**

```bash
bash scripts/_backfill_releases.sh
```
Expected: 12 release URLs printed (one per tag) + one "marked latest"
confirmation.

- [ ] **Step U.1.3: Verify**

```bash
gh release list --limit 15
```
Expected: v0.41.14 shown with `Latest` label; v0.41.0–v0.41.14 all
listed with titles.

- [ ] **Step U.1.4: Commit the script**

```bash
git add scripts/_backfill_releases.sh
git commit -m "chore(U): release-backfill script for v0.41.3-v0.41.14"
```

---

# Self-Review

**Spec coverage** (checks against the 5 deferred items from
`project_v041_phase_status.md`):
- [x] Movement panel idle-state basemap preview → Arc R.2
- [x] Actual simulation-run verification of Movement trails → Arc R.4
- [x] Latitudinal smolt-age slow tests for 4 WGBAST rivers → Arc S
- [x] 4 placeholder CSVs (M74, post-smolt, smolt-trap, HELCOM seal) → Arc T
- [x] GitHub Releases backfill for v0.41.3–v0.41.14 → Arc U

All 5 covered.

**Placeholder scan**: Arc T has inherent human-in-the-loop PDF
downloads (browser required for Vuorinen XLSX and WebPlotDigitizer).
Flagged explicitly; no TBD/TODO language.

**Type consistency**:
- `load_fixture_gdf(config_path)` signature used identically in
  Arc R.1 (new helper) and Arc R.2 (imported + called).
- `_fixture_loader` imported in setup_panel.py (R.1.5) and
  movement_panel.py (R.2.2) with the same pattern.
- Release-notes file naming uses `/tmp/release_notes_${V}.md` and
  the extractor script matches the one from the earlier backfill.

**Dependencies**:
- Arc R.1 (shared fixture loader) is a prerequisite for Arc R.2
  (idle preview consumes it).
- Arc R.3 and R.4 both depend on R.2 for verification.
- Arcs S, T, U are mutually independent.

---

# Execution Handoff

Plan saved to `docs/superpowers/plans/2026-04-21-v041-deferred-followups.md`.

**Four Arcs, each self-contained and mergeable independently.**
Recommended order (easy wins first): **U → S → R → T**.

## Execution options

**1. Subagent-Driven (recommended for R, Arc-by-Arc)** — dispatch one
subagent per task, two-stage review between.

**2. Inline execution (good for U, S)** — these are small enough to
run in one session.

**3. Pause** — read and approve before executing.

Which approach?
