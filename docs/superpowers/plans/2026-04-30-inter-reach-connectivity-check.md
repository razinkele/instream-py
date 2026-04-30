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
- Effective width vs. river threshold (`max_river_effective_width_m`)
  + minimum cell counts for marine reaches (`min_marine_cells`)
- Polygon-coverage ratio (when OSM polygon cache exists)
- Reach classification (`ReachClass = Literal["river", "marine"]` —
  lagoon and sea both fall under "marine" via `_MARINE_KEYWORDS`)

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

The YAML `upstream_junction` / `downstream_junction` fields (per-reach in
`ReachConfig`) are **flow-graph identifiers**, not physical positions.
Examples:
- `example_baltic`: Atmata, Sysa, Skirvyte, Leite, Gilija all share
  downstream junction 5 (the Curonian Lagoon receiver). Geographically
  they're scattered around the Nemunas Delta — different physical points
  flowing into the same lagoon.
- `example_minija_basin`: All 4 tributaries share downstream junction 3
  (Minija upstream end). Real geography has them joining Minija at very
  different points along its 200 km length (Plungė, Salantai, Lankupiai…).
  The star-graph at junction 3 is a deliberate simplification.
- `example_minija_basin` Atmata (junction 4 → 5) represents the
  Nemunas-Delta route to the lagoon. Its cells are extracted from
  example_baltic (geographically in the Klaipėda strait area). Minija's
  cells are in NW Lithuania (Plungė–Klaipėda corridor). **Direct
  Minija → Atmata cell adjacency would fail by ~50 km** even though
  the YAML legitimately wires them as flow-connected.

Therefore: a strict "shared junction → cells must be geometrically adjacent"
rule would **break valid abstractions**. The check needs a softer formulation
that walks the junction graph transitively (k hops) instead of demanding
direct contact.

## Design intent

Three kinds of plausibility a check could enforce, listed by strictness:

1. **(loose) No-orphan check**: Every reach must have at least one cell
   within N meters of at least one other reach's cells in the same fixture.
   Catches: a tributary generated with bad coordinates landing far from the
   river system entirely. Doesn't enforce specific topology.
2. **(medium) k-hop neighbor-proximity check**: Build the junction graph
   from `ReachConfig.{upstream_junction, downstream_junction}`. For each
   reach R, compute the set N_k(R) of reaches reachable within k hops
   (k=2 is the recommended default — direct flow neighbor + one transitive
   step). Assert AT LEAST ONE reach in N_k(R) has cells within
   `DEFAULT_CONNECTIVITY_THRESHOLD_M` of R's cells. Allows star-graph abstractions
   AND cross-basin abstractions (Minija → Atmata fails on direct contact
   because Atmata is geographically in the Nemunas Delta, but Minija's
   2-hop neighbors include the Curonian Lagoon, which IS adjacent).
3. **(strict) Confluence-position check**: Per-reach `confluence_lon_lat`
   declared in YAML; assert receiving reach has cells within N meters of
   that point. Most accurate but requires populating a new YAML field for
   every existing fixture.

## Recommended scope

Implement option **(2) k-hop neighbor-proximity** with k=2. It's a real
plausibility gate without forcing strict geometry. Existing fixtures
should already pass:
- `example_baltic`: every freshwater reach has cells near at least one
  other reach in the delta system (1-hop sufficient).
- `example_minija_basin`: tributaries are within ~100 m of Minija cells
  at their real confluence points (1-hop). Minija → Atmata fails 1-hop
  proximity but passes 2-hop via Atmata → Lagoon → adjacency back to
  Minija basin via the lagoon's spatial extent.
- WGBAST fixtures: 4-reach river chains are physically continuous (1-hop).

The k=2 threshold handles the Atmata cross-basin abstraction without
loosening to a fixture-wide bag-of-cells check.

## Implementation plan

### Step 1 — Add helpers to `app/modules/geographic_conformance.py`

```python
DEFAULT_CONNECTIVITY_THRESHOLD_M = 500.0
DEFAULT_CONNECTIVITY_HOPS = 2


def build_junction_graph(
    reaches: dict[str, "ReachConfig"],  # ModelConfig.reaches
) -> dict[str, set[str]]:
    """Adjacency from reach A → reach B if they share any junction
    (A.upstream_junction ∈ {B.upstream_junction, B.downstream_junction}
    or A.downstream_junction ∈ {…}). Symmetric.

    Reaches with both junctions unset are returned with empty edge sets;
    `ReachConfig` is Pydantic `extra='allow'` so the fields may be
    missing on some legacy reaches (treat as no edges, not as errors)."""


def find_neighbor_reaches(
    graph: dict[str, set[str]],
    target_reach: str,
    max_hops: int = DEFAULT_CONNECTIVITY_HOPS,
) -> set[str]:
    """BFS to depth `max_hops` over the junction graph. Excludes
    `target_reach` itself."""


def compute_min_reach_distance(
    target_cells_gdf: gpd.GeoDataFrame,
    neighbor_cells_gdf: gpd.GeoDataFrame,
) -> float:
    """Minimum cell-to-cell distance in meters.

    Both inputs must share a projected CRS (EPSG:3035 for Lithuanian
    fixtures; otherwise reproject to EPSG:3857 inside the function for
    geographic CRS inputs, mirroring `compute_reach_metrics`).

    Implementation note: `gpd.sjoin_nearest(target, neighbor,
    distance_col='dist_m')` uses a spatial index (R-tree) to find each
    target cell's nearest neighbor in O((N+M) log(N+M)) rather than
    naive O(N×M). Then `result['dist_m'].min()` gives the minimum.

    Returns 0.0 if ANY cells touch / overlap (intersection has zero
    distance). Returns the minimum distance in meters otherwise.
    """
```

The `ReachConfig` parameter type comes from
`src.salmopy.io.config.ReachConfig` (a Pydantic model with the
`upstream_junction` / `downstream_junction` fields).

### Step 2 — Wire connectivity into the per-fixture check

`check_fixture_geography(fixture_dir)` currently doesn't load the YAML
config — it only reads the shapefile. To add connectivity, EITHER:

- **(a) Load config inside `check_fixture_geography`**: Look for
  `configs/{fixture_dir.name}.yaml` relative to repo root. Falls back
  to skipping connectivity if config missing. Heuristic but matches
  the existing fixture-naming convention.
- **(b) Add explicit `config: ModelConfig | None = None` parameter**:
  Caller (the test) loads config and passes it in. More explicit but
  requires changing the test signature.

**Recommend (a)** for consistency with the auto-discovery pattern of
`discover_fixture_shapefile`. Add a helper:

```python
def _load_fixture_config(fixture_dir: Path) -> Optional["ModelConfig"]:
    """Auto-discover the YAML config for a fixture by name convention.

    Looks for `<repo_root>/configs/{fixture_dir.name}.yaml`. Returns None
    if missing OR if loading fails (logs a warning). Callers treat None
    as "skip connectivity check for this fixture" — it's a soft signal,
    not an error.
    """
    repo_root = fixture_dir.resolve().parents[2]  # tests/fixtures/X → repo_root
    cfg_path = repo_root / "configs" / f"{fixture_dir.name}.yaml"
    if not cfg_path.exists():
        return None
    try:
        from salmopy.io.config import load_config
        return load_config(cfg_path)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "could not load %s for connectivity check: %s", cfg_path, exc)
        return None
```

Edge case: a reach in the YAML config that's NOT in the shapefile
(orphan entry, common in reduced/test fixtures) — `build_junction_graph`
should keep the edge in the abstract graph, but `find_neighbor_reaches`
must guard against asking for cells of a missing reach. Filter to
shapefile-present reaches at the call site:

```python
shapefile_reaches = set(cells_gdf["REACH_NAME"].unique())
graph = build_junction_graph(config.reaches)
neighbors = find_neighbor_reaches(graph, target) & shapefile_reaches
```

Then extend `check_reach_plausibility` with a new keyword argument:

```python
def check_reach_plausibility(
    metrics: ReachMetrics,
    classification: ReachClass,
    *,
    max_river_effective_width_m: float = DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M,
    min_marine_cells: int = DEFAULT_MIN_MARINE_CELLS,
    polygon_coverage_ratio: Optional[float] = None,
    max_cell_to_polygon_area_ratio: float = DEFAULT_MAX_CELL_TO_POLYGON_AREA_RATIO,
    # v0.56:
    nearest_neighbor_distance_m: Optional[float] = None,
    connectivity_threshold_m: float = DEFAULT_CONNECTIVITY_THRESHOLD_M,
) -> list[ReachIssue]:
    ...
    # New rule: only fire when nearest_neighbor_distance_m is provided
    # (caller computed neighbor proximity). When None (no junction config
    # available, e.g. example_a / example_b single-reach fixtures), skip.
    if nearest_neighbor_distance_m is not None and \
       nearest_neighbor_distance_m > connectivity_threshold_m:
        issues.append(ReachIssue(
            severity="error",
            code="REACH_DISCONNECTED",
            message=(
                f"nearest 2-hop neighbor reach is {nearest_neighbor_distance_m:.0f} m "
                f"away (threshold {connectivity_threshold_m:.0f} m); cells likely "
                f"generated at wrong coordinates relative to the basin"
            ),
        ))
```

`check_fixture_geography` computes the junction graph once per fixture,
calls `find_neighbor_reaches` per reach, computes
`compute_min_reach_distance` to those neighbors' cells, and threads the
result into `check_reach_plausibility` via the new kwarg.

### Step 3 — Threshold tuning + KNOWN_GEOMETRY_DRIFT integration

Run the check against all existing fixtures. Expected outcomes:
- `example_a`, `example_b`: no `reaches:` block with `*_junction` fields
  configured (or single-reach), so config returns no graph edges →
  `nearest_neighbor_distance_m` stays None → check skipped.
- `example_baltic`: 14 reaches, geometrically contiguous in delta —
  expected pass at 500 m.
- `example_minija_basin`: tributaries within ~100 m of Minija (1-hop
  pass); Minija → Atmata fails 1-hop (~50 km apart) but passes via
  2-hop transit through Lagoon (Atmata's downstream). Expected pass.
- WGBAST 4-reach rivers: chain is contiguous — pass.

If a legitimate fixture fails at 500 m with k=2, FIRST option is to
add a registry entry to `tests/test_geographic_conformance.py::KNOWN_GEOMETRY_DRIFT`
with a clear reason (the existing pattern from v0.51.4) — same shape
as the geometry-drift xfails for Danė/Tornionjoki/Simojoki had before
those were fixed. Tightening or loosening the threshold is the LAST
resort, not first.

For threshold rationale: 500 m is roughly **6-17× the cell circumradius**
across existing fixtures (Minija basin uses 30 m cells per v0.55.2;
WGBAST fixtures use 60-150 m cells). A new fixture whose reach is 6+
cells away from any 2-hop neighbor is almost certainly mis-located.
500 m is conservative for delta systems with sparse cell coverage near
junctions; tighter would catch more real bugs but risk false positives
for marine reaches.

### Step 4 — Test parametrization

`tests/test_geographic_conformance.py::test_reach_geographic_plausibility`
already takes (fixture, reach) parametrize. The session-cached
`_get_fixture_results(fixture)` calls `check_fixture_geography(fx_dir)`.
With Step 2 (a), `check_fixture_geography` auto-discovers the YAML
config from `configs/{fixture_dir.name}.yaml` — no signature change
needed at the test layer. The new `REACH_DISCONNECTED` issue surfaces
through the existing `pytest.fail(...)` pretty-printer.

### Step 5 — Documentation

- Add a "Connectivity Plausibility" section to the
  `app/modules/geographic_conformance.py` module docstring explaining
  k-hop neighbor-proximity rule and the 500 m threshold rationale.
- Document the `KNOWN_GEOMETRY_DRIFT` registry as the OFFICIAL way to
  manage legitimate violations — same xfail-strict pattern that
  already governs width/polygon checks.

## Risks and mitigations

| Risk | Mitigation |
|--|--|
| Cell-distance computation is O(N×M); large fixtures could be slow | Use `gpd.sjoin_nearest`. For Tornionjoki (~3000 cells per reach) the union-then-distance approach is sub-second; sjoin_nearest scales to ~10k×10k in seconds. Validate during Step 3 tuning before claiming the perf budget. |
| Marine reaches (lagoon, sea) sit naturally far from river mouth cells | The `classification` is already passed into `check_reach_plausibility`. The connectivity check applies UNIFORMLY across river and marine — distance is just distance. A 500 m threshold is generous enough that lagoon-to-river-mouth proximity passes, even with sparse marine cell coverage. If marine fixtures fail systematically, add class-aware thresholds (e.g. `marine_connectivity_threshold_m=2000`) rather than disabling the check. |
| `example_minija_basin` Minija → Atmata fails direct adjacency (~50 km) | k=2 hop traversal: Minija's 2-hop neighbors include Lagoon (Atmata's downstream). Lagoon cells are near Minija cells via the geographic Klaipėda strait area → passes. |
| Single-reach fixtures (`example_a`, `example_b`) | When `find_neighbor_reaches` returns an empty set, `check_fixture_geography` MUST NOT call `compute_min_reach_distance` (no neighbors to compare against). It passes `nearest_neighbor_distance_m=None` to `check_reach_plausibility`, which short-circuits the connectivity check (None → skip, distinct from 0.0 → cells overlap). Existing test paths unchanged. |
| New fixtures with deliberately disconnected reaches by design | First option: add to `KNOWN_GEOMETRY_DRIFT` with a documented reason. Only if that pattern doesn't fit, consider a per-reach `connectivity_skip: true` field in `ReachConfig`. Avoid adding it speculatively. |
| `check_fixture_geography` becomes config-aware (Step 2a) — config loading might fail for malformed YAMLs | Wrap config-loading in a try/except; log a warning and proceed with `nearest_neighbor_distance_m=None` (skip connectivity check) on failure. The reach-level checks still fire, so partial failure mode is acceptable. |
| Junction graph circularity (e.g. delta loops) | BFS to depth k handles cycles via visited-set. Not a correctness risk, just performance. |

## Acceptance criteria

1. All existing fixtures (`example_a`, `example_b`, `example_baltic`,
   `example_byskealven`, `example_morrumsan`, `example_simojoki`,
   `example_tornionjoki`, `example_minija_basin`) pass the new check —
   either by satisfying the threshold or via documented
   `KNOWN_GEOMETRY_DRIFT` registry entries.
2. **Verify the Minija → Atmata 2-hop assumption**: instrument Step 3
   with a one-time print of `find_neighbor_reaches('Minija', max_hops=2)`
   for `example_minija_basin` and confirm Lagoon (or another adjacent
   reach) appears in the result. If 2 hops are insufficient, the
   recommended scope changes — re-evaluate before continuing.
3. A unit test (in-memory mock cells, NOT a full fixture directory)
   verifies the check fires when neighbor distance exceeds threshold.
   Mock setup: two `gpd.GeoDataFrame`s with cells separated by
   `threshold + 1` meters, dummy junction config wiring them as flow
   neighbors. Assert `REACH_DISCONNECTED` issue appears.
4. The new check adds no more than ~20% to the existing
   `test_reach_geographic_plausibility` runtime (currently ~3-4 min
   for the full parametrize across all 8 fixtures and ~60 reaches; the
   new sjoin_nearest pass per-reach should add <1 min total).
5. Documentation: a "Connectivity Plausibility" section in
   `app/modules/geographic_conformance.py` module docstring; this plan
   file referenced from the v0.56 release CHANGELOG entry.

## Out of scope (separate v0.57+ work)

- Confluence-position check (option 3 above). Requires populating a new
  YAML field across all fixtures.
- Junction-graph topology validation (e.g. detect cycles, verify single
  marine sink). The current model assumes well-formed graphs.
- Cell-level overlap detection (e.g. tributary cells overlapping Minija
  cells should be deduplicated). Different problem.
- Inter-fixture isolation (cells shouldn't overlap between fixtures).
  Not a fixture-internal property.

## Open questions (resolve during implementation)

1. **Is `k=2` the right hop count?** Reasoning above argues k=2 covers
   star-graph + cross-basin abstractions. Open: are there fixtures where
   3 hops are needed? Run the verification in Acceptance #2 first; raise
   k only if 2 is insufficient AND no fixture-level workaround exists.
2. **Class-specific thresholds?** The proposal uses a single 500 m
   threshold for both river and marine. If marine fixtures fail
   systematically (e.g. BalticCoast cells far from Lagoon cells via
   sparse coastal tiling), introduce
   `DEFAULT_MARINE_CONNECTIVITY_THRESHOLD_M = 2000` and key it off
   `classification`. Defer until measured.
3. **Should the check apply to all classes or river-only?** Marine
   reaches benefit from connectivity validation (catches the same
   "wrong coordinates" bug class). The proposal applies uniformly.
   Reverse only if false-positives surface during Step 3 tuning.
4. **Fail-loud vs warn?** v0.51.x checks all use `severity="error"`
   which fires `pytest.fail`. Connectivity could plausibly be a warning
   for the first few releases (CI sees the issue without breaking the
   build). Recommendation: error-severity from the start, with
   `KNOWN_GEOMETRY_DRIFT` registry as the safety valve. Matches the
   pattern v0.51.4 established for width/polygon checks.

## Implementation status / pickup notes

- This plan is a v0.56+ candidate, not v0.56-mandatory. It's defense-in-
  depth: today's existing per-reach checks already protect against the
  most common geometry bugs (RIVER_TOO_WIDE caught the v0.55.0 inflated
  tributaries). Connectivity adds a second layer specifically for the
  "right shape, wrong place" failure mode.
- Recommended pickup order: implement Step 1 helpers (pure functions,
  unit-testable in isolation) → Step 2 wiring → Step 3 verification.
  Don't ship until all 8 existing fixtures pass or have documented
  `KNOWN_GEOMETRY_DRIFT` entries.

## Estimated effort

- 3 helper functions (`build_junction_graph`, `find_neighbor_reaches`,
  `compute_min_reach_distance`) + `_load_fixture_config`: ~120 LOC, ~1.5 hours.
- Wire into `check_reach_plausibility` + `check_fixture_geography`: ~50 LOC, ~1 hour.
- Documentation (module docstring, this plan reference): ~30 LOC, ~30 min.
- Unit test for failure mode (mock cells, in-memory): ~80 LOC, ~1 hour.
- Threshold tuning + assumption verification (Acceptance #2): ~1 hour
  (one-shot run + log inspection across 8 fixtures).
- Total: **~5-6 hours of focused work** (revised up from initial ~4-5h
  estimate after Round 1-3 review surfaced edge cases).
