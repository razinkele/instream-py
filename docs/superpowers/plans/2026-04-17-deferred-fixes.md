# Deferred Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 deferred issues from the deep code review: junction topology in export, color state bleed, hexagon geometry, and fly_to race condition.

**Architecture:** All fixes are isolated — each task touches one file with no cross-dependencies.

**Tech Stack:** Python, Shiny, shapely, geopandas

---

## Task 1: Fix `export_yaml` to respect pre-computed junction topology

**Files:**
- Modify: `app/modules/create_model_export.py:130-145`
- Test: `tests/test_create_model_osm.py` (append)

The YAML export currently overwrites junction IDs with sequential integers (`i`, `i+1`) regardless of actual river network topology. If `detect_junctions` has populated `upstream_junction`/`downstream_junction` in the reaches dict, those values should be used.

- [ ] **Step 1: Write failing test**

```python
# Append to tests/test_create_model_osm.py or create tests/test_create_model_export.py

def test_export_yaml_respects_junction_ids():
    """export_yaml should use pre-computed junction IDs when present."""
    from app.modules.create_model_export import export_yaml
    from io import StringIO
    import yaml

    reaches = {
        "reach_A": {
            "segments": [],
            "properties": [],
            "color": [255, 0, 0, 255],
            "type": "river",
            "upstream_junction": 10,
            "downstream_junction": 20,
        },
        "reach_B": {
            "segments": [],
            "properties": [],
            "color": [0, 255, 0, 255],
            "type": "river",
            "upstream_junction": 20,
            "downstream_junction": 30,
        },
    }

    yaml_str = export_yaml(reaches=reaches)
    config = yaml.safe_load(yaml_str)

    assert config["reaches"]["reach_A"]["upstream_junction"] == 10
    assert config["reaches"]["reach_A"]["downstream_junction"] == 20
    assert config["reaches"]["reach_B"]["upstream_junction"] == 20
    assert config["reaches"]["reach_B"]["downstream_junction"] == 30
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_export.py::test_export_yaml_respects_junction_ids -v
```

Expected: FAIL — currently overwrites with sequential IDs.

- [ ] **Step 3: Fix `export_yaml`**

In `app/modules/create_model_export.py`, replace lines 140-141:

```python
# Before (broken):
merged["upstream_junction"] = junction_counter + i
merged["downstream_junction"] = junction_counter + i + 1

# After (respects pre-computed):
merged["upstream_junction"] = user_params.get(
    "upstream_junction", junction_counter + i
)
merged["downstream_junction"] = user_params.get(
    "downstream_junction", junction_counter + i + 1
)
```

The `user_params` dict is `reaches[rname]` which may contain junction IDs from `detect_junctions`. The `.get()` with fallback preserves backward compatibility for reaches without pre-computed junctions.

- [ ] **Step 4: Run test — expect PASS**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_export.py::test_export_yaml_respects_junction_ids -v
```

- [ ] **Step 5: Commit**

```bash
git add app/modules/create_model_export.py tests/test_create_model_export.py
git commit -m "fix: export_yaml respects pre-computed junction topology"
```

---

## Task 2: Fix `_color_index` module-level global in `create_model_reaches.py`

**Files:**
- Modify: `app/modules/create_model_reaches.py:17-26`

The `_color_index` global persists across Shiny sessions in the same process, causing color assignments to drift. `_color_cycle` is dead code. The fix: remove the global, make `_next_color` take an explicit index.

- [ ] **Step 1: Remove dead `_color_cycle` and `_color_index` global**

Replace lines 17-26:

```python
# Before:
_color_cycle = itertools.cycle(_TAB10)
_color_index = 0

def _next_color() -> list[float]:
    global _color_index
    color = _TAB10[_color_index % len(_TAB10)]
    _color_index += 1
    return list(color)

# After:
def _next_color(index: int) -> list[float]:
    """Return Tab10 RGBA color for the given reach index."""
    return list(_TAB10[index % len(_TAB10)])
```

- [ ] **Step 2: Update callers of `_next_color`**

In `assign_segment_to_reach` (same file), find where `_next_color()` is called and pass the reach count:

```python
# Before:
color = _next_color()

# After:
color = _next_color(len(reaches))
```

- [ ] **Step 3: Remove `itertools` import if no longer used**

Check if `itertools` is used elsewhere in the file. If not, remove the import.

- [ ] **Step 4: Run existing tests**

```bash
micromamba run -n shiny python -m pytest tests/ -v -q 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add app/modules/create_model_reaches.py
git commit -m "fix: remove module-level color index global, prevent session bleed"
```

---

## Task 3: Fix hexagon geometry — angles produce pointy-top but spacing is flat-top

**Files:**
- Modify: `app/modules/create_model_grid.py:17-18`
- Test: add to existing test file

The `_hexagon` function uses `angles_deg = [0, 60, 120, 180, 240, 300]` which produces **pointy-top** hexagons (first vertex at 0° = rightward). But the grid spacing `dx = 1.5 * R`, `dy = sqrt(3) * R` with odd-column offset is correct for **flat-top** hexagons. The docstring says "flat-top". Fix: change angles to flat-top.

- [ ] **Step 1: Write failing test**

```python
def test_hexagon_is_flat_top():
    """Hexagon should have flat top (vertex at 30°, not 0°)."""
    from app.modules.create_model_grid import _hexagon

    h = _hexagon(0, 0, 10)
    coords = list(h.exterior.coords)[:-1]  # drop closing point
    # Flat-top: topmost vertex pair should be at same y
    ys = sorted([c[1] for c in coords], reverse=True)
    # Top two y-values should be equal (flat edge)
    assert abs(ys[0] - ys[1]) < 0.01, f"Not flat-top: top two y={ys[0]:.2f}, {ys[1]:.2f}"
```

- [ ] **Step 2: Run test — expect FAIL**

Current pointy-top angles produce a vertex at (R, 0) — the top two y-values differ.

- [ ] **Step 3: Fix the angles**

In `app/modules/create_model_grid.py` line 18:

```python
# Before (pointy-top):
angles_deg = [0, 60, 120, 180, 240, 300]

# After (flat-top):
angles_deg = [30, 90, 150, 210, 270, 330]
```

This makes the first vertex at 30° (upper-right of flat top) and the top edge horizontal.

- [ ] **Step 4: Run test — expect PASS**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_grid.py::test_hexagon_is_flat_top -v
```

- [ ] **Step 5: Commit**

```bash
git add app/modules/create_model_grid.py tests/test_create_model_grid.py
git commit -m "fix: hexagon angles now produce flat-top to match grid spacing"
```

---

## Task 4: Fix `fly_to` race condition on early region change

**Files:**
- Modify: `app/modules/create_model_panel.py` (server section, ~lines 358-790)

When the user changes the region dropdown within 1.5s of page load (before `_map_initialized` is `True`), `_on_region_change` returns early and the fly-to is silently lost. The fix: store the pending target and fly when the map becomes ready.

- [ ] **Step 1: Add pending fly-to state**

After `_last_region = reactive.value("")`, add:

```python
_pending_fly_to = reactive.value(None)  # (lon, lat, zoom) or None
```

- [ ] **Step 2: Modify `_on_region_change` to store pending target**

```python
@reactive.effect
@reactive.event(input.osm_country)
async def _on_region_change():
    country = input.osm_country()
    prev = _last_region()
    _last_region.set(country)
    if not prev:
        return  # skip initial fire
    view = REGION_VIEWS.get(country)
    if not view:
        return
    if not _map_initialized():
        _pending_fly_to.set(view)  # defer until map ready
        return
    lon, lat, zoom = view
    await _widget.fly_to(session, lon, lat, zoom=zoom)
```

- [ ] **Step 3: Add effect to flush pending fly-to after map init**

After `_init_map`, add:

```python
@reactive.effect
async def _flush_pending_fly():
    """Fly to pending region after map initialization."""
    if not _map_initialized():
        return
    pending = _pending_fly_to()
    if pending is None:
        return
    _pending_fly_to.set(None)
    lon, lat, zoom = pending
    import asyncio
    await asyncio.sleep(0.5)  # let deck.gl finish layer init
    await _widget.fly_to(session, lon, lat, zoom=zoom)
```

- [ ] **Step 4: Test manually**

1. Start app, immediately switch to kaliningrad before map loads
2. Verify map flies to kaliningrad after initialization completes

- [ ] **Step 5: Commit**

```bash
git add app/modules/create_model_panel.py
git commit -m "fix: defer fly_to for region changes before map init"
```

---

## What stays unchanged

- `create_model_osm.py` — no changes needed
- `create_model_utils.py` — no changes needed
- All existing tests — should continue to pass
