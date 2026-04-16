# Local OSM PBF Hydrology Data — Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Overpass API (504 timeouts, 429 rate limits, broken geometries) with local `.osm.pbf` files from Geofabrik, using osmium-tool + pyosmium to extract river polygons, waterway centerlines, and water bodies.

**Architecture:**
```
Geofabrik PBF (219 MB, downloaded once)
  → osmium extract --bbox (10s, produces ~4 MB regional PBF)
    → pyosmium area()/way() handler (13s, builds GeoDataFrame)
      → Shiny map (instant refresh)
```
A new module `create_model_osm.py` handles download, bbox clipping via `osmium extract` CLI, and pyosmium extraction. The `area()` handler processes both closed ways AND multipolygon relations, giving us **6-8 river polygons + 1179 lines + 101 water bodies** for the Klaipėda bbox (vs 3 polygons from Overpass). Country-wide: **818 river polygons** for Lithuania.

**Tech Stack:** pyosmium (osmium 4.3.1, PBF parsing + WKB geometry), osmium-tool (CLI bbox clipping), geopandas, shapely (geometry validation), requests (one-time Geofabrik download)

**Why not pyrosm:** Requires Python 3.7-3.8, dead project — fails to install on Python 3.13. pyosmium works on 3.13.

---

## Verified data from Lithuania PBF scan

| Feature | Count | Geometry |
|---------|-------|----------|
| `waterway=river` centerlines | 2,914 | LineString |
| `waterway=stream` lines | 40,679 | LineString |
| `waterway=canal` lines | 291 | LineString |
| `waterway=ditch` lines | 104,355 | LineString |
| `natural=water`+`water=river` polygon ways | 174 | Polygon |
| `natural=water`+`water=river` polygon relations | 644 | MultiPolygon |
| **Total river area features** | **818** | Polygon/MultiPolygon |
| `natural=water` (all: lakes, ponds, reservoirs) | 16,257 | Polygon/MultiPolygon |

### Extraction time (verified on ThinkPad X1 Carbon, 16 GB RAM)

| Approach | Time | Peak RAM | Output |
|----------|------|----------|--------|
| Full Lithuania PBF, `locations=True` | **2.5 hours** | 737 MB | 818 polys, 149K lines |
| `osmium extract --bbox` + handler | **23 seconds** | ~100 MB | 6 polys, 1179 lines (Klaipėda) |

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app/modules/create_model_osm.py` | **Create** | PBF download, bbox clip, pyosmium extraction |
| `app/modules/create_model_panel.py` | **Modify** | Replace Overpass with `create_model_osm` calls |
| `app/data/osm/` | **Create dir** | Cached PBF + clipped PBF files (gitignored) |
| `.gitignore` | **Modify** | Add `app/data/osm/*.pbf` |
| `tests/test_create_model_osm.py` | **Create** | Unit + integration tests |

---

## Task 1: Install dependencies and set up data directory

**Files:**
- Modify: `.gitignore`
- Create: `app/data/osm/.gitkeep`

- [ ] **Step 1: Install pyosmium and osmium-tool**

```bash
micromamba run -n shiny pip install osmium
micromamba install -n shiny -c conda-forge osmium-tool -y
```

Verify both:
```bash
micromamba run -n shiny python -c "import osmium; print('pyosmium OK')"
micromamba run -n shiny osmium --version
```

- [ ] **Step 2: Create OSM data directory and gitignore**

```bash
mkdir -p app/data/osm
touch app/data/osm/.gitkeep
```

Add to `.gitignore`:
```
app/data/osm/*.pbf
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore app/data/osm/.gitkeep
git commit -m "chore: add OSM data directory, gitignore PBF caches"
```

---

## Task 2: Create `create_model_osm.py` — download, clip, extract

**Files:**
- Create: `app/modules/create_model_osm.py`
- Test: `tests/test_create_model_osm.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_create_model_osm.py
"""Tests for OSM PBF hydrology extraction."""
import pytest
from pathlib import Path


def test_geofabrik_url():
    from app.modules.create_model_osm import geofabrik_url
    assert geofabrik_url("lithuania") == "https://download.geofabrik.de/europe/lithuania-latest.osm.pbf"


def test_pbf_path():
    from app.modules.create_model_osm import pbf_path
    p = pbf_path("lithuania")
    assert p.name == "lithuania-latest.osm.pbf"
    assert "osm" in str(p)


def test_waterway_strahler():
    from app.modules.create_model_osm import WATERWAY_STRAHLER
    assert WATERWAY_STRAHLER["river"] == 6
    assert WATERWAY_STRAHLER["stream"] == 2
    assert WATERWAY_STRAHLER["ditch"] == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_osm.py -v
```

- [ ] **Step 3: Write the module**

```python
# app/modules/create_model_osm.py
"""Local OSM PBF hydrology extraction via osmium-tool + pyosmium.

Pipeline per "Fetch Rivers" click:
1. Download country .osm.pbf from Geofabrik (once, ~200 MB)
2. Clip to map bbox via ``osmium extract --bbox`` CLI (~10s)
3. Extract waterways + water bodies via pyosmium handler (~13s)
4. Return GeoDataFrames ready for deck.gl rendering

The pyosmium ``area()`` callback processes both closed ways AND
multipolygon relations, yielding actual river polygon geometries.
"""

import hashlib
import logging
import subprocess
from pathlib import Path

import geopandas as gpd
import requests
import shapely.wkb
from shapely.validation import make_valid

logger = logging.getLogger(__name__)

_OSM_DIR = Path(__file__).resolve().parent.parent / "data" / "osm"
_GEOFABRIK_BASE = "https://download.geofabrik.de/europe"

GEOFABRIK_COUNTRIES = {
    "lithuania", "latvia", "estonia", "poland", "finland",
    "sweden", "norway", "denmark", "germany", "france",
    "spain", "italy", "netherlands", "belgium", "ireland",
}

WATERWAY_STRAHLER = {
    "river": 6,
    "canal": 4,
    "stream": 2,
    "ditch": 1,
    "drain": 1,
}


def geofabrik_url(country: str) -> str:
    """Return Geofabrik download URL for a country PBF."""
    name = country.lower().replace(" ", "-")
    return f"{_GEOFABRIK_BASE}/{name}-latest.osm.pbf"


def pbf_path(country: str) -> Path:
    """Return local path for cached country PBF."""
    name = country.lower().replace(" ", "-")
    return _OSM_DIR / f"{name}-latest.osm.pbf"


def ensure_pbf(country: str, progress_cb=None) -> Path:
    """Download PBF if not cached. Returns local path."""
    path = pbf_path(country)
    if path.exists():
        if progress_cb:
            progress_cb(f"Using cached {path.name} ({path.stat().st_size // 1_000_000} MB)")
        return path

    _OSM_DIR.mkdir(parents=True, exist_ok=True)
    url = geofabrik_url(country)
    if progress_cb:
        progress_cb(f"Downloading {url} ...")

    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1_000_000):
            f.write(chunk)
            downloaded += len(chunk)
            if progress_cb and total > 0:
                pct = downloaded * 100 // total
                progress_cb(f"Downloading {path.name}: {pct}%")
    if progress_cb:
        progress_cb(f"Downloaded {path.name} ({path.stat().st_size // 1_000_000} MB)")
    return path


def _clip_pbf(pbf_file: Path, bbox_wgs84: tuple, progress_cb=None) -> Path:
    """Clip PBF to bbox using ``osmium extract`` CLI.

    ~10s for 219 MB Lithuania → ~4 MB regional extract.
    Caches by bbox hash so repeated queries for the same view are instant.
    """
    west, south, east, north = bbox_wgs84
    bbox_str = f"{west},{south},{east},{north}"
    bbox_hash = hashlib.md5(bbox_str.encode()).hexdigest()[:8]
    clip_path = _OSM_DIR / f"clip-{bbox_hash}.osm.pbf"

    if clip_path.exists():
        if progress_cb:
            progress_cb(f"Using cached clip ({clip_path.stat().st_size // 1024} KB)")
        return clip_path

    if progress_cb:
        progress_cb("Clipping PBF to map view (~10s)...")

    # osmium-tool is in the micromamba env; use full path on Windows
    import shutil
    osmium_bin = shutil.which("osmium")
    if osmium_bin is None:
        raise FileNotFoundError(
            "osmium CLI not found. Install: micromamba install -n shiny -c conda-forge osmium-tool"
        )

    subprocess.run(
        [osmium_bin, "extract", "--bbox", bbox_str,
         "-o", str(clip_path), "--overwrite", str(pbf_file)],
        check=True, timeout=120,
    )
    return clip_path


def _extract_hydro(pbf_file: Path, progress_cb=None):
    """Extract waterway + water body features from a (clipped) PBF.

    Returns ``(waterway_rows, water_body_rows)`` where each row is
    ``(wkb_hex, name, type_tag)``.
    """
    import osmium

    if progress_cb:
        progress_cb("Extracting hydrology features (~13s)...")

    class HydroHandler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.wkbfab = osmium.geom.WKBFactory()
            self.waterways = []     # (wkb_hex, name, type_tag)
            self.water_bodies = []  # (wkb_hex, name, type_tag)

        def area(self, a):
            """Process closed ways + multipolygon relations → polygons."""
            tags = dict(a.tags)
            try:
                wkb = self.wkbfab.create_multipolygon(a)
            except Exception:
                return
            nat = tags.get("natural")
            water = tags.get("water", "")
            ww = tags.get("waterway", "")
            name = tags.get("name", "")

            if nat == "water" and water in ("river", "stream", "canal", "oxbow"):
                self.waterways.append((wkb, name, water))
            elif ww == "riverbank":
                self.waterways.append((wkb, name, "river"))
            elif nat == "water":
                self.water_bodies.append((wkb, name, water if water else "water"))

        def way(self, w):
            """Process non-closed ways → centerlines."""
            tags = dict(w.tags)
            ww = tags.get("waterway", "")
            if ww not in ("river", "stream", "canal", "ditch", "drain"):
                return
            try:
                wkb = self.wkbfab.create_linestring(w)
                self.waterways.append((wkb, tags.get("name", ""), ww))
            except Exception:
                pass

    handler = HydroHandler()
    handler.apply_file(str(pbf_file), locations=True)
    return handler.waterways, handler.water_bodies


def _rows_to_gdf(rows, columns, wtype_key="waterway"):
    """Convert (wkb_hex, name, type_tag) rows to a GeoDataFrame."""
    gdf_rows = []
    for wkb, name, wtype in rows:
        try:
            geom = shapely.wkb.loads(wkb, hex=True)
            if not geom.is_valid:
                geom = make_valid(geom)
            row = {"geometry": geom, "name": name, "nameText": name, wtype_key: wtype, "DFDD": wtype}
            if wtype_key == "waterway":
                row["STRAHLER"] = WATERWAY_STRAHLER.get(wtype, 2)
            gdf_rows.append(row)
        except Exception:
            pass

    if not gdf_rows:
        return gpd.GeoDataFrame(columns=columns, geometry="geometry", crs="EPSG:4326")
    return gpd.GeoDataFrame(gdf_rows, crs="EPSG:4326")


def query_waterways(country: str, bbox_wgs84: tuple, progress_cb=None) -> gpd.GeoDataFrame:
    """Extract waterways for a bbox: download → clip → extract → GeoDataFrame.

    ~23s for a new bbox, instant for a cached bbox.

    Returns GeoDataFrame with columns:
    geometry, name, nameText, waterway, STRAHLER, DFDD
    """
    pbf = ensure_pbf(country, progress_cb=progress_cb)
    clip = _clip_pbf(pbf, bbox_wgs84, progress_cb=progress_cb)
    ww_rows, _ = _extract_hydro(clip, progress_cb=progress_cb)
    return _rows_to_gdf(
        ww_rows,
        ["geometry", "name", "nameText", "waterway", "STRAHLER", "DFDD"],
        wtype_key="waterway",
    )


def query_water_bodies(country: str, bbox_wgs84: tuple, progress_cb=None) -> gpd.GeoDataFrame:
    """Extract water bodies for a bbox: download → clip → extract → GeoDataFrame.

    Returns GeoDataFrame with columns:
    geometry, name, nameText, water, DFDD
    """
    pbf = ensure_pbf(country, progress_cb=progress_cb)
    clip = _clip_pbf(pbf, bbox_wgs84, progress_cb=progress_cb)
    _, wb_rows = _extract_hydro(clip, progress_cb=progress_cb)
    return _rows_to_gdf(
        wb_rows,
        ["geometry", "name", "nameText", "water", "DFDD"],
        wtype_key="water",
    )
```

- [ ] **Step 4: Run tests**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_osm.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/create_model_osm.py tests/test_create_model_osm.py
git commit -m "feat: add pyosmium-based OSM hydrology extraction module"
```

---

## Task 3: Integration test with Lithuania PBF

**Files:**
- Modify: `tests/test_create_model_osm.py` (append integration test)

- [ ] **Step 1: Add integration test**

Append to `tests/test_create_model_osm.py`:

```python
from pathlib import Path

PBF = Path("app/data/osm/lithuania-latest.osm.pbf")


@pytest.mark.skipif(not PBF.exists(), reason="Lithuania PBF not downloaded")
def test_bbox_query_klaipeda():
    """Query Klaipeda area via clip+extract and verify river polygons."""
    from app.modules.create_model_osm import query_waterways, query_water_bodies

    bbox = (20.9, 55.5, 21.3, 55.85)
    ww = query_waterways("lithuania", bbox)

    assert len(ww) > 50  # rivers + streams in Klaipeda area
    is_poly = ww.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    assert is_poly.sum() > 0  # at least some river polygons
    assert "nameText" in ww.columns
    assert "STRAHLER" in ww.columns
    assert "DFDD" in ww.columns

    # Water bodies
    wb = query_water_bodies("lithuania", bbox)
    assert len(wb) > 0
    assert "nameText" in wb.columns
```

- [ ] **Step 2: Run integration test**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_osm.py::test_bbox_query_klaipeda -v -s
```

Expected: PASS (~23s for clip+extract)

- [ ] **Step 3: Commit**

```bash
git add tests/test_create_model_osm.py
git commit -m "test: integration test for Lithuania PBF clip+extract pipeline"
```

---

## Task 4: Replace Overpass calls in `create_model_panel.py`

**Files:**
- Modify: `app/modules/create_model_panel.py`

- [ ] **Step 1: Replace imports and constants**

Remove:
- `OVERPASS_URL` constant
- `_query_osm_rivers()` function (entire, ~110 lines)
- `_query_osm_water()` function (entire, ~70 lines)
- `from shapely.ops import unary_union`
- `from shapely.validation import make_valid`

Add imports:

```python
from modules.create_model_osm import (
    query_waterways,
    query_water_bodies,
    WATERWAY_STRAHLER,
    GEOFABRIK_COUNTRIES,
)
```

Keep `_WATERWAY_STRAHLER` as alias:
```python
_WATERWAY_STRAHLER = WATERWAY_STRAHLER
```

Keep `_query_marine_regions()` unchanged.

- [ ] **Step 2: Add country selector to toolbar UI**

In the toolbar `div` (class `cm-toolbar`), add before the Rivers button:

```python
ui.tags.span("Region:", class_="cm-label"),
ui.div(
    ui.input_select(
        "osm_country", None,
        choices=sorted(GEOFABRIK_COUNTRIES),
        selected="lithuania",
        width="120px",
    ),
    style="display:inline-block; vertical-align:middle;",
),
```

- [ ] **Step 3: Rewrite `_on_fetch_rivers` handler**

```python
@reactive.effect
@reactive.event(input.fetch_rivers)
async def _on_fetch_rivers():
    country = input.osm_country()
    bbox = _get_view_bbox()

    import asyncio
    loop = asyncio.get_running_loop()

    _fetch_msg.set(f"Preparing {country} hydrology data...")
    try:
        gdf = await loop.run_in_executor(
            None, lambda: query_waterways(
                country, bbox,
                progress_cb=lambda msg: _fetch_msg.set(msg),
            )
        )
    except Exception as e:
        _fetch_msg.set(f"Failed: {e}")
        return

    if gdf is None or len(gdf) == 0:
        _fetch_msg.set("No waterway features found. Try zooming out or changing region.")
        return

    is_poly = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    n_polys = is_poly.sum()
    n_lines = len(gdf) - n_polys

    # Also fetch water bodies for context (reuses cached clip)
    _fetch_msg.set(f"Got {n_polys} river polygons + {n_lines} stream lines. Loading water bodies...")
    try:
        water_gdf = await loop.run_in_executor(
            None, lambda: query_water_bodies(country, bbox)
        )
    except Exception:
        water_gdf = None

    if water_gdf is not None and len(water_gdf) > 0:
        _water_gdf.set(water_gdf)

    # Clip small streams inside water bodies (optional, safe)
    clip_types = {"stream", "ditch", "drain"}
    if water_gdf is not None and len(water_gdf) > 0 and n_lines > 0:
        try:
            water_union = water_gdf.geometry.apply(
                lambda g: g.buffer(0) if g and not g.is_empty else g
            ).unary_union
            keep = []
            for _, row in gdf.iterrows():
                g = row.geometry
                if g is None or g.is_empty:
                    keep.append(False)
                elif g.geom_type in ("Polygon", "MultiPolygon"):
                    keep.append(True)
                elif row.get("waterway", "") not in clip_types:
                    keep.append(True)
                else:
                    try:
                        frac = g.intersection(water_union).length / g.length if g.length > 0 else 0
                        keep.append(frac < 0.5)
                    except Exception:
                        keep.append(True)
            gdf = gdf[keep].reset_index(drop=True)
        except Exception as e:
            logger.warning("Stream clipping failed: %s", e)

    _rivers_gdf.set(gdf)
    await _refresh_map()

    is_poly_final = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    water_msg = f" + {len(water_gdf)} water bodies" if water_gdf is not None else ""
    _fetch_msg.set(
        f"Loaded {is_poly_final.sum()} river polygons + {(~is_poly_final).sum()} lines{water_msg} (local)."
    )
```

- [ ] **Step 4: Rewrite `_on_fetch_water` handler**

```python
@reactive.effect
@reactive.event(input.fetch_water)
async def _on_fetch_water():
    country = input.osm_country()
    bbox = _get_view_bbox()

    import asyncio
    loop = asyncio.get_running_loop()

    _fetch_msg.set(f"Loading water bodies from {country} data...")
    try:
        gdf = await loop.run_in_executor(
            None, lambda: query_water_bodies(country, bbox)
        )
    except Exception as e:
        _fetch_msg.set(f"Water body query failed: {e}")
        return

    if gdf is None or len(gdf) == 0:
        _fetch_msg.set("No water bodies found in this area.")
        return

    _water_gdf.set(gdf)
    await _refresh_map()
    _fetch_msg.set(f"Loaded {len(gdf)} water bodies (local).")
```

- [ ] **Step 5: Update tooltips and help text**

Button titles:
```python
title="Extract river network from local OSM data"
title="Extract water bodies from local OSM data"
```

Help modal data source note:
```python
> River and water body data is extracted from OpenStreetMap via local
> .osm.pbf files downloaded from Geofabrik. Select your region from
> the dropdown — the data file is downloaded once (~200 MB) and
> clipped to your map view on each fetch (~23s). Sea areas come from
> the Marine Regions database (marineregions.org).
```

Module docstring:
```python
"""Create Model panel — build model grid from local OSM river data.
```

- [ ] **Step 6: Commit**

```bash
git add app/modules/create_model_panel.py
git commit -m "feat: replace Overpass API with local PBF hydrology extraction"
```

---

## Task 5: Clean up dead code

**Files:**
- Modify: `app/modules/create_model_panel.py`

- [ ] **Step 1: Remove all remaining Overpass/EU-Hydro references**

```bash
grep -n "Overpass\|OVERPASS\|EU.Hydro\|euhydro\|_query_osm" app/modules/create_model_panel.py
```

Remove any matches. Remove unused imports (`unary_union`, `make_valid` if only used in deleted code).

- [ ] **Step 2: Commit**

```bash
git add app/modules/create_model_panel.py
git commit -m "chore: remove dead Overpass/EU-Hydro code"
```

---

## Task 6: Smoke test

- [ ] **Step 1: Start the app**

```bash
cd app && micromamba run -n shiny shiny run --port 8001 app:app
```

- [ ] **Step 2: Full workflow test**

1. Open http://127.0.0.1:8001 → Create Model tab, expand card
2. Select "lithuania" from Region dropdown
3. Click "Rivers" — first time downloads PBF (~60s), clips + extracts (~23s)
4. Verify: river polygons (filled blue shapes) + thick river lines + thin stream lines
5. Move Strahler slider to 1 — verify rivers still visible (not clipped)
6. Move Strahler slider to 6 — only river polygons + river centerlines
7. Click "Water" — verify lakes/ponds appear (reuses cached clip, fast)
8. Click "Sea" — verify Marine Regions WFS still works
9. Enter River selection mode, click on a river polygon — verify it selects
10. Generate cells, export

- [ ] **Step 3: Verify no crashes**

```bash
tail -50 /tmp/instream-app.log | grep -i "error\|traceback\|exception"
```

---

## What stays unchanged

- **Marine Regions WFS** (`_query_marine_regions`) — stable, no change
- **`_build_river_layer`** — works on same GeoDataFrame schema (polygon fill + width-scaled lines)
- **`_filtered_rivers_gdf`** — same `STRAHLER` column
- **Click handler** — same polygon containment + line distance fallback
- **Reach selection, cell generation, export** — all unchanged
- **Tooltip** — same `nameText`, `STRAHLER`, `waterway` properties

## Performance comparison

| Metric | Overpass API | Local PBF (this plan) |
|--------|-------------|----------------------|
| First use | 10-30s + frequent failures | ~60s download + 23s extract |
| Same bbox again | 10-30s + failures | **~13s** (cached clip, re-extract) |
| New bbox | 10-30s + failures | **~23s** (re-clip + extract) |
| River polygons (Klaipėda) | 3 | **6-8** |
| River polygons (all Lithuania) | N/A | **818** |
| Reliability | 504/429 errors, TopologyException | 100% offline, validated geometries |
| Disk space | 0 | ~220 MB (country PBF + clips) |
