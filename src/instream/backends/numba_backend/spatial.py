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


@numba.njit(cache=True)
def build_candidates_from_cache_numba(
    alive, cell_idx, lengths, wet_mask,
    geo_offsets, geo_flat, geo_dist2, neighbor_indices,
    move_radius_max, move_radius_L1, move_radius_L9,
):
    """Build candidate lists using pre-computed geometry table. O(n_fish * avg_candidates)."""
    LN81 = 4.394449154672439
    n_fish = alive.shape[0]

    # Compute worst-case buffer size
    total_max = np.int64(0)
    for i in range(n_fish):
        if alive[i] and cell_idx[i] >= 0:
            c = cell_idx[i]
            total_max += geo_offsets[c + 1] - geo_offsets[c]
            # Extra room for neighbors that might not be in geo_flat
            max_nb = neighbor_indices.shape[1]
            total_max += max_nb

    flat_buf = np.empty(max(total_max, np.int64(1)), dtype=np.int32)
    offsets = np.zeros(n_fish + 1, dtype=np.int64)
    pos = np.int64(0)

    for i in range(n_fish):
        if not alive[i] or cell_idx[i] < 0:
            offsets[i + 1] = pos
            continue

        c = cell_idx[i]

        # Compute per-fish radius via logistic fraction
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

        r2 = (move_radius_max * frac) ** 2

        # Filter pre-computed candidates by radius and wet mask
        start = geo_offsets[c]
        end = geo_offsets[c + 1]
        fish_start = pos
        for k in range(start, end):
            j = geo_flat[k]
            if wet_mask[j] and geo_dist2[k] <= r2:
                flat_buf[pos] = j
                pos += 1

        # Ensure wet neighbors are included (even if outside radius)
        max_nb = neighbor_indices.shape[1]
        for nb_k in range(max_nb):
            nb = neighbor_indices[c, nb_k]
            if nb < 0:
                break
            if not wet_mask[nb]:
                continue
            found = False
            for m in range(fish_start, pos):
                if flat_buf[m] == nb:
                    found = True
                    break
            if not found:
                flat_buf[pos] = nb
                pos += 1

        # Ensure current cell included if wet
        if wet_mask[c]:
            found = False
            for m in range(fish_start, pos):
                if flat_buf[m] == c:
                    found = True
                    break
            if not found:
                flat_buf[pos] = c
                pos += 1

        # Sort this fish's candidates to match original behavior
        n_cands = pos - fish_start
        if n_cands > 1:
            # Simple insertion sort (candidates are small)
            for a in range(fish_start + 1, pos):
                key = flat_buf[a]
                b = a - 1
                while b >= fish_start and flat_buf[b] > key:
                    flat_buf[b + 1] = flat_buf[b]
                    b -= 1
                flat_buf[b + 1] = key

        offsets[i + 1] = pos

    flat = flat_buf[:pos].copy()
    return offsets, flat
