"""Reader for inSTREAM time-series input CSV files.

These files contain daily environmental data (temperature, flow, turbidity)
with semicolon-prefixed comment lines and M/d/yyyy HH:mm date format.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pandas as pd


def read_time_series(path: str | Path) -> pd.DataFrame:
    """Read an inSTREAM time-series CSV file into a DataFrame.

    Parameters
    ----------
    path : str or Path
        Path to the CSV file.

    Returns
    -------
    pd.DataFrame
        DataFrame with DatetimeIndex and numeric columns (e.g.
        temperature, flow, turbidity).
    """
    path = Path(path)

    # Read lines, skip comment lines starting with ';'
    with open(path, "r") as fh:
        lines = [line for line in fh if not line.lstrip().startswith(";")]

    # Parse from the filtered lines
    from io import StringIO
    text = "".join(lines)
    df = pd.read_csv(StringIO(text), index_col=0, parse_dates=True)

    # Ensure the index is DatetimeIndex (parse_dates should handle it,
    # but be explicit for the M/d/yyyy HH:mm format if needed)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, format="%m/%d/%Y %H:%M")

    df.index.name = "Date"
    return df


def check_gaps(
    df: pd.DataFrame, max_gap_days: float = 1.0
) -> List[Tuple[pd.Timestamp, float]]:
    """Check for temporal gaps in a time-series DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with a DatetimeIndex (sorted).
    max_gap_days : float
        Maximum allowed gap in days. Gaps exceeding this are reported.

    Returns
    -------
    list of (timestamp, gap_days)
        Each entry gives the timestamp *after* the gap and the gap size
        in days.
    """
    if len(df) < 2:
        return []

    deltas = df.index.to_series().diff().dropna()
    threshold = pd.Timedelta(days=max_gap_days)
    mask = deltas > threshold

    gaps: List[Tuple[pd.Timestamp, float]] = []
    for ts, delta in deltas[mask].items():
        gaps.append((ts, delta.total_seconds() / 86400.0))

    return gaps
