# v0.51.0 — Add Danė river to example_baltic fixture

**Status:** Design — pending review
**Date:** 2026-04-26
**Origin:** Deferred from v0.50.0 release notes ("v0.51.0: use these new buttons end-to-end to add the Danė river to example_baltic"). The natural integration test for v0.50.0's three new Create Model panel buttons.

## Summary

Add the Danė river (~89 km — Wikipedia/EU rivers gazetteer; flows through
Klaipėda directly into the Klaipėda Strait → Baltic Sea, NOT through the
Nemunas delta) to `example_baltic` as **5 new reaches**: Dane_Mouth,
Dane_Lower, Dane_Middle, Dane_Upper, plus KlaipedaStrait. example_baltic
grows from 9 reaches (~1591 cells, v0.30.1 baseline) to 14 reaches
(~1791-1991 cells projected).

**Note on Danė salmon habitat**: the lower ~5 km of Danė inside Klaipėda is
channelized; a weir near the city limits is the upstream extent of historical
salmon migration. Spec sets `frac_spawn=0` for `Dane_Mouth` (brackish) and
keeps reach-extraction inclusive (the panel will likely include the weir-blocked
section in `Dane_Lower`; biological calibration is downstream concern).

This is a **fixture-extension release** — no code changes to `app/modules/`
or `src/salmopy/`. The work is the v0.50.0 buttons performed end-to-end on
real Klaipėda OSM data, plus a manual merge of the exported reaches into
the existing example_baltic fixture, plus a smoke probe to defend against
silent breakage.

## Out of scope (deferred)

- "Merge fixture A into fixture B" UI button — v0.52+.
- Per-param Danė biological calibration beyond clone-and-tune-pspc — v0.51.x or v0.52.x.
- Lithuanian-language reach segment names (Klaipėda/Kretinga/Kūlupėnai/Vyžuonai) — not in scope; English `Dane_*` matches the existing reach-naming convention (Nemunas/Atmata/Minija are river-named, Skirvyte/Leite/Gilija are tributary-named).
- Updating `BalticExample-InitialPopulations.csv` for Danė-natal cohort — defaults to 0 (returners populate via AdultArrivals).
- Tornionjoki juvenile-growth calibration (Workstream B from v0.46+) — v0.52.0.

## Architecture

**One operator workflow** (Section 2 below) using the v0.50.0 Create Model
panel buttons end-to-end on Klaipėda OSM data, plus a manual YAML/CSV/shapefile
merge into the existing example_baltic fixture, plus a smoke probe.

**Five new reaches** added to example_baltic:

| Reach | Calibration source | Pspc smolts/yr | Junction (up→dn) |
|-------|-------------------|----------------|-------------------|
| Dane_Upper | clone Minija | 150 | 10 → 11 |
| Dane_Middle | clone Minija | 100 | 11 → 12 |
| Dane_Lower | clone Minija | 50 | 12 → 13 |
| Dane_Mouth | clone Minija (pspc=0; brackish) | 0 | 13 → 14 |
| KlaipedaStrait | clone **BalticCoast** (saline strait, seal+cod predation; NOT lagoon) | n/a (sea reach) | 14 → 6 |

Total Danė pspc = ~300 smolts/yr (small historical population, smaller than
Minija's 1200 — Danė has urban/pollution pressures from Klaipėda city).

**KlaipedaStrait calibration source = BalticCoast** (revised from the initial
proposal of CuronianLagoon). Klaipėda Strait is a saline (5–7 PSU) tidal
channel with seal/cod predation pressure typical of the open Baltic, NOT
the brackish (~0–7 PSU) lagoon predation regime (pike, perch, cormorants).
Cloning BalticCoast's params (`fish_pred_min: 0.650`, etc.) is the
ecologically correct analog. Spec earlier inverted lagoon-vs-sea sides; corrected.

**Junction wiring** verified against `configs/example_baltic.yaml`:
- Existing max junction ID = **6** (BalticCoast.downstream_junction).
- Junction 5 is the lagoon-confluence hub (6 reaches share `downstream=5`:
  CuronianLagoon, Atmata, Sysa, Skirvyte, Leite, Gilija).
- Junction 6 is the sea sink (BalticCoast.downstream, no consumer).

The Danė chain uses fresh IDs 10–14 (gap from 7–9 left for clarity). KlaipedaStrait
drains to junction **6** (the existing sea sink) — Danė smolts join the open Baltic
parallel to BalticCoast, NOT through the lagoon. This preserves the cardinality-1
sea-sink invariant (junction 6 has multiple producers — BalticCoast and KlaipedaStrait —
but no consumer).

**The Mesh shapefile is `Shapefile/BalticExample.shp`** (NOT `example_baltic.shp`
— corrected from initial spec). DBF column for reach name is `REACH_NAME` (uppercase).

**Files modified/created** (concrete list):

| File | Action | Notes |
|------|--------|-------|
| `configs/example_baltic.yaml` | Modify | +5 reach blocks at the appropriate position in the `reaches:` section |
| `tests/fixtures/example_baltic/Dane_Mouth-Depths.csv` | Create | from Create Model export |
| `tests/fixtures/example_baltic/Dane_Mouth-Vels.csv` | Create | from export |
| `tests/fixtures/example_baltic/Dane_Mouth-TimeSeriesInputs.csv` | Create | from export |
| (same 3 files × 3 more reaches) | Create | Dane_Lower, Dane_Middle, Dane_Upper |
| `tests/fixtures/example_baltic/KlaipedaStrait-Depths.csv` | Create | hand-written (sea reach) |
| `tests/fixtures/example_baltic/KlaipedaStrait-Vels.csv` | Create | hand-written |
| `tests/fixtures/example_baltic/KlaipedaStrait-TimeSeriesInputs.csv` | Create | hand-written |
| `tests/fixtures/example_baltic/Shapefile/BalticExample.shp` (and .dbf/.shx/.prj) | Modify | append 5 polygons |
| `tests/fixtures/example_baltic/BalticExample-AdultArrivals.csv` | Modify | append 26 yearly rows (one per year 2011–2036) targeting `Dane_Lower` (NOT Dane_Mouth — natal-river concept needs pspc>0); ~7 fish/yr (1.5% of yearly total ~465). Format matches existing 11-column header: `Year,Species,Reach,Number,Fraction female,Arrival start,Arrival peak,Arrival end,Length min,Length mode,Length max`. |
| `tests/test_baltic_geometry.py` | **Modify** | Add the 5 new reach names to `EXPECTED_REACHES`; raise `CELL_COUNT_MAX` from 2200 to ~2800; add new entries to `DIRECT_ADJACENCY_PAIRS` (Dane_Upper↔Middle, Middle↔Lower, Lower↔Mouth, Mouth↔KlaipedaStrait, KlaipedaStrait↔BalticCoast); add `Dane_Upper`/`Dane_Middle`/`Dane_Lower` to `SPAWNING_REACHES`; add `KlaipedaStrait` to the non-spawning-reaches assertion (alongside BalticCoast and CuronianLagoon). |
| `scripts/_probe_baltic_with_dane.py` | Create | smoke probe ~70 LOC, 8 assertions |
| `pyproject.toml` | Modify | version bump 0.50.0 → 0.51.0 |
| `src/salmopy/__init__.py` | Modify | version bump |
| `CHANGELOG.md` | Modify | prepend v0.51.0 entry |

## Components & data flow (the workflow)

Step-by-step operator runbook:

1. Start local Shiny:
   `micromamba run -n shiny python -m shiny run --port 9050 app/app.py`

2. In browser, open Create Model panel.

3. Type "Klaipėda, Lithuania" → click 🔍 Find. (Disambiguation: typing the
   full "Klaipėda, Lithuania" picks the city over the county/district
   homonyms; Nominatim's `limit=1` returns the highest-ranked result.)
   - Region dropdown auto-sets to "lithuania".
   - Map zooms to bbox (~lat 55.71, lon 21.15, zoom ~13). The Nominatim bbox
     covers only Klaipėda city (~13 km × 9 km). To extract the FULL Danė
     centerline (which extends ~70 km inland to Kretinga), the operator must
     manually pan/zoom-out the map to cover lat 55.7–56.0, lon 21.0–21.4
     BEFORE clicking 🌊 Sea / Auto-extract. (The OSM Overpass query in
     `_do_fetch_rivers` uses the current map view's bbox.)
   - Rivers + Water layers auto-fetched (~10 s).

4. Click 🌊 Sea.
   - Marine Regions WFS returns the **full Baltic Sea polygon** (the IHO
     Sea Areas dataset has no separate "Klaipėda Strait" entry — the strait
     is part of the Baltic Sea). `_pick_mouth_from_sea` will work fine
     because Danė's mouth touches the Baltic polygon directly.
   - `_sea_gdf` populated; Sea layer rendered.

5. (Optional) Adjust Strahler slider down to ≥2 if Danė centerline doesn't
   appear at default ≥3 (Danė is small; per OSM Strahler tagging, mainstem
   may be Strahler 2 in upper sections).

6. Click ✨ Auto-extract.
   - `filter_polygons_by_centerline_connectivity` drops polygons not
     connected to Danė centerline.
   - Toast: "Kept N of M polygons in the main river system."
   - **CRITICAL visual checkpoint** (high-probability port-flood scenario):
     Klaipėda has dense port geometry — dredged harbor channels, the
     Klaipėda port basin, marina inlets — many of these touch the Danė
     centerline directly via OSM `natural=water` polygons. Auto-extract's
     BFS will pull in the entire connected port network. Inspect the map
     after the toast: if the kept-polygons set extends south into the
     Klaipėda port (visible as a wide harbor on the map) or includes
     ferry slips, click-deselect those polygons via the existing 💧 Lagoon
     mode (toggle the button → click each unwanted polygon → it
     un-highlights). This is expected workflow, not a fallback.

7. Click ⚡ Auto-split with N=4 (default).
   - Mouth auto-detected: closest centerline endpoint to Sea polygon.
   - 4 reaches produced: Mouth, Lower, Middle, Upper.
   - Toast: "Split into 4 reaches: Mouth (X), Lower (Y), Middle (Z), Upper (W)."
   - **Visual checkpoint** (added per Loop 1 review): inspect the colored
     reach overlays on the map. "Mouth" should be the downstream-most
     (closest to the Baltic at Klaipėda); "Upper" should be furthest inland
     (toward Kretinga). If the colors are inverted, the centerline's
     mouth-to-source orientation failed — proceed but rename inverted in
     step 9 (e.g., what shows as "Mouth" gets renamed to "Dane_Upper").

8. Click 📦 Export → save as temp fixture `tests/fixtures/_dane_temp/`. Per
   v0.49.0, the export produces loader-compatible per-cell CSVs.

9. Switch to Edit Model panel → from the fixture-load dropdown, select
   `_dane_temp` (Edit Model loads from disk per v0.45.3, NOT from Create
   Model's in-memory state). Rename:
   - Mouth → Dane_Mouth
   - Lower → Dane_Lower
   - Middle → Dane_Middle
   - Upper → Dane_Upper

   (Uses the v0.45.3 reach-rename feature; updates `_dane_temp/`'s
   shapefile DBF + YAML config + CSV stems in place.)

10. **Backup-first**: `cp -r tests/fixtures/example_baltic tests/fixtures/example_baltic.bak`. The merge modifies the shapefile in place; if it goes wrong, restore from `.bak`.

11. Manual merge into `tests/fixtures/example_baltic/`:
    a. Copy `_dane_temp/Dane_*.csv` (12 files: 4 reaches × 3 file types) →
       `tests/fixtures/example_baltic/`.
    b. **Shapefile append** (use Python, not QGIS for reproducibility):
       ```python
       import geopandas as gpd
       import pandas as pd

       baltic = gpd.read_file("tests/fixtures/example_baltic/Shapefile/BalticExample.shp")
       dane = gpd.read_file("tests/fixtures/_dane_temp/Shapefile/<dane_temp>.shp")
       merged = gpd.GeoDataFrame(pd.concat([baltic, dane], ignore_index=True), crs=baltic.crs)
       # Verify column-set match BEFORE saving
       assert list(merged.columns) == list(baltic.columns), \
           f"Column mismatch: baltic={list(baltic.columns)}, dane={list(dane.columns)}"
       merged.to_file("tests/fixtures/example_baltic/Shapefile/BalticExample.shp")
       # geopandas regenerates .shp/.dbf/.shx/.prj/.cpg automatically.
       ```
       The DBF reach-name column is `REACH_NAME` (verified in
       `tests/test_baltic_geometry.py:88`).

    c. Manual edit to `configs/example_baltic.yaml`: append 5 reach blocks
       in the `reaches:` section after `BalticCoast:`. Sample (Dane_Upper):
       ```yaml
         Dane_Upper:                  # upper Dane, ~22 km, best spawning
           pspc_smolts_per_year: 150
           drift_conc: 1.5e-08        # cloned from Minija
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
       ```
       Repeat for `Dane_Middle` (pspc=100, junctions 11→12), `Dane_Lower`
       (pspc=50, junctions 12→13), `Dane_Mouth` (pspc=0, junctions 13→14;
       NO `pspc_smolts_per_year` key OR set to 0). Then KlaipedaStrait —
       see step 11d below.

    d. Hand-write KlaipedaStrait reach block (clone BalticCoast,
       upstream=14, downstream=6):
       ```yaml
         KlaipedaStrait:              # saline strait, Smiltynė–Klaipėda port channel
           drift_conc: 0.2e-09        # cloned from BalticCoast
           search_prod: 1.00e-07
           shelter_speed_frac: 0.0
           prey_energy_density: 1500
           drift_regen_distance: 20000
           shading: 0.02
           fish_pred_min: 0.700       # slightly less than BalticCoast (0.650) — sheltered channel
           terr_pred_min: 0.995
           light_turbid_coef: 0.007
           light_turbid_const: 0.004
           max_spawn_flow: 999
           shear_A: 0.001
           shear_B: 0.15
           upstream_junction: 14
           downstream_junction: 6
           time_series_input_file: "KlaipedaStrait-TimeSeriesInputs.csv"
           depth_file: "KlaipedaStrait-Depths.csv"
           velocity_file: "KlaipedaStrait-Vels.csv"
       ```

    e. Hand-write KlaipedaStrait CSVs. Format = same as BalticCoast (10
       flow columns; per `_parse_hydraulic_csv`'s contract). Cell count
       depends on the polygon (step 11f). For a 1 km × 5 km strait with
       BalticCoast's hex-cell resolution, expect ~50–100 cells (BalticCoast
       has 64 cells per its DBF row count). Sample structure:
       ```
       ; Depths for Baltic example — KlaipedaStrait
       ; 5–14 m typical depth, tidal channel between Smiltynė & Klaipėda
       ; CELL DEPTHS IN METERS
       10,Number of flows in table,,,,,,,,,,,,,,,,,,
       ,10.0,20.0,30.0,40.0,60.0,90.0,130.0,200.0,400.0,1000.0
       1,8.0,8.5,9.0,9.5,10.5,12.0,13.5,15.0,18.0,22.0
       2,8.5,9.0,9.5,10.0,11.0,12.5,14.0,15.5,18.5,22.5
       ... (repeat for each cell from step 11f)
       ```
       Velocities: 0.1–0.3 m/s near-uniform (tidal exchange is weak in the
       strait). TimeSeriesInputs: copy BalticCoast's flat schedule.

    f. Hand-trace the KlaipedaStrait polygon. The strait is at approximately
       55.71°N–55.74°N, 21.10°E–21.12°E (Smiltynė side: ~55.71°, 21.10°;
       Klaipėda side: ~55.71°, 21.12°). Approximate WKT (~1 km × 5 km
       channel between the lagoon outlet and the open Baltic):
       ```python
       from shapely.geometry import Polygon
       klaipeda_strait = Polygon([
           (21.103, 55.685),  # SW corner — south of strait at Baltic edge
           (21.130, 55.685),  # SE corner — south Klaipėda port
           (21.130, 55.745),  # NE corner — north Klaipėda waterfront
           (21.103, 55.745),  # NW corner — north Smiltynė tip
           (21.103, 55.685),  # close
       ])
       # Sanity: ~1.7km wide × 6.7km long in degrees → ~1km × 5km in
       # meters at 56°N (degree-of-longitude shrinks ~0.56× at this
       # latitude). Refine in QGIS or via Marine Regions if needed.
       ```
       Add this polygon to the merged shapefile as a single feature with
       REACH_NAME='KlaipedaStrait', then re-grid via `generate_cells` to
       produce the actual cell count + IDs that match the CSVs. The
       hand-written CSVs in step 11e must have one row per cell produced
       by the regrid.

12. **Update `tests/test_baltic_geometry.py`** — required, NOT optional:
    - Add to `EXPECTED_REACHES`: `Dane_Upper`, `Dane_Middle`, `Dane_Lower`,
      `Dane_Mouth`, `KlaipedaStrait` (set grows from 9 → 14 entries).
    - Raise `CELL_COUNT_MAX` from 2200 to 2800 (allow new ~200–400 cells).
    - Add to `DIRECT_ADJACENCY_PAIRS` (must be < 0.5 km on cell grid):
      `(Dane_Upper, Dane_Middle)`, `(Dane_Middle, Dane_Lower)`,
      `(Dane_Lower, Dane_Mouth)`, `(Dane_Mouth, KlaipedaStrait)`,
      `(KlaipedaStrait, BalticCoast)`.
    - Add `Dane_Upper`, `Dane_Middle`, `Dane_Lower` to `SPAWNING_REACHES`
      (NOT `Dane_Mouth` — pspc=0 → no spawning expected).
    - Add `KlaipedaStrait` to `test_non_spawning_reaches_have_zero_frac_spawn`'s
      reach tuple alongside `CuronianLagoon` and `BalticCoast`.

13. Run new smoke probe:
    `micromamba run -n shiny python scripts/_probe_baltic_with_dane.py`
    → 8 assertions (Section "Smoke probe responsibilities" below).

14. Run regression test:
    `micromamba run -n shiny python -m pytest tests/test_baltic_example.py::test_fixture_loads_and_runs_3_days tests/test_baltic_geometry.py -v`
    → fixture-load smoke + all 9 geometry tests PASS with 14 reaches.

15. **Update `BalticExample-AdultArrivals.csv`** — required (NOT optional;
    spec table marks it as a required modify file). Append 26 yearly rows
    (one per year 2011–2036) targeting `Dane_Lower` (NOT Dane_Mouth — natal
    homing requires non-zero pspc). Each row: `<year>,BalticAtlanticSalmon,Dane_Lower,7,0.55,5/15/<year>,7/1/<year>,8/31/<year>,55,68,85`.
    Why Dane_Lower: pspc=50 is the smallest non-zero pspc among Danė reaches
    (matches the small-population narrative); homers naturally redistribute
    upstream during in-river migration. 7 fish/yr × 26 years = 182 new rows
    appended; total file grows from 182 → 364 rows.

## Calibration plan (per Q4 — clone-and-go)

**Dane_Upper, Middle, Lower, Mouth**: clone Minija's params verbatim — the
COMPLETE param set (~30 keys) is copied from Minija's YAML block, except
that `pspc_smolts_per_year`, `upstream_junction`, `downstream_junction`, and
the 3 file-path fields are reset per the Architecture table. The sample
YAML in step 11c shows the full Dane_Upper block.

Per-reach pspc rationale:
- **Dane_Mouth: 0** — salmon don't spawn at the river mouth (brackish water,
  no gravel substrate). Set `frac_spawn=0` via the YAML's `pspc=0` (or omit
  the key entirely; loader defaults to 0).
- **Dane_Lower: 50** — lower Danė runs through Klaipėda city limits (~5 km);
  urban pollution + a weir limit upstream salmon migration. Treated as
  natal-river endpoint for AdultArrivals (homers redistribute upstream
  in-river).
- **Dane_Middle: 100** — main spawning zone if any; rural mid-river.
- **Dane_Upper: 150** — best spawning habitat; cooler water, less pollution,
  natural substrate.

Total = 300 smolts/yr. Smaller than Minija's 1200 — Danė is shorter
(~89 km vs Minija's ~204 km) and has had documented salmon-population
declines from urban pressures (per Lithuanian fisheries reports).

**KlaipedaStrait**: clone **BalticCoast** (revised from initial CuronianLagoon
proposal per Loop 1 architect review):
- `fish_pred_min: 0.700` — slightly less than BalticCoast's 0.650 to reflect
  the sheltered nature of the strait (still saline, still seal/cod predation,
  but reduced compared to open sea).
- All other params (`drift_conc: 0.2e-09`, `search_prod: 1.00e-07`,
  `shelter_speed_frac: 0.0`, etc.) cloned from BalticCoast verbatim.

KlaipedaStrait is a saline sea channel between the lagoon outlet and the
open Baltic; ecologically closer to BalticCoast (open sea) than to
CuronianLagoon (brackish lagoon). Cloning BalticCoast gives the correct
seal+cod predation regime for smolts transiting the strait. The 0.700
fudge accounts for the strait's narrower geometry (some shelter from the
quay walls and the Curonian Spit).

## Junction wiring (verified)

Existing example_baltic junction IDs in use: 1, 2, 3, 5, 6 (max=6, verified
by reading `configs/example_baltic.yaml`). Junction 5 is the lagoon-confluence
hub (6 reaches share `downstream=5`). Junction 6 is the unique sea sink
(`BalticCoast.downstream`, no consumer).

The Danė chain uses fresh IDs 10–14:

```
Dane_Upper:     upstream=10, downstream=11
Dane_Middle:    upstream=11, downstream=12
Dane_Lower:     upstream=12, downstream=13
Dane_Mouth:     upstream=13, downstream=14
KlaipedaStrait: upstream=14, downstream=6  # joins existing sea sink
```

After the merge: junctions 1–14 used; junction 6 has 2 producers
(BalticCoast, KlaipedaStrait) — both feed the open Baltic. Sea sink
invariant preserved: `set(all_downstream) - set(all_upstream) == {6}`.

The smoke probe asserts this invariant directly (assertion 4):
`set(downstream_junctions) - set(upstream_junctions) == {6}`.

## Error handling & edge cases

| Risk | Mitigation |
|------|------------|
| Auto-extract drops Danė centerline (Strahler too high; Danė is small) | Workflow step 5: lower Strahler to ≥2 before Auto-extract. Smoke probe step 11 asserts all 4 Dane_* reaches non-empty. |
| Auto-split assigns wrong polygons to Upper vs Lower (along-channel direction backwards) | `_orient_centerline_mouth_to_source` proven since v0.47.0. Manual visual check at step 7 — if Upper looks like Mouth on the map, the centerline orientation failed; rename via Edit Model post-hoc. |
| Mouth auto-detection picks wrong endpoint (Danė splits in Klaipėda port; centerline may have multiple endpoints) | `_pick_mouth_from_sea` uses closest endpoint to Sea. If wrong endpoint chosen, use click-mouth fallback: deselect 🌊 Sea before clicking ⚡, then click the actual mouth on the map. |
| OSM data sparse (Danė shows only 2-3 polygons; Auto-split N=4 produces empty reaches) | The N>polygons toast warns upfront. Workflow contingency: rerun with N=2 (Mouth + Upper). Document the actual N in release notes. |
| Junction ID collision with existing example_baltic IDs | Spec uses IDs 10+; verify at spec-time. Smoke probe asserts each `upstream_junction`/`downstream_junction` is referenced consistently (graph integrity). |
| YAML formatting mismatch between exported reach blocks and example_baltic style | Existing example_baltic uses 2-space indent + comments. Hand-edit during merge to match. |
| Shapefile DBF column-set mismatch | Both produced by the same Create Model export pipeline; columns should match. Smoke probe asserts shapefile column-set is identical pre- and post-merge. |
| CSV stem collision in `tests/fixtures/example_baltic/` | Reach names start with `Dane_` or are `KlaipedaStrait` — no collision with existing 9 reach names. |
| Klaipėda Strait polygon overlap with existing BalticCoast cells | Manual: define KlaipedaStrait polygon to be the narrow channel BETWEEN the lagoon and the open Baltic, NOT overlapping existing BalticCoast. Visual inspection during merge. |
| 3-day fixture-load smoke fails after merge | Most likely: junction wiring inconsistency. Probe outputs which assertion failed; fix manually, rerun. |
| `export_template_csvs` format mismatch (would have been a v0.49.0-era bug) | Closed by v0.49.0; per-cell CSVs now load through `_parse_hydraulic_csv`. Smoke probe verifies by loading each new CSV. |

## Smoke probe responsibilities

`scripts/_probe_baltic_with_dane.py` (~70 LOC) checks 8 assertions:

```python
EXPECTED_REACHES = {
    "Nemunas", "Atmata", "Minija", "Sysa", "Skirvyte", "Leite",
    "Gilija", "CuronianLagoon", "BalticCoast",
    "Dane_Upper", "Dane_Middle", "Dane_Lower", "Dane_Mouth", "KlaipedaStrait",
}
SEA_SINK_JUNCTION = 6  # the unique downstream-only junction
```

1. **YAML parses with 14 reaches**: `yaml.safe_load(...).reaches.keys() == EXPECTED_REACHES`.
2. **Each reach has 3 CSVs**: for each reach name, `<reach_name>-Depths.csv`,
   `<reach_name>-Vels.csv`, `<reach_name>-TimeSeriesInputs.csv` exist in
   `tests/fixtures/example_baltic/`.
3. **Each per-cell CSV loads via `_parse_hydraulic_csv`** (validates v0.49.0 format):
   `from salmopy.io.hydraulics_reader import _parse_hydraulic_csv;
   df = _parse_hydraulic_csv(path); assert df.shape[1] == 10` (10 flow columns).
4. **Junction graph integrity**: collect all `upstream_junction` and
   `downstream_junction` values from the YAML;
   `set(downstream_junctions) - set(upstream_junctions) == {SEA_SINK_JUNCTION}` (cardinality 1 — only junction 6 is a sea sink).
5. **Shapefile feature count ≥ `len(reaches)`** (each reach has at least 1 cell;
   a non-empty fixture has many cells per reach).
6. **Shapefile `REACH_NAME` column contains exactly the 14 expected names**:
   `set(gdf['REACH_NAME'].unique()) == EXPECTED_REACHES`.
7. **Per-reach minimum cell counts** (tighter than a global range):
   each Dane_* reach ≥ 30 cells; KlaipedaStrait ≥ 30 cells; existing 9
   reaches retain their v0.30.1 cell counts ± 10%. Total: 1591 + (5 × ≥30) + buffer.
8. **AdultArrivals reach-name consistency**: every `Reach` value in
   `BalticExample-AdultArrivals.csv` is in `EXPECTED_REACHES` (catches
   typos like `dane_lower` vs `Dane_Lower`).

If any assertion fails, the probe prints the specific reach/file/junction
that's broken so the operator can fix the merge and rerun.

If any assertion fails, the probe prints the specific reach/file/junction
that's broken so the operator can fix the merge and rerun.

## Testing

### Existing test gates

`tests/test_baltic_example.py::test_fixture_loads_and_runs_3_days[example_baltic]`
must continue to PASS after the merge. Loads YAML, instantiates simulation,
runs 3 simulated days, verifies no crashes. Does NOT check biological
correctness — just structural integrity.

### New smoke probe

Per Section 3, ~50 LOC, 7 assertions. Run manually post-merge as a self-check
before committing. NOT a pytest fixture — one-shot probe that prints
PASS/FAIL per assertion.

### No new pytest cases

Deliberately. The work is data-addition, not code-addition. Existing tests
cover the loaders. Auto-extract/Auto-split/Find handlers are tested in
v0.50.0 (38 unit tests). A "Danė-specific behavior" test would be premature
— biological calibration is out of scope per Q4.

### Manual verification checklist

Run before commit:

1. **Workflow walkthrough** — perform Section 2 steps 1–15 in a clean checkout. Verify each step produces expected toast / state change.
2. **Smoke probe** — `micromamba run -n shiny python scripts/_probe_baltic_with_dane.py` → 8/8 PASS.
3. **Geometry tests** — `micromamba run -n shiny python -m pytest tests/test_baltic_geometry.py -v` → all 9 (existing 6 + new 3 adjacency-pair checks for Danė chain) PASS. The updates from step 12 (EXPECTED_REACHES, CELL_COUNT_MAX, DIRECT_ADJACENCY_PAIRS, SPAWNING_REACHES) must be applied before this passes.
4. **Fixture-load smoke** — `micromamba run -n shiny python -m pytest tests/test_baltic_example.py::test_fixture_loads_and_runs_3_days -v` → PASS.
5. **Other example fixtures unaffected** — `micromamba run -n shiny python -m pytest tests/test_baltic_example.py tests/test_fixture_loads.py -v` → all existing tests PASS (no regression in example_a, example_b, the WGBAST four).
6. **Visual map QA** — load the merged fixture in the Edit Model panel; verify all 14 reach polygons render at sensible Klaipėda+Nemunas geography; no overlap; no orphan polygons.

## Commit cadence

Per the v0.47–v0.50 pattern, but lighter (data-addition release):

1. `feat(example_baltic): add Danė river (4 reaches) + Klaipėda Strait` —
   single commit covering YAML edit + 15 new CSVs + shapefile changes +
   smoke probe + AdultArrivals update.

2. `release(v0.51.0): Danė river fixture` — version bump + CHANGELOG.

Two commits total.

## Required dependencies

No new dependencies. Existing geopandas, shapely, pyyaml, pytest cover
everything.

## Risks / open questions for plan-time review

(Most Loop 1 risks resolved inline in this revision — junction IDs verified at 6
max, KlaipedaStrait switched to BalticCoast clone, AdultArrivals format pinned,
CSV format spec'd, polygon coords given, mesh filename corrected.)

1. **Auto-extract port-flood is high-probability**, not edge case (per Loop 1
   architect review). Klaipėda has dense port geometry — dredged harbor
   channels, port basin, marina inlets — many touch the Danė centerline.
   Workflow step 6 documents this explicitly with manual click-deselect via
   💧 Lagoon mode as the expected (not fallback) procedure.

2. **Auto-split orientation check** — workflow step 7's visual checkpoint
   catches inverted Mouth/Upper labelling before rename. Renames in step 9
   handle the swap if needed.

3. **KlaipedaStrait polygon is approximate** — coordinates given in step 11f
   are first-pass (~55.685–55.745°N, 21.103–21.130°E). Operator should
   refine via QGIS or visual inspection before saving if the polygon
   crosses the Curonian Spit's land area (the strait runs north-south
   between Smiltynė and Klaipėda; ensure the polygon stays in water).

4. **Operator must zoom out before clicking Auto-extract** to capture the
   full Danė centerline up to Kretinga (~70 km from Klaipėda). The Nominatim
   bbox covers only the city. Step 3 explicitly notes this.

5. **`generate_cells` regrid for KlaipedaStrait is the source of truth for
   cell count**: hand-written CSVs in step 11e must have exactly the cell
   count produced by the regrid. Operator runs the regrid first, counts the
   rows in the resulting shapefile, then writes that many CSV rows. The
   smoke probe assertion 7 enforces the count match.

6. **Pre-existing test_baltic_geometry.py contract** must be updated atomically
   with the fixture changes (step 12). Without these updates, CI fails on the
   first push (test asserts EXACT 9-reach set; merging adds 5 → fail).
