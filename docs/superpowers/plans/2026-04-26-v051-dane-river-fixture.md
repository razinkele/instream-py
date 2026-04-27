# v0.51.0 — Add Danė river to example_baltic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Note:** Task 1 is an interactive Shiny UI workflow that REQUIRES a human operator at the browser. Subagents cannot execute it; the plan controller (you) executes Task 1 by relaying instructions to the user, who reports back. Tasks 2–8 are scriptable.

**Goal:** Add the Danė river (4 reaches: Dane_Upper/Middle/Lower/Mouth) plus KlaipedaStrait sea-edge reach to `example_baltic`, exercising the v0.50.0 Find/Auto-extract/Auto-split buttons end-to-end on real Klaipėda OSM data.

**Architecture:** Fixture-extension release. NO code changes to `app/modules/` or `src/salmopy/`. example_baltic grows from 9 reaches (~1591 cells) to 14 reaches (~1791-1991 cells projected). Junction wiring uses fresh IDs 10-14; KlaipedaStrait drains to existing junction 6 (sea sink, parallel to BalticCoast).

**Tech Stack:** Python 3.13 + micromamba env `shiny`, Shiny ≥1.5, geopandas ≥1.0, shapely ≥2.0, pyyaml, pytest.

**Spec reference:** `docs/superpowers/specs/2026-04-26-v051-dane-river-fixture-design.md`

**Working branch:** `v051-dane-river-fixture` (already created from master; spec already committed at `75e3d14`).

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `tests/fixtures/example_baltic/Dane_*-Depths.csv` (×4) | Create | Per-cell depths for 4 Danė reaches; produced by Create Model export |
| `tests/fixtures/example_baltic/Dane_*-Vels.csv` (×4) | Create | Per-cell velocities |
| `tests/fixtures/example_baltic/Dane_*-TimeSeriesInputs.csv` (×4) | Create | Daily flow/temp series |
| `tests/fixtures/example_baltic/KlaipedaStrait-*.csv` (×3) | Create | Hand-written sea-reach CSVs (matches BalticCoast format) |
| `tests/fixtures/example_baltic/Shapefile/BalticExample.shp` (+ .dbf/.shx/.prj/.cpg) | Modify | Append 5 polygons (4 Danė reaches + KlaipedaStrait) |
| `tests/fixtures/example_baltic/BalticExample-AdultArrivals.csv` | Modify | Append 28 yearly rows targeting Dane_Lower (2011-2038) |
| `configs/example_baltic.yaml` | Modify | Append 5 reach blocks in `reaches:` section |
| `tests/test_baltic_geometry.py` | Modify | Update EXPECTED_REACHES, CELL_COUNT_MAX, DIRECT_ADJACENCY_PAIRS, SPAWNING_REACHES, non-spawning assertion |
| `scripts/_probe_baltic_with_dane.py` | Create | Smoke probe ~70 LOC, 8 assertions |
| `pyproject.toml` | Modify | Version bump 0.50.0 → 0.51.0 |
| `src/salmopy/__init__.py` | Modify | Version bump |
| `CHANGELOG.md` | Modify | Prepend v0.51.0 entry |

---

## Task 1: Operator workflow — produce `tests/fixtures/_dane_temp/` (interactive, no commit)

This task uses the v0.50.0 buttons end-to-end. Subagents cannot execute it; the plan controller relays instructions to a human operator and waits for confirmation.

**Files produced (in `tests/fixtures/_dane_temp/`)**:
- `Mouth-Depths.csv`, `Mouth-Vels.csv`, `Mouth-TimeSeriesInputs.csv`
- (same × Lower, Middle, Upper)
- `Shapefile/<dane_temp>.shp` (and .dbf/.shx/.prj/.cpg)
- `<dane_temp>.yaml` (4 reach blocks)

After Edit Model rename (step 1.9), file stems become `Dane_Mouth-*.csv` etc.

- [ ] **Step 1.1: Start local Shiny**

```bash
micromamba run -n shiny python -m shiny run --port 9050 app/app.py
```

Browser opens at http://localhost:9050. Open Create Model panel.

- [ ] **Step 1.2: Find Klaipėda**

Type `Klaipėda, Lithuania` (with comma — disambiguates city from county) → click 🔍 Find.

Expected: Region dropdown auto-sets to `lithuania`. Map zooms to ~lat 55.71, lon 21.15. Rivers + Water layers auto-fetched.

- [ ] **Step 1.3: Zoom out to capture full Danė centerline**

The Nominatim bbox covers only Klaipėda city (~13×9 km). The Danė extends ~70 km inland to Kretinga. **Manually pan/zoom-out** the map to cover lat 55.7–56.0, lon 21.0–21.4 BEFORE clicking 🌊 Sea.

- [ ] **Step 1.4: Fetch Sea**

Click 🌊 Sea. Marine Regions WFS returns the full Baltic Sea polygon.

- [ ] **Step 1.5: (Optional) Lower Strahler threshold**

If the Danė centerline doesn't appear at default Strahler ≥3, lower the slider to ≥2. Danė is small.

- [ ] **Step 1.6: Auto-extract with port-flood deselect**

Click ✨ Auto-extract.

**CRITICAL visual checkpoint**: Klaipėda has dense port geometry (dredged harbor channels, port basin, marina inlets). Auto-extract's BFS will likely pull in the entire connected port network. Inspect the map:
- If kept polygons extend south into the Klaipėda port → those are unwanted.
- Toggle 💧 Lagoon mode → click each unwanted polygon to un-highlight.
- This is expected workflow, not a fallback.

After deselection, only Danė channel + adjacent Klaipėda Strait water should remain.

- [ ] **Step 1.7: Auto-split N=4**

Click ⚡ Auto-split with N=4 (default).

Expected toast: `Split into 4 reaches: Mouth (X), Lower (Y), Middle (Z), Upper (W).`

**Visual checkpoint**: 4 colored reach overlays on the map. "Mouth" = downstream-most (closest to Baltic). "Upper" = furthest inland (toward Kretinga). If colors are inverted, proceed but plan to swap names in step 1.9.

- [ ] **Step 1.8: Export to temp fixture**

Click 📦 Export → save as `tests/fixtures/_dane_temp/`.

- [ ] **Step 1.9: Edit Model rename**

Switch to Edit Model panel → from the fixture-load dropdown, select `_dane_temp` (loads from disk). Rename:
- `Mouth` → `Dane_Mouth`
- `Lower` → `Dane_Lower`
- `Middle` → `Dane_Middle`
- `Upper` → `Dane_Upper`

(If step 1.7 colors were inverted, rename accordingly: what showed as "Mouth" → `Dane_Upper`, etc.)

Edit Model rewrites `_dane_temp/` shapefile DBF + YAML + CSV stems in place.

- [ ] **Step 1.10: Verify temp fixture**

```bash
ls tests/fixtures/_dane_temp/Dane_*-{Depths,Vels,TimeSeriesInputs}.csv
```

Expected: 12 CSV files, named with `Dane_` prefix.

- [ ] **Step 1.11: Stop the Shiny server**

Ctrl+C in the terminal that started Shiny. Task 1 ends. NO commit.

---

## Task 2: Backup + manual merge of Danė reaches into example_baltic

- [ ] **Step 2.1: Backup example_baltic**

```bash
cp -r "tests/fixtures/example_baltic" "tests/fixtures/example_baltic.bak"
```

The merge modifies the shapefile in place; if it goes wrong, restore from `.bak`.

- [ ] **Step 2.2: Copy 12 Danė per-cell CSVs**

```bash
cp tests/fixtures/_dane_temp/Dane_*-Depths.csv tests/fixtures/example_baltic/
cp tests/fixtures/_dane_temp/Dane_*-Vels.csv tests/fixtures/example_baltic/
cp tests/fixtures/_dane_temp/Dane_*-TimeSeriesInputs.csv tests/fixtures/example_baltic/
```

Verify: `ls tests/fixtures/example_baltic/Dane_*` shows 12 files.

- [ ] **Step 2.3: Append Danė shapefile features**

Run this Python snippet (save as `scripts/_merge_dane_shapefile.py` or run interactively):

```python
import geopandas as gpd
import pandas as pd

baltic = gpd.read_file("tests/fixtures/example_baltic/Shapefile/BalticExample.shp")
dane_dir = "tests/fixtures/_dane_temp/Shapefile"
import glob
dane_shp = glob.glob(f"{dane_dir}/*.shp")[0]
dane = gpd.read_file(dane_shp)

# Verify column-set match BEFORE merging
baltic_cols = set(baltic.columns)
dane_cols = set(dane.columns)
assert baltic_cols == dane_cols, f"Column mismatch: only-in-baltic={baltic_cols - dane_cols}, only-in-dane={dane_cols - baltic_cols}"

merged = gpd.GeoDataFrame(pd.concat([baltic, dane], ignore_index=True), crs=baltic.crs)
merged.to_file("tests/fixtures/example_baltic/Shapefile/BalticExample.shp")
print(f"Merged: {len(baltic)} + {len(dane)} = {len(merged)} cells")
```

Expected output: roughly `1591 + 200..400 = 1791..1991` (Danė cell count varies by Auto-split groups).

- [ ] **Step 2.4: Verify reach names in merged shapefile**

```bash
micromamba run -n shiny python -c "
import geopandas as gpd
g = gpd.read_file('tests/fixtures/example_baltic/Shapefile/BalticExample.shp')
print(sorted(g['REACH_NAME'].unique()))
"
```

Expected: 13 reach names (existing 9 + 4 Danė reaches; KlaipedaStrait added in Task 3).

---

## Task 3: Add KlaipedaStrait reach (polygon + CSVs + YAML block)

- [ ] **Step 3.1: Append KlaipedaStrait polygon to shapefile**

Run this Python snippet:

```python
import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

baltic = gpd.read_file("tests/fixtures/example_baltic/Shapefile/BalticExample.shp")

# Klaipėda Strait approximate WKT — refine in QGIS if it crosses land
strait_polygon = Polygon([
    (21.103, 55.685),  # SW corner — south of strait at Baltic edge
    (21.130, 55.685),  # SE corner — south Klaipėda port
    (21.130, 55.745),  # NE corner — north Klaipėda waterfront
    (21.103, 55.745),  # NW corner — north Smiltynė tip
    (21.103, 55.685),  # close
])

# Build a single-row GeoDataFrame matching baltic's schema
new_row = {col: baltic.iloc[0][col] for col in baltic.columns if col != "geometry"}
new_row["REACH_NAME"] = "KlaipedaStrait"
# Reset numeric/index columns to defaults (FRACSPWN=0 for sea reach)
if "FRACSPWN" in new_row:
    new_row["FRACSPWN"] = 0.0
new_row["geometry"] = strait_polygon

new_gdf = gpd.GeoDataFrame([new_row], crs=baltic.crs)
merged = gpd.GeoDataFrame(pd.concat([baltic, new_gdf], ignore_index=True), crs=baltic.crs)
merged.to_file("tests/fixtures/example_baltic/Shapefile/BalticExample.shp")
print(f"Added KlaipedaStrait single polygon. Total cells: {len(merged)}")
```

(The single-polygon approach is simpler than the regrid mentioned in the spec's risk #5. KlaipedaStrait gets exactly 1 cell, which is fine for a small sea-edge transition reach. If finer resolution is needed, defer to v0.51.x.)

- [ ] **Step 3.2: Hand-write `KlaipedaStrait-Depths.csv`**

Create `tests/fixtures/example_baltic/KlaipedaStrait-Depths.csv` with the 10-flow format:

```
; Depths for Baltic example — KlaipedaStrait
; ~10m typical depth, tidal channel between Smiltynė & Klaipėda
; CELL DEPTHS IN METERS
10,Number of flows in table,,,,,,,,,,,,,,,,,,
,10.0,20.0,30.0,40.0,60.0,90.0,130.0,200.0,400.0,1000.0
1,8.0,8.5,9.0,9.5,10.5,12.0,13.5,15.0,18.0,22.0
```

Single cell (cell ID 1), 10 flow columns, depths increasing with flow.

- [ ] **Step 3.3: Hand-write `KlaipedaStrait-Vels.csv`**

```
; Velocities for Baltic example — KlaipedaStrait
; weak tidal exchange with Baltic, 0.1-0.3 m/s typical
; CELL VELOCITIES IN M/S
10,Number of flows in table,,,,,,,,,,,,,,,,,,
,10.0,20.0,30.0,40.0,60.0,90.0,130.0,200.0,400.0,1000.0
1,0.10,0.12,0.14,0.16,0.18,0.20,0.22,0.24,0.27,0.30
```

- [ ] **Step 3.4: Hand-write `KlaipedaStrait-TimeSeriesInputs.csv`**

Copy `BalticCoast-TimeSeriesInputs.csv` verbatim:

```bash
cp "tests/fixtures/example_baltic/BalticCoast-TimeSeriesInputs.csv" \
   "tests/fixtures/example_baltic/KlaipedaStrait-TimeSeriesInputs.csv"
```

Sea-reach time series uses the same flat schedule.

- [ ] **Step 3.5: Append 5 reach blocks to `configs/example_baltic.yaml`**

Find the `BalticCoast:` block in `configs/example_baltic.yaml` (around line 370). Insert the 5 new reach blocks immediately AFTER `BalticCoast:` ends and BEFORE the `marine:` section.

```yaml
  Dane_Upper:                  # upper Dane, ~22 km, best spawning habitat
    pspc_smolts_per_year: 150
    drift_conc: 1.5e-08          # cloned from Minija
    search_prod: 1.80e-06
    shelter_speed_frac: 0.22
    prey_energy_density: 4000
    drift_regen_distance: 700
    shading: 0.72
    fish_pred_min: 0.980
    terr_pred_min: 0.970
    light_turbid_coef: 0.0028
    light_turbid_const: 0.0005
    max_spawn_flow: 14
    shear_A: 0.010
    shear_B: 0.35
    upstream_junction: 10
    downstream_junction: 11
    time_series_input_file: "Dane_Upper-TimeSeriesInputs.csv"
    depth_file: "Dane_Upper-Depths.csv"
    velocity_file: "Dane_Upper-Vels.csv"

  Dane_Middle:                 # middle Dane, ~22 km, rural mid-river
    pspc_smolts_per_year: 100
    drift_conc: 1.5e-08
    search_prod: 1.80e-06
    shelter_speed_frac: 0.22
    prey_energy_density: 4000
    drift_regen_distance: 700
    shading: 0.72
    fish_pred_min: 0.980
    terr_pred_min: 0.970
    light_turbid_coef: 0.0028
    light_turbid_const: 0.0005
    max_spawn_flow: 14
    shear_A: 0.010
    shear_B: 0.35
    upstream_junction: 11
    downstream_junction: 12
    time_series_input_file: "Dane_Middle-TimeSeriesInputs.csv"
    depth_file: "Dane_Middle-Depths.csv"
    velocity_file: "Dane_Middle-Vels.csv"

  Dane_Lower:                  # lower Dane through Klaipėda, urban; AdultArrivals target
    pspc_smolts_per_year: 50
    drift_conc: 1.5e-08
    search_prod: 1.80e-06
    shelter_speed_frac: 0.22
    prey_energy_density: 4000
    drift_regen_distance: 700
    shading: 0.72
    fish_pred_min: 0.980
    terr_pred_min: 0.970
    light_turbid_coef: 0.0028
    light_turbid_const: 0.0005
    max_spawn_flow: 14
    shear_A: 0.010
    shear_B: 0.35
    upstream_junction: 12
    downstream_junction: 13
    time_series_input_file: "Dane_Lower-TimeSeriesInputs.csv"
    depth_file: "Dane_Lower-Depths.csv"
    velocity_file: "Dane_Lower-Vels.csv"

  Dane_Mouth:                  # brackish mouth at Klaipėda — no spawning
    pspc_smolts_per_year: 0
    drift_conc: 1.5e-08
    search_prod: 1.80e-06
    shelter_speed_frac: 0.22
    prey_energy_density: 4000
    drift_regen_distance: 700
    shading: 0.72
    fish_pred_min: 0.980
    terr_pred_min: 0.970
    light_turbid_coef: 0.0028
    light_turbid_const: 0.0005
    max_spawn_flow: 14
    shear_A: 0.010
    shear_B: 0.35
    upstream_junction: 13
    downstream_junction: 14
    time_series_input_file: "Dane_Mouth-TimeSeriesInputs.csv"
    depth_file: "Dane_Mouth-Depths.csv"
    velocity_file: "Dane_Mouth-Vels.csv"

  KlaipedaStrait:              # saline strait Smiltynė–Klaipėda; clones BalticCoast
    drift_conc: 0.2e-09          # cloned from BalticCoast
    search_prod: 1.00e-07
    shelter_speed_frac: 0.0
    prey_energy_density: 1500
    drift_regen_distance: 20000
    shading: 0.02
    fish_pred_min: 0.700         # 0.65 (BalticCoast) + 0.05 fudge for sheltered geometry
    terr_pred_min: 0.995
    light_turbid_coef: 0.007
    light_turbid_const: 0.004
    max_spawn_flow: 999
    shear_A: 0.001
    shear_B: 0.15
    upstream_junction: 14
    downstream_junction: 6        # joins existing sea sink (parallel to BalticCoast)
    time_series_input_file: "KlaipedaStrait-TimeSeriesInputs.csv"
    depth_file: "KlaipedaStrait-Depths.csv"
    velocity_file: "KlaipedaStrait-Vels.csv"
```

---

## Task 4: Append Danė returner rows to AdultArrivals CSV

- [ ] **Step 4.1: Append 28 rows to `BalticExample-AdultArrivals.csv`**

Run this Python snippet:

```python
from pathlib import Path

csv = Path("tests/fixtures/example_baltic/BalticExample-AdultArrivals.csv")
existing = csv.read_text(encoding="utf-8")
new_rows = []
for year in range(2011, 2039):  # 2011 through 2038 inclusive (28 years)
    new_rows.append(
        f"{year},BalticAtlanticSalmon,Dane_Lower,7,0.55,5/15/{year},7/1/{year},8/31/{year},55,68,85"
    )
csv.write_text(existing.rstrip("\n") + "\n" + "\n".join(new_rows) + "\n", encoding="utf-8")
print(f"Appended {len(new_rows)} rows")
```

Expected output: `Appended 28 rows`.

Verify:
```bash
wc -l tests/fixtures/example_baltic/BalticExample-AdultArrivals.csv
# Expected: 227 (199 existing + 28 new)
tail -5 tests/fixtures/example_baltic/BalticExample-AdultArrivals.csv
# Last 5 rows should be Dane_Lower 2034-2038
```

---

## Task 5: Update `tests/test_baltic_geometry.py`

- [ ] **Step 5.1: Add 5 new reaches to `EXPECTED_REACHES`**

Edit `tests/test_baltic_geometry.py:30-33`:

```python
EXPECTED_REACHES = {
    "Nemunas", "Atmata", "Minija", "Sysa", "Skirvyte", "Leite",
    "Gilija", "CuronianLagoon", "BalticCoast",
    # v0.51.0: Danė river + Klaipėda Strait
    "Dane_Upper", "Dane_Middle", "Dane_Lower", "Dane_Mouth", "KlaipedaStrait",
}
```

- [ ] **Step 5.2: Raise `CELL_COUNT_MAX`**

Edit `tests/test_baltic_geometry.py:38`:

```python
CELL_COUNT_MIN = 1300
CELL_COUNT_MAX = 2800   # v0.51.0: was 2200, +600 for Danė reaches + KlaipedaStrait
```

- [ ] **Step 5.3: Add Danė chain to `DIRECT_ADJACENCY_PAIRS`**

Edit `tests/test_baltic_geometry.py:42-56`. Append:

```python
DIRECT_ADJACENCY_PAIRS = [
    # ... (existing pairs unchanged) ...
    # Danė chain (v0.51.0)
    ("Dane_Upper", "Dane_Middle"),
    ("Dane_Middle", "Dane_Lower"),
    ("Dane_Lower", "Dane_Mouth"),
    ("Dane_Mouth", "KlaipedaStrait"),
    ("KlaipedaStrait", "BalticCoast"),
]
```

- [ ] **Step 5.4: Add Danė reaches to `SPAWNING_REACHES`**

Edit `tests/test_baltic_geometry.py:196-197`:

```python
SPAWNING_REACHES = ["Nemunas", "Atmata", "Minija", "Sysa", "Skirvyte",
                    "Leite", "Gilija",
                    # v0.51.0: Danė reaches with non-zero pspc
                    "Dane_Upper", "Dane_Middle", "Dane_Lower"]
                    # NOT Dane_Mouth (pspc=0, brackish)
```

- [ ] **Step 5.5: Add KlaipedaStrait to non-spawning assertion**

Edit `tests/test_baltic_geometry.py:230` (`test_non_spawning_reaches_have_zero_frac_spawn`):

```python
    for r in ("CuronianLagoon", "BalticCoast", "KlaipedaStrait"):
```

---

## Task 6: Create smoke probe `scripts/_probe_baltic_with_dane.py`

- [ ] **Step 6.1: Create the probe**

Write `scripts/_probe_baltic_with_dane.py`:

```python
"""Smoke probe for the v0.51.0 example_baltic fixture with Danė + KlaipedaStrait.

Asserts 8 invariants on the merged fixture before commit. Run as:
    micromamba run -n shiny python scripts/_probe_baltic_with_dane.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import geopandas as gpd
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "example_baltic"
SHP = FIXTURE_DIR / "Shapefile" / "BalticExample.shp"
YAML_PATH = ROOT / "configs" / "example_baltic.yaml"
ARRIVALS = FIXTURE_DIR / "BalticExample-AdultArrivals.csv"

EXPECTED_REACHES = {
    "Nemunas", "Atmata", "Minija", "Sysa", "Skirvyte", "Leite",
    "Gilija", "CuronianLagoon", "BalticCoast",
    "Dane_Upper", "Dane_Middle", "Dane_Lower", "Dane_Mouth", "KlaipedaStrait",
}
SEA_SINK_JUNCTION = 6


def _check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    msg = f"[{name}] {status}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


def main() -> int:
    cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    reaches = cfg.get("reaches", {})

    a1 = _check(
        "1/8 YAML 14 reaches",
        set(reaches.keys()) == EXPECTED_REACHES,
        f"got {sorted(reaches.keys())}",
    )

    csvs_ok = True
    for r in EXPECTED_REACHES:
        for suffix in ("Depths", "Vels", "TimeSeriesInputs"):
            f = FIXTURE_DIR / f"{r}-{suffix}.csv"
            if not f.exists():
                csvs_ok = False
                print(f"   missing: {f.name}")
    a2 = _check("2/8 CSVs present (3 per reach)", csvs_ok)

    sys.path.insert(0, str(ROOT / "src"))
    try:
        from salmopy.io.hydraulics_reader import _parse_hydraulic_csv
        load_ok = True
        for r in EXPECTED_REACHES:
            for suffix in ("Depths", "Vels"):
                f = FIXTURE_DIR / f"{r}-{suffix}.csv"
                try:
                    df = _parse_hydraulic_csv(f)
                    if df.shape[1] != 10:
                        load_ok = False
                        print(f"   {f.name} has {df.shape[1]} flow cols, expected 10")
                except Exception as exc:
                    load_ok = False
                    print(f"   {f.name} parse error: {type(exc).__name__}: {exc}")
        a3 = _check("3/8 per-cell CSVs load via _parse_hydraulic_csv", load_ok)
    except ImportError as exc:
        a3 = _check("3/8 per-cell CSVs load via _parse_hydraulic_csv", False,
                    f"import failed: {exc}")

    upstreams = {r["upstream_junction"] for r in reaches.values()}
    downstreams = {r["downstream_junction"] for r in reaches.values()}
    sinks = downstreams - upstreams
    a4 = _check(
        "4/8 junction graph: unique sea sink",
        sinks == {SEA_SINK_JUNCTION},
        f"sinks={sorted(sinks)}, expected={SEA_SINK_JUNCTION}",
    )

    gdf = gpd.read_file(str(SHP))
    a5 = _check(
        "5/8 shapefile feature count >= reach count",
        len(gdf) >= len(EXPECTED_REACHES),
        f"got {len(gdf)} cells",
    )

    actual_reaches = set(gdf["REACH_NAME"].unique())
    a6 = _check(
        "6/8 shapefile REACH_NAME == EXPECTED_REACHES",
        actual_reaches == EXPECTED_REACHES,
        f"missing={EXPECTED_REACHES - actual_reaches}, extra={actual_reaches - EXPECTED_REACHES}",
    )

    per_reach_min = {
        r: 30 for r in ("Dane_Upper", "Dane_Middle", "Dane_Lower", "Dane_Mouth")
    }
    per_reach_min["KlaipedaStrait"] = 1  # single hand-written polygon
    a7_ok = True
    for r, min_cells in per_reach_min.items():
        n = int((gdf["REACH_NAME"] == r).sum())
        if n < min_cells:
            a7_ok = False
            print(f"   {r}: {n} cells < {min_cells} minimum")
    a7 = _check("7/8 per-reach minimum cell counts", a7_ok)

    a8_ok = True
    with ARRIVALS.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith(";") or not line.strip():
                continue
            cols = line.split(",")
            if len(cols) >= 3:
                reach = cols[2].strip()
                if reach not in EXPECTED_REACHES:
                    a8_ok = False
                    print(f"   AdultArrivals row references unknown reach: {reach!r}")
    a8 = _check("8/8 AdultArrivals reach names ⊆ EXPECTED_REACHES", a8_ok)

    all_ok = all([a1, a2, a3, a4, a5, a6, a7, a8])
    print()
    print("=" * 60)
    print(f"OVERALL: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6.2: Run the smoke probe**

```bash
micromamba run -n shiny python scripts/_probe_baltic_with_dane.py
```

Expected: `OVERALL: PASS` (8/8 assertions). If any assertion fails, the probe prints the specific reach/file/junction that's broken; fix manually and rerun.

---

## Task 7: Run all verification gates

- [ ] **Step 7.1: Run test_baltic_geometry.py**

```bash
micromamba run -n shiny python -m pytest tests/test_baltic_geometry.py -v
```

Expected: all 9+ tests PASS (existing tests + parametrized adjacency-pair tests for new Danė chain).

- [ ] **Step 7.2: Run fixture-load smoke**

```bash
micromamba run -n shiny python -m pytest tests/test_baltic_example.py::test_fixture_loads_and_runs_3_days -v
```

Expected: PASS. 3-day sim succeeds with 14 reaches, no crashes.

- [ ] **Step 7.3: Run other example fixtures (regression check)**

```bash
micromamba run -n shiny python -m pytest tests/test_baltic_example.py tests/test_fixture_loads.py -v
```

Expected: all existing tests PASS (no regression in example_a, example_b, example_baltic, WGBAST four).

---

## Task 8: First commit (data + test + smoke probe)

- [ ] **Step 8.1: Clean up temp fixture**

```bash
rm -rf tests/fixtures/_dane_temp/
rm -rf tests/fixtures/example_baltic.bak/  # if probe + tests passed
```

- [ ] **Step 8.2: Commit Task 2-7 changes**

```bash
git add \
    tests/fixtures/example_baltic/Dane_*-Depths.csv \
    tests/fixtures/example_baltic/Dane_*-Vels.csv \
    tests/fixtures/example_baltic/Dane_*-TimeSeriesInputs.csv \
    tests/fixtures/example_baltic/KlaipedaStrait-*.csv \
    tests/fixtures/example_baltic/Shapefile/BalticExample.* \
    tests/fixtures/example_baltic/BalticExample-AdultArrivals.csv \
    configs/example_baltic.yaml \
    tests/test_baltic_geometry.py \
    scripts/_probe_baltic_with_dane.py

git commit -m "$(cat <<'EOF'
feat(example_baltic): add Danė river (4 reaches) + Klaipėda Strait

example_baltic grows from 9 to 14 reaches:
- Dane_Upper, Dane_Middle, Dane_Lower, Dane_Mouth (4 Danė reaches via
  v0.50.0 Auto-split N=4 on Klaipėda OSM data, calibration cloned from
  Minija; per-reach pspc 150/100/50/0)
- KlaipedaStrait (sea-edge transition, hand-written single-polygon at
  Smiltynė-Klaipėda strait, calibration cloned from BalticCoast with
  fish_pred_min: 0.700)

Junction wiring uses fresh IDs 10-14; KlaipedaStrait drains to existing
sea sink junction 6 (parallel to BalticCoast). 28 yearly AdultArrivals
rows appended targeting Dane_Lower (2011-2038, 7 fish/yr).

Updates tests/test_baltic_geometry.py: EXPECTED_REACHES +5,
CELL_COUNT_MAX 2200→2800, 5 new DIRECT_ADJACENCY_PAIRS for Danė chain,
SPAWNING_REACHES +Dane_Upper/Middle/Lower, KlaipedaStrait added to
non-spawning assertion.

New scripts/_probe_baltic_with_dane.py (~70 LOC, 8 assertions) verifies
fixture integrity post-merge.

Closes the v0.50.0 deferred-followup ("use these new buttons end-to-end
to add the Danė river"). Defers Tornionjoki calibration to v0.52.0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Release commit + tag

- [ ] **Step 9.1: Bump version in `pyproject.toml`**

Change `version = "0.50.0"` to `version = "0.51.0"` (line 7).

- [ ] **Step 9.2: Bump version in `src/salmopy/__init__.py`**

Change `__version__ = "0.50.0"` to `__version__ = "0.51.0"` (line 3).

- [ ] **Step 9.3: Prepend CHANGELOG entry**

Prepend to `CHANGELOG.md` after the heading:

```markdown
## [0.51.0] — 2026-04-26

### Added — Danė river fixture

example_baltic grows from 9 to 14 reaches with the addition of the Danė
river (~89 km, Klaipėda, Lithuania) and the Klaipėda Strait sea-edge
reach. First end-to-end exercise of the v0.50.0 Find/Auto-extract/Auto-split
buttons on real OSM data.

- 4 Danė reaches (Upper/Middle/Lower/Mouth) via Auto-split N=4, calibration
  cloned from Minija. Per-reach pspc: 150/100/50/0. Total 300 smolts/yr.
- KlaipedaStrait sea-edge transition reach, calibration cloned from
  BalticCoast (`fish_pred_min: 0.700`). Joins existing sea sink junction 6
  parallel to BalticCoast.
- 28 yearly AdultArrivals rows appended (2011-2038, 7 fish/yr) targeting
  Dane_Lower.

### Updates
- `tests/test_baltic_geometry.py`: EXPECTED_REACHES +5, CELL_COUNT_MAX
  2200→2800, 5 new DIRECT_ADJACENCY_PAIRS for Danė chain, SPAWNING_REACHES
  +3 Danė freshwater reaches, KlaipedaStrait added to non-spawning
  assertion.
- New `scripts/_probe_baltic_with_dane.py` (~70 LOC, 8 assertions).

### Notes
- Closes PR-X deferred from v0.50.0 release notes.
- v0.52.0 (next): Tornionjoki juvenile-growth calibration (Workstream B
  from v0.46+).

```

- [ ] **Step 9.4: Final test gate**

```bash
micromamba run -n shiny python -m pytest tests/test_baltic_geometry.py tests/test_baltic_example.py -v
```

Expected: all PASS.

- [ ] **Step 9.5: Commit release**

```bash
git add pyproject.toml src/salmopy/__init__.py CHANGELOG.md
git commit -m "$(cat <<'EOF'
release(v0.51.0): Danė river fixture

Adds Danė river (4 reaches) + Klaipėda Strait to example_baltic, exercising
the v0.50.0 Create Model panel buttons end-to-end on real OSM data. Closes
PR deferred from v0.50.0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 9.6: Create annotated tag**

```bash
git tag -a v0.51.0 -m "v0.51.0: Danė river + Klaipėda Strait added to example_baltic"
```

- [ ] **Step 9.7: Verify final state**

```bash
git log --oneline -5
git tag -l v0.51.0 -n1
```

Expected:
- HEAD points to release commit.
- Tag `v0.51.0` resolves to release commit.
- Two implementation commits on the branch (Task 8 + Task 9).
