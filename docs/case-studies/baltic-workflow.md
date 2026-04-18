# Building a Real-Data Case Study: The Baltic Example

A reference walkthrough of how the `example_baltic` case study
(`configs/example_baltic.yaml`) was built from real-world data sources
(OpenStreetMap, Marine Regions, EMODnet Bathymetry). Use this as a template
for constructing similar case studies for other salmon-bearing systems
(e.g. Daugava, Vistula, Scottish coast, or a Norwegian fjord).

Status: landed on `master` as of tag **v0.30.0** (2026-04-18).
Full implementation plan preserved at
`docs/superpowers/plans/2026-04-18-baltic-real-data-upgrades.md`.

---

## 1. What the Baltic case study models

- **Species**: Baltic Atlantic salmon (anadromous, iteroparous).
- **Geographic scope**: lower Nemunas River + Nemunas Delta + Curonian Lagoon
  + ~15 km Baltic coastal strip off Klaipėda (Lithuania / Kaliningrad).
- **8 reaches** (ASCII keys; OSM names in parentheses):
  - `Nemunas` — main channel
  - `Minija` — Nemunas-basin river feeding the Curonian Lagoon at Klaipėda
  - `Sysa` — Šyša, real Nemunas-Delta channel
  - `Skirvyte` — Skirvytė, reed-choked middle delta branch
  - `Leite` — Leitė, small delta-area tributary
  - `Gilija` — Матросовка (Matrosovka) on the Kaliningrad side
  - `CuronianLagoon` — Kuršių marios (brackish 0–7 PSU)
  - `BalticCoast` — nearshore Baltic strip W of the Curonian Spit
- **Scale**: 1,774 hex/rect cells total. Simulation window: 2011–2036.
- **Marine domain**: three abstract zones (Estuary → Coastal → Baltic
  Proper) declared under `marine.zones` in the YAML.

---

## 2. Data sources

| Purpose | Source | Access | Size |
|---|---|---|---|
| River geometry (Nemunas + tributaries + delta branches) | OpenStreetMap, Geofabrik PBFs | HTTP download → local cache | Lithuania 219 MB, Kaliningrad 27 MB |
| Curonian Lagoon polygon | Marine Regions gazetteer **MRGID 3642** (attempted) → hand-traced fallback | WFS at `geo.vliz.be` | ~50 kB GeoJSON |
| Baltic coastal polygon | Hand-defined rectangle west of Curonian Spit | None (inline coords) | N/A |
| Marine reach bathymetry | EMODnet Bathymetry DTM 1/16 arc-min | WCS at `ows.emodnet-bathymetry.eu` | ~16 MB GeoTIFF for Baltic bbox |
| Strahler stream order | Heuristic from OSM `waterway` tag | (in code) `WATERWAY_STRAHLER` dict | N/A |
| Hydraulic time series (temp/flow/turbidity) | Synthetic (seasonal sinusoids + noise) | Generated inline | ~200 kB × 8 reaches |
| Populations (initial + adult arrivals) | Hand-weighted across reaches | Generated inline | ~2 kB each |

**Attribution requirement**: EMODnet data requires attribution. The
generator's commit messages + CSV headers include:
`Data source: EMODnet Bathymetry Consortium. https://emodnet.ec.europa.eu/en/bathymetry`

---

## 3. Prerequisites

### System dependencies

```bash
micromamba install -n shiny -c conda-forge osmium-tool rasterio
```

- **`osmium-tool`** — CLI used by `_clip_pbf` to slice PBFs to the run bbox
- **`rasterio`** — reads EMODnet GeoTIFFs for per-cell depth sampling

`pyosmium` (Python bindings) ships separately but is already in the `shiny`
env via `micromamba install -n shiny -c conda-forge pyosmium`.

### PBF files (downloaded lazily on first fetch)

`app/modules/create_model_osm.py::ensure_pbf(region)` downloads to
`app/data/osm/<region>-latest.osm.pbf` on first use. For this case study:

- `lithuania` → `https://download.geofabrik.de/europe/lithuania-latest.osm.pbf`
- `kaliningrad` → `https://download.geofabrik.de/russia/kaliningrad-latest.osm.pbf`
  (NB: Kaliningrad uses an **absolute URL override** in `GEOFABRIK_REGIONS`
  because Geofabrik moved Russia regions out of `/europe/`; see Gotcha 1.)

### EMODnet DTM (downloaded lazily on first sample)

`app/modules/bathymetry.py::fetch_emodnet_dtm(bbox)` downloads a GeoTIFF
to `app/data/emodnet/emodnet_<hash>.tif` (gitignored; 15-20 MB for the
Baltic bbox). Coverage ID `emodnet__mean` (note **double underscore** —
see Gotcha 4).

---

## 4. The workflow, step by step

All steps run via the single entry point:

```bash
micromamba run -n shiny python scripts/generate_baltic_example.py
```

Internally, `main()` proceeds as follows:

### Step 4.1: Fetch OSM waterways (merged LT + Kaliningrad)

```python
from modules.create_model_osm import query_waterways

BBOX = (20.80, 54.90, 22.20, 55.95)  # lower Nemunas + delta + lagoon + coast
ww = query_waterways(("lithuania", "kaliningrad"), BBOX)
```

`query_waterways` accepts `str` or `Iterable[str]`; the multi-region fetch
downloads both PBFs, clips each to the bbox via `osmium extract`, and runs
a single `_HydroHandler` over all clipped PBFs.

### Step 4.2: Filter by reach name

```python
REACH_OSM = {
    "Nemunas":  ("waterway", ("Nemunas",)),
    "Minija":   ("waterway", ("Minija",)),
    "Sysa":     ("waterway", ("Šyša",)),
    "Skirvyte": ("waterway", ("Skirvytė",)),
    "Leite":    ("waterway", ("Leitė",)),
    "Gilija":   ("waterway", ("Матросовка", "Matrosovka", "Gilija")),
}

for reach, (col, targets) in REACH_OSM.items():
    hits = ww[ww["nameText"].isin(targets)]
    merged = unary_union(hits.geometry.values)
    clipped = merged.intersection(box(*RIVER_CLIP_BBOX))  # tighter delta bbox
    reach_geoms[reach] = clipped
```

### Step 4.3: Fetch the Curonian Lagoon

Priority chain in `fetch_curonian_lagoon()`:

1. Read cached `app/data/marineregions/curonian_lagoon.geojson` if present
2. Query Marine Regions WFS with `cql_filter=MRGID=3642`. As of
   2026-04-18, **no WFS typeName exposes MRGID 3642**, so this returns
   `None` and we fall through.
3. Return an 18-coord hand-traced polygon (`_fallback_curonian_polygon`).
   Area 2,585 km² vs real 1,584 km² — ~63 % over-sized but accurate along
   the shoreline to about 500 m.

### Step 4.4: Define the Baltic coastal strip

Hand-defined 5-vertex polygon at
`(20.45-20.80, 55.00-55.80)` — offshore of the Curonian Spit. Inline
coordinates in `fetch_baltic_coast()`. About 1,973 km² real area.

### Step 4.5: Generate cells per reach

```python
from modules.create_model_grid import generate_cells

CELL_SIZE_M = {
    "Nemunas":         300,    "Minija":         250,
    "Sysa":            200,    "Skirvyte":       200,
    "Leite":           250,    "Gilija":         250,
    "CuronianLagoon":  2500,   "BalticCoast":    2500,
}

for reach, geom in reach_geoms.items():
    segments = _flatten_geometry(geom)   # handles Multi* + GeometryCollection
    cells = generate_cells(
        {reach: {"segments": segments, "type": reach_type}},
        cell_size=CELL_SIZE_M[reach],
        cell_shape="hexagonal",
    )
```

Cell sizes are tuned so each reach produces 50-500 cells and the total
lands near 1,800. If you retune, update the assertion range in
`tests/e2e/test_baltic_e2e.py::test_setup_summary_reports_cell_count`.

### Step 4.6: Sample EMODnet bathymetry for marine reaches

```python
from modules.bathymetry import fetch_emodnet_dtm, sample_depth

dtm_path = fetch_emodnet_dtm(BBOX_WITH_MARGIN)
for reach in ("CuronianLagoon", "BalticCoast"):
    mask = gdf_wgs["REACH_NAME"] == reach
    depths_by_reach[reach] = sample_depth(gdf_wgs[mask], dtm_path)
```

`sample_depth` reprojects centroids into the raster's CRS (or a
data-derived UTM when the raster is geographic), samples via
`rasterio.sample`, flips sign (EMODnet encodes elevation as negative
below sea level), and clamps land cells (positive elevation) to 0.1 m.

### Step 4.7: Write per-cell CSVs

For each reach, the generator writes three CSVs in
`tests/fixtures/example_baltic/`:

- `<Reach>-Depths.csv` — per-cell depth at 10 flow levels. For
  `CuronianLagoon` and `BalticCoast`, the base depth comes from EMODnet;
  the per-flow scaling is synthetic (preserves the reach's published
  `flood:base` ratio).
- `<Reach>-Vels.csv` — per-cell velocity at 10 flow levels. Synthetic.
- `<Reach>-TimeSeriesInputs.csv` — daily temperature / flow / turbidity
  over 2011-2038. Synthetic seasonal sinusoids seeded by reach-name hash.

Plus reach-level:

- `BalticExample-InitialPopulations.csv`
- `BalticExample-AdultArrivals.csv`

### Step 4.8: Write shapefile

Combines all per-reach cells into a single `BalticExample.shp` in EPSG:3035
(ETRS89/LAEA Europe) under `tests/fixtures/example_baltic/Shapefile/`.
Columns match the `spatial.gis_properties` map in
`configs/example_baltic.yaml`:

```yaml
spatial:
  backend: "shapefile"
  mesh_file: "Shapefile/BalticExample.shp"
  gis_properties:
    cell_id: "ID_TEXT"
    reach_name: "REACH_NAME"
    area: "AREA"
    dist_escape: "M_TO_ESC"
    num_hiding_places: "NUM_HIDING"
    frac_vel_shelter: "FRACVSHL"
    frac_spawn: "FRACSPWN"
```

### Step 4.9: Sync app-side fixtures

```bash
rm -rf app/data/fixtures/example_baltic
cp -r tests/fixtures/example_baltic app/data/fixtures/example_baltic
```

The app loads from `app/data/fixtures/<config_stem>/` when running from
the `app/` directory; tests load from `tests/fixtures/<config_stem>/`.
These dirs are kept in sync by hand (no symlink to avoid OneDrive
mischief on Windows).

### Step 4.10: Run the end-to-end test

```bash
micromamba run -n shiny python -m pytest \
    tests/test_model.py::test_adult_arrives_as_returning_adult -v
```

This loads the full config + fixtures and runs the simulation for 90 days,
verifying that returning adults arrive at the real Nemunas-basin reaches.
Runs in ~140 s.

---

## 5. Gotchas & workarounds (all discovered during the 2026-04-18 upgrade)

### Gotcha 1: Geofabrik moved Russia regions out of `/europe/`

**Symptom**: PBF download is 9.6 kB of HTML (the Geofabrik landing page)
instead of 20-200 MB of binary. `pyosmium.apply_file` raises
`RuntimeError: PBF error: invalid BlobHeader size`.

**Root cause**: Geofabrik reorganized URLs. `kaliningrad` used to live
under `/europe/russia/` (so `GEOFABRIK_REGIONS["kaliningrad"] = "russia/kaliningrad"`
with base `/europe/` gave a working URL). It now lives at `/russia/`
directly. Old URLs 302 to the homepage — which our downloader saves as-is.

**Fix**: `GEOFABRIK_REGIONS` entries starting with `http(s)://` are now
treated as absolute URL overrides by `geofabrik_url()`:

```python
GEOFABRIK_REGIONS = {
    ...
    "kaliningrad": f"{_GEOFABRIK_ROOT}/russia/kaliningrad",
}
```

**Detection tip**: `file <pbf_file>` should say "Serialized protobuf
data"; if it says "HTML document", the download URL is broken.

### Gotcha 2: pyosmium silently drops cross-border multipolygons

**Symptom**: `query_water_bodies("lithuania", bbox)` returns 1,814 water
polygons but none is the Curonian Lagoon, even though OSM has it as a
named relation.

**Root cause**: The lagoon is an OSM multipolygon whose rings span
Lithuania and Russia. `_HydroHandler.area()` wraps
`create_multipolygon(a)` in a bare `except Exception: return`, so when
pyosmium can't assemble all rings (because Kaliningrad-side rings aren't
in the Lithuania PBF), the relation is silently dropped.

**Attempted fix**: merge LT + Kaliningrad PBFs via the multi-region
`query_water_bodies` (Task 3.2/3.3). The lagoon **still** doesn't
assemble — its full ring closure needs ways from yet more PBFs we don't
currently fetch.

**Accepted workaround**: hand-trace the polygon from published
coordinates (18 vertices, ~500 m shoreline accuracy) as a fallback
inside `fetch_curonian_lagoon`. The Marine Regions WFS path is kept as
future-proofing in case MRGID 3642 is ever exposed.

**Adapt for other cross-border features**: either use an external
gazetteer (Marine Regions, EU-Hydro, Copernicus Land Cover), or
hand-trace, or fetch all PBFs whose bounding boxes overlap the feature.

### Gotcha 3: Marine Regions REST geometry endpoint returns 404

**Symptom**: `GET https://marineregions.org/rest/getGazetteerGeometries.json/3642/`
returns HTTP 404.

**Root cause**: That REST endpoint isn't implemented for all MRGIDs;
most polygons are only reachable via WFS at `geo.vliz.be`.

**Fix**: Query WFS with `cql_filter=MRGID=<N>` against typeName
candidates in order — Marine Regions has ~20 polygon layers and MRGID
coverage varies per layer. Probe script:
`scripts/_probe_marineregions.py` (not committed — diagnostic only).

**For Curonian Lagoon specifically**: no tried typeName
(`MarineRegions:iho`, `:iho_v3`, `:gazetteer_polygon`, `:world_bay_gulf`,
`:world_estuary_delta`, `:seavox_v19`) returns MRGID 3642. Gazetteer
record exists (has name, centroid, bbox) but no polygon geometry is
served. We log a WARN and fall through to the hand-traced polygon.

### Gotcha 4: EMODnet coverageId uses double underscore

**Symptom**: WCS `GetCoverage` with `coverageId=emodnet:mean` returns
HTTP 400.

**Fix**: Use `emodnet__mean` (double underscore). Confirmed via
`GetCapabilities`:

```
https://ows.emodnet-bathymetry.eu/wcs?service=WCS&request=GetCapabilities
```

Available coverages as of 2026-04-18:
`emodnet__mean`, `emodnet__mean_2016/2018/2020/2022`,
`emodnet__mean_atlas_land`, `emodnet__mean_multicolour`,
`emodnet__mean_rainbowcolour`.

`emodnet__mean` is the blended composite; the yearly ones pin specific releases.

### Gotcha 5: `generate_cells` crashed on water polygons smaller than one cell

**Symptom**: `ValueError: Assigning CRS to a GeoDataFrame without a
geometry column is not supported` at the end of `generate_cells`.

**Root cause**: When a reach polygon's area was smaller than `10 % *
cell_area`, the `min_overlap` filter rejected every raw hex cell, leaving
`records = []`. `gpd.GeoDataFrame([], crs=...)` then crashed.

**Fix** (`app/modules/create_model_grid.py`, tag v0.30.0):
- Cap the filter threshold by the **reach area**:
  `min(cell_area, combined_buffer.area) * min_overlap`. For small
  reaches the threshold drops proportionally so some cells still pass.
- Guard the empty case: return a typed empty `GeoDataFrame` with the
  full column schema instead of crashing.
- Regression tests in `tests/test_create_model_grid.py`.

### Gotcha 6: Gilija's OSM features merged into a `GeometryCollection`

**Symptom**: `NotImplementedError: Sub-geometries may have coordinate
sequences, but multi-part geometries do not` inside `generate_cells`.

**Root cause**: When OSM features for the same reach mix `LineString`
and `Polygon` types (as Gilija does — some canal segments are polygons,
main channel is lines), `unary_union` returns a `GeometryCollection`.
The existing flattener in `build_cells()` only handled `Multi*`.

**Fix**: Extended `build_cells()` to detect `GeometryCollection` and
extract its `LineString` / `Polygon` / nested `Multi*` members.

### Gotcha 7: Windows zombie sockets when running Shiny with `--reload`

**Symptom**: Port stays `LISTENING` in `netstat` under a PID that
`ps` can't see; can't be killed without a reboot.

**Root cause**: `shiny run --reload` on OneDrive-backed directories
leaks sockets (known issue per `CLAUDE.md`).

**Workaround**: Use a different port or restart the machine. For tests,
`test_e2e_spatial.py` moved `PORT = 18901 → 18903` after the `18901`
socket got stuck. Don't use `18901` until it clears.

---

## 6. Testing the case study

### Unit regression

```bash
micromamba run -n shiny python -m pytest \
    tests/test_create_model_grid.py \
    tests/test_create_model_osm.py \
    tests/test_bathymetry.py \
    tests/test_marineregions_cache.py \
    tests/test_model.py::test_adult_arrives_as_returning_adult -v
```

### End-to-end (requires running Shiny app)

```bash
# In one shell, run the app:
cd app && micromamba run -n shiny shiny run --port 8001 app:app

# In another shell:
E2E_BASE_URL=http://127.0.0.1:8001 \
    micromamba run -n shiny python -m pytest tests/e2e/test_baltic_e2e.py -v
```

Fast smoke suite (6 tests, ~60 s). For the full opt-in integration:

```bash
E2E_INTEGRATION=1 E2E_BASE_URL=http://127.0.0.1:8001 \
    micromamba run -n shiny python -m pytest tests/e2e/test_baltic_e2e.py -v
```

Integration adds the 2-minute simulation run.

---

## 7. Adapting to a different salmon system

The Baltic case study is essentially a 7-step template:

1. **Choose bbox** in WGS84. Keep it wide enough that cross-border OSM
   multipolygons can assemble, narrow enough that cell counts stay
   reasonable (<10k).
2. **Pick a file-naming convention**: ASCII keys for shapefile DBF
   compatibility, diacritics allowed in YAML comments and code
   docstrings.
3. **Identify reach names** in OSM by running the probe pattern of
   `scripts/_probe_baltic_osm.py` (not committed; shows the top-N named
   waterways by length in the bbox). Cross-reference with a hydrography
   map.
4. **Decide which PBFs to merge**. For Baltic we merged Lithuania +
   Kaliningrad. For, say, Daugava basin, you'd merge Latvia + Belarus.
5. **Pick cell sizes** per reach by running the generator and checking
   total counts; retune `CELL_SIZE_M` until you're in the 1k-2k range.
6. **If the system has a large enclosed water body** (lake / lagoon /
   fjord) that OSM can't assemble, hand-trace a polygon from published
   coordinates. Verify area against the real value and tolerate some
   over-sizing — the EMODnet sampler will correct the depth distribution.
7. **Write a YAML config** with all 8 reaches / N reaches, `marine.zones`
   block, and `spatial.gis_properties` map. Add a CHANGELOG entry and
   release.

### Files to copy/adapt

- `scripts/generate_baltic_example.py` → `scripts/generate_<name>_example.py`
- `configs/example_baltic.yaml` → `configs/example_<name>.yaml`
- `tests/fixtures/example_baltic/` → `tests/fixtures/example_<name>/`
  (populated by the generator)
- `tests/e2e/test_baltic_e2e.py` → `tests/e2e/test_<name>_e2e.py`
  (update `BALTIC_REACHES`, `BALTIC_MARINE_ZONES` to your system's names)

---

## 8. Outstanding limitations

Carried from v0.30.0:

1. **Curonian Lagoon polygon is 63 % over-sized** (2,585 km² vs real
   1,584 km²) because it's hand-traced. This pulls EMODnet-sampled mean
   depth down to 2.9 m vs published 3.8 m. Fix would require either
   (a) Marine Regions adding MRGID 3642 polygon to a WFS layer, or
   (b) pulling enough additional OSM PBFs for the relation to assemble.
2. **River-cell depths are synthetic** (per-cell jitter around published
   mean). EMODnet doesn't cover rivers; correcting this needs national
   hydrography surveys (Lithuania's AHHS, etc.).
3. **Hydraulic time series are synthetic** (seasonal sinusoid + noise).
   Real temperature/flow/turbidity time series for the Nemunas exist
   (HELCOM, ICES, national monitoring agencies) but weren't integrated
   — the model tolerates the synthesized series for calibration purposes.
4. **No tidal forcing** in `BalticCoast`. Baltic tides are negligible
   (< 10 cm amplitude) so this is scientifically defensible, but if the
   case study is extended to, say, the Irish Sea, tidal series would
   need to be sourced from Copernicus Marine.

---

## 9. Quick reference: the commit history

| Commit | What |
|---|---|
| `4424192` | Marine Regions WFS fetcher with hand-traced fallback |
| `246fe4f` | Multi-region OSM (`str | Iterable[str]`) + Kaliningrad URL override + `_clip_pbf` cache fix |
| `add61fb` | Gilija delta branch from Kaliningrad PBF + `GeometryCollection` handler |
| `9463ebb` | EMODnet DTM sampling for `CuronianLagoon` + `BalticCoast` cells |
| `0a28e0e` | Baltic e2e test suite (6 smoke + 1 integration) |
| `8c5a825` | Release v0.30.0 — docs + version bump |

---

## 10. Further reading

- Full implementation plan (reviewed three times before execution):
  `docs/superpowers/plans/2026-04-18-baltic-real-data-upgrades.md`
- Plan's "Self-Review Checklist" section — useful set of review patterns
  for writing similar case-study plans
- `app/modules/create_model_osm.py` for the OSM pipeline internals
- `app/modules/bathymetry.py` for the EMODnet pipeline internals
- `app/modules/create_model_grid.py` for the cell-generation algorithm
