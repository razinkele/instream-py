"""Runtime guards for NaN detection, capacity monitoring, and value validation."""
import logging
import numpy as np

logger = logging.getLogger("instream.guards")


def check_nan(array: np.ndarray, name: str, raise_on_error: bool = True) -> None:
    """Check for NaN or Inf values in an array.

    Parameters
    ----------
    array : np.ndarray
    name : str — descriptive name for error messages
    raise_on_error : bool — if False, log warning instead of raising
    """
    if len(array) == 0:
        return
    has_nan = np.any(np.isnan(array))
    has_inf = np.any(np.isinf(array))
    if has_nan:
        msg = f"NaN detected in {name}: {np.sum(np.isnan(array))} values"
        if raise_on_error:
            raise ValueError(msg)
        logger.warning(msg)
    if has_inf:
        msg = f"Inf detected in {name}: {np.sum(np.isinf(array))} values"
        if raise_on_error:
            raise ValueError(msg)
        logger.warning(msg)


def check_capacity(alive_count: int, max_capacity: int, name: str) -> None:
    """Log warnings when agent array capacity is getting full."""
    if max_capacity == 0:
        return
    occupancy = alive_count / max_capacity
    if occupancy >= 0.95:
        logger.error(
            f"{name} capacity critical: {alive_count}/{max_capacity} "
            f"({occupancy:.0%}). Increase {name}_capacity in config."
        )
    elif occupancy >= 0.80:
        logger.warning(
            f"{name} capacity warning: {alive_count}/{max_capacity} "
            f"({occupancy:.0%}). Consider increasing {name}_capacity."
        )


def check_positive(array: np.ndarray, name: str) -> None:
    """Warn if any values are negative."""
    if len(array) == 0:
        return
    neg_count = np.sum(array < 0)
    if neg_count > 0:
        logger.warning(
            f"Negative values in {name}: {neg_count} values below zero "
            f"(min={np.min(array):.6g})"
        )
