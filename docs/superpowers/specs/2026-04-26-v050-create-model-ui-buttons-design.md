# v0.50.0 — Create Model UI buttons (Find by name + Auto-extract + Auto-split)

**Status:** Design — pending review
**Date:** 2026-04-26
**Origin:** PR-3 deferred from v0.47.0 follow-ups list (also flagged in v0.48.0/v0.49.0 release notes).

## Summary

Add three new buttons to the Create Model panel that wire the v0.47.0 helper modules
(`app/modules/create_model_marine.py`, `create_model_river.py`) into a discoverable UX:

1. **🔍 Find by name** — Nominatim place lookup → set Region dropdown + zoom map + auto-trigger fetch_rivers + fetch_water.
2. **✨ Auto-extract** — `filter_polygons_by_centerline_connectivity` on the loaded Rivers + Water layers; replaces the unfiltered Water polygons with the connected-component subset.
3. **⚡ Auto-split** — `partition_polygons_along_channel` partitions the extracted polygons into N reaches by along-channel distance from the river mouth.

These buttons collapse the manual workflow used in v0.45–v0.47 (find a place on
Google Maps → copy waypoint → hand-edit `RIVERS` table in `_generate_wgbast_physical_domains.py`
→ regenerate fixture) into 3 clicks inside the panel. v0.51.0 will exercise the buttons
end-to-end by adding the Danė river to `example_baltic`.

## Out of scope (deferred)

- Danė fixture itself (v0.51.0).
- Tornionjoki juvenile-growth calibration (v0.52.0).
- Reach renaming UI (already handled by Edit Model panel since v0.45.3).
- Per-reach `frac_spawn` / `BalticCoast` calibration — Auto-split produces reach
  geometry only.
- Playwright e2e tests — no precedent in this codebase; defer until v0.51.0
  when Danė is the natural full-pipeline fixture.
- Undo for destructive Auto-extract polygon replacement — Edit Model handles
  undo; Create Model is a one-shot wizard.

## Architecture

**One new toolbar row** added as a separate `<div class="cm-toolbar">` directly
below the existing one (NOT a wrapped continuation of the same div — the existing
`flex-wrap` would mix old and new controls):

```
Auto:  [text input: Place name        ] 🔍 Find  ·  ✨ Auto-extract  ·  ⚡ Auto-split  [N: 4 ⬍]
```

### Required panel module-level imports

Add to `create_model_panel.py` near the existing imports (after line 17):

```python
from shapely.geometry import Point          # used by _pick_mouth_from_sea
from shapely.ops import unary_union         # used by _pick_mouth_from_sea
```

`asyncio` and `math` are imported LOCALLY inside the `_on_find` handler body
to match the existing per-handler `import asyncio` pattern (panel:336, 600,
683, 708, 767, 1075, 1300).

And extend the existing helper-import try/except block (already has
`query_named_sea_polygon` from `create_model_marine`):

```python
try:
    from modules.create_model_river import (
        filter_polygons_by_centerline_connectivity,
        partition_polygons_along_channel,
        default_reach_names,
    )
except ImportError:  # pragma: no cover
    filter_polygons_by_centerline_connectivity = None
    partition_polygons_along_channel = None
    default_reach_names = None
```

The Auto-extract / Auto-split handlers must guard with
`if filter_polygons_by_centerline_connectivity is None: ui.notification_show(...); return`
on entry — same pattern as `query_named_sea_polygon`.

### UI controls (concrete declarations)

Inside `create_model_ui()`, after the existing toolbar div closes (line ~268)
and before the rest of the panel:

```python
ui.div(
    {"class": "cm-toolbar"},
    ui.tags.span("Auto:", class_="cm-label"),
    ui.input_text(
        "place_name", None,
        placeholder="Place name…",
        width="180px",
    ),
    ui.input_action_button("find_btn", "🔍 Find",
                           class_="btn btn-cm",
                           title="Look up a place via Nominatim and load Rivers + Water"),
    ui.tags.div(class_="cm-sep"),
    ui.input_action_button("auto_extract_btn", "✨ Auto-extract",
                           class_="btn btn-cm",
                           title="Filter water polygons to the centerline-connected component"),
    ui.tags.div(class_="cm-sep"),
    ui.input_action_button("auto_split_btn", "⚡ Auto-split",
                           class_="btn btn-cm",
                           title="Partition extracted polygons into N reaches by along-channel distance"),
    ui.tags.span("N:", class_="cm-label"),
    ui.div(
        ui.input_numeric("auto_split_n", None, value=4, min=2, max=8, step=1, width="70px"),
        style="display:inline-block; vertical-align:middle;",
    ),
),
```

Five new input ids: `place_name`, `find_btn`, `auto_extract_btn`,
`auto_split_btn`, `auto_split_n`. Numeric upper bound is 8 (length of the
existing `REACH_COLORS` palette at panel line 70).

**Three new reactive event handlers** in `app/modules/create_model_panel.py`
(one per button), all soft-fail with `ui.notification_show` toasts.

**Reactive vars reused** (verified against `create_model_panel.py:324-350`):
- `_rivers_gdf = reactive.value(None)` — Rivers OSM GDF (truthy via `is not None`).
- `_water_gdf = reactive.value(None)` — Water OSM GDF.
- `_sea_gdf = reactive.value(None)` — Sea polygon GDF.
- `_reaches_dict = reactive.value({})` — schema verified at panel line 898:
  `{name: {"segments": [Geometry, ...], "properties": [{}], "color": [r,g,b,a], "type": "river"|"water"|"sea"}}`.
  Auto-split writes this exact dict-of-dicts shape with `type="water"`.
- `_selection_mode = reactive.value("")` — currently `""/"river"/"lagoon"/"sea"`; add fourth value `"mouth_pick"` for click-mouth fallback.
- `_pending_fly_to = reactive.value(None)` — `(lon, lat, zoom)` tuple consumed by
  `_flush_pending_fly` at panel line 758. Find handler writes here.
- `REACH_COLORS = [[r,g,b,a], ...]` (panel line 70) — RGBA list-of-lists, 8 colors.
  Auto-split indexes this cyclically (`REACH_COLORS[i % len(REACH_COLORS)]`).
  **No new color constant.**

**Three new reactive vars** added (declared near the existing var block at
panel line ~351, after `_workflow_msg`):

- `_auto_extract_done = reactive.value(False)` — Auto-split's prereq flag.
  Reset rules:
  - Set `True` on successful Auto-extract.
  - Set `False` inside the lifted `_do_fetch_rivers()` and `_do_fetch_water()`
    helpers (NOT in the `@reactive.event` wrappers). Reason: Find calls the
    helpers directly to refetch fresh data; that fresh data invalidates the
    prior Auto-extract result, so the flag MUST reset whether the trigger
    was a button click or a Find call. The helpers are the single source of
    truth for "fresh data was loaded".
- `_mouth_lon_lat = reactive.value(None)` — `(lon, lat)` tuple set by the
  mouth-pick branch of `_on_map_click`. Read by Auto-split when `_sea_gdf() is None`.
- `_finding = reactive.value(False)` — debounce guard for 🔍 Find (Nominatim
  1 req/sec ToS).

**One new helper module** `app/modules/create_model_geocode.py` (~100 LOC):

```python
def lookup_place_bbox(
    name: str,
    timeout_s: int = 10,
) -> tuple[str | None, tuple[float, float, float, float]] | None:
    """Geocode `name` via Nominatim → return (geofabrik_country, bbox_wgs84).

    Returns:
      (geofabrik_name, (lon_w, lat_s, lon_e, lat_n)) — happy path, country has Geofabrik extract.
      (None, bbox) — country recognized but not in GEOFABRIK_COUNTRIES.
      None — empty input / 0 results / network error.
    """
    if not name or not name.strip():
        return None

    params = {
        "q": name.strip(),
        "format": "json",
        "limit": 1,
        "addressdetails": 1,  # required to get country_code
    }
    headers = {"User-Agent": _USER_AGENT}

    try:
        with requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params, headers=headers, timeout=timeout_s,
        ) as resp:
            resp.raise_for_status()
            if int(resp.headers.get("Content-Length", 0) or 0) > 5_000_000:
                return None
            results = resp.json()
    except Exception as exc:
        logging.warning(
            "Nominatim lookup failed (%s): %s",
            type(exc).__name__, exc,
        )
        return None

    if not results:
        return None

    item = results[0]
    # Nominatim's boundingbox: ["lat_s", "lat_n", "lon_w", "lon_e"] as STRINGS
    bb = item.get("boundingbox") or []
    if len(bb) != 4:
        return None
    try:
        lat_s, lat_n, lon_w, lon_e = (float(x) for x in bb)
    except (TypeError, ValueError):
        return None
    bbox_wgs84 = (lon_w, lat_s, lon_e, lat_n)  # west, south, east, north

    iso2 = (item.get("address", {}).get("country_code") or "").lower()
    geofabrik = _ISO_TO_GEOFABRIK.get(iso2)  # may be None
    return (geofabrik, bbox_wgs84)
```

Plus:
- `_ISO_TO_GEOFABRIK: dict[str, str]` — ISO 3166-1 alpha-2 to Geofabrik country
  name. Initial coverage: WGBAST + Baltic countries (`"lt": "lithuania"`,
  `"lv": "latvia"`, `"ee": "estonia"`, `"pl": "poland"`, `"de": "germany"`,
  `"se": "sweden"`, `"fi": "finland"`, `"no": "norway"`, `"dk": "denmark"`).
  ISO `"ru"` is intentionally NOT mapped — `GEOFABRIK_REGIONS` only has
  `"kaliningrad"` for Russia (see `create_model_osm.py:54`); Russian places
  outside Kaliningrad fall through to the `(None, bbox)` "no Geofabrik
  extract" path. The module's import-time `assert all(v in GEOFABRIK_COUNTRIES
  for v in _ISO_TO_GEOFABRIK.values())` guards against future bad additions.
- `_USER_AGENT: str` — module-level constant computed from
  `f"inSTREAM-py/{__version__} ({_CONTACT})"` where `__version__` is loaded
  with a fallback: `try: from salmopy import __version__; except ImportError: __version__ = "dev"`. `_CONTACT` reads from env var `INSTREAM_NOMINATIM_CONTACT`
  with fallback `"arturas.razinkovas-baziukas@ku.lt"` (per CLAUDE.md identity).

**One smart-naming helper** added to `app/modules/create_model_river.py`:

- `default_reach_names(n_reaches: int) -> list[str]` — Returns
  `["Mouth", "Lower", "Middle", "Upper"]` when `n_reaches == 4`, else
  `[f"Reach{i+1}" for i in range(n_reaches)]`.

## Components & data flow

### 🔍 Find by name

```python
@reactive.effect
@reactive.event(input.find_btn)
async def _on_find():
    import asyncio  # local imports match existing handlers (panel:336,600,683,...)
    import math

    # Debounce: ignore re-clicks while a previous Find is in flight (Nominatim 1 req/sec ToS).
    # Shiny's single-threaded asyncio event loop makes the check-then-set safe; rapid double
    # clicks queue rather than race.
    if _finding():
        return
    _finding.set(True)
    try:
        name = input.place_name() or ""
        if not name.strip():
            ui.notification_show("Type a place name first", type="warning")  # sync, no await
            return

        result = await asyncio.to_thread(lookup_place_bbox, name)
        if result is None:
            ui.notification_show(f"No place found for '{name}'", type="warning")
            return

        country_geofabrik, bbox = result
        lon_w, lat_s, lon_e, lat_n = bbox
        cx = (lon_w + lon_e) / 2.0
        cy = (lat_s + lat_n) / 2.0
        # Compute zoom from bbox span: smaller span → higher zoom
        span = max(lon_e - lon_w, lat_n - lat_s)
        zoom = int(max(5, min(13, 9 - math.log2(max(span, 0.05)))))

        if country_geofabrik is None:
            # Country not in Geofabrik — zoom map only, leave dropdown stale
            ui.notification_show(
                f"Place found at ({cy:.2f}, {cx:.2f}) but its country has no "
                "Geofabrik OSM extract; map zoomed but Rivers/Water not auto-fetched",
                type="warning",
            )
            _pending_fly_to.set((cx, cy, zoom))
            return

        # Happy path: update dropdown, fly to bbox center, run fetch
        ui.update_select("osm_country", selected=country_geofabrik)
        _pending_fly_to.set((cx, cy, zoom))
        # NOTE: `_on_region_change` will ALSO fly the map to the country center.
        # The two fly-to calls run in sequence (region change first, bbox-precise
        # 0.5 s later via _flush_pending_fly's existing sleep). Cosmetic double-fly
        # is acceptable — final position is the bbox center.

        ui.notification_show(
            f"Loaded {name} (lat {cy:.2f}, lon {cx:.2f}). Fetching rivers and water…",
            type="message",
        )
        # Existing _on_fetch_rivers ALREADY fetches water internally
        # (panel line 626: `_water_gdf.set(water_gdf)`). Find calls rivers ONLY
        # to avoid a redundant Overpass query.
        await _do_fetch_rivers()
    finally:
        _finding.set(False)
```

**Implementation note — handler refactor**: the existing
`@reactive.event(input.fetch_rivers)` handler body (panel lines 595–674)
lifts into a nested `async def _do_fetch_rivers()` defined INSIDE
`create_model_server` (so it captures `input`, `session`, and the reactive
vars via closure). The function takes no arguments. **`_do_fetch_rivers`
sets `_auto_extract_done.set(False)` as its first line** — fresh data
invalidates any prior Auto-extract result. The original `@reactive.event`
wrapper shrinks to:

```python
@reactive.effect
@reactive.event(input.fetch_rivers)
async def _on_fetch_rivers():
    await _do_fetch_rivers()
```

Same pattern for `input.fetch_water` → `_do_fetch_water()`. The reset lives
in the helpers (single source of truth — both manual button clicks AND Find
trigger fresh fetches that invalidate the flag).

### ✨ Auto-extract

```python
@reactive.effect
@reactive.event(input.auto_extract_btn)
async def _on_auto_extract():
    if _rivers_gdf() is None:
        ui.notification_show("Click 🌊 Rivers first to load the centerline", type="warning")
        return
    if _water_gdf() is None:
        ui.notification_show("Click 💧 Water first to load polygons", type="warning")
        return

    if filter_polygons_by_centerline_connectivity is None:
        ui.notification_show("create_model_river module not available", type="error")
        return

    rivers_gdf = _rivers_gdf()
    water_gdf  = _water_gdf()
    n_before   = len(water_gdf)

    # Filter rivers GDF to LineStrings only — _rivers_gdf may contain
    # both Polygons and LineStrings (OSM rivers can be tagged either way),
    # but the connectivity helper expects centerline geometries only.
    centerline_mask = rivers_gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
    centerline_geoms = list(rivers_gdf[centerline_mask].geometry)
    if not centerline_geoms:
        ui.notification_show(
            "Rivers layer has no LineString geometries — cannot extract main system",
            type="warning",
        )
        return

    kept = filter_polygons_by_centerline_connectivity(
        centerline_geoms,
        list(water_gdf.geometry),
        tolerance_deg=0.0005,
        max_polys=2000,
        label="auto-extract",
    )
    if not kept:
        ui.notification_show(
            "No connected polygons — try lowering Strahler threshold or "
            "checking that Rivers + Water cover the same area",
            type="warning",
        )
        return  # leave _auto_extract_done as-is (False)

    # Preserve original attribute columns (nameText etc.) by FILTERING the GDF,
    # not reconstructing it. `kept` returns the SAME shapely objects (verified
    # against create_model_river.py:113), so id-based membership is reliable.
    kept_ids = {id(g) for g in kept}
    mask = water_gdf.geometry.apply(lambda g: id(g) in kept_ids)
    filtered_gdf = water_gdf[mask].reset_index(drop=True)
    _water_gdf.set(filtered_gdf)
    _auto_extract_done.set(True)

    await _refresh_map()  # explicit redraw — no reactive watcher exists for _water_gdf
    ui.notification_show(
        f"Kept {len(kept)} of {n_before} polygons in the main river system.",
        type="message",
    )
```

### ⚡ Auto-split

```python
@reactive.effect
@reactive.event(input.auto_split_btn)
async def _on_auto_split():
    if partition_polygons_along_channel is None or default_reach_names is None:
        ui.notification_show("create_model_river module not available", type="error")
        return
    if not _auto_extract_done():
        ui.notification_show("Click ✨ Auto-extract first", type="warning")
        return

    n_reaches = int(input.auto_split_n() or 4)
    rivers_gdf = _rivers_gdf()
    water_gdf  = _water_gdf()

    # Same LineString filter as Auto-extract — partition needs centerline only
    centerline_mask = rivers_gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
    centerline_geoms = list(rivers_gdf[centerline_mask].geometry)
    polys_list = list(water_gdf.geometry)

    # Warn upfront if N exceeds polygon count (would produce interleaved-empty groups)
    if n_reaches > len(polys_list):
        ui.notification_show(
            f"N={n_reaches} exceeds polygon count ({len(polys_list)}); "
            f"some reaches will be empty. Consider lowering N.",
            type="warning",
        )

    # Determine mouth waypoint
    sea_gdf = _sea_gdf()
    if sea_gdf is not None and len(sea_gdf) > 0:
        mouth = _pick_mouth_from_sea(centerline_geoms, sea_gdf)
        if mouth is None:
            ui.notification_show(
                "River centerline doesn't reach any sea polygon — click on map to set mouth",
                type="warning",
            )
            _current_reach_name.set("")  # clear any stale auto-named reach
            _selection_mode.set("mouth_pick")
            _workflow_msg.set("Click on the map to set the river mouth, then ⚡ Auto-split again")
            return
    elif _mouth_lon_lat() is not None:
        mouth = _mouth_lon_lat()
    else:
        # First ⚡ click with no Sea fetched → arm click-mouth mode
        _current_reach_name.set("")  # clear any stale auto-named reach
        _selection_mode.set("mouth_pick")
        _workflow_msg.set("Click on the map to set the river mouth, then ⚡ Auto-split again")
        return

    groups = partition_polygons_along_channel(
        centerline_geoms,
        polys_list,
        mouth_lon_lat=mouth,
        n_reaches=n_reaches,
    )
    names = default_reach_names(n_reaches)

    # Build dict-of-dicts schema matching panel line 898 (used by _build_reach_layers)
    reaches = {}
    for i, polys in enumerate(groups):
        if not polys:
            continue
        reaches[names[i]] = {
            "segments": polys,
            "properties": [{} for _ in polys],
            "color": REACH_COLORS[i % len(REACH_COLORS)],
            "type": "water",  # polygons → water styling (fill + outline)
        }
    _reaches_dict.set(reaches)
    _cells_gdf.set(None)  # invalidate any prior cell-generation
    _mouth_lon_lat.set(None)  # consumed; reset for next round

    await _refresh_map()  # explicit redraw

    counts_str = ", ".join(f"{n} ({len(reaches[n]['segments'])})" for n in names if n in reaches)
    ui.notification_show(
        f"Split into {len(reaches)} reaches: {counts_str}.",
        type="message",
    )
```

**Reach color palette**: reuse the existing module-level constant
`REACH_COLORS` at `create_model_panel.py:70` (RGBA list-of-lists, 8 colors).
Indexed cyclically as `REACH_COLORS[i % len(REACH_COLORS)]`. **No new
constant.** This matches the format `_build_reach_layers` expects (panel
line 493) and the format used by the existing manual-click path
(panel line 900).

**Mouth-from-Sea-polygon algorithm** (`_pick_mouth_from_sea` — defined as a
**module-level** function at the top of `create_model_panel.py` after the
`REACH_COLORS` constant block, so it's importable by unit tests; the
function takes its inputs as explicit arguments rather than capturing
reactive state):

```python
def _pick_mouth_from_sea(
    centerline_geoms: list,
    sea_gdf: gpd.GeoDataFrame,
) -> tuple[float, float] | None:
    """Pick the centerline endpoint closest to any sea polygon.

    Args:
      centerline_geoms: list of LineString / MultiLineString from rivers GDF
        (already filtered to lines-only by the caller).
      sea_gdf: GeoDataFrame of one or more sea polygons.

    Returns:
      (lon, lat) in WGS84 of the closest endpoint, or None if all endpoints
      are >5 km from any sea polygon, or if `detect_utm_epsg` is unavailable.
    """
    if detect_utm_epsg is None:
        return None  # graceful degradation; caller falls back to click mode
    if not centerline_geoms or len(sea_gdf) == 0:
        return None

    centerline = unary_union(centerline_geoms)
    sea_union = unary_union(list(sea_gdf.geometry))

    # Collect endpoints from the centerline (LineString or MultiLineString)
    if centerline.geom_type == "LineString":
        endpoints = [Point(centerline.coords[0]), Point(centerline.coords[-1])]
    elif centerline.geom_type == "MultiLineString":
        endpoints = []
        for sub in centerline.geoms:
            endpoints.append(Point(sub.coords[0]))
            endpoints.append(Point(sub.coords[-1]))
    else:
        # GeometryCollection or other — defensive fallback
        return None

    # Reproject to UTM for true-meters distance
    centroid = centerline.centroid
    utm_epsg = detect_utm_epsg(centroid.x, centroid.y)  # signature: (lon, lat)
    ep_gdf = gpd.GeoDataFrame(
        geometry=endpoints, crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg).reset_index(drop=True)
    sea_utm = gpd.GeoDataFrame(
        geometry=[sea_union], crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg)
    distances = ep_gdf.geometry.distance(sea_utm.geometry.iloc[0])

    # argmin returns POSITION (not label); reset_index above keeps position == label,
    # but argmin is the safer primitive against future refactors.
    min_pos = int(distances.values.argmin())
    if distances.iloc[min_pos] > 5000:  # 5 km threshold
        return None
    closest = endpoints[min_pos]
    return (closest.x, closest.y)
```

`detect_utm_epsg` signature is `(center_lon: float, center_lat: float) -> int`
(verified at `app/modules/create_model_utils.py:9`). The call passes
`centroid.x` and `centroid.y` explicitly. Module-level `None` guard handles
the panel's import-failure fallback (panel line 46-48).

**Helper visibility**: the earlier proposal to promote
`_orient_centerline_mouth_to_source` to public is **rescinded** — it's used
only inside `create_model_river.py:151` and `_pick_mouth_from_sea` doesn't
need it (raw endpoints + UTM distance is simpler). Keep private. No rename.

**Click-mouth mode** (Auto-split fallback when `_sea_gdf() is None`):

The existing `_on_map_click` handler at `create_model_panel.py:880` early-returns
on `if not sel:` (line 881) and again on `if not reach_name:` (line 889). The
mouth_pick branch must be inserted **between** those two early-returns —
i.e., after `if not sel:` but **before** the `reach_name = _current_reach_name()`
guard, since mouth_pick has no associated reach name.

Concrete edit to `_on_map_click` (insert after line 883, before line 885):

```python
        # NEW: mouth_pick mode handled before reach_name check
        if sel == "mouth_pick":
            _mouth_lon_lat.set((lon, lat))
            _selection_mode.set("")  # consume the mode
            _workflow_msg.set(
                f"River mouth set to ({lon:.4f}, {lat:.4f}). Click ⚡ Auto-split to run."
            )
            return
```

**State machine — full transition table** (new mode `_selection_mode == "mouth_pick"`):

| User action while in mouth_pick mode | Outcome |
|---|---|
| Clicks on map | `_on_map_click` mouth_pick branch fires: sets `_mouth_lon_lat`, clears mode. |
| Clicks ⚡ Auto-split | If `_mouth_lon_lat()` is now set → split runs; else (still None) → toast "Click on the map first" and remain in mouth_pick mode. |
| Clicks ✨ Auto-extract | Auto-extract handler does NOT touch `_selection_mode`; runs normally. mouth_pick mode persists across the Auto-extract click. |
| Clicks 🔍 Find | Find handler does NOT touch `_selection_mode`; runs normally. mouth_pick persists; the user's pending mouth pick will be discarded if they click on a new map area unrelated to the river they previously had loaded. Toast warns: not added — out of scope for v0.50.0; documented as a known minor edge. |
| Clicks 🌊 Rivers / 💧 Water / 🌊 Sea (fetch) | Fetch handlers do NOT touch `_selection_mode`. mouth_pick persists. Existing handlers reset `_rivers_gdf`/`_water_gdf`/`_sea_gdf` — Auto-split's prereq check (`_auto_extract_done`) will fail anyway, forcing the user to re-run Auto-extract. mouth_pick stays armed silently. |
| Clicks 🏞️ River / 💧 Lagoon / 🌊 Sea (selection) | `_toggle_selection_mode("river"/"lagoon"/"sea")` reads `current = _selection_mode()`, finds `"mouth_pick"` (truthy), `current != mode` → enters the else branch: writes new mode + auto-names a reach. **mouth_pick is silently overwritten** with no warning toast. Acceptable: user explicitly chose another selection mode. |
| Clicks 🗑 Clear | `_on_clear_reaches` already resets `_selection_mode.set("")` (panel line 787); mouth_pick clears. **Required edit**: insert `_mouth_lon_lat.set(None)` immediately after the existing `_selection_mode.set("")` line at panel line 787 (within `_on_clear_reaches`). |
| Strahler slider change | `_on_strahler_change` (panel line 773-776) calls `_refresh_map()` only; does NOT touch `_selection_mode`. mouth_pick mode persists across Strahler changes. |
| Never clicks anywhere | Mode persists indefinitely. No timeout. The next ⚡ Auto-split click will see `_selection_mode == "mouth_pick"` and `_mouth_lon_lat() is None` → re-arms the mode and re-toasts. Idempotent; no error. |

Existing pickability flags at panel lines 464 and 480 (`pickable=(sel ==
"lagoon")` and `pickable=(sel == "sea")`) evaluate to `False` when
`sel == "mouth_pick"` — neither water nor sea polygons are individually
pickable in this mode. **This is acceptable** because mouth_pick captures
the raw `(lon, lat)` from the map's click bridge (panel line 875: `lon =
data.get("longitude")`), not from a specific feature's properties. The
click is captured at the map level via the JS bridge regardless of any
layer's `pickable` setting.

## Error handling

### Find by name

| Case | Behavior |
|------|----------|
| Empty input | Toast "Type a place name first" — no API call |
| Nominatim 0 results | Toast "No place found for '<name>'" |
| Country code unknown to Geofabrik | Toast "Country '<X>' has no Geofabrik OSM extract; map zoomed but Rivers/Water not auto-fetched". Map zoom still happens; Region dropdown unchanged. |
| Network/HTTP error | Toast "Geocoding failed (check connection)"; log exception class+message |
| Rate limit (1 req/sec ToS) | One-shot per click. No retry loop. User-Agent header set. |

### Auto-extract

| Case | Behavior |
|------|----------|
| `_rivers_gdf() is None` | Toast "Click 🌊 Rivers first to load the centerline" |
| `_water_gdf() is None` | Toast "Click 💧 Water first to load polygons" |
| BFS returns empty (centerline doesn't touch any polygon) | Toast "No connected polygons — try lowering Strahler threshold or checking that Rivers + Water cover the same area"; `_auto_extract_done` stays False |
| Single polygon (no-op) | Run anyway; toast "Kept 1 of 1 polygons"; `_auto_extract_done.set(True)` |

### Auto-split

| Case | Behavior |
|------|----------|
| `_auto_extract_done() is False` | Toast "Click ✨ Auto-extract first" |
| `_sea_gdf() is None and _mouth_lon_lat() is None` (no Sea, no prior click) | Set `_selection_mode.set("mouth_pick")`; status text "Click on the map to set the river mouth, then ⚡ again". Skip split this time. |
| N > polygon count | Pre-check at handler entry shows toast: `f"N={n_reaches} exceeds polygon count ({len(polys_list)}); some reaches will be empty. Consider lowering N."` Non-fatal — partition still runs and produces interleaved-empty groups; the toast text matches the handler code exactly. |
| N=1 | Single reach with all polygons; toast "Created 1 reach (try N≥2 for spatial split)" |
| Re-running Auto-split | Overwrites `_reaches_dict`; resets `_cells_gdf` (clears any stale cell generation); resets `_mouth_lon_lat` to None |
| `fetch_water` clicked after Auto-extract | The `@reactive.event(input.fetch_water)` handler explicitly calls `_auto_extract_done.set(False)` BEFORE running the fetch helper — Auto-split prereq fails until user re-runs Auto-extract. (Same pattern for `@reactive.event(input.fetch_rivers)` since the rivers fetch also overwrites `_water_gdf`.) |

## Testing

### New unit tests — `tests/test_create_model_geocode.py` (~120 LOC, 7 cases)

Reference Nominatim response shape used by mocks:
```python
NOMINATIM_KLAIPEDA = [{
    "place_id": 12345,
    "lat": "55.7128",
    "lon": "21.1351",
    "boundingbox": ["55.65", "55.78", "21.05", "21.25"],  # [lat_s, lat_n, lon_w, lon_e]
    "display_name": "Klaipėda, Lithuania",
    "address": {"country_code": "lt", "country": "Lithuania"},
}]
```

| Test | Mocks | Asserts |
|------|-------|---------|
| `test_lookup_place_bbox_klaipeda_success` | `requests.get` → mock with json() returning NOMINATIM_KLAIPEDA | returns `("lithuania", bbox)` where `bbox[0] ≈ 21.05` (lon_w, NOT lat) and `bbox[1] ≈ 55.65` (lat_s) — explicit order assertion |
| `test_lookup_place_bbox_empty_results` | `requests.get` → mock with json() returning `[]` | returns `None` |
| `test_lookup_place_bbox_unknown_country_code` | Same shape but `address.country_code = "zz"` | returns `(None, bbox)` — bbox still parsed correctly |
| `test_lookup_place_bbox_network_error` | `requests.get` raises `requests.ConnectionError` | returns `None`; assert log record at WARNING level matches "Nominatim lookup failed" |
| `test_lookup_place_bbox_empty_input` | (no patch needed) | `lookup_place_bbox("")` and `lookup_place_bbox("   ")` both return `None`; mocked `requests.get` is never called (assert via `mock.assert_not_called()`) |
| `test_lookup_place_bbox_special_chars` | input `"Mörrumsån"` → mock returns valid response | assert `mock.call_args.kwargs["params"]["q"] == "Mörrumsån"` (literal Python str — `requests` URL-encodes internally; we don't test the encoding, just that the param is passed through unchanged) |
| `test_lookup_place_bbox_addressdetails_param` | input `"Klaipėda"` → mock returns valid response | assert `mock.call_args.kwargs["params"]["addressdetails"] == 1` (required to populate `address.country_code`) |

### Smart-naming helper test — extend `tests/test_create_model_river.py` (+2 cases)

| Test | Asserts |
|------|---------|
| `test_default_reach_names_n4` | helper returns `["Mouth", "Lower", "Middle", "Upper"]` |
| `test_default_reach_names_other_n` | N=3 → `["Reach1", "Reach2", "Reach3"]`; N=8 → `["Reach1", …, "Reach8"]`; N=2 → `["Reach1", "Reach2"]` |

### `_pick_mouth_from_sea` test — new file `tests/test_pick_mouth_from_sea.py` (+4 cases)

`_pick_mouth_from_sea` is defined inside `create_model_server`; for
testability the spec promotes it to a module-level helper at the top of
`create_model_panel.py` (after `REACH_COLORS`). Tests import it directly.

| Test | Setup | Asserts |
|------|-------|---------|
| `test_pick_mouth_returns_endpoint_near_sea_offshore_gap` | Single LineString centerline (1.0,1.0)→(2.0,2.0); sea polygon offset so the (2.0,2.0) endpoint sits ~1 km OUTSIDE the polygon's nearest edge (e.g., polygon = 0.05° square centered on (2.015, 2.015) — endpoint→edge distance ~1 km in mid-latitude UTM, well within the 5 km threshold). This setup exercises the Simojoki-class regression where the v0.47.0 batch generator's centerline endpoint sat 945 m offshore from its IHO sea polygon (NOT inside the polygon). | returns `(2.0, 2.0)` — the offshore endpoint, distance > 0 but < 5 km |
| `test_pick_mouth_returns_none_if_far_from_sea` | LineString centerline well inland; sea polygon >>5 km away in UTM meters | returns `None` |
| `test_pick_mouth_handles_multilinestring` | MultiLineString with 2 sub-segments, one near sea | returns the sub-segment endpoint nearest the sea |
| `test_pick_mouth_handles_unavailable_detect_utm_epsg` | Patch `create_model_panel.detect_utm_epsg = None` (simulating import failure); call with valid centerline + sea inputs | returns `None` (graceful degradation; verifies the safety net for the panel's try/except detect_utm_epsg import at line 46-48) |

### Reused tests (no changes needed)

- `test_create_model_marine.py` (8 cases, v0.47.0)
- `test_create_model_river.py` (9 cases pre-existing, +2 from above)

### Manual verification checklist

Run before commit (and again post-deploy on laguna):

1. `shiny run app/app.py` → Create Model panel loads with new "Auto:" row visible (separate cm-toolbar div below the existing one).
2. Type "Klaipėda" → 🔍 Find → Region dropdown updates to "lithuania", map zooms (cosmetic double-fly: country first, then place ~0.5s later), Rivers + Water layers appear within 10s.
3. Click ✨ Auto-extract → toast shows polygon count drop (e.g., "Kept 26 of 92"); the Water layer on the map redraws to show only the connected-component subset.
4. Click ⚡ Auto-split with N=4 → toast confirms "Split into 4 reaches: Mouth (M), Lower (L), Middle (M2), Upper (U)"; the existing `data_summary` workflow status badge updates to show 4 reaches; the map shows 4 colored polygon overlays (one color per reach, drawn over the Water layer).
5. Click ⚡ Auto-split again with N=2 → re-split works; the prior 4-reach overlay is replaced by 2 reaches; toast confirms the new split.
6. Type a fake place ("xyzzyfoo") → 🔍 Find → toast "No place found for 'xyzzyfoo'"; panel state unchanged (no fetch, no zoom).
7. Mouth-pick fallback test: clear all sea polygons (don't click 🌊 Sea), click ⚡ Auto-split → toast "Click on the map to set the river mouth, then ⚡ Auto-split again"; click on the map → workflow status confirms "River mouth set to (X, Y)"; click ⚡ Auto-split again → split runs.

## Commit cadence

Per the v0.47–v0.49 pattern:

1. `feat(create_model_geocode): add lookup_place_bbox helper + tests` (new module `app/modules/create_model_geocode.py` + `tests/test_create_model_geocode.py` 7 cases)
2. `feat(create_model_river): add default_reach_names helper + extend test file` (1 new function in existing `app/modules/create_model_river.py` + 2 cases in `tests/test_create_model_river.py`). **Must come BEFORE commit 4** — the helper-import try/except in commit 4 references `default_reach_names`; without this commit, the panel falls back to None and silently disables Auto-split.
3. `feat(create_model_panel): add 🔍 Find by name button` (Find handler + `_do_fetch_rivers` / `_do_fetch_water` body lift + new reactive vars `_finding`)
4. `feat(create_model_panel): add ✨ Auto-extract + ⚡ Auto-split buttons + _pick_mouth_from_sea` (extract + split handlers + module-level `_pick_mouth_from_sea` + click-mode state machine + tests `tests/test_pick_mouth_from_sea.py` 4 cases + edits to `_on_map_click` and `_on_clear_reaches`)
5. `release(v0.50.0): Create Model UI buttons` (version bump + CHANGELOG + annotated tag)

## Required dependencies

No new dependencies. Uses already-present:
- `requests` (already used by `query_named_sea_polygon`)
- `shapely ≥ 2.0` (already used; `_orient_centerline_mouth_to_source` is shapely-based)
- `geopandas ≥ 1.0` (already used)

## Risks / open questions for plan-time review

1. **Fetch handler refactor**: lifting `_on_fetch_rivers` body (panel line 595)
   into `async def _do_fetch_rivers()` is a mechanical extraction. Both the
   helper and the original `@reactive.event` handler use closure for `input`,
   `session`, and reactive vars — no signature change. The original handler
   adds one line: `_auto_extract_done.set(False)` BEFORE calling
   `await _do_fetch_rivers()`. Same for water. Find handler calls helpers only.
2. **`_pick_mouth_from_sea` UTM reproject**: `detect_utm_epsg(point)` is
   imported at panel line 47. Plan to verify its signature (`detect_utm_epsg`
   may take a Point or coords pair). The 5km threshold is heuristic — ample
   margin for the WGBAST + Baltic + Danė workflows.
3. **Cosmetic double-fly in Find**: `ui.update_select("osm_country")` triggers
   `_on_region_change` (panel line 741), which flies the map to the country
   center via `_widget.fly_to`. Find ALSO sets `_pending_fly_to` for the
   bbox-precise location. The two run sequentially: country fly first,
   then bbox-precise fly ~0.5s later (via `_flush_pending_fly`'s sleep at
   panel line 768). Final position is correct (bbox center). Plan to
   accept this as expected UX, NOT a bug. If users complain, follow-up
   polish: pre-set `_last_region` to suppress `_on_region_change` fly.
4. **Reach overlay vs Water layer z-order**: existing `_refresh_map` (panel
   line 562 onward) appends layers in order: sea → water → rivers → cells →
   reaches (top). Auto-split's reach polygons render OVER the Water layer
   they were extracted from. Visual inspection in step 4 confirms this.
5. **Nominatim ToS — User-Agent identity**: header includes user's email
   per CLAUDE.md. Production deployers should override via
   `INSTREAM_NOMINATIM_CONTACT` env var. Plan to add this to the deploy skill
   doc as a follow-up note (out of v0.50.0 scope).
6. **`_finding` debounce flag scope**: protects only the Find button. Auto-extract
   and Auto-split don't make external API calls; mashing them is harmless
   (BFS / partition are CPU-bound, would queue rather than racing).
7. **mouth_pick mode persistence**: edge cases (Find clicked while in
   mouth_pick mode, never-clicks) leave the mode armed indefinitely.
   Acceptable: clears on next 🗑 Clear, or on any 🏞️/💧/🌊 selection
   button press, or on the next ⚡ click after a map click. Documented
   in the state machine table.
