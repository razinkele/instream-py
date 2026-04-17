"""Barrier/dam passage system for inSTREAM migration.

Barriers sit on reach-graph edges and produce stochastic outcomes
(mortality, deflection, transmission) for fish crossing them.
Direction is implicit: edge (A, B) stores the downstream outcome,
edge (B, A) stores the upstream outcome.

When ``barrier_map`` is ``None`` (no barriers configured), all call sites
skip barrier checks — zero overhead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


# ── Data types ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BarrierOutcome:
    """Stochastic outcome probabilities for one barrier direction.

    Invariant: ``mortality + deflection + transmission == 1.0`` (±1e-6).
    """

    mortality: float
    deflection: float
    transmission: float

    def __post_init__(self):
        total = self.mortality + self.deflection + self.transmission
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"BarrierOutcome probabilities must sum to 1.0, got {total:.6f}"
            )


@dataclass(frozen=True)
class BarrierDef:
    """One physical barrier with directional outcomes."""

    name: str
    from_reach_idx: int
    to_reach_idx: int
    downstream: BarrierOutcome
    upstream: BarrierOutcome


# ── BarrierMap ────────────────────────────────────────────────────────────

class BarrierMap:
    """Look-up table mapping reach-graph edges to barrier outcomes.

    Usage::

        outcome = barrier_map.check(from_reach=3, to_reach=5)
        if outcome is not None:
            ...  # roll dice against outcome probabilities
    """

    def __init__(self, barriers: List[BarrierDef]) -> None:
        # Key: (from_reach_idx, to_reach_idx) → BarrierOutcome
        self._edges: Dict[Tuple[int, int], BarrierOutcome] = {}
        self._barriers = barriers

        for b in barriers:
            # Downstream direction: from → to
            self._edges[(b.from_reach_idx, b.to_reach_idx)] = b.downstream
            # Upstream direction: to → from
            self._edges[(b.to_reach_idx, b.from_reach_idx)] = b.upstream

    def check(self, from_reach: int, to_reach: int) -> Optional[BarrierOutcome]:
        """Return the outcome for the edge, or ``None`` if no barrier."""
        return self._edges.get((from_reach, to_reach))

    @property
    def barriers(self) -> List[BarrierDef]:
        return list(self._barriers)

    def __len__(self) -> int:
        return len(self._barriers)


# ── Outcome rolling ──────────────────────────────────────────────────────

RESULT_TRANSMIT = 0
RESULT_DEFLECT = 1
RESULT_MORTALITY = 2


def roll_barrier_outcome(outcome: BarrierOutcome, rng: np.random.Generator) -> int:
    """Roll a single stochastic barrier outcome.

    Returns
    -------
    int
        ``RESULT_TRANSMIT`` (0), ``RESULT_DEFLECT`` (1), or
        ``RESULT_MORTALITY`` (2).
    """
    draw = rng.random()
    if draw < outcome.transmission:
        return RESULT_TRANSMIT
    elif draw < outcome.transmission + outcome.deflection:
        return RESULT_DEFLECT
    else:
        return RESULT_MORTALITY


# ── Route computation ────────────────────────────────────────────────────

def build_reverse_reach_graph(
    reach_graph: Dict[int, List[int]],
) -> Dict[int, List[int]]:
    """Build reverse (upstream) graph from a downstream reach graph.

    Given ``reach_graph[i] = [j, ...]`` meaning i→j is downstream,
    returns ``reverse[j] = [i, ...]`` meaning j→i is upstream.
    """
    reverse: Dict[int, List[int]] = {}
    for src, destinations in reach_graph.items():
        for dst in destinations:
            reverse.setdefault(dst, []).append(src)
    return reverse


def find_upstream_route(
    from_reach: int,
    to_reach: int,
    reverse_graph: Dict[int, List[int]],
    max_hops: int = 100,
) -> Optional[List[int]]:
    """Find a route from ``from_reach`` to ``to_reach`` via upstream edges.

    Uses BFS on the reverse graph. Returns list of reach indices from
    ``from_reach`` to ``to_reach`` (inclusive), or ``None`` if no route.
    """
    if from_reach == to_reach:
        return [from_reach]

    from collections import deque
    visited = {from_reach}
    queue: deque = deque([(from_reach, [from_reach])])

    while queue:
        current, path = queue.popleft()
        if len(path) > max_hops:
            break
        for neighbor in reverse_graph.get(current, []):
            if neighbor in visited:
                continue
            new_path = path + [neighbor]
            if neighbor == to_reach:
                return new_path
            visited.add(neighbor)
            queue.append((neighbor, new_path))
    return None


# ── High-level passage functions ─────────────────────────────────────────

def attempt_downstream_passage(
    barrier_map: Optional[BarrierMap],
    from_reach: int,
    to_reach: int,
    rng: np.random.Generator,
) -> int:
    """Check downstream barrier and roll outcome.

    Returns ``RESULT_TRANSMIT`` if no barrier exists or fish passes.
    """
    if barrier_map is None:
        return RESULT_TRANSMIT
    outcome = barrier_map.check(from_reach, to_reach)
    if outcome is None:
        return RESULT_TRANSMIT
    return roll_barrier_outcome(outcome, rng)


def attempt_upstream_route(
    barrier_map: Optional[BarrierMap],
    estuary_reach: int,
    natal_reach: int,
    reverse_graph: Dict[int, List[int]],
    rng: np.random.Generator,
) -> Tuple[int, int]:
    """Simulate upstream passage through all barriers on route to natal reach.

    Returns
    -------
    (result, last_passable_reach) : tuple[int, int]
        ``result`` is RESULT_TRANSMIT if fish reached natal reach,
        RESULT_DEFLECT if blocked (placed at ``last_passable_reach``),
        or RESULT_MORTALITY if killed at a barrier.
    """
    if barrier_map is None or len(barrier_map) == 0:
        return RESULT_TRANSMIT, natal_reach

    route = find_upstream_route(estuary_reach, natal_reach, reverse_graph)
    if route is None:
        # No route found — place at estuary
        return RESULT_DEFLECT, estuary_reach

    last_passable = estuary_reach
    for i in range(len(route) - 1):
        from_r = route[i]
        to_r = route[i + 1]
        outcome = barrier_map.check(from_r, to_r)
        if outcome is None:
            last_passable = to_r
            continue
        result = roll_barrier_outcome(outcome, rng)
        if result == RESULT_TRANSMIT:
            last_passable = to_r
        elif result == RESULT_DEFLECT:
            return RESULT_DEFLECT, last_passable
        else:
            return RESULT_MORTALITY, last_passable

    return RESULT_TRANSMIT, natal_reach
