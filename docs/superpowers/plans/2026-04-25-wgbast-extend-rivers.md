# WGBAST rivers — extend Tornionjoki + materialize BalticCoast cells (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Tornionjoki's full extent (add Muonionjoki tributary) and give all 4 WGBAST rivers (Tornionjoki, Simojoki, Byskealven, Morrumsan) shapefile cells under the existing `BalticCoast` reach so smolts have a marine transit zone, while moving 4 reusable algorithms from `scripts/_generate_wgbast_physical_domains.py` into `app/modules/create_model_*` so the Create Model UI can share them.

**Architecture:** Two independent PRs. PR-1 is a one-line OSM-regex change to `scripts/_fetch_wgbast_osm_polylines.py` plus a Tornionjoki fixture regeneration. PR-2 introduces 2 new pure-Python helper modules (`create_model_marine.py`, `create_model_river.py`), refactors the WGBAST batch generator to import from them, adds Marine Regions WFS-clipped BalticCoast cells via `sea_polygon.intersection(disk)`, tunes per-river BalticCoast YAML parameters for Bothnian Bay vs Hanöbukten predator regimes, drops 4 orphan Lithuanian template reaches, and regenerates all 4 fixtures.

**Tech Stack:** Python 3.11+, geopandas, shapely, pyproj, pandas, requests, pyyaml, pytest. Project conda env: `shiny` (per `CLAUDE.md`).

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

# Pre-flight (run before either PR)

## Task 0: Verify external services are reachable

PR-1 depends on Overpass; PR-2 depends on Marine Regions WFS. Both are external services. Failures from network timeouts mid-task waste a lot of time. Check up-front:

- [ ] **Step 1: Verify Overpass is reachable**

```bash
curl -sf -o /dev/null -w "%{http_code}" --max-time 10 https://overpass-api.de/api/status
```

Expected: `200`. If anything else, try the kumi or osm.ch endpoints (`scripts/_fetch_wgbast_osm_polylines.py:38-41` lists them) before aborting. If all three fail, defer PR-1 until later.

- [ ] **Step 2: Verify Marine Regions WFS is reachable**

```bash
curl -sf -o /dev/null -w "%{http_code}" --max-time 30 "https://geo.vliz.be/geoserver/MarineRegions/wfs?service=WFS&version=2.0.0&request=GetCapabilities"
```

Expected: `200`. If `503` or timeout, defer PR-2.

- [ ] **Step 3: No commit; this is a pre-flight gate.**

If both services are up, proceed to PR-1. Otherwise wait and retry.

---

# PR-1 — Tornionjoki regex extension

## Task 1.1: Extend Tornionjoki OSM regex to capture Muonionjoki

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

- [ ] **Step 4: Regenerate the Tornionjoki shapefile**

```bash
micromamba run -n shiny python scripts/_generate_wgbast_physical_domains.py
```

Runtime: ~2-3 min total for all 4 rivers (most spent on Tornionjoki and Simojoki). Expected output (Tornionjoki only):

```
INFO ... [Tornionjoki] connectivity filter: NNN/MMMM polygons in the centerline-connected component
...
Generated XXXX cells
Per-reach distribution:
  Lower    NN cells
  Middle   NN cells
  Mouth    NN cells
  Upper    NN cells
```

Cell count must exceed Simojoki's current 2595. If it doesn't, the Muonio names didn't pick up — check whether the bbox needs widening or the Overpass result actually matched the regex.

- [ ] **Step 5: Verify with the per-river extent probe**

```bash
micromamba run -n shiny python scripts/_probe_wgbast_river_extents.py
```

Expected: `example_tornionjoki` total cells > `example_simojoki` cells (which is currently 2595). Cell count for Lower / Middle / Mouth / Upper should all be non-zero.

- [ ] **Step 6: Verify the fixture still loads in the simulation**

```bash
micromamba run -n shiny python -m pytest tests/test_multi_river_baltic.py::test_fixture_loads_and_runs_3_days -v -k tornionjoki
```

Expected: PASS. (The 3-day run only verifies the fixture loads and ticks; smolt outmigration won't occur in 3 days.)

- [ ] **Step 7: Commit PR-1**

```bash
git add scripts/_fetch_wgbast_osm_polylines.py tests/fixtures/_osm_cache/example_tornionjoki.json tests/fixtures/_osm_cache/example_tornionjoki_polygons.json tests/fixtures/example_tornionjoki/Shapefile/
git commit -m "fix(wgbast): include Muonionjoki in Tornionjoki OSM regex

Was: ^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne)$
Now: + Muonionjoki|Muonio älv|Muonio

Tornionjoki main stem only spans ~150 km; the basin extends another
~150 km north along the Muonio tributary. WGBAST stock-assessment
practice treats Muonio as part of the Tornionjoki population.

Pre: Tornionjoki 860 cells (4 OSM seed polygons → 71 connected).
Post: Tornionjoki >2600 cells (target ratio: > Simojoki's 2595).

Regenerated tests/fixtures/example_tornionjoki/Shapefile/ and the OSM
caches under tests/fixtures/_osm_cache/example_tornionjoki*.json."
```

---

# PR-2 — BalticCoast cells + helper extraction

PR-2 has six sections (A–F). Sections A and B are pure refactors with no behaviour change; C–F add the new BalticCoast cells, the YAML cleanup, the tests, and the release.

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
    assert result.buffer(1e-7).contains(result)
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
    """10 polygons distributed along a centerline → 4 groups of 3,2,2,3
    (or similar; the last absorbs the remainder)."""
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
    polygons furthest from mouth."""
    from modules.create_model_river import partition_polygons_along_channel

    centerline = [LineString([(0, 0), (10, 0)])]
    near_mouth = Polygon([(0, -0.5), (1, -0.5), (1, 0.5), (0, 0.5)])
    middle = Polygon([(4, -0.5), (5, -0.5), (5, 0.5), (4, 0.5)])
    far = Polygon([(9, -0.5), (10, -0.5), (10, 0.5), (9, 0.5)])

    groups = partition_polygons_along_channel(
        centerline=centerline,
        polygons=[far, near_mouth, middle],   # input order shuffled
        mouth_lon_lat=(0.0, 0.0),
        n_reaches=3,
    )
    assert len(groups) == 3
    # First group should contain near_mouth
    assert near_mouth in groups[0]
    assert far in groups[2]
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
```

Add to the existing imports at the top of the file:
```python
from shapely.geometry import Point  # noqa: F401  (used inside _orient_centerline_mouth_to_source)
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_river.py -v
```

Expected: 6 PASS (3 from Task 2.A.3 + 3 new).

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

- [ ] **Step 1: Replace the private helper with an import**

Open `app/modules/create_model_panel.py`. The current lines 86–108 define `_query_marine_regions`:

```python
def _query_marine_regions(bbox_wgs84):
    """Query Marine Regions WFS for IHO sea area polygons in a bounding box.
    ...
```

Replace those lines (86–108) with:

```python
from modules.create_model_marine import query_named_sea_polygon as _query_marine_regions  # noqa: E402
```

**IMPORTANT**: this is an ABSOLUTE import (`from modules.create_model_marine`), NOT a relative import (`from .create_model_marine`). The Shiny app loads `create_model_panel.py` as a top-level module, not as part of a package — `__package__` is `None`, so a leading-dot import would raise `ImportError: attempted relative import with no known parent package` at startup. This matches the pattern of every other internal import in `create_model_panel.py` (verified at lines 26–65: `from modules.create_model_grid import ...`, `from modules.create_model_osm import ...`, etc.).

This preserves the existing call site `_query_marine_regions(bbox)` at line 733 (`_on_fetch_sea` handler) without further edits.

- [ ] **Step 2: Verify no other call sites of `_query_marine_regions` exist**

```bash
grep -rn "_query_marine_regions" app/ scripts/
```

Expected: only the import at line 86 and the call at line 733 (or thereabouts) in the same file. If anything else references it, update the import accordingly.

- [ ] **Step 3: Smoke-test the panel module imports cleanly**

There is no dedicated `tests/test_create_model_panel.py` covering `_query_marine_regions` (verified by grep). Add a minimal smoke test as part of this step. Append to `tests/test_create_model_marine.py`:

```python
def test_create_model_panel_reexport_intact():
    """Behaviour-preserving extraction: create_model_panel must still
    expose _query_marine_regions as before, now resolved via the
    shared module."""
    import sys
    sys.path.insert(0, str(ROOT / "app"))
    from modules import create_model_panel
    assert hasattr(create_model_panel, "_query_marine_regions")
    # Same callable as the new public name
    from modules.create_model_marine import query_named_sea_polygon
    assert create_model_panel._query_marine_regions is query_named_sea_polygon
```

Run:

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_marine.py::test_create_model_panel_reexport_intact -v
```

Expected: PASS. If it fails with `ImportError: attempted relative import with no known parent package`, the import in Step 1 used a leading `.` — fix to absolute.

Also run the broader Create Model test surface to catch any other regression:

```bash
micromamba run -n shiny python -m pytest tests/ -k create_model -v 2>&1 | tail -20
```

Expected: same pass/fail counts as before this task.

- [ ] **Step 4: Commit**

```bash
git add app/modules/create_model_panel.py
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

The helper has been duplicated (privately) inside `app/modules/create_model_river.py`. Find `_orient_centerline_mouth_to_source` in `_generate_wgbast_physical_domains.py` and delete the entire function (it's around 30 lines).

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
            return None
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
        return None
    # Cache as a list of GeoJSON features
    payload = json.loads(gdf.to_json())["features"]
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

**Note on commit granularity:** the prescribed replacement adds ~90 lines to `write_river_shapefile`. To keep bisection narrow if the smoke-test fails, decompose into THREE commits within this task:

- Commit A: Convert `cells = generate_cells(...)` → `fresh = generate_cells(...)` (pure rename, no behaviour change). Add `import pandas as pd` to module-level imports if absent. Run smoke test on Mörrumsån; expected: identical cell count.
- Commit B: Add the BalticCoast geometry block (UTM detect, WFS load via `_load_or_fetch_marineregions`, mouth containment, `clip_sea_polygon_to_disk`, second `generate_cells` call). Concat `fresh + marine` into `cells`. Run smoke test; expected: 5 reaches per fixture, BalticCoast non-empty.
- Commit C: Add the cell_id renumber + adjacency sanity check + the empty-Mouth guard. Run smoke test; expected: same 5 reaches, no RuntimeError.

The Steps below describe the FINAL state after all 3 commits. Engineer applies each commit incrementally, smoke-testing between them.

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
    # Pin both grids to the SAME UTM zone (freshwater centroid's zone)
    # so the adjacency check below sees no UTM↔WGS84 round-trip drift.
    # IMPORTANT: also add `from shapely.geometry import Point` and
    # `from modules.create_model_utils import detect_utm_epsg`,
    # `from modules.create_model_marine import clip_sea_polygon_to_disk`
    # at the MODULE TOP of the script (alongside the existing imports
    # near line 30-42). Importing inside the function works but is
    # fragile under future refactors.

    fresh_geoms = []
    for info in reach_segments.values():
        fresh_geoms.extend(info["segments"])
    fresh_centroid = unary_union(fresh_geoms).centroid
    utm_epsg = detect_utm_epsg(fresh_centroid.x, fresh_centroid.y)

    sea_gdf = _load_or_fetch_marineregions(river)
    if sea_gdf is None or sea_gdf.empty:
        raise RuntimeError(
            f"{river.river_name}: Marine Regions returned no sea polygon. "
            f"Re-run when WFS recovers (or run with --refresh-marineregions)."
        )
    mouth_pt = Point(river.waypoints[0])
    sea_gdf = sea_gdf[sea_gdf.geometry.contains(mouth_pt)]
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
    bc_segment = {"segments": [bc_polygon], "frac_spawn": 0.0, "type": "sea"}
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

    # Concat freshwater + marine, renumber cell_ids with width adapted
    # to the total count (so C00001 and C99999 sort lexically).
    cells = pd.concat([fresh, marine], ignore_index=True)
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
    marine_union = marine_subset.geometry.unary_union
    if marine_union is None or marine_union.is_empty:
        raise RuntimeError(
            f"{river.river_name}: BalticCoast geometry empty after concat."
        )
    # Use a 1m buffer (≈1e-5° at WGS84 latitudes) to absorb sub-meter
    # UTM↔WGS84 round-trip drift between the freshwater and marine grids.
    hits = mouth_subset.geometry.buffer(1e-5).intersects(marine_union).sum()
    if hits == 0:
        raise RuntimeError(
            f"{river.river_name}: BalticCoast not adjacent to Mouth — "
            f"disk geometry leaves a gap (radius {BALTICCOAST_RADIUS_M}m). "
            f"Increase radius or move mouth waypoint seaward."
        )

    # Rename columns to match the shapefile-loader contract
    cells = cells.rename(columns=COLUMN_RENAME)
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
  4. Concat fresh + marine, renumber cell_ids as f'C{i+1:04d}',
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

    # Drop orphan reaches (Lithuanian template leftovers)
    short_name = cfg_path.stem
    for orphan in ORPHAN_REACHES:
        if orphan in cfg.get("reaches", {}):
            del cfg["reaches"][orphan]
            log.info("[%s] dropped orphan reach: %s", short_name, orphan)

    # Apply per-river BalticCoast overrides
    overrides = BALTICCOAST_OVERRIDES.get(short_name, {})
    if overrides and "BalticCoast" in cfg.get("reaches", {}):
        for k, v in overrides.items():
            cfg["reaches"]["BalticCoast"][k] = v
        log.info("[%s] BalticCoast overrides applied: %s", short_name, overrides)

    # ... rest of existing rewrite_config body unchanged ...
```

**Add at module top if not present** (verified absent today): both `import logging` AND `log = logging.getLogger(__name__)`. Without the import the logger creation will fail with `NameError: name 'logging' is not defined`.

- [ ] **Step 3: Commit**

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

`_expand_per_cell_csv(src, dst, n_cells)` exists at line 211 of the file. It reads a Depths/Vels CSV, preserves the header lines (lines starting with `;` plus the count + flow-values rows), and replicates the first data row N times.

- [ ] **Step 2: Ensure the helper is called for BalticCoast**

Find `copy_reach_csvs(short_name, stem)` at line 164. It currently copies CSVs for each river's reaches. Audit whether `BalticCoast` is in its loop. If not, extend the loop to include BalticCoast.

The `n_cells` parameter for BalticCoast must match the new shapefile cell count. Read it from the regenerated shapefile:

```python
def _balticcoast_cell_count(short_name: str) -> int:
    fix_dir = ROOT / "tests" / "fixtures" / short_name
    shp = next((fix_dir / "Shapefile").glob("*.shp"))
    gdf = gpd.read_file(shp)
    reach_col = "REACH_NAME" if "REACH_NAME" in gdf.columns else "reach_name"
    return int((gdf[reach_col] == "BalticCoast").sum())
```

Add this as a helper near the top of the file. Then in `copy_reach_csvs` add an explicit BalticCoast branch:

```python
def copy_reach_csvs(short_name: str, stem: str) -> None:
    """... existing docstring ..."""
    # ... existing body ...

    # Re-expand BalticCoast Depths/Vels to match the new cell count
    n_bc = _balticcoast_cell_count(short_name)
    if n_bc > 0:
        fix_dir = ROOT / "tests" / "fixtures" / short_name
        for suffix in ("Depths.csv", "Vels.csv"):
            path = fix_dir / f"BalticCoast-{suffix}"
            if path.exists():
                _expand_per_cell_csv(path, path, n_bc)
                log.info("[%s] re-expanded BalticCoast-%s to %d rows",
                         short_name, suffix, n_bc)
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
    reaches = list(cfg['reaches'].keys())
    bc = cfg['reaches'].get('BalticCoast', {})
    print(f'{r:12s} reaches={reaches} fish_pred_min={bc.get(\"fish_pred_min\")}')"
```

Expected:
```
tornionjoki  reaches=['Mouth', 'Lower', 'Middle', 'Upper', 'BalticCoast'] fish_pred_min=0.95
simojoki     reaches=['Mouth', 'Lower', 'Middle', 'Upper', 'BalticCoast'] fish_pred_min=0.95
byskealven   reaches=['Mouth', 'Lower', 'Middle', 'Upper', 'BalticCoast'] fish_pred_min=0.95
morrumsan    reaches=['Mouth', 'Lower', 'Middle', 'Upper', 'BalticCoast'] fish_pred_min=0.90
```

- [ ] **Step 5: Verify the simulation can still load each fixture**

```bash
micromamba run -n shiny python -m pytest tests/test_multi_river_baltic.py::test_fixture_loads_and_runs_3_days -v
```

Expected: 4 PASS (one per WGBAST fixture).

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
  - BalticCoast cell count is in [100, 3000]
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
    bc_union = bc.geometry.unary_union
    hits = mouth.geometry.buffer(1e-7).intersects(bc_union).sum()
    assert hits >= 1, (
        f"{short_name}: no Mouth↔BalticCoast geometric adjacency"
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


def test_balticcoast_coastward_of_mouth():
    """Sanity: BalticCoast centroid is at least 1 km away from Mouth
    centroid (in any direction). For Bothnian Bay rivers the bay is
    south of the mouth; for Mörrumsån, also south. The 0.01° threshold
    (~1 km) detects "BalticCoast disk centred ON the mouth" or "disk
    spuriously inland" — both bug modes."""
    for short_name in WGBAST:
        gdf, _cfg, reach_col = _load(short_name)
        mouth = gdf[gdf[reach_col] == "Mouth"]
        bc = gdf[gdf[reach_col] == "BalticCoast"]
        if mouth.empty or bc.empty:
            continue
        mouth_centroid = mouth.geometry.unary_union.centroid
        bc_centroid = bc.geometry.unary_union.centroid
        dist_deg = mouth_centroid.distance(bc_centroid)
        assert dist_deg > 0.01, (
            f"{short_name}: BalticCoast centroid {dist_deg:.4f}° from Mouth "
            f"centroid (expected > 0.01° = ~1 km)"
        )
        # Bothnian Bay rivers + Mörrumsån all open SOUTH of the mouth
        assert bc_centroid.y < mouth_centroid.y, (
            f"{short_name}: BalticCoast centroid lat {bc_centroid.y:.4f} "
            f"is not south of Mouth lat {mouth_centroid.y:.4f}"
        )
```

- [ ] **Step 2: Run the tests**

```bash
micromamba run -n shiny python -m pytest tests/test_wgbast_river_extents.py -v
```

Expected: all PASS (~25 tests across 4 rivers × 5 parametrized cases + 2 standalone).

- [ ] **Step 3: Commit**

```bash
git add tests/test_wgbast_river_extents.py
git commit -m "test(wgbast): fixture-shape regression for 5-reach WGBAST fixtures

Asserts each fixture has {Mouth, Lower, Middle, Upper, BalticCoast},
BalticCoast cell count in [100, 3000], BalticCoast adjacent to Mouth
both geometrically and via junction integers, and Tornionjoki > Simojoki
in cell count (PR-1 acceptance)."
```

### Task 2.E.2: Run full test suite

- [ ] **Step 1: Run the full project test suite**

```bash
micromamba run -n shiny python -m pytest tests/ -m "not slow" --ignore=tests/_debug_alignment.py --ignore=tests/test_e2e_spatial.py -q
```

Runtime: ~25-30 minutes per CLAUDE.md memory.

Expected: same xfail/skip count as v0.46.0 baseline (`1087 passed, 52 skipped, 64 deselected, 2 xfailed`). Any new failures must be diagnosed before proceeding.

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
The reaches contributed nothing to the simulation (no shapefile cells,
no spawn weight). They were carried as dead config from the original
template-copy. `example_baltic.yaml` retains them since they represent
real Curonian Lagoon distributaries.

### Verified

- New tests under `tests/test_create_model_marine.py`,
  `tests/test_create_model_river.py`,
  `tests/test_wgbast_river_extents.py` (~25 cases).
- Full suite: same xfail/skip baseline as v0.46.0.
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

# Plan revision history (v1 → v2)

The original plan went through a multi-tool review (4 reviewers in parallel: codebase-fidelity, logic, numerical, skeptical-architect). 14 findings surfaced, all applied inline:

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
