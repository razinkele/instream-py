# Inter-Reach Connectivity Check (v0.56+ candidate)

**Status**: planning, not implemented
**Author**: Claude Opus (with arturas.razinkovas-baziukas)
**Date**: 2026-04-30
**Triggered by**: v0.55.0 → v0.55.1 → v0.55.2 Minija arc surfacing geometric
issues that the existing per-reach `test_geographic_conformance` couldn't
catch. Specifically: a tributary could be generated with correct width
but at a location that doesn't physically connect to its receiving reach.

## Problem statement

The existing geographic-conformance check (`tests/test_geographic_conformance.py`,
introduced in v0.51.2 + extended in v0.51.4) validates **per-reach properties**:
- Effective width vs. river/lagoon/sea threshold
- Polygon-coverage ratio (when OSM polygon cache exists)
- Reach classification (river / lagoon / sea heuristic)

What it does **NOT** validate:
- Whether reach A's cells are geometrically near reach B's cells when the
  YAML config declares them as flow-connected (shared junction)
- Whether a tributary's downstream end actually reaches its receiving reach
- Whether marine reaches are downstream of all freshwater reaches
- Orphan reaches (cells with no geometric proximity to any other reach)

Today's Minija arc surfaced this: when v0.54.4 added Atmata as a connector,
it would have been valid (per per-reach checks) for Atmata cells to live
anywhere in the bbox — only common sense and the user's domain knowledge
caught that Minija → Atmata → Lagoon needed contact between the cells.

## Tension: junctions are LOGICAL, not PHYSICAL

The YAML `upstream_junction` / `downstream_junction` fields are **flow-graph
identifiers**, not physical positions. Examples:
- `example_baltic`: Atmata, Sysa, Skirvyte, Leite, Gilija all share
  downstream junction 5 (the Curonian Lagoon receiver). Geographically
  they're scattered around the Nemunas Delta — different physical points
  flowing into the same lagoon.
- `example_minija_basin`: All 4 tributaries share downstream junction 3
  (Minija upstream end). Real geography has them joining Minija at very
  different points along its 200 km length (Plungė, Salantai, Lankupiai…).
  The star-graph at junction 3 is a deliberate simplification.

Therefore: a strict "shared junction → cells must be geometrically adjacent"
rule would **break valid abstractions**. The check needs a softer formulation.

## Design intent

Three kinds of plausibility a check could enforce, listed by strictness:

1. **(loose) No-orphan check**: Every reach must have at least one cell
   within N meters of at least one other reach's cells in the same fixture.
   Catches: a tributary generated with bad coordinates landing far from the
   river system entirely. Doesn't enforce specific topology.
2. **(medium) Receiver-proximity check**: For each reach with a configured
   `downstream_junction`, find the OTHER reach(es) sharing that junction
   as their `upstream_junction` (or as another `downstream_junction` for
   sinks like the lagoon). Assert that AT LEAST ONE of those receivers
   has cells within N meters of THIS reach's cells. Allows star-graph
   abstractions (any tributary ending at junction 3 just needs proximity
   to Minija somewhere; doesn't have to be at the right confluence point).
3. **(strict) Confluence-position check**: Per-reach `confluence_lon_lat`
   declared in YAML; assert receiving reach has cells within N meters of
   that point. Most accurate but requires populating a new YAML field for
   every existing fixture.

## Recommended scope

Implement option **(2) Receiver-proximity**. It's a real plausibility gate
without forcing strict geometry. Existing fixtures should already pass:
- `example_baltic`: every freshwater reach has cells near at least one
  other reach (the delta system is geometrically contiguous).
- `example_minija_basin`: tributaries are within ~100 m of Minija cells
  at their real confluence points; star-graph abstraction is preserved.
- WGBAST fixtures: 4-reach river chains are physically continuous.

Edge case to design around: **disconnected freshwater islands**.
`example_minija_basin` has Minija + 4 tributaries in a contiguous mesh;
Atmata is geographically separate (the Nemunas Delta) but logically
downstream. The check needs to handle this: Atmata is NOT directly near
any Minija basin cells, but it IS the configured downstream of Minija
via junction 4 → 5. The check should follow the YAML topology, not raw
geometry.

## Implementation plan

### Step 1 — Add helper to `app/modules/geographic_conformance.py`

```python
def find_connected_reaches(
    config: SalmopyConfig,
    target_reach: str,
) -> set[str]:
    """Return reach names that share a junction with `target_reach` per
    YAML config. Includes both upstream and downstream connections."""
```

### Step 2 — Add new plausibility issue type

In `check_reach_plausibility`, after existing width/polygon checks:

```python
# v0.56: connectivity check — tributary cells should be near at least
# one of the reaches the YAML config flags as a flow neighbor.
connected_reaches = find_connected_reaches(config, reach_name)
if connected_reaches and reach_class == "river":
    target_cells = ...  # cells in `reach_name`
    neighbor_cells = ...  # cells in `connected_reaches`
    nearest_distance_m = compute_min_distance(target_cells, neighbor_cells)
    if nearest_distance_m > CONNECTIVITY_THRESHOLD_M:
        issues.append(Issue(
            severity="error",
            code="REACH_DISCONNECTED",
            message=(
                f"Nearest configured-neighbor reach is {nearest_distance_m:.0f} m "
                f"away (threshold {CONNECTIVITY_THRESHOLD_M:.0f} m). "
                f"Cells likely generated at wrong location relative to "
                f"the {connected_reaches} system."
            ),
        ))
```

`CONNECTIVITY_THRESHOLD_M`: start at **500 m** (allows for sparse cell
coverage near confluence points but catches cells in entirely wrong
geographies).

### Step 3 — Threshold tuning

Run the check against all existing fixtures. Expected outcomes:
- `example_a`, `example_b`: single-river fixtures, 1 reach → check skipped
  (no connected reaches to test against).
- `example_baltic`: 14 reaches, all geometrically contiguous in delta — pass.
- `example_minija_basin`: tributaries at <100m from Minija cells — pass.
- WGBAST 4-reach rivers: chain is contiguous — pass.

If anything fails, raise `CONNECTIVITY_THRESHOLD_M` to the smallest value
that lets all current fixtures pass. Document the value as the "geometric
sloppiness budget" any future fixture must stay within.

### Step 4 — Test parametrization

Extend `tests/test_geographic_conformance.py::test_reach_geographic_plausibility`
to load the YAML config (currently it only loads the shapefile). The
existing parametrization stays the same; the check just gains an additional
input.

### Step 5 — Documentation

Add a "Connectivity Plausibility" section to `app/modules/geographic_conformance.py`
docstring explaining the receiver-proximity rule and the threshold rationale.

## Risks and mitigations

| Risk | Mitigation |
|--|--|
| Cell-distance computation is O(N×M); large fixtures could be slow | Use `gpd.sjoin_nearest` with k=1; tested as fast for ~10k cells. |
| Sea/lagoon reaches sit far from river mouth cells | Restrict the new check to `river`-classified reaches only (`reach_class == "river"`). Lagoon and sea checks stay as today (width thresholds). |
| `example_baltic` Atmata is downstream of Minija via junction 4 → 5; cells aren't adjacent because Atmata is a Nemunas-delta branch | The receiver-proximity rule allows ANY of the configured neighbors to satisfy proximity. Atmata cells ARE near Nemunas/Sysa/Lagoon cells — passes. |
| Small fixtures with isolated reaches by design | Add an opt-out marker in the YAML (`disable_connectivity_check: true`) for cases where the abstraction intentionally separates reaches. |

## Acceptance criteria

1. All existing fixtures (`example_a`, `example_b`, `example_baltic`,
   `example_byskealven`, `example_morrumsan`, `example_simojoki`,
   `example_tornionjoki`, `example_minija_basin`) pass the new check.
2. A test fixture with a deliberately misplaced tributary (cells far from
   Minija) is added to verify the check fails as expected.
3. The check runs in under ~30 seconds across all fixtures (fits the
   existing CI budget for the conformance test).
4. Documentation note in `app/modules/geographic_conformance.py` and
   the planning doc references this plan file.

## Out of scope (separate v0.57+ work)

- Confluence-position check (option 3 above). Requires populating a new
  YAML field across all fixtures.
- Junction-graph topology validation (e.g. detect cycles, verify single
  marine sink). The current model assumes well-formed graphs.
- Cell-level overlap detection (e.g. tributary cells overlapping Minija
  cells should be deduplicated). Different problem.

## Estimated effort

- Helper + check logic: ~150 LOC, ~2 hours.
- Test fixture for the failure case: ~1 hour.
- Threshold tuning across 8 existing fixtures: ~1 hour.
- Total: **~4-5 hours of focused work**.
