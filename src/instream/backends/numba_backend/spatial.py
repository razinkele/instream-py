"""Numba-compiled brute-force candidate cell search."""

import math
import numba
import numpy as np


@numba.njit(cache=True)
def _find_candidates_single(
    cell_idx, radius, centroid_x, centroid_y, wet_mask, neighbor_indices
):
    """Find wet cells within radius of cell_idx, plus wet neighbors. Returns sorted int32 array."""
    n_cells = centroid_x.shape[0]
    px = centroid_x[cell_idx]
    py = centroid_y[cell_idx]
    r2 = radius * radius
    max_neighbors = neighbor_indices.shape[1]

    # Use a buffer (worst case: all cells are candidates)
    buf = np.empty(n_cells, dtype=np.int32)
    count = 0

    # Distance-based search
    for j in range(n_cells):
        if not wet_mask[j]:
            continue
        dx = centroid_x[j] - px
        dy = centroid_y[j] - py
        if dx * dx + dy * dy <= r2:
            buf[count] = j
            count += 1

    # Add wet neighbors not already found
    for k in range(max_neighbors):
        nb = neighbor_indices[cell_idx, k]
        if nb < 0:
            break
        if not wet_mask[nb]:
            continue
        already = False
        for m in range(count):
            if buf[m] == nb:
                already = True
                break
        if not already:
            buf[count] = nb
            count += 1

    # Ensure current cell included
    if wet_mask[cell_idx]:
        already = False
        for m in range(count):
            if buf[m] == cell_idx:
                already = True
                break
        if not already:
            buf[count] = cell_idx
            count += 1

    result = buf[:count].copy()
    result.sort()
    return result


@numba.njit(cache=True)
def build_all_candidates_numba(
    alive,
    cell_idx,
    lengths,
    centroid_x,
    centroid_y,
    wet_mask,
    neighbor_indices,
    move_radius_max,
    move_radius_L1,
    move_radius_L9,
):
    """Build candidate lists for ALL fish. Returns (offsets, flat) CSR format."""
    LN81 = 4.394449154672439
    n_fish = alive.shape[0]
    n_cells = centroid_x.shape[0]

    # Pre-allocate worst-case buffer and offsets
    flat_buf = np.empty(n_fish * n_cells, dtype=np.int32)
    offsets = np.zeros(n_fish + 1, dtype=np.int64)
    pos = 0

    for i in range(n_fish):
        if not alive[i] or cell_idx[i] < 0:
            offsets[i + 1] = pos
            continue

        # Compute search radius via logistic fraction
        if move_radius_L9 == move_radius_L1:
            frac = 0.9 if lengths[i] >= move_radius_L1 else 0.1
        else:
            mid = (move_radius_L1 + move_radius_L9) * 0.5
            slp = LN81 / (move_radius_L9 - move_radius_L1)
            arg = -slp * (lengths[i] - mid)
            if arg > 500.0:
                arg = 500.0
            elif arg < -500.0:
                arg = -500.0
            frac = 1.0 / (1.0 + math.exp(arg))

        radius = move_radius_max * frac
        cands = _find_candidates_single(
            cell_idx[i], radius, centroid_x, centroid_y, wet_mask, neighbor_indices
        )
        n_cands = len(cands)
        for k in range(n_cands):
            flat_buf[pos + k] = cands[k]
        pos += n_cands
        offsets[i + 1] = pos

    flat = flat_buf[:pos].copy()
    return offsets, flat
