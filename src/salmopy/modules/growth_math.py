"""Shared math helpers for the bioenergetics / growth module.

Kept separate from :mod:`instream.modules.growth` so the numba and jax
backends can import these primitives without pulling in the scalar
pure-Python CMax path.

The canonical contract for CMax temperature interpolation is defined by
:func:`safe_cmax_interp`. All three backends (numpy, numba, jax) must
agree with this function for the same table/temperature inputs.
"""

from __future__ import annotations

import numpy as np


def safe_cmax_interp(temperature: float, table_x, table_y) -> float:
    """Linear interpolation of the CMax temperature multiplier.

    Contract (identical to the scalar :func:`cmax_temp_function` that
    numpy-backend simulations used for years):

    * ``len(table_x) == 0``  → raises :class:`ValueError`. A missing
      temperature table is a configuration error, not a signal to skip
      growth.
    * ``len(table_x) == 1``  → returns ``table_y[0]`` (flat response).
    * Otherwise: linear interpolation between table nodes, clamped to
      the end-point values for temperatures outside ``[table_x[0],
      table_x[-1]]``. Matches :func:`numpy.interp` for non-empty tables.

    The function accepts Python lists, numpy arrays, or any
    ``np.asarray``-convertible sequence for the two tables. It returns
    a plain Python ``float`` so it can be used directly from scalar
    per-fish loops without triggering 0-d array arithmetic.
    """
    xs = np.asarray(table_x, dtype=np.float64)
    ys = np.asarray(table_y, dtype=np.float64)
    if xs.shape != ys.shape:
        raise ValueError(
            "CMax temperature table is malformed: table_x has "
            f"shape {xs.shape} but table_y has shape {ys.shape}."
        )
    n = xs.size
    if n == 0:
        raise ValueError(
            "CMax temperature table is empty. Configure "
            "`cmax_temp_table` on the species (at least one "
            "(temperature, multiplier) pair)."
        )
    if n == 1:
        return float(ys[0])
    t = float(temperature)
    if t <= xs[0]:
        return float(ys[0])
    if t >= xs[-1]:
        return float(ys[-1])
    return float(np.interp(t, xs, ys))
