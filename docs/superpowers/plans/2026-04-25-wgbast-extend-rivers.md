# WGBAST rivers — extend Tornionjoki + materialize BalticCoast cells (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Tornionjoki's full extent (add Muonionjoki tributary) and give all 4 WGBAST rivers (Tornionjoki, Simojoki, Byskealven, Morrumsan) shapefile cells under the existing `BalticCoast` reach so smolts have a marine transit zone, while moving 4 reusable algorithms from `scripts/_generate_wgbast_physical_domains.py` into `app/modules/create_model_*` so the Create Model UI can share them.

**Architecture:** Two independent PRs. PR-1 is a one-line OSM-regex change to `scripts/_fetch_wgbast_osm_polylines.py` plus a Tornionjoki fixture regeneration. PR-2 introduces 2 new pure-Python helper modules (`create_model_marine.py`, `create_model_river.py`), refactors the WGBAST batch generator to import from them, adds Marine Regions WFS-clipped BalticCoast cells via `sea_polygon.intersection(disk)`, tunes per-river BalticCoast YAML parameters for Bothnian Bay vs Hanöbukten predator regimes, drops 4 orphan Lithuanian template reaches, and regenerates all 4 fixtures.

**Tech Stack:** Python 3.11+, **geopandas ≥ 1.0** (uses `.union_all()`; the `.unary_union` accessor is deprecated in 1.0 and removed in 2.0), shapely ≥ 2.0, pyproj, pandas, requests, pyyaml, pytest. Project conda env: `shiny` (per `CLAUDE.md`). Verify the env meets the geopandas lower bound before starting:
```bash
micromamba run -n shiny python -c "import geopandas; print(geopandas.__version__)"
```
Expected: ≥ 1.0. If lower, `micromamba update -n shiny -c conda-forge geopandas` first.

**Spec:** `docs/superpowers/specs/2026-04-25-wgbast-extend-rivers-design.md` (v4)

**Branch:** `wgbast-extend-rivers` (already created; v4 spec committed at `f1391ad`).

---

## File structure

### PR-1
- Modify: `scripts/_fetch_wgbast_osm_polylines.py` (regex line ~64)
- Modify (regenerated, binary): `tests/fixtures/_osm_cache/example_tornionjoki.json`
- Modify (regenerated, binary): `tests/fixtures/_osm_cache/example_tornionjoki_polygons.json`
- Modify (regenerated, binary): `tests/fixtures/example_tornionjoki/Shapefile/TornionjokiExample.{shp,shx,dbf,prj,cpg}`

### PR-2
- Create: `app/modules/create_model_marine.py` — Marine Regions WFS + disk clip
- Create: `app/modules/create_model_river.py` — connectivity filter + along-channel partition
- Create: `tests/test_create_model_marine.py` — unit tests (mocked WFS)
- Create: `tests/test_create_model_river.py` — unit tests (synthetic geometries)
- Create: `tests/test_wgbast_river_extents.py` — fixture-shape regression
- Modify: `app/modules/create_model_panel.py` — re-export `_query_marine_regions` from new module (5 lines)
- Modify: `scripts/_generate_wgbast_physical_domains.py` — import helpers, add BalticCoast generation, add WFS cache (substantial refactor; net thinner)
- Modify: `scripts/_wire_wgbast_physical_configs.py` — drop orphan reaches, tune BalticCoast, re-expand its CSVs
- Modify: `configs/example_tornionjoki.yaml` — tune BalticCoast `fish_pred_min`; drop Skirvyte/Leite/Gilija/CuronianLagoon
- Modify: `configs/example_simojoki.yaml` — same
- Modify: `configs/example_byskealven.yaml` — same
- Modify: `configs/example_morrumsan.yaml` — same (different `fish_pred_min` value: Hanöbukten not Bothnian Bay)
- Modify (regenerated): `tests/fixtures/example_{tornionjoki,simojoki,byskealven,morrumsan}/Shapefile/*Example.*`
- Modify (regenerated): `tests/fixtures/example_*/BalticCoast-{Depths,Vels}.csv` (re-expanded to new cell counts)
- Create (cached payloads): `tests/fixtures/_osm_cache/example_*_marineregions.json`
- Modify: `pyproject.toml` (version bump)
- Modify: `src/salmopy/__init__.py` (`__version__`)
- Modify: `CHANGELOG.md` (release note)

---

# Pre-flight check (orchestrator runs ONCE before dispatching any task)

This is NOT a task and should NOT be dispatched to a subagent (no code change, no commit). The orchestrator (or the engineer running this plan inline) verifies external service reachability before starting:

```bash
# 1. Overpass interpreter (used by PR-1's _fetch_wgbast_osm_polylines.py --refresh)
curl -sf --max-time 15 --data "data=[out:json];node(1);out;" https://overpass-api.de/api/interpreter -o /tmp/preflight_overpass.json
test -s /tmp/preflight_overpass.json || echo "OVERPASS UNREACHABLE — defer PR-1"

# 2. Marine Regions WFS (used by PR-2 Task 2.C.1's _load_or_fetch_marineregions)
curl -sf --max-time 30 -o /dev/null -w "%{http_code}\n" \
  "https://geo.vliz.be/geoserver/MarineRegions/wfs?service=WFS&version=2.0.0&request=GetCapabilities"
# Expected: 200. If 503/timeout: defer PR-2.
```

If both services respond, proceed. If either is down, defer the corresponding PR until the service recovers — fixture regeneration depends on live data.

---

# PR-1 — Tornionjoki regex extension

## Task 1.1: Extend Tornionjoki OSM regex to capture Muonionjoki

**ORCHESTRATOR PRECONDITION:** Confirm the pre-flight curl checks at the top of this plan ("Pre-flight check" section before PR-1) have passed. This task hits Overpass; if Overpass is unreachable, defer this task. A subagent dispatched to this task should not retry on network failure — that's the orchestrator's call.

**Why:** Per spec §Problem.1, the current regex matches only the lower 151 km of Tornionjoki. Adding Muonionjoki names extends the basin to ~270 km of centerline, restoring the river's expected size relative to Simojoki.

**Files:**
- Modify: `scripts/_fetch_wgbast_osm_polylines.py:64`

- [ ] **Step 1: Open the file and locate the regex**

The file has 4 `RiverQuery` definitions starting at `scripts/_fetch_wgbast_osm_polylines.py:57`. The Tornionjoki entry currently has:
```python
name_regex="^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne)$",
```

- [ ] **Step 2: Update the regex**

Replace that single line with:
```python
name_regex="^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne|Muonionjoki|Muonio älv|Muonio)$",
```

The bbox `(65.5, 22.8, 68.6, 25.6)` already covers the Muonio basin — no bbox change needed.

- [ ] **Step 3: Refresh the Tornionjoki cache (line ways + polygons)**

```bash
micromamba run -n shiny python scripts/_fetch_wgbast_osm_polylines.py --refresh
```

The `--refresh` flag forces a re-fetch even though caches exist. Expected runtime: 30–90 s (Overpass-side latency dominates).

After completion, sanity-check:
```bash
micromamba run -n shiny python scripts/_diag_tornionjoki_polygon_filter.py
```

Expected: Tornionjoki seed polygon count rises from 4 to **>20** (Muonio brings additional polygon coverage). Centerline length grows from ~1.36° (~151 km) to **>2.4°** (~270 km).

- [ ] **Step 4: Sanity-check the new connectivity (no fixture regenerate yet)**

PR-1 ships the regex change + the refreshed OSM caches ONLY. The shapefile regeneration is deferred to PR-2 Section C, which will run the regenerator AFTER the helper-extraction refactor lands. This avoids regenerating Tornionjoki twice (once in PR-1, again in PR-2 Section B claims "byte-equivalent refactor" — which is a strong byte-level claim that STRtree iteration order + dict ordering may not actually meet). PR-2 Section C is the single regenerate point.

The diagnostic confirms the cache refresh worked:
```bash
micromamba run -n shiny python scripts/_diag_tornionjoki_polygon_filter.py
```

Expected: Tornionjoki seed polygon count >20 (was 4); centerline >2.4° (was 1.36°).

- [ ] **Step 5: Commit PR-1 (regex + OSM caches only)**

```bash
git add scripts/_fetch_wgbast_osm_polylines.py tests/fixtures/_osm_cache/example_tornionjoki.json tests/fixtures/_osm_cache/example_tornionjoki_polygons.json
git commit -m "fix(wgbast): include Muonionjoki in Tornionjoki OSM regex

Was: ^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne)$
Now: + Muonionjoki|Muonio älv|Muonio

Tornionjoki main stem only spans ~150 km; the basin extends another
~150 km north along the Muonio tributary. WGBAST stock-assessment
practice treats Muonio as part of the Tornionjoki population.

The OSM line-way and water-polygon caches are refreshed here.
The Tornionjoki shapefile is intentionally NOT regenerated in this
commit — the same generator changes substantially in PR-2 (helper
extraction + BalticCoast cells), so regenerating fixtures once after
PR-2 lands avoids producing two distinct Tornionjoki shapefiles in
the git history within hours of each other.

Diagnostic post-refresh:
- Pre: 4 OSM seed polygons -> 71 connected, ~150 km centerline.
- Post: >20 OSM seed polygons -> >300 connected, ~270 km centerline."
```

---

# PR-2 — BalticCoast cells + helper extraction

PR-2 has six sections (A–F). Sections A and B are pure refactors with no behaviour change; C–F add the new BalticCoast cells, the YAML cleanup, the tests, and the release.

## Task dependency DAG (read this if dispatching subagents in parallel)

```
2.A.1 (create_model_marine + clip_sea + 3 tests)
2.A.2 (mock-WFS tests)                    ← depends on 2.A.1
2.A.3 (create_model_river + filter)
2.A.4 (partition + 6 tests)               ← depends on 2.A.3
2.A.5 (panel refactor + handler rewrite)  ← depends on 2.A.1

2.B.1 (generator refactor)                ← depends on 2.A.3 + 2.A.4

2.C.1 (constants + WFS cache helper)      ← depends on 2.B.1, 2.A.1
2.C.2 (BalticCoast cell generation)       ← depends on 2.C.1, 2.A.1, 2.A.4

2.D.1 (orphan drop + tuning)              ← depends on 2.C.2 (needs new shapefiles)
2.D.2 (CSV re-expand)                     ← depends on 2.D.1, 2.C.2

2.E.1 (river extents tests)               ← depends on 2.D.2 (needs final fixtures)
2.E.2 (full suite)                        ← depends on 2.E.1

2.F.1 (release)                           ← depends on 2.E.2
```

**Parallel-safe groups:** {2.A.1, 2.A.3} — different new files. {2.A.2, 2.A.4} (after 2.A.1, 2.A.3 land) — different new files.

**Strictly serial:** 2.B.1 → 2.C.1 → 2.C.2 → 2.D.1 → 2.D.2 (each modifies the previous file or its outputs). Subagents dispatched in parallel within this chain WILL race on shared files; do not parallelize.

## Section A — Shared helpers in `app/modules/`

### Task 2.A.1: Create `app/modules/create_model_marine.py` with `clip_sea_polygon_to_disk`

**Files:**
- Create: `app/modules/create_model_marine.py`
- Create: `tests/test_create_model_marine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_create_model_marine.py` with this content (we'll add more cases in subsequent tasks):

```python
"""Unit tests for app/modules/create_model_marine.py.

Pure-Python tests on synthetic + mocked inputs. No network access.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import geopandas as gpd
from shapely.geometry import Point, Polygon, box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_clip_sea_polygon_to_disk_basic_intersection():
    """Sea polygon covers a disk at the mouth → result is non-empty
    and inside both the sea polygon and the disk's circular bound."""
    from modules.create_model_marine import clip_sea_polygon_to_disk

    # Sea polygon: a 2°×2° box around (0,0). At equator, ~222 km × 222 km.
    sea = box(-1.0, -1.0, 1.0, 1.0)
    mouth = (0.5, 0.5)
    radius_m = 50_000  # 50 km
    utm_epsg = 32631   # lon 0.5° lies in UTM zone 31 (0°E–6°E central meridian 3°E)

    result = clip_sea_polygon_to_disk(
        sea_polygon=sea,
        mouth_lon_lat=mouth,
        radius_m=radius_m,
        utm_epsg=utm_epsg,
    )

    assert not result.is_empty
    # Result should be inside the sea polygon (with sub-meter tolerance for round-trip)
    assert sea.buffer(1e-6).contains(result), "result not inside sea polygon"


def test_clip_sea_polygon_to_disk_mouth_outside_sea_raises():
    """Mouth far from any sea → intersection empty → ValueError."""
    from modules.create_model_marine import clip_sea_polygon_to_disk

    sea = box(0.0, 0.0, 1.0, 1.0)
    mouth_far_inland = (10.0, 10.0)
    with pytest.raises(ValueError, match="does not intersect"):
        clip_sea_polygon_to_disk(
            sea_polygon=sea,
            mouth_lon_lat=mouth_far_inland,
            radius_m=10_000,
            utm_epsg=32633,
        )


def test_clip_sea_polygon_to_disk_empty_sea_raises():
    """Empty sea polygon → ValueError."""
    from modules.create_model_marine import clip_sea_polygon_to_disk

    sea = Polygon()  # empty
    with pytest.raises(ValueError, match="empty"):
        clip_sea_polygon_to_disk(
            sea_polygon=sea,
            mouth_lon_lat=(0.5, 0.5),
            radius_m=10_000,
            utm_epsg=32633,
        )
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_marine.py -v
```

Expected: 3 tests fail with `ModuleNotFoundError: No module named 'modules.create_model_marine'`.

- [ ] **Step 3: Create the implementation**

Create `app/modules/create_model_marine.py`:

```python
"""Marine sea-reach geometry helpers shared by Create Model UI and the
WGBAST batch generator.

Two functions:
  * `query_named_sea_polygon(bbox)` — Marine Regions WFS for IHO sea-area
    polygons (extracted from `create_model_panel.py::_query_marine_regions`).
  * `clip_sea_polygon_to_disk(...)` — clips a sea polygon to a true-meters
    disk around a river mouth.
"""
from __future__ import annotations

from typing import Optional

import geopandas as gpd
import requests
from shapely.geometry import MultiPolygon, Point, Polygon, box

MARINE_REGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"


def clip_sea_polygon_to_disk(
    sea_polygon: Polygon | MultiPolygon,
    mouth_lon_lat: tuple[float, float],
    radius_m: float,
    utm_epsg: int,
) -> Polygon | MultiPolygon:
    """Return `sea_polygon` clipped to a true-meters disk around the mouth.

    Algorithm (no land subtraction needed — sea_polygon is sea-only by
    definition):
      1. Reproject sea_polygon and mouth point to `utm_epsg`.
      2. Build a true-meters disk: mouth_pt.buffer(radius_m).
      3. Intersect: clipped = sea_polygon_utm.intersection(disk).
      4. Reproject the result back to EPSG:4326. Return.

    Raises:
      ValueError if the input sea_polygon is empty.
      ValueError if the intersection is empty (sea polygon does not
        cover the mouth at all).
    """
    if sea_polygon.is_empty:
        raise ValueError("sea_polygon is empty; nothing to clip")
    sea_gdf = gpd.GeoDataFrame(
        geometry=[sea_polygon], crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg)
    mouth_gdf = gpd.GeoDataFrame(
        geometry=[Point(mouth_lon_lat)], crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg)
    disk = mouth_gdf.geometry.iloc[0].buffer(radius_m)
    clipped = sea_gdf.geometry.iloc[0].intersection(disk)
    if clipped.is_empty:
        raise ValueError(
            f"sea polygon does not intersect a {radius_m}m disk at "
            f"mouth {mouth_lon_lat} — wrong waypoint?"
        )
    out = gpd.GeoDataFrame(
        geometry=[clipped], crs=f"EPSG:{utm_epsg}"
    ).to_crs("EPSG:4326")
    return out.geometry.iloc[0]


def query_named_sea_polygon(
    bbox_wgs84: tuple[float, float, float, float],
    timeout_s: int = 60,
) -> Optional[gpd.GeoDataFrame]:
    """Query Marine Regions WFS for IHO sea-area polygons within bbox.

    Returns a GeoDataFrame in EPSG:4326 with columns ['name', 'geometry'],
    post-filtered to features whose geometry actually intersects the bbox
    (Marine Regions returns global polygons that merely touch the bbox).
    Returns None on network/HTTP failure or empty result.
    """
    west, south, east, north = bbox_wgs84
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "MarineRegions:iho",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{west},{south},{east},{north},EPSG:4326",
    }
    try:
        resp = requests.get(MARINE_REGIONS_WFS, params=params, timeout=timeout_s)
        resp.raise_for_status()
        geoj = resp.json()
    except Exception:
        return None
    if not geoj.get("features"):
        return None
    gdf = gpd.GeoDataFrame.from_features(geoj["features"], crs="EPSG:4326")
    view_box = box(*bbox_wgs84)
    gdf = gdf[gdf.geometry.intersects(view_box)].copy()
    if len(gdf) > 1:
        centre = view_box.centroid
        covers = gdf[gdf.geometry.contains(centre)]
        if len(covers) > 0:
            gdf = covers.copy()
    if "name" not in gdf.columns:
        gdf["name"] = ""
    return gdf[["name", "geometry"]].reset_index(drop=True)
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_marine.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/modules/create_model_marine.py tests/test_create_model_marine.py
git commit -m "feat(create_model_marine): clip_sea_polygon_to_disk + WFS helper

New shared module app/modules/create_model_marine.py exposes:
  - clip_sea_polygon_to_disk(sea, mouth, radius_m, utm_epsg) -> Polygon
    Reprojects to UTM for true-meters disk, intersects, reprojects back.
  - query_named_sea_polygon(bbox) -> GeoDataFrame|None
    Marine Regions WFS query (extracted from create_model_panel.py).

Both will be consumed by the WGBAST batch generator (next commits) and
remain available for a future Create Model UI button."
```

### Task 2.A.2: Add `query_named_sea_polygon` mocked test

**Files:**
- Modify: `tests/test_create_model_marine.py`

- [ ] **Step 1: Add mocked-WFS tests to the existing file**

Append to `tests/test_create_model_marine.py`:

```python
def test_query_named_sea_polygon_post_filters_centroid_match(monkeypatch):
    """Among multiple polygons returned by WFS, only the one containing
    the bbox centroid should be returned."""
    from modules import create_model_marine as m

    # Two polygons — one covers the bbox centre, one only touches the bbox edge.
    fake_geoj = {
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "True Match"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {"name": "Edge Toucher"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [1, 1], [3, 1], [3, 3], [1, 3], [1, 1]
                    ]],
                },
            },
        ],
    }

    class _FakeResp:
        def raise_for_status(self): pass
        def json(self): return fake_geoj

    monkeypatch.setattr(m.requests, "get", lambda *a, **kw: _FakeResp())

    result = m.query_named_sea_polygon((-1.0, -1.0, 1.0, 1.0))
    assert result is not None
    assert len(result) == 1
    assert result.iloc[0]["name"] == "True Match"


def test_query_named_sea_polygon_returns_none_on_http_error(monkeypatch):
    """HTTP error → None (no exception)."""
    from modules import create_model_marine as m

    class _FailResp:
        def raise_for_status(self):
            raise RuntimeError("HTTP 500")

    monkeypatch.setattr(m.requests, "get", lambda *a, **kw: _FailResp())
    result = m.query_named_sea_polygon((0, 0, 1, 1))
    assert result is None


def test_query_named_sea_polygon_returns_none_on_empty_features(monkeypatch):
    """Empty WFS response → None."""
    from modules import create_model_marine as m

    class _EmptyResp:
        def raise_for_status(self): pass
        def json(self): return {"features": []}

    monkeypatch.setattr(m.requests, "get", lambda *a, **kw: _EmptyResp())
    result = m.query_named_sea_polygon((0, 0, 1, 1))
    assert result is None
```

- [ ] **Step 2: Run the new tests**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_marine.py -v
```

Expected: 6 PASS (3 from Task 2.A.1 + 3 new).

- [ ] **Step 3: Commit**

```bash
git add tests/test_create_model_marine.py
git commit -m "test(create_model_marine): mocked-WFS coverage for query_named_sea_polygon"
```

### Task 2.A.3: Create `app/modules/create_model_river.py` with `filter_polygons_by_centerline_connectivity`

**Files:**
- Create: `app/modules/create_model_river.py`
- Create: `tests/test_create_model_river.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_create_model_river.py`:

```python
"""Unit tests for app/modules/create_model_river.py.

Pure-Python tests on synthetic geometries.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from shapely.geometry import LineString, Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_filter_keeps_polygons_touching_centerline():
    """Three polygons; one is on the centerline, one touches it, one is
    far away. The far one is dropped; the touching one is kept."""
    from modules.create_model_river import filter_polygons_by_centerline_connectivity

    centerline = [LineString([(0, 0), (10, 0)])]
    on_centerline = Polygon([(0, -0.5), (10, -0.5), (10, 0.5), (0, 0.5)])
    near_centerline = Polygon([(2, 0.5), (4, 0.5), (4, 1.5), (2, 1.5)])  # touches via buffer
    far_away = Polygon([(50, 50), (52, 50), (52, 52), (50, 52)])

    kept = filter_polygons_by_centerline_connectivity(
        centerline=centerline,
        polygons=[on_centerline, near_centerline, far_away],
        tolerance_deg=0.001,  # ~110m
        max_polys=100,
    )
    kept_set = {id(p) for p in kept}
    assert id(on_centerline) in kept_set, "on-centerline polygon dropped"
    assert id(far_away) not in kept_set, "far polygon was kept"


def test_filter_caps_at_max_polys():
    """If the connected component is huge, return at most max_polys."""
    from modules.create_model_river import filter_polygons_by_centerline_connectivity

    centerline = [LineString([(0, 0), (100, 0)])]
    polys = [
        Polygon([(i, -0.5), (i + 1, -0.5), (i + 1, 0.5), (i, 0.5)])
        for i in range(20)
    ]
    kept = filter_polygons_by_centerline_connectivity(
        centerline=centerline,
        polygons=polys,
        tolerance_deg=0.001,
        max_polys=5,
    )
    assert len(kept) <= 5


def test_filter_empty_polygons_returns_empty():
    """Empty input → empty output, no errors."""
    from modules.create_model_river import filter_polygons_by_centerline_connectivity

    kept = filter_polygons_by_centerline_connectivity(
        centerline=[LineString([(0, 0), (1, 0)])],
        polygons=[],
        tolerance_deg=0.001,
        max_polys=100,
    )
    assert kept == []
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_river.py -v
```

Expected: 3 fail with `ModuleNotFoundError: No module named 'modules.create_model_river'`.

- [ ] **Step 3: Implement the helper**

Create `app/modules/create_model_river.py`:

```python
"""Centerline-driven river-polygon analysis helpers.

Extracted from `scripts/_generate_wgbast_physical_domains.py` so both
the WGBAST batch generator AND a future Create Model UI button can
share the algorithms.
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

log = logging.getLogger(__name__)


def filter_polygons_by_centerline_connectivity(
    centerline: Sequence[LineString] | LineString | MultiLineString,
    polygons: Sequence[Polygon | MultiPolygon],
    tolerance_deg: float = 0.0005,
    max_polys: int = 2000,
    label: Optional[str] = None,
) -> list[Polygon | MultiPolygon]:
    """Return only the polygons in the connected component touching the centerline.

    Algorithm (graph flood-fill):
      1. Buffer each polygon by `tolerance_deg` (small bridge over OSM
         tagging gaps).
      2. Build an STRtree spatial index for fast neighbor lookup.
      3. Seed the visited-set with polygons whose buffered envelope
         intersects the buffered centerline.
      4. BFS: for each visited polygon, find polygons whose buffered
         envelope intersects → add to visited.
      5. Return only visited polygons (capped at `max_polys`).
    """
    if not polygons:
        return []

    # Normalize centerline to a single geometry
    if isinstance(centerline, (LineString, MultiLineString)):
        centerline_union = centerline
    else:
        centerline_union = unary_union(list(centerline))

    polys = list(polygons)
    buffered = [p.buffer(tolerance_deg) for p in polys]
    tree = STRtree(buffered)
    n = len(polys)
    visited = [False] * n
    queue: list[int] = []

    seed_buffered_line = centerline_union.buffer(tolerance_deg)
    for i in tree.query(seed_buffered_line):
        if seed_buffered_line.intersects(buffered[i]) and not visited[i]:
            visited[i] = True
            queue.append(i)

    if not queue:
        log.warning(
            "[%s] no polygons touch the centerline within %.4f deg",
            label or "<unlabeled>", tolerance_deg,
        )
        return []

    while queue and sum(visited) < max_polys:
        i = queue.pop()
        for j in tree.query(buffered[i]):
            if visited[j]:
                continue
            if buffered[i].intersects(buffered[j]):
                visited[j] = True
                queue.append(j)

    kept = [polys[i] for i, v in enumerate(visited) if v]
    log.info(
        "[%s] connectivity filter: %d/%d polygons in the centerline-connected component",
        label or "<unlabeled>", len(kept), n,
    )
    return kept
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_river.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/modules/create_model_river.py tests/test_create_model_river.py
git commit -m "feat(create_model_river): filter_polygons_by_centerline_connectivity

Extracted from scripts/_generate_wgbast_physical_domains.py:
_load_osm_polygons_filtered. Generalised: takes (centerline, polygons,
tolerance_deg, max_polys, label) instead of a River dataclass.

Pure-Python helper, importable by the WGBAST batch generator and
(future) Create Model UI 'Auto-extract main river system' button."
```

### Task 2.A.4: Add `partition_polygons_along_channel` to the river module

**Files:**
- Modify: `app/modules/create_model_river.py`
- Modify: `tests/test_create_model_river.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_create_model_river.py`:

```python
def test_partition_into_4_equal_groups():
    """10 polygons distributed along a centerline → 4 groups whose sizes
    sum to 10. With n=10, n_reaches=4, q=2.5 the slice math gives
    [(0,2),(2,5),(5,7),(7,10)] → group sizes [2, 3, 2, 3]. The last
    slice always extends to n (absorbs rounding remainder)."""
    from modules.create_model_river import partition_polygons_along_channel

    centerline = [LineString([(0, 0), (10, 0)])]
    # 10 polygons strung along x = 0..10
    polys = [
        Polygon([(i, -0.5), (i + 0.5, -0.5), (i + 0.5, 0.5), (i, 0.5)])
        for i in range(10)
    ]

    groups = partition_polygons_along_channel(
        centerline=centerline,
        polygons=polys,
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=4,
    )
    assert len(groups) == 4
    # All polygons must be in exactly one group; total count preserved.
    total = sum(len(g) for g in groups)
    assert total == 10


def test_partition_with_too_few_polygons():
    """Fewer polygons than n_reaches → some groups empty; no errors."""
    from modules.create_model_river import partition_polygons_along_channel

    centerline = [LineString([(0, 0), (10, 0)])]
    polys = [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])]  # only 1 polygon

    groups = partition_polygons_along_channel(
        centerline=centerline,
        polygons=polys,
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=4,
    )
    assert len(groups) == 4
    # All polygons accounted for
    assert sum(len(g) for g in groups) == 1


def test_partition_orders_by_along_channel_distance():
    """First group contains polygons closest to mouth; last group contains
    polygons furthest from mouth.

    Uses 6 polygons over 3 reaches (2 per group) so the assertion
    actually exercises the partition algorithm, not just len-1 slicing.
    With 3 polys / 3 reaches each group would have exactly 1 polygon
    and the assertion `near_mouth in groups[0]` would pass even with
    a buggy zero-everything `.project()` because Python's stable sort
    preserves insertion order — a false-positive."""
    from modules.create_model_river import partition_polygons_along_channel

    centerline = [LineString([(0, 0), (12, 0)])]
    p_a = Polygon([(0.5, -0.3), (1.5, -0.3), (1.5, 0.3), (0.5, 0.3)])    # near
    p_b = Polygon([(2.5, -0.3), (3.5, -0.3), (3.5, 0.3), (2.5, 0.3)])    # near-mid
    p_c = Polygon([(4.5, -0.3), (5.5, -0.3), (5.5, 0.3), (4.5, 0.3)])    # mid-low
    p_d = Polygon([(6.5, -0.3), (7.5, -0.3), (7.5, 0.3), (6.5, 0.3)])    # mid-high
    p_e = Polygon([(8.5, -0.3), (9.5, -0.3), (9.5, 0.3), (8.5, 0.3)])    # far-low
    p_f = Polygon([(10.5, -0.3), (11.5, -0.3), (11.5, 0.3), (10.5, 0.3)])  # far

    groups = partition_polygons_along_channel(
        centerline=centerline,
        polygons=[p_f, p_d, p_b, p_a, p_e, p_c],   # input shuffled
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=3,
    )
    assert len(groups) == 3
    # First group should contain the two nearest (p_a, p_b)
    assert p_a in groups[0] and p_b in groups[0]
    # Middle group should contain p_c, p_d
    assert p_c in groups[1] and p_d in groups[1]
    # Last group should contain p_e, p_f
    assert p_e in groups[2] and p_f in groups[2]
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_river.py -v
```

Expected: 3 new fail with `ImportError: cannot import name 'partition_polygons_along_channel'`.

- [ ] **Step 3: Implement the helper**

Append to `app/modules/create_model_river.py`:

```python
def partition_polygons_along_channel(
    centerline: Sequence[LineString] | LineString | MultiLineString,
    polygons: Sequence[Polygon | MultiPolygon],
    mouth_lon_lat: tuple[float, float],
    n_reaches: int,
) -> list[list[Polygon | MultiPolygon]]:
    """Partition polygons into N groups by ALONG-channel distance from mouth.

    Each polygon's centroid is projected onto the centerline; polygons are
    sorted by along-line distance from the mouth point and split into N
    equal-count groups (the last group absorbs any rounding remainder).

    Returns a list of N lists. Caller assigns reach names + frac_spawn
    afterwards. For len(polygons) < n_reaches, returns mostly-empty
    lists with the polygons distributed across the first slots.
    """
    from shapely.geometry import Point

    if n_reaches < 1:
        raise ValueError(f"n_reaches must be >= 1, got {n_reaches}")
    if not polygons:
        return [[] for _ in range(n_reaches)]

    if isinstance(centerline, (LineString, MultiLineString)):
        centerline_union = centerline
    else:
        centerline_union = unary_union(list(centerline))

    mouth = Point(mouth_lon_lat)
    oriented = _orient_centerline_mouth_to_source(centerline_union, mouth)

    polys = list(polygons)
    scored = sorted(
        ((oriented.project(p.centroid), p) for p in polys),
        key=lambda t: t[0],
    )

    n = len(scored)
    q = n / float(n_reaches)
    slices = [(int(q * i), int(q * (i + 1))) for i in range(n_reaches)]
    if slices:
        slices[-1] = (slices[-1][0], n)

    return [
        [p for _, p in scored[lo:hi]]
        for lo, hi in slices
    ]


def _orient_centerline_mouth_to_source(
    centerline_union: LineString | MultiLineString,
    mouth: "Point",
) -> LineString | MultiLineString:
    """Return centerline oriented mouth → source so that .project()
    returns 0 at mouth and increases upstream.

    For a LineString: flip if mouth is closer to the end than the start.
    For a MultiLineString: try shapely.ops.linemerge first — if all
    sub-lines connect end-to-end the result is a single LineString and
    we orient it the same way. Otherwise (genuinely disjoint segments,
    common for OSM way collections like Tornionjoki+Muonio), fall back
    to a coordinate-based proxy: build a single LineString from the
    sequence of all sub-line coordinates concatenated, sorted by
    distance from the mouth. This is approximate but produces a
    monotone .project() that respects mouth → source ordering for
    ALL the common WGBAST cases.

    Returning a raw MultiLineString here is a BUG: shapely's
    MultiLineString.project() returns 0.0 for every input regardless
    of geometry, which silently scrambles the partition.
    """
    from shapely.ops import linemerge

    if centerline_union.geom_type == "LineString":
        coords = list(centerline_union.coords)
        d_start = mouth.distance(Point(coords[0]))
        d_end = mouth.distance(Point(coords[-1]))
        if d_start > d_end:
            coords = list(reversed(coords))
        return LineString(coords)

    # MultiLineString: try linemerge first
    merged = linemerge(centerline_union)
    if merged.geom_type == "LineString":
        coords = list(merged.coords)
        d_start = mouth.distance(Point(coords[0]))
        d_end = mouth.distance(Point(coords[-1]))
        if d_start > d_end:
            coords = list(reversed(coords))
        return LineString(coords)

    # Disconnected: concatenate sub-line coordinates sorted by distance
    # from the mouth. Approximate but produces a monotone .project().
    all_coords: list[tuple[float, float]] = []
    for sub in merged.geoms:
        all_coords.extend(list(sub.coords))
    # Deduplicate while preserving order
    seen: set[tuple[float, float]] = set()
    unique: list[tuple[float, float]] = []
    for c in all_coords:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    # Sort by distance from mouth
    unique.sort(key=lambda c: mouth.distance(Point(c)))
    if len(unique) < 2:
        return merged  # fall through; downstream will detect a degenerate input
    return LineString(unique)
```

**Add a unit test** that exercises the MultiLineString path. Append to `tests/test_create_model_river.py`:

```python
def test_partition_handles_multilinestring_centerline():
    """Tornionjoki centerline is a MultiLineString; project() on a raw
    MultiLineString returns 0.0 for every point. Verify partition
    still orders polygons mouth → source after linemerge / coordinate
    concatenation."""
    from shapely.geometry import MultiLineString
    from modules.create_model_river import partition_polygons_along_channel

    # Two sub-lines that merge cleanly into a single LineString
    cl = MultiLineString([
        [(0, 0), (5, 0)],
        [(5, 0), (10, 0)],
    ])
    near_mouth = Polygon([(0, -0.5), (1, -0.5), (1, 0.5), (0, 0.5)])
    far = Polygon([(9, -0.5), (10, -0.5), (10, 0.5), (9, 0.5)])

    groups = partition_polygons_along_channel(
        centerline=cl,
        polygons=[far, near_mouth],
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=2,
    )
    assert near_mouth in groups[0], "near-mouth polygon not in first group"
    assert far in groups[1], "far polygon not in last group"


def test_partition_handles_disjoint_multilinestring():
    """Genuinely disjoint MultiLineString (no shared endpoints) — linemerge
    cannot merge, so the helper falls back to coordinate-distance sort.
    Approximate but should still order polygons mouth → source for a
    river-shaped (roughly radial-from-mouth) input."""
    from shapely.geometry import MultiLineString
    from modules.create_model_river import partition_polygons_along_channel

    # Disjoint: no endpoint shared between (0,0)→(4,0) and (6,0)→(10,0)
    cl = MultiLineString([
        [(0, 0), (4, 0)],
        [(6, 0), (10, 0)],
    ])
    near_mouth = Polygon([(0, -0.5), (1, -0.5), (1, 0.5), (0, 0.5)])
    far = Polygon([(9, -0.5), (10, -0.5), (10, 0.5), (9, 0.5)])

    groups = partition_polygons_along_channel(
        centerline=cl,
        polygons=[far, near_mouth],
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=2,
    )
    assert near_mouth in groups[0], "near-mouth polygon not in first group (disjoint MLS)"
    assert far in groups[1], "far polygon not in last group (disjoint MLS)"


def test_partition_handles_y_shaped_multilinestring():
    """Y-junction case (real Tornionjoki+Muonio shape): mouth at one end,
    centerline branches in two directions. The fallback's
    Euclidean-distance sort produces a self-crossing synthetic
    LineString — verify partition still places near-mouth polygons in
    the first reach group regardless of which branch they're on.

    This is the case the prior tests (1-D colinear segments) cannot
    surface: real branching geometry where Euclidean distance from
    mouth ≠ along-channel distance."""
    from shapely.geometry import MultiLineString
    from modules.create_model_river import partition_polygons_along_channel

    # Trunk going north, then branches NE (Torne main) and NW (Muonio)
    # Mouth at (0, 0). Trunk: (0,0)→(0,3). NE branch: (0,3)→(2,5). NW: (0,3)→(-2,5).
    cl = MultiLineString([
        [(0, 0), (0, 3)],     # trunk (mouth → confluence)
        [(0, 3), (2, 5)],     # NE branch (Torne main)
        [(0, 3), (-2, 5)],    # NW branch (Muonio)
    ])
    # 6 polygons: 2 near mouth, 2 mid-trunk, 1 each on NE and NW branches
    p_mouth_a = Polygon([(0.1, 0.0), (0.4, 0.0), (0.4, 0.3), (0.1, 0.3)])
    p_mouth_b = Polygon([(-0.4, 0.0), (-0.1, 0.0), (-0.1, 0.3), (-0.4, 0.3)])
    p_mid_a = Polygon([(0.1, 1.5), (0.4, 1.5), (0.4, 1.8), (0.1, 1.8)])
    p_mid_b = Polygon([(-0.4, 1.5), (-0.1, 1.5), (-0.1, 1.8), (-0.4, 1.8)])
    p_ne = Polygon([(1.7, 4.5), (2.0, 4.5), (2.0, 4.8), (1.7, 4.8)])
    p_nw = Polygon([(-2.0, 4.5), (-1.7, 4.5), (-1.7, 4.8), (-2.0, 4.8)])

    groups = partition_polygons_along_channel(
        centerline=cl,
        polygons=[p_ne, p_nw, p_mid_a, p_mid_b, p_mouth_a, p_mouth_b],
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=3,
    )
    # First group must contain BOTH near-mouth polygons (they're closer
    # to mouth than mid-trunk, regardless of which branch they sit on).
    assert p_mouth_a in groups[0] and p_mouth_b in groups[0], (
        "near-mouth polygons not in first group (Y-shaped MLS): "
        f"groups[0]={groups[0]}"
    )
    # Last group must contain BOTH branch-end polygons.
    assert p_ne in groups[2] and p_nw in groups[2], (
        "branch-end polygons not in last group (Y-shaped MLS): "
        f"groups[2]={groups[2]}"
    )
```

Add to the existing imports at the top of the file:
```python
from shapely.geometry import Point  # noqa: F401  (used inside _orient_centerline_mouth_to_source)
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_river.py -v
```

Expected: 9 PASS (3 from Task 2.A.3 + 3 partition tests + 1 MLS-merge + 1 MLS-disjoint + 1 Y-shape).

- [ ] **Step 5: Commit**

```bash
git add app/modules/create_model_river.py tests/test_create_model_river.py
git commit -m "feat(create_model_river): partition_polygons_along_channel

Extracted from scripts/_generate_wgbast_physical_domains.py:
build_reach_segments_from_polygons. Generalised: returns N lists of
polygons; caller assigns reach names + frac_spawn separately. Drops the
WGBAST-specific REACH_NAMES/FRAC_SPAWN hardcoding."
```

### Task 2.A.5: Refactor `create_model_panel.py` to import `query_named_sea_polygon`

**Why:** Behaviour-preserving extraction. The 🌊 Sea button keeps working bit-for-bit; the helper now lives in a shared module.

**Files:**
- Modify: `app/modules/create_model_panel.py:86-108` (replace the private `_query_marine_regions`)

**IMPORTANT — TYPE-CONTRACT CHANGE.** The existing `_query_marine_regions` returns a **dict** (raw GeoJSON via `resp.json()`). The new `query_named_sea_polygon` returns a **GeoDataFrame**. These are NOT swap-compatible — the consumer at `_on_fetch_sea` (lines 727–763) does `geoj.get("features")` and `gpd.GeoDataFrame.from_features(geoj["features"], ...)`, both of which fail on a GeoDataFrame. This step rewrites BOTH the helper and its consumer.

- [ ] **Step 1: Replace the private helper with an import**

Open `app/modules/create_model_panel.py`. The current lines 86–108 define `_query_marine_regions`:

```python
def _query_marine_regions(bbox_wgs84):
    """Query Marine Regions WFS for IHO sea area polygons in a bounding box.
    ...
```

Replace those lines (86–108) with the existing project pattern of try/except-guarded imports (verified at `create_model_panel.py:25-49` — every internal `modules.*` import is wrapped so a single missing module doesn't crash the whole Shiny app):

```python
try:
    from modules.create_model_marine import query_named_sea_polygon
except ImportError:  # pragma: no cover — matches existing fallback pattern
    query_named_sea_polygon = None  # type: ignore[assignment]
```

**IMPORTANT**: this is an ABSOLUTE import (`from modules.create_model_marine`), NOT a relative import (`from .create_model_marine`). The Shiny app loads `create_model_panel.py` as a top-level module, not as part of a package — `__package__` is `None`, so a leading-dot import would raise `ImportError: attempted relative import with no known parent package` at startup. This matches the pattern of every other internal import in `create_model_panel.py` (verified at lines 26–65: `from modules.create_model_grid import ...`, `from modules.create_model_osm import ...`, etc.).

Note we do NOT alias as `_query_marine_regions` — the consumer is being rewritten in Step 2 below to consume a GeoDataFrame directly.

The smoke-test in Step 3 below uses source-string substring matching that still matches the guarded form (the literal `from modules.create_model_marine import query_named_sea_polygon` substring is unchanged, just nested in a `try:` block).

**Also remove now-orphaned imports/constants from `create_model_panel.py`:**
- Line 16: `import requests` — no longer used after Step 2 (handler uses the helper, not `requests` directly).
- Line 71: `MARINE_REGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"` — moved into `create_model_marine.py`.

After the edit, verify with:
```bash
grep -n "import requests\|MARINE_REGIONS_WFS\|requests\.get\|_query_marine_regions" app/modules/create_model_panel.py
```
Expected: **no matches** (empty grep output). Specifically, no `requests.get(...)` reference must remain — that would mean the body of the original `_query_marine_regions` was left in place when only its `def` line was removed. Strict-mode ruff (CI) flags F401 for unused imports — leaving them in breaks CI.

- [ ] **Step 2: Rewrite the `_on_fetch_sea` handler to consume a GeoDataFrame**

The current handler is at lines 727–763 of `app/modules/create_model_panel.py`. The function signature `async def _on_fetch_sea():` is at line 727; KEEP that line and the next two (`_fetch_msg.set("Fetching ...")` + `bbox = _get_view_bbox()`). REPLACE the body from `import asyncio` through `await _refresh_map()` (approximately lines 731–763).

The current handler body is shaped for a dict return:

```python
geoj = await loop.run_in_executor(None, _query_marine_regions, bbox)
if geoj is None or not geoj.get("features"):
    _fetch_msg.set("No sea areas found — try zooming out to see the coast.")
    return
gdf = gpd.GeoDataFrame.from_features(geoj["features"], crs="EPSG:4326")
# Post-filter: WFS bbox returns global polygons that merely touch the bbox.
from shapely.geometry import box as _box
view_box = _box(*bbox)
gdf = gdf[gdf.geometry.intersects(view_box)].copy()
if len(gdf) > 1:
    center = view_box.centroid
    covers = gdf[gdf.geometry.contains(center)]
    if len(covers) > 0:
        gdf = covers.copy()
if len(gdf) == 0:
    _fetch_msg.set("No sea areas found — try zooming out to see the coast.")
    return
gdf["geometry"] = gdf.geometry.simplify(0.01, preserve_topology=True)
_sea_gdf.set(gdf)
names = ", ".join(gdf["name"].dropna().unique()[:5]) if "name" in gdf.columns else ""
_fetch_msg.set(f"Loaded {len(gdf)} sea areas. {names}")
await _refresh_map()
```

Replace the body of `_on_fetch_sea` (the lines AFTER `bbox = _get_view_bbox()` through the end of the handler — keeping the `async def` signature and the first two body lines intact) with:

```python
import asyncio
# Guard against the helper-module import having failed (matches the
# graceful-degradation pattern of other panel imports at lines 25-49)
if query_named_sea_polygon is None:
    _fetch_msg.set(
        "Marine Regions helper unavailable (create_model_marine module "
        "failed to import). Sea-fetch disabled."
    )
    return
loop = asyncio.get_running_loop()
gdf = await loop.run_in_executor(None, query_named_sea_polygon, bbox)
# query_named_sea_polygon already does the bbox-intersect + centroid-cover
# post-filter that this handler used to do inline (see create_model_marine.py).
# It returns a GeoDataFrame in EPSG:4326 with columns ['name', 'geometry'],
# or None on failure / empty result.
if gdf is None or len(gdf) == 0:
    _fetch_msg.set("No sea areas found — try zooming out to see the coast.")
    return
gdf = gdf.copy()
gdf["geometry"] = gdf.geometry.simplify(0.01, preserve_topology=True)
_sea_gdf.set(gdf)
names = ", ".join(gdf["name"].dropna().unique()[:5]) if "name" in gdf.columns else ""
_fetch_msg.set(f"Loaded {len(gdf)} sea areas. {names}")
await _refresh_map()
```

This is a behaviour-preserving rewrite: the bbox-intersect + centroid-cover filter is now in `query_named_sea_polygon` instead of inline. Net effect: the handler is ~10 lines shorter, and the helper does the geographic filtering once for both UI and batch callers.

- [ ] **Step 2b: Verify no other call sites of `_query_marine_regions` exist**

```bash
grep -rn "_query_marine_regions" app/ scripts/
```

Expected: only the import at line 86 and the call at line 733 (or thereabouts) in the same file. If anything else references it, update the import accordingly.

- [ ] **Step 3: Smoke-test the panel module imports cleanly + handler is callable**

Append to `tests/test_create_model_marine.py`:

```python
def test_create_model_panel_imports_query_named_sea_polygon():
    """The panel must import the helper and no longer define
    its own private dict-returning version. Detects (via source-string
    substring matching, NOT runtime import):
      - missing absolute import: catches the case where the engineer
        used `from .create_model_marine` (relative) — the required
        absolute-import substring would be absent
      - residual references to the old _query_marine_regions function
        or its supporting `requests`/MARINE_REGIONS_WFS imports

    Source-read check rather than importing `create_model_panel`,
    because the panel module loads Shiny `@module.ui` / `@module.server`
    decorators and deck.gl bindings that may fail outside a Shiny
    session (no other test imports the panel module)."""
    panel_src = (ROOT / "app" / "modules" / "create_model_panel.py").read_text(encoding="utf-8")

    # Required: the new import line is present
    assert "from modules.create_model_marine import query_named_sea_polygon" in panel_src, (
        "create_model_panel.py missing the import of query_named_sea_polygon — "
        "Task 2.A.5 Step 1 was incomplete"
    )
    # Forbidden: stale references to the old private function
    assert "_query_marine_regions" not in panel_src, (
        "stale _query_marine_regions reference still in create_model_panel.py — "
        "Task 2.A.5 Step 2 (handler rewrite) was incomplete"
    )
    # Forbidden: the old WFS endpoint constant
    assert "MARINE_REGIONS_WFS" not in panel_src, (
        "stale MARINE_REGIONS_WFS constant still in create_model_panel.py — "
        "Task 2.A.5 Step 1 (orphan-import cleanup) was incomplete"
    )
    # Forbidden: direct use of requests in the panel (handler now uses the helper)
    assert "requests.get" not in panel_src, (
        "stale requests.get(...) call still in create_model_panel.py — "
        "Task 2.A.5 Step 2 (handler rewrite) was incomplete"
    )


def test_query_named_sea_polygon_returns_geodataframe_for_handler(monkeypatch):
    """Type-contract test on the helper: confirms the return type is
    a GeoDataFrame (not a dict). The handler in _on_fetch_sea was
    rewritten in Task 2.A.5 Step 2 to consume a GeoDataFrame directly;
    if the helper ever regresses to returning a dict, this test fails
    fast and signals the handler will break.

    Note: this is a CONTRACT test, not a handler integration test —
    the handler itself runs inside a Shiny session and is not
    directly invoked here. A regression that broke the handler's
    interaction with `_sea_gdf` or `_refresh_map` would not be caught;
    those are exercised by the broader Create Model panel test suite."""
    from modules import create_model_marine as m

    fake_geoj = {
        "features": [{
            "type": "Feature",
            "properties": {"name": "Mock Sea"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]],
            },
        }],
    }
    class _FakeResp:
        def raise_for_status(self): pass
        def json(self): return fake_geoj
    monkeypatch.setattr(m.requests, "get", lambda *a, **kw: _FakeResp())

    result = m.query_named_sea_polygon((-0.5, -0.5, 0.5, 0.5))
    # Contract assertions used by _on_fetch_sea:
    assert result is not None, "helper returned None on success path"
    import geopandas as gpd
    assert isinstance(result, gpd.GeoDataFrame), (
        f"helper returned {type(result).__name__}, not GeoDataFrame"
    )
    assert "name" in result.columns
    assert "geometry" in result.columns
    # The handler does len(gdf) and gdf.geometry.simplify; both must work
    assert len(result) >= 1
    _ = result.geometry.simplify(0.01, preserve_topology=True)
```

Run:

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_marine.py -v
```

Expected: 8 PASS (3 from Task 2.A.1 + 3 from Task 2.A.2 + 2 new from this step).

Also run the broader Create Model test surface:

```bash
micromamba run -n shiny python -m pytest tests/ -k create_model -v 2>&1 | tail -20
```

Expected: same pre-task baseline + 8 new tests in test_create_model_marine.py.

- [ ] **Step 4: Commit**

```bash
git add app/modules/create_model_panel.py tests/test_create_model_marine.py
git commit -m "refactor(create_model_panel): use shared query_named_sea_polygon

Replaces the private _query_marine_regions with a re-export from
app/modules/create_model_marine.py. The 🌊 Sea button at line 229 keeps
its existing behaviour — same call site at line 733, just resolved
via the new shared module.

Behaviour-preserving."
```

## Section B — WGBAST generator refactor (extraction only)

### Task 2.B.1: Refactor `_generate_wgbast_physical_domains.py` to import the helpers

**Why:** Today the connectivity filter and along-channel partition are private functions inside the script. Replacing them with imports from `app/modules/` removes ~100 lines from the script and makes the behaviour-preserving link between batch + UI.

**Files:**
- Modify: `scripts/_generate_wgbast_physical_domains.py`

- [ ] **Step 1: Add imports for the new helpers**

Open `scripts/_generate_wgbast_physical_domains.py`. Locate the existing import at line 42:
```python
from modules.create_model_grid import generate_cells  # noqa: E402
```

Add these imports immediately after:
```python
from modules.create_model_river import (  # noqa: E402
    filter_polygons_by_centerline_connectivity,
    partition_polygons_along_channel,
)
```

- [ ] **Step 2: Replace `_load_osm_polygons_filtered` body with a call to the new helper**

Locate `_load_osm_polygons_filtered` (around line 201 in the original file; the function has the docstring "Load cached OSM water polygons, keep only the connected component..."). Replace its body — the part AFTER the `data = json.loads(...)` line and the `raw_polys` assembly loop — with:

```python
def _load_osm_polygons_filtered(
    river: River, centerline: list[LineString]
) -> list:
    """Load cached OSM water polygons, keep only the connected component
    that touches the centerline.

    Thin wrapper around create_model_river.filter_polygons_by_centerline_connectivity.
    """
    poly_cache = OSM_CACHE / f"{river.short_name}_polygons.json"
    if not poly_cache.exists():
        return []
    data = json.loads(poly_cache.read_text(encoding="utf-8"))
    raw_polys: list = []
    for item in data:
        try:
            poly = shape(item["geometry"])
        except Exception:
            continue
        if not poly.is_valid or poly.is_empty:
            continue
        if poly.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        raw_polys.append(poly)
    return filter_polygons_by_centerline_connectivity(
        centerline=centerline,
        polygons=raw_polys,
        tolerance_deg=POLY_CONNECT_TOL_DEG,
        max_polys=MAX_CONNECTED_POLYS,
        label=river.river_name,
    )
```

- [ ] **Step 3: Replace `build_reach_segments_from_polygons` body**

Locate `build_reach_segments_from_polygons` (the function with docstring "Partition water polygons into 4 reaches by ALONG-CHANNEL distance"). Replace its body with:

```python
def build_reach_segments_from_polygons(
    river: River, centerline: list[LineString], polygons: list
) -> dict:
    """Partition water polygons into 4 reaches by along-channel distance,
    delegating geometry to create_model_river.partition_polygons_along_channel.
    """
    if len(polygons) < 4:
        log.warning(
            "[%s] only %d polygons (need ≥4) — falling back to line-buffer split.",
            river.river_name, len(polygons),
        )
        return build_reach_segments_from_osm(river, centerline)

    groups = partition_polygons_along_channel(
        centerline=centerline,
        polygons=polygons,
        mouth_lon_lat=river.waypoints[0],
        n_reaches=len(REACH_NAMES),  # 4
    )

    segments: dict = {}
    for name, frac, group in zip(REACH_NAMES, FRAC_SPAWN, groups):
        if not group:
            continue
        segments[name] = {
            "segments": group,
            "frac_spawn": frac,
            "type": "water",
        }
        log.info("  [%s] %d polys", name, len(group))
    return segments
```

- [ ] **Step 4: Delete the now-unused `_orient_centerline_mouth_to_source` function from the script**

The helper has been moved (as a private helper) into `app/modules/create_model_river.py` (where `partition_polygons_along_channel` calls it internally). Find `_orient_centerline_mouth_to_source` in `_generate_wgbast_physical_domains.py` and delete the entire function (it's around 30 lines).

- [ ] **Step 5: Verify the regenerator still produces identical output**

Save the existing fixtures' shapefile metadata as a baseline:
```bash
micromamba run -n shiny python scripts/_probe_wgbast_river_extents.py > /tmp/wgbast_extents_before.txt 2>&1
```

Re-run the generator (it will regenerate all 4 fixtures, but PR-1 already changed Tornionjoki's so we expect Tornionjoki to differ from a hypothetical pre-PR-1 baseline; the right comparison is "post-PR-1 vs post-Section-B"):
```bash
micromamba run -n shiny python scripts/_generate_wgbast_physical_domains.py
micromamba run -n shiny python scripts/_probe_wgbast_river_extents.py > /tmp/wgbast_extents_after.txt 2>&1
diff /tmp/wgbast_extents_before.txt /tmp/wgbast_extents_after.txt
```

Expected: empty diff (Section B is a pure refactor).

- [ ] **Step 6: Commit**

```bash
git add scripts/_generate_wgbast_physical_domains.py
git commit -m "refactor(wgbast): use shared helpers from create_model_river

_load_osm_polygons_filtered → thin wrapper over
filter_polygons_by_centerline_connectivity.

build_reach_segments_from_polygons → thin wrapper over
partition_polygons_along_channel + reach naming.

_orient_centerline_mouth_to_source removed (now lives in
create_model_river.py as private helper).

Behaviour-preserving — fixtures regenerate identically."
```

## Section C — BalticCoast cell generation

### Task 2.C.1: Add module-level constants + WFS payload caching helper

**ORCHESTRATOR PRECONDITION:** This task and Task 2.C.2 hit Marine Regions WFS on first run. Confirm the pre-flight check from the plan preamble passed before dispatching. If WFS is down, defer Task 2.C.1 onwards; Tasks 2.A/2.B can proceed independently.

**Files:**
- Modify: `scripts/_generate_wgbast_physical_domains.py`

- [ ] **Step 1: Add the two constants**

After the existing `MAX_CONNECTED_POLYS = 2000` line in `_generate_wgbast_physical_domains.py`, add:

```python
# BalticCoast (marine) reach constants. v0.46+ spec §Architecture overview.
BALTICCOAST_RADIUS_M = 10_000.0       # 10 km clip around river mouth

# Marine cell_size = river.cell_size_m × factor. Per-river so Mörrumsån's
# 60 m freshwater cells don't produce >5000 marine cells (the 10 km disk
# at Hanöbukten is mostly open water). Tornionjoki/Simojoki/Byskeälven
# use factor=4 (river cells 80–150 m → marine 320–600 m).
# Mörrumsån uses factor=8 (river 60 m → marine 480 m, ~1500 disk cells).
BALTICCOAST_CELL_FACTOR_DEFAULT = 4.0
BALTICCOAST_CELL_FACTOR_OVERRIDE = {
    "example_morrumsan": 8.0,
}
```

- [ ] **Step 2: Add the WFS-payload cache helper**

Add this function after `_load_osm_ways` in the same file:

```python
def _load_or_fetch_marineregions(
    river: River,
    refresh: bool = False,
    bbox_pad_deg: float = 0.5,
) -> "gpd.GeoDataFrame | None":
    """Return the Marine Regions IHO polygons for `river`, cached at
    tests/fixtures/_osm_cache/<short_name>_marineregions.json.

    On first call (or when `refresh=True`), queries Marine Regions WFS
    via `create_model_marine.query_named_sea_polygon`. Caches the
    response as a flat list of GeoJSON features (matching the existing
    OSM line/polygon cache shape).

    Returns None if WFS fetch fails on a fresh attempt.
    """
    cache = OSM_CACHE / f"{river.short_name}_marineregions.json"
    if not refresh and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if not data:
            # An empty cache file is never a legitimate state — we only
            # write the cache when WFS returned a non-empty result.
            # Surface this as a hard error rather than silently returning
            # None (which would mask the real cause: the cache was
            # corrupted, manually emptied, or written by an old buggy
            # version of this script).
            raise RuntimeError(
                f"Cache file {cache} is empty. Delete it and re-run "
                f"with --refresh-marineregions, or copy a known-good "
                f"cache from another developer's machine."
            )
        gdf = gpd.GeoDataFrame.from_features(data, crs="EPSG:4326")
        return gdf[["name", "geometry"]] if "name" in gdf.columns else gdf

    from modules.create_model_marine import query_named_sea_polygon
    mouth_lon, mouth_lat = river.waypoints[0]
    bbox = (
        mouth_lon - bbox_pad_deg, mouth_lat - bbox_pad_deg,
        mouth_lon + bbox_pad_deg, mouth_lat + bbox_pad_deg,
    )
    gdf = query_named_sea_polygon(bbox)
    if gdf is None or gdf.empty:
        # WFS unreachable or empty result — do NOT write an empty cache
        # file. Future calls will see "no cache" and retry the WFS,
        # rather than seeing a corrupt empty cache.
        return None
    # Cache as a list of GeoJSON features (always non-empty here)
    payload = json.loads(gdf.to_json())["features"]
    if not payload:
        # Defensive: gdf was non-empty but to_json round-trip yielded
        # no features. Don't write a misleading empty cache.
        return gdf
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return gdf
```

Add `import geopandas as gpd` to the imports at the top of the file if it's not already there (it should be — the existing imports use it).

- [ ] **Step 3: Commit**

```bash
git add scripts/_generate_wgbast_physical_domains.py
git commit -m "feat(wgbast): add BalticCoast constants + Marine Regions cache helper

Constants:
  BALTICCOAST_RADIUS_M = 10_000.0                (10 km disk at river mouth)
  BALTICCOAST_CELL_FACTOR_DEFAULT = 4.0          (marine cells coarser than river)
  BALTICCOAST_CELL_FACTOR_OVERRIDE['example_morrumsan'] = 8.0
                                                 (Mörrumsån's open Hanöbukten
                                                 would otherwise blow past
                                                 the cell-count cap)

_load_or_fetch_marineregions caches the WFS response to
tests/fixtures/_osm_cache/<short_name>_marineregions.json so the
regenerator is offline-clean after the first run with network."
```

**Important — commit the cached payloads in this same PR.** Once Task 2.C.2 has run successfully and produced the 4 `_marineregions.json` files in `tests/fixtures/_osm_cache/`, those are committed alongside the regenerated shapefiles. Future re-runs of the generator and CI test runs are then fully offline-clean. The `--refresh` flag (still to be added; see _fetch_wgbast_osm_polylines.py for the existing pattern) is the only trigger to re-fetch.

### Task 2.C.2: Add BalticCoast cell-generation step to the generator

**Files:**
- Modify: `scripts/_generate_wgbast_physical_domains.py`

**Note on commit granularity:** the prescribed replacement adds ~90 lines to `write_river_shapefile`. The block is logically one change (build BalticCoast cells); attempts to artificially split it into multiple commits create commits that don't compile or that have unused imports. **Land it as one commit.** Bisection granularity is achieved by:

1. Smoke-test on Mörrumsån (smallest fixture, ~30s) BEFORE applying the BalticCoast block — confirms the existing path still works.
2. Apply the block.
3. Smoke-test on Mörrumsån AFTER — confirms the new path works.
4. Smoke-test on Tornionjoki (largest, ~2 min) — confirms scaling.

If smoke-test #3 fails, the failure is contained to "the BalticCoast block" — narrower than re-bisecting the whole release.

**Rollback strategy:** the regenerator iterates through 4 rivers in `RIVERS`. If any river fails (Marine Regions WFS rejects a query, disk-clip raises `ValueError`, adjacency check raises `RuntimeError`), the regenerator dies mid-iteration leaving a half-converted state: rivers 1..N have new 5-reach shapefiles; rivers N+1..4 have the old 4-reach shapefiles. Section D's `_balticcoast_cell_count` would then crash on the half-converted rivers with a `FileNotFoundError`-or-similar.

To avoid this:
- Before commit: regenerate ALL 4 rivers and verify with `_probe_wgbast_river_extents.py`. If any river shows fewer than 5 reaches, do NOT commit; investigate the regenerator log and re-run.
- If you've already committed and discover the half-converted state mid-Section-D: `git reset --hard HEAD~1` to revert the partial regenerate, then fix the root cause and re-run from Task 2.C.2.

`git status tests/fixtures/example_*/Shapefile/` after a successful run should show all 4 rivers' shapefiles modified, not just some.

- [ ] **Step 1: Locate the `write_river_shapefile` function**

It's around line 478 of the file. Find the section after `cells = generate_cells(...)` and before `cells = cells.rename(columns=COLUMN_RENAME)`.

- [ ] **Step 2: Replace the single-pass `generate_cells` block with a fresh+marine two-pass approach**

The existing block looks like this (approximate, exact lines may shift):

```python
    cells = generate_cells(
        reach_segments=reach_segments,
        cell_size=river.cell_size_m,
        cell_shape="hexagonal",
        buffer_factor=river.buffer_factor,
        min_overlap=0.1,
    )

    if cells.empty:
        raise RuntimeError(...)

    log.info("Generated %d cells", len(cells))
    log.info("Per-reach distribution:")
    for reach, count in cells["reach_name"].value_counts().sort_index().items():
        log.info("  %-8s %d cells", reach, count)

    # Rename columns to match the shapefile-loader contract
    cells = cells.rename(columns=COLUMN_RENAME)
```

Replace it with:

```python
    fresh = generate_cells(
        reach_segments=reach_segments,
        cell_size=river.cell_size_m,
        cell_shape="hexagonal",
        buffer_factor=river.buffer_factor,
        min_overlap=0.1,
    )
    if fresh.empty:
        raise RuntimeError(
            f"{river.short_name}: generate_cells returned 0 freshwater cells. "
            f"Increase buffer_factor or cell_size and re-run."
        )

    # --- BalticCoast marine reach -----------------------------------------
    # Pin the marine disk to the MOUTH's UTM zone (NOT the freshwater
    # centroid's zone). The mouth is where the disk is centred, and for
    # Tornionjoki the mouth lon=24.142° is in zone 35 while the centerline
    # centroid is at ~23.77° (zone 34); using the freshwater zone for a
    # mouth-centred disk would push the entire disk to the far edge of
    # the wrong zone where UTM scale distortion grows.
    #
    # The freshwater grid was already generated by `generate_cells` in a
    # zone derived from its own internal centroid logic. Both grids are
    # reprojected to WGS84 by `generate_cells` before they are returned
    # (see app/modules/create_model_grid.py:237 `gdf.to_crs("EPSG:4326")`),
    # so cross-zone differences are eliminated in the output. The 1e-5°
    # WGS84 buffer (~1m) absorbs cell-edge round-trip drift, not zone
    # drift — adjacency between Mouth and BalticCoast cells is
    # reliable as long as the disk extends to the freshwater shoreline.
    #
    # IMPORTANT: also add `from shapely.geometry import Point` and
    # `from modules.create_model_utils import detect_utm_epsg`,
    # `from modules.create_model_marine import clip_sea_polygon_to_disk`
    # at the MODULE TOP of the script (alongside the existing imports
    # near line 30-42). Importing inside the function works but is
    # fragile under future refactors.

    mouth_lon, mouth_lat = river.waypoints[0]
    utm_epsg = detect_utm_epsg(mouth_lon, mouth_lat)

    sea_gdf = _load_or_fetch_marineregions(river)
    if sea_gdf is None or sea_gdf.empty:
        raise RuntimeError(
            f"{river.river_name}: Marine Regions returned no sea polygon. "
            f"Re-run when WFS recovers (or run with --refresh-marineregions)."
        )
    # Use a tiny buffer + intersects rather than strict contains.
    # The mouth waypoint often lies exactly on the IHO sea-area boundary
    # (river mouths ARE coastlines); strict contains() returns False on
    # boundary points and would raise a spurious "no sea polygon" error.
    mouth_pt = Point(river.waypoints[0])
    mouth_buffered = mouth_pt.buffer(1e-6)  # ~10 cm tolerance for boundary cases
    sea_gdf = sea_gdf[sea_gdf.geometry.intersects(mouth_buffered)]
    if sea_gdf.empty:
        raise RuntimeError(
            f"{river.river_name}: no sea polygon contains the mouth point "
            f"{river.waypoints[0]}. Mouth waypoint may need updating."
        )
    sea_polygon = sea_gdf.geometry.iloc[0]

    bc_polygon = clip_sea_polygon_to_disk(
        sea_polygon=sea_polygon,
        mouth_lon_lat=river.waypoints[0],
        radius_m=BALTICCOAST_RADIUS_M,
        utm_epsg=utm_epsg,
    )
    # The intersection can return a MultiPolygon if the disk straddles
    # an island, peninsula, or skerry (e.g., Tärnö near Mörrum, the many
    # small skerries near Tornio). Pass the geoms separately to
    # generate_cells so each piece tessellates independently. Polygon-
    # with-holes is also handled correctly by generate_cells (line 173
    # uses combined_buffer.intersection(poly) which preserves holes —
    # cells inside an island get empty intersection and are dropped).
    #
    # Edge case: shapely's intersection can return a GeometryCollection
    # when the disk and sea polygon share an exact boundary segment.
    # Filter to (Multi)Polygon members so generate_cells doesn't get
    # passed a degenerate Point/LineString that would silently produce
    # zero cells.
    if bc_polygon.geom_type == "MultiPolygon":
        bc_segments = list(bc_polygon.geoms)
    elif bc_polygon.geom_type == "Polygon":
        bc_segments = [bc_polygon]
    elif bc_polygon.geom_type == "GeometryCollection":
        bc_segments = [
            g for g in bc_polygon.geoms
            if g.geom_type in ("Polygon", "MultiPolygon")
        ]
        if not bc_segments:
            raise RuntimeError(
                f"{river.river_name}: BalticCoast intersection returned a "
                f"GeometryCollection with no polygon members "
                f"(only points/lines). Disk likely tangent to coastline."
            )
    else:
        raise RuntimeError(
            f"{river.river_name}: unexpected geometry type "
            f"{bc_polygon.geom_type!r} from clip_sea_polygon_to_disk"
        )
    bc_segment = {"segments": bc_segments, "frac_spawn": 0.0, "type": "sea"}
    bc_cell_factor = BALTICCOAST_CELL_FACTOR_OVERRIDE.get(
        river.short_name, BALTICCOAST_CELL_FACTOR_DEFAULT,
    )
    marine = generate_cells(
        reach_segments={"BalticCoast": bc_segment},
        cell_size=river.cell_size_m * bc_cell_factor,
        cell_shape="hexagonal",
        buffer_factor=1.0,
        min_overlap=0.1,
    )
    if marine.empty:
        raise RuntimeError(
            f"{river.river_name}: BalticCoast generated 0 cells "
            f"(disk minus coastline likely too small at "
            f"radius={BALTICCOAST_RADIUS_M}m)."
        )

    # Concat freshwater + marine. pd.concat of two GeoDataFrames may
    # return a plain DataFrame (CRS lost) on older geopandas — wrap
    # explicitly so downstream .geometry.buffer() and .to_file() work.
    cells = gpd.GeoDataFrame(
        pd.concat([fresh, marine], ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    # Renumber cell_ids with width adapted to the total count
    # (so C00001 and C99999 sort lexically).
    width = max(4, len(str(len(cells))))
    cells["cell_id"] = [f"C{i+1:0{width}d}" for i in range(len(cells))]

    log.info("Generated %d cells (fresh=%d + BalticCoast=%d)",
             len(cells), len(fresh), len(marine))
    log.info("Per-reach distribution:")
    for reach, count in cells["reach_name"].value_counts().sort_index().items():
        log.info("  %-12s %d cells", reach, count)

    # --- Adjacency sanity check ------------------------------------------
    mouth_subset = cells[cells["reach_name"] == "Mouth"]
    marine_subset = cells[cells["reach_name"] == "BalticCoast"]
    if mouth_subset.empty:
        raise RuntimeError(
            f"{river.river_name}: 0 cells assigned to 'Mouth' reach — "
            f"check REACH_NAMES + partition output."
        )
    # Quick empty check before the UTM reproject + adjacency math
    if marine_subset.geometry.union_all().is_empty:
        raise RuntimeError(
            f"{river.river_name}: BalticCoast geometry empty after concat."
        )
    # Project both subsets to UTM for a true-meters adjacency check.
    # A WGS84-degree buffer is anisotropic at high latitudes (1e-5° is
    # ~0.45 m east-west at 65°N, ~1.1 m north-south) — the Tornio coast
    # runs roughly N-S so a degree-buffer's E-W slack would be the
    # constraint. UTM gives uniform meters; 5 m absorbs UTM↔WGS84
    # round-trip drift comfortably without false-positives.
    mouth_utm = mouth_subset.to_crs(epsg=utm_epsg)
    marine_utm = marine_subset.to_crs(epsg=utm_epsg)
    marine_union_utm = marine_utm.geometry.union_all()
    hits = mouth_utm.geometry.buffer(5.0).intersects(marine_union_utm).sum()
    if hits == 0:
        raise RuntimeError(
            f"{river.river_name}: BalticCoast not adjacent to Mouth — "
            f"disk geometry leaves a gap (radius {BALTICCOAST_RADIUS_M}m). "
            f"Increase radius or move mouth waypoint seaward."
        )

    # Rename columns to match the shapefile-loader contract
    cells = cells.rename(columns=COLUMN_RENAME)
    # Re-cast ID_TEXT to string explicitly — pandas can demote dtype
    # across concat; this keeps the DBF column type consistent.
    cells["ID_TEXT"] = cells["ID_TEXT"].astype(str)
```

Add the missing import at the top of the file if not already present:
```python
import pandas as pd
```

- [ ] **Step 3: Smoke-test the regenerator on Mörrumsån (smallest fixture, fastest)**

Edit the `RIVERS` list temporarily or invoke the function directly:
```bash
micromamba run -n shiny python -c "
import sys
sys.path.insert(0, 'app')
from scripts._generate_wgbast_physical_domains import write_river_shapefile, RIVERS
mor = next(r for r in RIVERS if r.short_name == 'example_morrumsan')
write_river_shapefile(mor)
"
```

(If the import path doesn't work — `scripts` isn't a package — just run the full regenerator: `python scripts/_generate_wgbast_physical_domains.py`. Mörrumsån is the smallest, ~30 s.)

Expected log output:
- `Generated XXXX cells (fresh=489 + BalticCoast=NNN)`
- Per-reach distribution shows 5 reaches: BalticCoast, Lower, Middle, Mouth, Upper
- BalticCoast cell count between 100 and 3000

- [ ] **Step 4: Re-run the diagnostic probe**

```bash
micromamba run -n shiny python scripts/_probe_wgbast_river_extents.py
```

Expected: each river now lists 5 reaches. If any river's BalticCoast cell count is 0 or > 3000, the disk radius / cell factor needs adjusting.

- [ ] **Step 5: Commit**

```bash
git add scripts/_generate_wgbast_physical_domains.py tests/fixtures/_osm_cache/example_*_marineregions.json
git commit -m "feat(wgbast): generate BalticCoast cells via Marine Regions + disk clip

Each WGBAST fixture's shapefile now contains a BalticCoast reach with
hex cells covering a 10 km coastline-clipped disk at the river mouth.
Cells are coarser than freshwater (4× the river cell size).

Algorithm:
  1. Marine Regions WFS returns the IHO polygon for the bbox
     (Gulf of Bothnia for the 3 northern rivers; Baltic Sea for Morrumsan).
  2. Clip the polygon to a true-meters disk at the mouth (UTM, then back
     to WGS84). Both grids pinned to the same UTM zone for clean adjacency.
  3. generate_cells(..., type='sea') with the clipped polygon.
  4. Concat fresh + marine, renumber cell_ids with adaptive width
     (max(4, len(str(total_cells)))),
     run an adjacency sanity check.

Existing BalticCoast YAML entry + per-reach CSVs (already shipped in
each fixture from the original Lithuanian template) now have matching
shapefile cells. Junction integers (5, 6) unchanged."
```

## Section D — YAML cleanup + per-river BalticCoast tuning

### Task 2.D.1: Drop orphan reaches and tune BalticCoast in `_wire_wgbast_physical_configs.py`

**Files:**
- Modify: `scripts/_wire_wgbast_physical_configs.py`

- [ ] **Step 1: Add per-river BalticCoast parameter overrides**

Open `scripts/_wire_wgbast_physical_configs.py`. Near the top (after imports), add:

```python
# v0.46+ spec §Components.5b: per-river BalticCoast tuning.
# Bothnian Bay (3 northern rivers): historically lower seal density →
#   fish_pred_min=0.95 (~5%/day mortality). The Klaipėda BalticCoast value
#   of 0.65 (~35%/day) would eliminate all smolts in days.
# Hanöbukten (Mörrumsån): intermediate seal density → fish_pred_min=0.90.
BALTICCOAST_OVERRIDES = {
    "example_tornionjoki": {"fish_pred_min": 0.95},
    "example_simojoki":    {"fish_pred_min": 0.95},
    "example_byskealven":  {"fish_pred_min": 0.95},
    "example_morrumsan":   {"fish_pred_min": 0.90},
}

# Reaches inherited from the example_baltic Lithuanian template that
# don't apply to the WGBAST rivers; remove them from each WGBAST yaml.
ORPHAN_REACHES = ("Skirvyte", "Leite", "Gilija", "CuronianLagoon")
```

- [ ] **Step 2: Update `rewrite_config` to apply overrides + drop orphans**

Locate `rewrite_config` (around line 74). After it loads the existing YAML, add cleanup logic. Find the section that walks `cfg["reaches"]` and add the orphan-removal + override-application:

```python
def rewrite_config(cfg_path: Path, stem: str, pspc_total: int) -> None:
    """... existing docstring ..."""
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    # Drop orphan reaches (Lithuanian template leftovers). Surface any
    # non-zero pspc_smolts_per_year being dropped so the engineer can
    # update the CHANGELOG.
    short_name = cfg_path.stem
    for orphan in ORPHAN_REACHES:
        if orphan in cfg.get("reaches", {}):
            pspc = cfg["reaches"][orphan].get("pspc_smolts_per_year", 0) or 0
            if pspc:
                log.warning(
                    "[%s] dropping orphan reach %s with pspc_smolts_per_year=%d "
                    "— update CHANGELOG ### Breaking section",
                    short_name, orphan, pspc,
                )
            del cfg["reaches"][orphan]
            log.info("[%s] dropped orphan reach: %s", short_name, orphan)

    # Apply per-river BalticCoast overrides
    overrides = BALTICCOAST_OVERRIDES.get(short_name, {})
    if overrides and "BalticCoast" in cfg.get("reaches", {}):
        for k, v in overrides.items():
            cfg["reaches"]["BalticCoast"][k] = v
        log.info("[%s] BalticCoast overrides applied: %s", short_name, overrides)

    # Verify BalticCoast junction integers connect to Upper.downstream.
    # Pre-existing template-inherited reaches may have stale junctions
    # (e.g. Klaipėda topology). After orphan reaches are dropped, the
    # chain should be Mouth(1→2) → Lower(2→3) → Middle(3→4) →
    # Upper(4→5) → BalticCoast(5→6).
    #
    # Defensive: on the current 4 WGBAST configs this branch is a
    # no-op (BC.upstream=5 == Upper.downstream=5 already). Kept for
    # robustness against future config drift or template changes.
    upper = cfg["reaches"].get("Upper", {})
    bc = cfg["reaches"].get("BalticCoast", {})
    if upper and bc:
        upper_dn = upper.get("downstream_junction")
        bc_up = bc.get("upstream_junction")
        if upper_dn != bc_up:
            log.warning(
                "[%s] BalticCoast.upstream_junction=%s != Upper.downstream_junction=%s; "
                "fixing to match",
                short_name, bc_up, upper_dn,
            )
            cfg["reaches"]["BalticCoast"]["upstream_junction"] = upper_dn
            # downstream_junction stays as 6 (or whatever next-int is) —
            # BalticCoast is the terminal reach
            if cfg["reaches"]["BalticCoast"].get("downstream_junction") in (None, upper_dn):
                cfg["reaches"]["BalticCoast"]["downstream_junction"] = upper_dn + 1

    # ... rest of existing rewrite_config body unchanged ...
```

**Add at module top if not present** (verified absent today): both `import logging` AND `log = logging.getLogger(__name__)`. Without the import the logger creation will fail with `NameError: name 'logging' is not defined`.

- [ ] **Step 3: Run the wire script and capture pspc warnings**

```bash
micromamba run -n shiny python scripts/_wire_wgbast_physical_configs.py 2>&1 | tee /tmp/wire_log.txt
grep -i "pspc_smolts_per_year" /tmp/wire_log.txt
```

If any line appears in the grep, **update the CHANGELOG `### Breaking` enumeration in Task 2.F.1 BEFORE committing** to list every dropped non-zero pspc value (river, reach, integer count). Loop-2 review found `Skirvyte.pspc_smolts_per_year=13000` in `example_byskealven.yaml`; the other 3 yamls may have additional values surfaced only by this run.

If grep is empty, the only known value is `Skirvyte=13000` — leave the CHANGELOG as-is.

- [ ] **Step 4: Commit**

```bash
git add scripts/_wire_wgbast_physical_configs.py
git commit -m "feat(wgbast): drop orphan reaches + per-river BalticCoast tuning

Each WGBAST yaml inherited 4 reaches from the example_baltic template
(Skirvyte, Leite, Gilija, CuronianLagoon) that don't apply to the
WGBAST rivers — remove them.

BalticCoast fish_pred_min was 0.65 (Klaipėda seal regime, lethal for
Bothnian smolts). Per-river overrides:
  - Tornionjoki, Simojoki, Byskealven (Bothnian Bay): 0.95
  - Morrumsan (Hanöbukten):                            0.90"
```

### Task 2.D.2: Re-expand BalticCoast-Depths.csv and -Vels.csv to new cell counts

**Files:**
- Modify: `scripts/_wire_wgbast_physical_configs.py`

- [ ] **Step 1: Locate the existing CSV-expansion helper**

`_expand_per_cell_csv(src, dst, n_cells)` exists in `scripts/_wire_wgbast_physical_configs.py`. (Line number was 211 in master pre-PR-2; after Task 2.D.1 lands new module-level constants and a junction-fix-up block, the line shifts. Locate by name.) It reads a Depths/Vels CSV, preserves the header lines (lines starting with `;` plus the count + flow-values rows), and replicates the first data row N times.

**Module-level imports needed for the new helpers:** `_wire_wgbast_physical_configs.py` currently imports only `shutil`, `sys`, `pathlib.Path`, and `yaml` at module level (lines 22–28). `geopandas` is currently imported INSIDE `copy_reach_csvs` as a local. The new `_balticcoast_cell_count` helper needs `geopandas` at MODULE level — add `import geopandas as gpd` to the top-of-file imports BEFORE pasting the new helper. The local `import geopandas as gpd` inside `copy_reach_csvs` can stay or be removed (harmless duplicate).

- [ ] **Step 2: Ensure the helper is called for BalticCoast**

Find `copy_reach_csvs(short_name, stem)` at line 164. It currently copies CSVs for each river's reaches. Audit whether `BalticCoast` is in its loop. If not, extend the loop to include BalticCoast.

The `n_cells` parameter for BalticCoast must match the new shapefile cell count. Read it from the regenerated shapefile:

```python
def _balticcoast_cell_count(short_name: str) -> int:
    fix_dir = ROOT / "tests" / "fixtures" / short_name
    try:
        shp = next((fix_dir / "Shapefile").glob("*.shp"))
    except StopIteration:
        raise FileNotFoundError(
            f"No shapefile in {fix_dir / 'Shapefile'} — Section C "
            f"(BalticCoast cell generation) likely never ran for "
            f"{short_name}. Re-run scripts/_generate_wgbast_physical_domains.py "
            f"before retrying Section D."
        ) from None
    gdf = gpd.read_file(shp)
    reach_col = "REACH_NAME" if "REACH_NAME" in gdf.columns else "reach_name"
    return int((gdf[reach_col] == "BalticCoast").sum())
```

Add this as a helper near the top of the file. Then in `copy_reach_csvs` add an explicit BalticCoast branch:

```python
def copy_reach_csvs(short_name: str, stem: str) -> None:
    """... existing docstring ..."""
    # ... existing body ...

    # Re-expand BalticCoast Depths/Vels to match the new cell count.
    # Match the integration test's lower bound (100): below that, the
    # disk geometry is too small to be useful and Section E will fail
    # anyway with a less-actionable error. Raise here so the engineer
    # gets a clear pointer to fix Section C (radius / waypoint).
    n_bc = _balticcoast_cell_count(short_name)
    if n_bc < 100:
        raise RuntimeError(
            f"[{short_name}] BalticCoast has only {n_bc} cells; "
            f"expected ≥100 (matches test_balticcoast_cell_count_in_range). "
            f"Section C disk geometry is too small — increase "
            f"BALTICCOAST_RADIUS_M or move the mouth waypoint seaward, "
            f"then re-run Section C before retrying Section D."
        )
    fix_dir = ROOT / "tests" / "fixtures" / short_name
    # Verify the per-reach CSVs exist. Existing fixtures all ship them
    # (template-inherited from example_baltic), but a future river may
    # not — surface the missing-file case explicitly.
    required_csvs = ("Depths.csv", "Vels.csv", "TimeSeriesInputs.csv")
    missing = [s for s in required_csvs
               if not (fix_dir / f"BalticCoast-{s}").exists()]
    if missing:
        raise RuntimeError(
            f"[{short_name}] missing BalticCoast CSVs: {missing}. "
            f"Copy from configs/example_baltic.yaml's fixture template "
            f"or generate via _wire_wgbast_physical_configs.py's "
            f"`copy_reach_csvs` extended for BalticCoast."
        )
    for suffix in ("Depths.csv", "Vels.csv"):
        path = fix_dir / f"BalticCoast-{suffix}"
        _expand_per_cell_csv(path, path, n_bc)
        log.info("[%s] re-expanded BalticCoast-%s to %d rows",
                 short_name, suffix, n_bc)
    # BalticCoast-TimeSeriesInputs.csv is per-reach (not per-cell), so
    # its row count doesn't change with cell count. Verify presence
    # but don't modify.
```

- [ ] **Step 3: Run the wire script for all 4 rivers**

```bash
micromamba run -n shiny python scripts/_wire_wgbast_physical_configs.py
```

Expected log output: for each river, `dropped orphan reach: <name>` × 4 + `BalticCoast overrides applied: ...` + `re-expanded BalticCoast-Depths.csv to NNN rows` + `re-expanded BalticCoast-Vels.csv to NNN rows`.

- [ ] **Step 4: Verify per-fixture state**

```bash
micromamba run -n shiny python -c "
import yaml
from pathlib import Path
for r in ['tornionjoki', 'simojoki', 'byskealven', 'morrumsan']:
    cfg = yaml.safe_load(Path(f'configs/example_{r}.yaml').read_text(encoding='utf-8'))
    reaches = sorted(cfg['reaches'].keys())  # sorted for stable comparison
    bc = cfg['reaches'].get('BalticCoast', {})
    print(f'{r:12s} reaches={reaches} fish_pred_min={bc.get(\"fish_pred_min\")}')"
```

Expected (reaches printed in sorted order; YAML insertion order may differ but the SET must match):
```
tornionjoki  reaches=['BalticCoast', 'Lower', 'Middle', 'Mouth', 'Upper'] fish_pred_min=0.95
simojoki     reaches=['BalticCoast', 'Lower', 'Middle', 'Mouth', 'Upper'] fish_pred_min=0.95
byskealven   reaches=['BalticCoast', 'Lower', 'Middle', 'Mouth', 'Upper'] fish_pred_min=0.95
morrumsan    reaches=['BalticCoast', 'Lower', 'Middle', 'Mouth', 'Upper'] fish_pred_min=0.90
```

- [ ] **Step 5: Verify the simulation can still load each fixture**

```bash
micromamba run -n shiny python -m pytest tests/test_multi_river_baltic.py::test_fixture_loads_and_runs_3_days -v
```

Expected: 4 PASS (one per WGBAST fixture).

**WORKFLOW NOTE — DO NOT STAGE FIXTURE FILES BETWEEN GENERATOR AND WIRE-SCRIPT RUNS.**
The CSV files (`tests/fixtures/example_*/BalticCoast-*.csv`) are modified by BOTH:
- `_generate_wgbast_physical_domains.py` (writes the shapefile; CSV row counts mismatch)
- `_wire_wgbast_physical_configs.py` (re-expands the CSVs to match the new cell counts)
Both must complete before any `git add` of fixture files. If you stage between the two scripts, the committed CSVs will have the WRONG row count. The `Step 5` simulation-load test will then fail mid-way through the commit cycle.

Sequencing: regenerator → wire script → simulation-load test → `git add` → commit.

- [ ] **Step 6: Commit**

```bash
git add scripts/_wire_wgbast_physical_configs.py configs/example_*.yaml tests/fixtures/example_*/BalticCoast-*.csv tests/fixtures/example_*/Shapefile/
git commit -m "feat(wgbast): regenerate fixtures with BalticCoast cells + tuned configs

Per-river:
  - YAML now has exactly 5 reaches (Mouth, Lower, Middle, Upper, BalticCoast)
  - 4 orphan Lithuanian reaches removed (Skirvyte, Leite, Gilija, CuronianLagoon)
  - BalticCoast.fish_pred_min tuned per regional predator regime
  - BalticCoast-Depths.csv + -Vels.csv re-expanded to match new cell counts
  - Shapefile contains 5 distinct REACH_NAME values; BalticCoast cells
    spatially adjacent to Mouth cells (verified by adjacency sanity check
    at fixture-generation time).

All 4 fixtures load via test_fixture_loads_and_runs_3_days."
```

## Section E — Integration tests

### Task 2.E.1: Create `tests/test_wgbast_river_extents.py`

**Files:**
- Create: `tests/test_wgbast_river_extents.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_wgbast_river_extents.py`:

```python
"""Fixture-shape regression tests for the 4 WGBAST rivers.

Asserts post-regeneration invariants:
  - Each fixture has exactly 5 reaches: {Mouth, Lower, Middle, Upper, BalticCoast}
  - BalticCoast cell count is in [100, 5000]
  - BalticCoast cells are spatially adjacent to Mouth cells
  - YAML reaches: section has exactly 5 entries (no orphans)
  - Tornionjoki has more cells than Simojoki (PR-1 acceptance)
  - YAML BalticCoast.upstream_junction == Upper.downstream_junction (topology)
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

WGBAST = ["example_tornionjoki", "example_simojoki", "example_byskealven", "example_morrumsan"]
EXPECTED_REACHES = {"Mouth", "Lower", "Middle", "Upper", "BalticCoast"}


def _load(short_name: str) -> tuple[gpd.GeoDataFrame, dict, str]:
    fix = ROOT / "tests" / "fixtures" / short_name
    shp = next((fix / "Shapefile").glob("*.shp"))
    gdf = gpd.read_file(shp)
    cfg = yaml.safe_load((ROOT / "configs" / f"{short_name}.yaml").read_text(encoding="utf-8"))
    reach_col = "REACH_NAME" if "REACH_NAME" in gdf.columns else "reach_name"
    return gdf, cfg, reach_col


@pytest.mark.parametrize("short_name", WGBAST)
def test_reach_name_set(short_name: str):
    gdf, _cfg, reach_col = _load(short_name)
    assert set(gdf[reach_col].unique()) == EXPECTED_REACHES, (
        f"{short_name}: reach set wrong"
    )


@pytest.mark.parametrize("short_name", WGBAST)
def test_balticcoast_cell_count_in_range(short_name: str):
    gdf, _cfg, reach_col = _load(short_name)
    n_bc = int((gdf[reach_col] == "BalticCoast").sum())
    assert 100 <= n_bc <= 5000, (
        f"{short_name}: BalticCoast cell count {n_bc} outside [100, 5000]"
    )


@pytest.mark.parametrize("short_name", WGBAST)
def test_balticcoast_geometric_adjacency_to_mouth(short_name: str):
    gdf, _cfg, reach_col = _load(short_name)
    mouth = gdf[gdf[reach_col] == "Mouth"]
    bc = gdf[gdf[reach_col] == "BalticCoast"]
    assert not mouth.empty
    assert not bc.empty
    # Project to UTM for a true-meters adjacency check, matching the
    # generator's tolerance (5 m). A WGS84-degree buffer here would be
    # anisotropic at Bothnian Bay latitudes and could spuriously fail.
    import sys
    from pathlib import Path
    sys.path.insert(0, str(ROOT / "app"))
    from modules.create_model_utils import detect_utm_epsg
    mouth_centroid = mouth.geometry.union_all().centroid
    utm_epsg = detect_utm_epsg(mouth_centroid.x, mouth_centroid.y)
    mouth_utm = mouth.to_crs(epsg=utm_epsg)
    bc_utm = bc.to_crs(epsg=utm_epsg)
    bc_union_utm = bc_utm.geometry.union_all()
    hits = mouth_utm.geometry.buffer(5.0).intersects(bc_union_utm).sum()
    assert hits >= 1, (
        f"{short_name}: no Mouth↔BalticCoast geometric adjacency "
        f"(within 5 m UTM tolerance)"
    )


@pytest.mark.parametrize("short_name", WGBAST)
def test_yaml_no_orphan_reaches(short_name: str):
    _gdf, cfg, _reach_col = _load(short_name)
    yaml_reaches = set(cfg["reaches"].keys())
    assert yaml_reaches == EXPECTED_REACHES, (
        f"{short_name}: YAML reaches set {yaml_reaches} != expected {EXPECTED_REACHES}"
    )


@pytest.mark.parametrize("short_name", WGBAST)
def test_yaml_junction_topology(short_name: str):
    _gdf, cfg, _reach_col = _load(short_name)
    upper_dn = cfg["reaches"]["Upper"]["downstream_junction"]
    bc_up = cfg["reaches"]["BalticCoast"]["upstream_junction"]
    assert upper_dn == bc_up, (
        f"{short_name}: junction graph broken — Upper.downstream={upper_dn} "
        f"!= BalticCoast.upstream={bc_up}"
    )


def test_tornionjoki_larger_than_simojoki():
    """PR-1 acceptance: Tornionjoki regex extension restored its size."""
    torn, _, _ = _load("example_tornionjoki")
    simo, _, _ = _load("example_simojoki")
    assert len(torn) > len(simo), (
        f"Tornionjoki ({len(torn)} cells) should exceed Simojoki ({len(simo)})"
    )


def test_balticcoast_offset_from_mouth():
    """Sanity: BalticCoast centroid is at least 1 km away from Mouth
    centroid. The 0.01° threshold (~1 km) detects "BalticCoast disk
    centred ON the mouth" or "disk spuriously inland" — both bug
    modes that would slip past geometric-adjacency checks.

    NOTE: a strict "BalticCoast south of Mouth" assertion was tried in
    an earlier draft, but Byskeälven's mouth opens east-southeast into
    Byskefjärden — the marine disk centroid lies east of the mouth and
    can be at the same latitude or slightly north. Distance-only is
    the correct generic invariant."""
    for short_name in WGBAST:
        gdf, _cfg, reach_col = _load(short_name)
        mouth = gdf[gdf[reach_col] == "Mouth"]
        bc = gdf[gdf[reach_col] == "BalticCoast"]
        if mouth.empty or bc.empty:
            continue
        # union_all() per GeoPandas 1.0+ (unary_union accessor deprecated)
        mouth_centroid = mouth.geometry.union_all().centroid
        bc_centroid = bc.geometry.union_all().centroid
        dist_deg = mouth_centroid.distance(bc_centroid)
        assert dist_deg > 0.01, (
            f"{short_name}: BalticCoast centroid {dist_deg:.4f}° from Mouth "
            f"centroid (expected > 0.01° = ~1 km). Disk likely centred on "
            f"land or on the mouth itself."
        )
```

- [ ] **Step 2: Run the tests**

```bash
micromamba run -n shiny python -m pytest tests/test_wgbast_river_extents.py -v
```

Expected: all PASS (22 tests = 4 rivers × 5 parametrized cases + 2 standalone).

- [ ] **Step 3: Commit**

```bash
git add tests/test_wgbast_river_extents.py
git commit -m "test(wgbast): fixture-shape regression for 5-reach WGBAST fixtures

Asserts each fixture has {Mouth, Lower, Middle, Upper, BalticCoast},
BalticCoast cell count in [100, 5000], BalticCoast adjacent to Mouth
both geometrically and via junction integers, and Tornionjoki > Simojoki
in cell count (PR-1 acceptance)."
```

### Task 2.E.2: Run full test suite

- [ ] **Step 1: Run the full project test suite**

```bash
micromamba run -n shiny python -m pytest tests/ -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py -q
```

Runtime: ~25-30 minutes per CLAUDE.md memory.

Expected: v0.46.0 baseline + ~39 new tests:
- `test_create_model_marine.py`: 8 (3 from 2.A.1 + 3 from 2.A.2 + 2 from 2.A.5)
- `test_create_model_river.py`: 9 (3 from 2.A.3 + 3 partition from 2.A.4 + 1 MLS-merge + 1 MLS-disjoint + 1 Y-shape)
- `test_wgbast_river_extents.py`: 22 (4 rivers × 5 parametrized + 2 standalone)

Total ≈ `1126 passed, 52 skipped, 64 deselected, 2 xfailed`. Treat as expected the new ~39 passes. Any pre-existing test that now FAILS must be diagnosed before proceeding.

- [ ] **Step 2: If a previously-passing test fails, debug**

Common failure modes:
- A test loads a WGBAST fixture and asserts something specific about reach names → may need updating to expect 5 reaches instead of 4.
- A test loads `configs/example_*.yaml` and assumes the orphan reaches exist → update or skip.

If failures are unrelated to this PR, that's a separate bug; report it but don't block.

- [ ] **Step 3: No commit unless changes were needed in Step 2**

If you had to update other tests, commit with:
```bash
git add tests/<changed_files>
git commit -m "test: update assertions for 5-reach WGBAST fixtures"
```

## Section F — Release v0.47.0

### Task 2.F.1: Bump version + update CHANGELOG

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/salmopy/__init__.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump pyproject version**

In `pyproject.toml`, change:
```toml
version = "0.46.0"
```
to:
```toml
version = "0.47.0"
```

- [ ] **Step 2: Bump `__version__`**

In `src/salmopy/__init__.py`:
```python
__version__ = "0.46.0"
```
becomes:
```python
__version__ = "0.47.0"
```

- [ ] **Step 3: Prepend CHANGELOG entry**

At the top of `CHANGELOG.md` (after the header), prepend:

```markdown
## [0.47.0] — 2026-04-25

### Fixed — Tornionjoki extent (PR-1)

`scripts/_fetch_wgbast_osm_polylines.py` Tornionjoki name regex now
matches Muonionjoki tributary names. The Tornionjoki main stem only
spans ~150 km; the basin extends another ~150 km along Muonio. WGBAST
stock-assessment practice treats Muonio as part of the Tornionjoki
population.

- Pre: Tornionjoki 860 cells (4 OSM seed polygons → 71 connected).
- Post: Tornionjoki >2600 cells (now exceeds Simojoki's 2595).

### Added — BalticCoast cells in 4 WGBAST fixtures (PR-2)

Each WGBAST fixture (Tornionjoki, Simojoki, Byskeälven, Mörrumsån) now
has shapefile cells under the existing `BalticCoast` reach. The 10 km
coastline-clipped marine disk at each river mouth is built from
Marine Regions IHO sea polygons (`Gulf of Bothnia` for the 3 northern
rivers; `Baltic Sea` for Mörrumsån) clipped to a true-meters disk in UTM.
Smolts now have a marine transit zone before they leave the model into
the zone-based marine pipeline.

Per-river `BalticCoast.fish_pred_min` tuned to match regional predator
regime: 0.95 for Bothnian Bay (lower historical seal density), 0.90 for
Hanöbukten (Mörrumsån). The previous value of 0.65 (Klaipėda seal-dense
zone) would have eliminated all smolts in days.

### Refactored — 4 algorithms moved to `app/modules/`

To support the same UI/batch sharing pattern v0.46 introduced for
edit-model panel, four pure-Python helpers moved out of WGBAST scripts:

- `app/modules/create_model_marine.py`:
  - `query_named_sea_polygon(bbox)` — Marine Regions WFS query
    (extracted from `create_model_panel.py::_query_marine_regions`)
  - `clip_sea_polygon_to_disk(...)` — UTM-disk clip
- `app/modules/create_model_river.py`:
  - `filter_polygons_by_centerline_connectivity(...)` — STRtree BFS
    (extracted from `_generate_wgbast_physical_domains.py::_load_osm_polygons_filtered`)
  - `partition_polygons_along_channel(...)` — quartile by along-channel distance
    (extracted from `build_reach_segments_from_polygons`)

The Create Model UI's 🌊 Sea button is unchanged behaviourally; it just
now imports from the shared module. The WGBAST batch generator is
thinner — geometric algorithms live in `app/modules/`.

### Breaking — orphan Lithuanian template reaches removed from WGBAST yamls

Each WGBAST yaml inherited 4 stale reaches from the original
`example_baltic` template (`Skirvyte`, `Leite`, `Gilija`, `CuronianLagoon`)
that don't represent the WGBAST rivers. Removed; each WGBAST yaml now has
exactly 5 reaches.

**Downstream impact:** Any user code or analysis pinned to those reach
names in `example_tornionjoki.yaml` / `example_simojoki.yaml` /
`example_byskealven.yaml` / `example_morrumsan.yaml` will see KeyError.

These reaches had **no shapefile cells attached**, so the spatial
simulation was unaffected by their presence. However, **some do carry
non-zero `pspc_smolts_per_year` values** that contributed to stock
accounting:

- `example_byskealven.yaml`: `Skirvyte.pspc_smolts_per_year = 13000`
  (verified pre-removal; other 3 orphan reaches in this config have
  no `pspc_smolts_per_year` field)
- Other 3 WGBAST configs (`example_tornionjoki`, `example_simojoki`,
  `example_morrumsan`): the implementation step verifies whether any
  orphan reach carries `pspc_smolts_per_year` and lists it here before
  the release.

If a user-facing analysis depended on these `pspc_smolts_per_year`
values, the impact is a corresponding reduction in total smolts/year
modelled for that river. `example_baltic.yaml` retains the reaches —
they represent real Curonian Lagoon distributaries there.

### Required dependency

- **GeoPandas ≥ 1.0** (uses `.union_all()`; the `.unary_union`
  accessor is deprecated in 1.0 and removed in 2.0). The `shiny`
  conda env on developer machines and the laguna server must be
  updated before installing this release.

### Verified

- New tests under `tests/test_create_model_marine.py` (8),
  `tests/test_create_model_river.py` (9),
  `tests/test_wgbast_river_extents.py` (22) — 39 new cases total.
- Full suite: same xfail/skip baseline as v0.46.0.

### Internal changes

- `_wire_wgbast_physical_configs.rewrite_config` now verifies and
  fixes `BalticCoast.upstream_junction` to match
  `Upper.downstream_junction` after orphan-reach removal.
- `_wire_wgbast_physical_configs._balticcoast_cell_count` raises
  `RuntimeError` if BalticCoast cells are absent (previously returned
  0 silently and skipped CSV expansion).
- `BalticCoast-{Depths,Vels,TimeSeriesInputs}.csv` presence is now
  required and verified before CSV expansion; missing files raise
  `RuntimeError` with a pointer to the prototype to copy from.
```

- [ ] **Step 4: Run the full suite once more**

```bash
micromamba run -n shiny python -m pytest tests/ -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py -q
```

Expected: same baseline as v0.46.0.

- [ ] **Step 5: Commit + tag**

```bash
git add pyproject.toml src/salmopy/__init__.py CHANGELOG.md
git commit -m "release(v0.47.0): WGBAST extend + BalticCoast cells + helper refactor

PR-1 + PR-2 of the 2026-04-25 wgbast-extend-rivers spec. See CHANGELOG."
git tag -a v0.47.0 -m "v0.47.0: WGBAST rivers extended + BalticCoast cells"
```

DO NOT push or deploy in this plan. The user controls when to publish.

---

# Future work (out of scope for this plan)

These are deferred per the v4 spec's "Deferred follow-ups" section:

- **PR-3 — Wire Create Model UI buttons to the v4 helpers.** "Auto-extract main river system" + "Auto-split into N reaches" + "Find by name". Estimate 300–500 lines.
- **PR-4 — Fix `create_model_export.py::export_template_csvs` CSV format.** Empirical probe at `scripts/_probe_create_model_csv_format.py` confirms a fixture exported from the Create Model UI cannot be loaded by the simulation today (`ValueError: invalid literal for int() with base 10: 'flow'`). Independent of WGBAST work.

---

# Self-review

**Spec coverage:** Each spec section maps to one or more tasks:

| Spec section | Implementing task(s) |
|---|---|
| §Components.PR-1 (regex) | Task 1.1 |
| §Components.PR-2.1 (`create_model_marine.py`) | Task 2.A.1 + 2.A.2 |
| §Components.PR-2.1b (`create_model_river.py`) | Task 2.A.3 + 2.A.4 |
| §Components.PR-2.2 (panel refactor) | Task 2.A.5 |
| §Components.PR-2.3a (WFS cache) | Task 2.C.1 |
| §Components.PR-2.3b (BalticCoast generation) | Task 2.C.2 |
| §Components.PR-2.4 (adjacency check) | Task 2.C.2 (inline) |
| §Components.PR-2.5 (yaml cleanup + tuning) | Task 2.D.1 + 2.D.2 |
| §Components.PR-2.6 (UI continuity) | Task 2.A.5 + Section E (regression) |
| §Testing | Task 2.E.1 |

No gaps.

**Type consistency:** The four helper signatures used in tasks match exactly:
- `clip_sea_polygon_to_disk(sea_polygon, mouth_lon_lat, radius_m, utm_epsg)` — Tasks 2.A.1 + 2.C.2
- `query_named_sea_polygon(bbox_wgs84, timeout_s=60)` — Tasks 2.A.1 + 2.A.5 (re-export)
- `filter_polygons_by_centerline_connectivity(centerline, polygons, tolerance_deg, max_polys, label)` — Tasks 2.A.3 + 2.B.1
- `partition_polygons_along_channel(centerline, polygons, mouth_lon_lat, n_reaches)` — Tasks 2.A.4 + 2.B.1

Constant names consistent: `BALTICCOAST_RADIUS_M = 10_000.0`, `BALTICCOAST_CELL_FACTOR_DEFAULT = 4.0`, and `BALTICCOAST_CELL_FACTOR_OVERRIDE = {"example_morrumsan": 8.0}` in Task 2.C.1, used in 2.C.2 via `BALTICCOAST_CELL_FACTOR_OVERRIDE.get(river.short_name, BALTICCOAST_CELL_FACTOR_DEFAULT)`.

Reach name set `{Mouth, Lower, Middle, Upper, BalticCoast}` consistent across Section D + E.

**Placeholder scan:** Each `[ ]` step has a concrete action. No "TBD"/"TODO"/"similar to". Every code block is complete and self-contained. Commit messages follow the existing repo convention.

---

# Plan revision history — 12 review loops

TWELVE multi-tool review loops. Loops 1-3: 33 findings. Loops 4-6 (fresh-eyes mandate): 24 more (5 critical). Loop 7: 13 cleanup. Loop 8: 2 LOW. Loop 9: 1 IMP + 3 LOW. Loop 10: 3 IMP + 2 LOW. Loop 11 (narrow regression check): **0 findings**. Loop 12 (final broad sweep): 2 IMP — graceful-degradation guard + cache disambiguation.

## Loop 12 (v11 → v12) — broad sweep, 2 IMP

| Sev | # | Issue | Fix |
|---|---|---|---|
| IMP | 1 | Bare `from modules.create_model_marine import ...` in panel breaks the project's existing try/except graceful-degradation pattern (lines 25-49). If the import fails, the whole Shiny app crashes at startup. | Wrap in `try: ... except ImportError: query_named_sea_polygon = None`. Handler fast-fails with user-facing message when None. |
| IMP | 2 | `_load_or_fetch_marineregions` cache empty-payload masking — read path returns None on empty cache, hiding "cache corrupted" vs "WFS down". | Read path raises `RuntimeError` on empty cache; write path does NOT write empty payloads (defensive). |

**Critical-bug trajectory across 12 loops: 4, 3, 0, 3, 1, 1, 0, 0, 0, 0, 0, 0.** SIX consecutive zero-CRIT loops.

## Loop 11 (v11) — narrow regression check, ZERO findings

Verified loop-10 fixes are clean (no regressions, self-consistent, correctly interact with surroundings).

## Loop 10 (v10 → v11) — find any meaningful issue

## Loop 10 (v10 → v11) — find any meaningful issue

| Sev | # | Issue | Fix |
|---|---|---|---|
| IMP | 1 | Task 2.A.5 Step 4 commit dropped the new tests (orphaned from semantic commit) | `git add ... tests/test_create_model_marine.py` added to the commit |
| IMP | 2 | Task 2.A.5 Step 2 line range "727-763" includes the `async def` signature but instructions say "after the initial _fetch_msg.set" — internally inconsistent. Engineer could delete the def line. | Clarified to "KEEP signature + first 2 body lines; REPLACE body from `import asyncio` through `await _refresh_map()`" |
| IMP | 3 | `_balticcoast_cell_count` raised only at <=0, but integration test requires >=100. A 1-99 cell case passes Section D silently → fails Section E with no clue. | Tightened lower bound to <100 with actionable error message pointing at radius/waypoint |
| LOW | 4 | Test docstring claimed "Detects ImportError" but the test is a source-string check (no import) | Rephrased to "Detects via source-string substring matching" with concrete failure modes |
| LOW | 5 | "~25 tests" arithmetic was wrong (4×5+2=22) | Updated to "22 tests" |

**Critical-bug trajectory across 10 loops: 4, 3, 0, 3, 1, 1, 0, 0, 0, 0.** Four consecutive zero-CRIT loops.

## Loop 9 (v9 → v10) — verifying loop-8 convergence claim

## Loop 9 (v9 → v10) — verifying loop-8 convergence claim

Loop 9 was an explicit "prove or disprove convergence" mandate, given that prior reviewers had declared convergence prematurely twice (loops 3 and 8 originally). Result: convergence holds for runtime correctness, but one IMPORTANT test-design issue surfaced.

| Sev | # | Issue | Fix |
|---|---|---|---|
| IMP | 1 | `test_create_model_panel_imports_query_named_sea_polygon` imports `create_model_panel` in pytest. The panel module loads Shiny `@module.ui`/`@module.server` decorators and depends on `MapWidget`, deck.gl bindings — never imported in any other test. May fail at module load outside a Shiny session. | Switched to a source-string check (`(ROOT / "app/modules/create_model_panel.py").read_text()` + 4 substring assertions). Robust to any Shiny init issues. |
| LOW | 2 | `test_partition_into_4_equal_groups` docstring said "3,2,2,3 (or similar)"; actual is `[2, 3, 2, 3]` | Updated docstring with concrete slice math. |
| LOW | 3 | Section B Step 4 said "_orient_centerline_mouth_to_source has been duplicated (privately)" — actually moved, not duplicated | Corrected wording. |
| LOW | 4 | Junction fix-up branch (loop-6 IMP-4) is dead code on the current 4 WGBAST configs | Added comment noting it's defensive, not currently exercised. |

**Critical-bug trajectory across 9 loops: 4, 3, 0, 3, 1, 1, 0, 0, 0.** THREE consecutive zero-CRIT loops = convergence robustly confirmed.

## Loop 8 (v8 → v9) — first "converged" verdict

| Sev | # | Issue | Fix |
|---|---|---|---|
| LOW | 1 | Vacuous test assertion `assert result.buffer(1e-7).contains(result)` (always trivially true) | Removed |
| LOW | 2 | Contradictory grep verification text ("only one match" vs "EMPTY") | Rewrote as "Expected: no matches (empty grep output)" |

## Loop 7 (v7 → v8) — workflow consistency cleanup, no runtime bugs

Architect-only review (numerical/logic reviewers' surface area covered exhaustively in prior loops). No runtime bugs surfaced.

| Sev | # | Issue | Fix |
|---|---|---|---|
| HIGH | 1 | Duplicate "Step 2" in Task 2.A.5 (loop-4 fix inserted a new Step 2 in front of existing one) | Renumbered second occurrence to "Step 2b" |
| HIGH | 2 | Test count math inconsistent across DAG, plan, self-review (8 vs 9 vs ~36 vs ~39) | Swept all references to: 9 in test_create_model_river.py, 39 new total, 1126 expected pass count |
| HIGH | 3 | Stale commit message in Task 2.C.2 Step 5 — said `:04d` but code uses adaptive width | Updated commit message |
| HIGH | 4 | CHANGELOG missing loop-6 additions (junction fix-up, required-CSV check, GeoPandas 1.0 dependency) | Added "Required dependency" + "Internal changes" subsections |
| IMP | 5 | Stale absolute line citations after multiple fixes drift them | Switched to "locate by name" instructions |
| IMP | 6 | Section D dict-key order assertion was fragile (relied on YAML insertion order) | Use `sorted()` for stable comparison |
| LOW | 7 | Duplicate revision-history headers from prior edit conflicts | Deduped Loop 4 + Loop 5 headers |

## Loop 6 (v6 → v7) — fresh-eyes continued

| Sev | # | Issue | Fix |
|---|---|---|---|
| CRIT | 1 | **Y-shape MLS test missing** — disjoint-MLS test used 1-D colinear segments. Real Tornionjoki+Muonio Y-junction would silently mis-partition (Euclidean-distance sort interleaves branches). | Added `test_partition_handles_y_shaped_multilinestring` with explicit Y-geometry; updated test count to 9. |
| IMP | 2 | `[100, 3000]` cell count range mismatch in test docstring + commit message (test asserts 5000) | Swept all references to the widened bound. |
| IMP | 3 | `test_partition_orders_by_along_channel_distance` was vacuous (3 polys / 3 reaches → 1 each, stable sort). | Rewrote with 6 polys / 3 reaches; tests middle group too. |
| IMP | 4 | BalticCoast `upstream_junction` not verified to match `Upper.downstream_junction` after orphan-reach removal. | Added junction-graph fix-up logic in `rewrite_config`. |
| IMP | 5 | BalticCoast-TimeSeriesInputs.csv presence not verified (only Depths/Vels). | Added required-file verification + raise on missing. Wire script now raises if BalticCoast cells = 0 (instead of silently skipping). |
| IMP | 6 | `union_all()` requires GeoPandas ≥1.0; project's lower bound was 0.14. | Added explicit GeoPandas ≥1.0 requirement to Tech Stack + version-check command. |
| IMP | 7 | Task 2.A.5 deletion boundary unclear — could leave `requests.get(...)` if engineer mis-bounds the replacement. | Verification grep extended to also check for `requests.get` and `_query_marine_regions`. |
| IMP | 8 | `bc_polygon` could be `GeometryCollection` (disk-coastline tangent case) — guard didn't cover. | Added explicit branch: GeometryCollection → filter polygons; else → raise on unexpected type. |
| LOW | 9 | `_balticcoast_cell_count` returned 0 silently if cells absent | Now raises `RuntimeError` with re-run instruction. |

## Loop 5 (v5 → v6) — fresh-eyes continued

| Sev | # | Issue | Fix |
|---|---|---|---|
| CRIT | 1 | **Adjacency `buffer(1e-5)` anisotropic at 65°N** (~0.45m east-west, only ~1.1m north-south) — Tornio coast is N-S so E-W axis is the constraint. Test used `1e-7` (~1cm) — even worse. Both reviewers (architect + numerical) flagged independently. | Switched to UTM-projected buffer of 5 m in both generator and test. True meters, isotropic. |
| IMP | 2 | **Orphaned `import requests` and `MARINE_REGIONS_WFS` constant** in `create_model_panel.py` after Task 2.A.5 — strict-mode ruff F401 fails CI. | Task 2.A.5 Step 1 now explicitly removes both. |
| IMP | 3 | **`contains(mouth_pt)` boundary semantics** — river-mouth waypoints often lie ON IHO sea-area boundary, `contains()` returns False, raising spurious "no sea polygon" error. | Switched to `intersects(mouth_pt.buffer(1e-6))` (~10cm tolerance) for boundary cases. |
| IMP | 4 | **Test name dishonest** — `test_query_named_sea_polygon_handler_contract` doesn't test the handler, only the helper return type. | Renamed to `test_query_named_sea_polygon_returns_geodataframe_for_handler`; docstring states the test scope honestly. |
| IMP | 5 | **Step ordering between regenerator and wire-script** — staging fixture files between the two scripts commits short CSVs. | Added explicit "DO NOT STAGE BETWEEN GENERATOR AND WIRE-SCRIPT RUNS" workflow note to Section D. |
| LOW | 6 | `gdf.geometry.unary_union` deprecated in GeoPandas 1.0+ | Switched to `.union_all()` in the test file (loop-5 fix only; the generator already used `union_all()` after the buffer fix). |
| INFO | 7 | Plan's loop-4 INFO-8 claim that `geom.exterior` drops holes during cell generation is WRONG — verified `generate_cells` line 173 uses `combined_buffer.intersection(poly)` which preserves holes. The note should be removed/updated. | Revision history table corrected; the original loop-4 INFO-8 entry is annotated. |

## Loop 4 (v4 → v5) — fresh-eyes architect found bugs all 3 prior loops missed

The architect (Opus) was given an explicit "fresh eyes, look for what prior reviewers missed" mandate. This produced findings of much higher severity than loops 2-3.

| Sev | # | Issue | Fix |
|---|---|---|---|
| CRIT | 1 | **Task 2.A.5 type-contract bug**: `_query_marine_regions` returns `dict`; new helper returns `GeoDataFrame`. Caller does `geoj.get("features")` → AttributeError. Smoke test only checked identity, not behaviour. 🌊 Sea button silently broken. | Step 1 + new Step 2 rewrite the `_on_fetch_sea` handler to consume GeoDataFrame; new test exercises the handler contract end-to-end. |
| CRIT | 2 | **`pd.concat` may drop CRS**: `cells = pd.concat([fresh, marine])` returns a plain DataFrame on older geopandas; `cells.geometry.buffer(...)` then crashes. | Wrap explicitly: `gpd.GeoDataFrame(pd.concat([fresh, marine], ignore_index=True), geometry="geometry", crs="EPSG:4326")`. |
| CRIT | 3 | **`_balticcoast_cell_count` raises bare `StopIteration`** on missing shapefile (Section C failed mid-way) → opaque error. | `try/except StopIteration` → raise `FileNotFoundError` naming the river + instructing re-run. |
| IMP | 4 | **Test count baseline wrong**: plan said `1087 passed` but PR-2 adds ~36 new tests | Updated to `~1123 passed`. |
| IMP | 5 | **No task DAG for parallel/serial dispatch**: subagents could race on shared files | Added a "Task dependency DAG" block to PR-2 preamble. |
| IMP | 6 | **No rollback / partial-failure handling**: half-converted state across 4 fixtures | Added rollback strategy note to Task 2.C.2. |
| IMP | 7 | **`cells["ID_TEXT"].astype(str)` line dropped** from prescribed code | Restored. |
| INFO | 8 | ~~Polygon-with-holes (interior islands) silently dropped by `geom.exterior` in `generate_cells`~~ — **CORRECTED in loop 5**: `generate_cells` line 173 uses `combined_buffer.intersection(poly)` which DOES preserve holes; cells inside an island are dropped via empty intersection. The `geom.exterior` usage at line 137 is for endpoint collection only (used by `dist_escape`). The loop-4 finding was a misread; documented for transparency. | No-op; misread in loop 4. |

## Loop 3 (v3 → v4) — 4 polish items

| Sev | # | Issue | Fix |
|---|---|---|---|
| IMP | 1 | UTM cross-zone comment was misleading (claimed buffer absorbs zone drift) | Comment now states `generate_cells` reprojects to WGS84 internally; buffer absorbs cell-edge drift only |
| IMP | 2 | CHANGELOG `### Breaking` back-fill not enforced | Added explicit grep step in Task 2.D.1 with "update CHANGELOG before commit" instruction |
| IMP | 3 | Pre-flight visibility gap for subagents (preamble not visible per-task) | Added `ORCHESTRATOR PRECONDITION` note to Tasks 1.1 and 2.C.1 |
| INFO | 4 | Loop-3 architect verified other concerns NOT issues (binary churn ~2.8 MB, hydraulics loader is positional, integration test in Section D) | No fix needed; documented |

## Loop 2 (v2 → v3) — 10 fixes applied

| Sev | # | Issue | Fix |
|---|---|---|---|
| CRIT | 1 | Tornionjoki UTM zone boundary (mouth in 35, freshwater centroid in 34) | Pin UTM to `detect_utm_epsg(mouth_lon, mouth_lat)` instead of freshwater centroid |
| HIGH | 2 | PR-1 regenerated Tornionjoki with old code; Section B byte-equivalence claim was unprovable | PR-1 ships regex + cache only; PR-2 Section C does the single regenerate |
| HIGH | 3 | Task 2.C.2 "3-commit decomposition" was theatre | Replaced with honest single-commit + smoke-tests-mid-block |
| IMP | 4 | Byskeälven `bc.y < mouth.y` test would fail (bay opens E/SE) | Dropped strict directional check; kept distance check only |
| IMP | 5 | CHANGELOG falsely claimed orphan reaches had no spawn weight | Enumerated `Skirvyte.pspc_smolts_per_year=13000`; helper logs warning when dropping non-zero pspc |
| IMP | 6 | `_wire_wgbast_physical_configs.py` lacked module-level `geopandas` import | Plan now flags the missing import explicitly |
| IMP | 7 | Test count off-by-one (Task 2.A.4) | Fixed: 8 PASS (was incorrectly stated as 6, then 7) |
| IMP | 8 | Disjoint-MultiLineString fallback shipped untested | Added `test_partition_handles_disjoint_multilinestring` |
| IMP | 9 | Pre-flight Task 0 was curl-only (incompatible with subagent workflow) | Moved out of the task list into the plan preamble |
| IMP | 10 | `bc_polygon` could be MultiPolygon (islands/skerries) | Added MultiPolygon → list-of-polygons conditional handling |

## Loop 1 (v1 → v2) — 14 fixes applied

| Sev | # | Issue | Fix |
|---|---|---|---|
| CRIT | 1 | Task 2.A.5 relative import `from .create_model_marine` would crash Shiny panel | Switched to absolute `from modules.create_model_marine import ...`; added warning |
| CRIT | 2 | `MultiLineString.project()` returns 0 → Tornionjoki partition silently mis-ordered | `_orient_centerline_mouth_to_source` now does `linemerge` first, then coordinate-concat fallback for genuinely disjoint MLS; added unit test |
| CRIT | 3 | Mörrumsån 240m cells × open Hanöbukten disk would trip `[100, 3000]` upper bound | Per-river `BALTICCOAST_CELL_FACTOR_OVERRIDE` (Mörrumsån: 8.0); test bound widened to `[100, 5000]` |
| CRIT | 4 | Task 2.C.2 was one 90-line replacement with no bisection target | Decomposed into 3 commits (rename → BalticCoast block → checks) within the same task |
| IMP | 5 | Test #1 used UTM zone 32633 for lon=0.5° (correct: 32631) | Fixed |
| IMP | 6 | Cell-id width hardcoded `:04d`; overflows past 9999 | Adaptive width: `max(4, len(str(len(cells))))` |
| IMP | 7 | Empty Mouth reach → misleading "no adjacency" error | Explicit `if mouth_subset.empty: raise` guard before the adjacency check |
| IMP | 8 | `bc_lat < mouth_lat + 0.05` test trivially true | Tightened to `dist > 0.01°` AND `bc_lat < mouth_lat` |
| IMP | 9 | UI regression test pointed at "the existing tests" with no file | Added explicit `test_create_model_panel_reexport_intact` |
| IMP | 10 | Orphan removal silent breaking change | CHANGELOG entry promoted from `### Removed` to `### Breaking` with downstream-impact note |
| IMP | 11 | WFS dependency with no fallback | Added Task 0 pre-flight + explicit "commit cached payloads" instruction |
| INFO | 12 | No pre-flight Overpass check | Added Task 0 |
| INFO | 13 | `_wire_wgbast_physical_configs.py` missing `import logging` | Plan now says to add both `import logging` and the logger |
| INFO | 14 | `Point` imported only inside `write_river_shapefile` | Plan tells engineer to add at module top |
