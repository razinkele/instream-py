"""Read adult arrival CSV files for anadromous species.

Parses the inSTREAM adult arrival input format and provides a schedule
of daily arrivals computed from a triangular temporal distribution.

The CSV "year" column indicates which simulation year the record applies to.
The arrival start/peak/end dates provide month-day patterns that are
shifted to the current simulation year when computing daily arrivals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any

import pandas as pd


def read_adult_arrivals(path: Path) -> List[Dict[str, Any]]:
    """Read adult arrival CSV file.

    Skips comment lines starting with ';'.
    Expects columns (order matters):
        Year, Species, Reach, Number, Fraction female,
        Arrival start, Arrival peak, Arrival end,
        Length min, Length mode, Length max

    The arrival start/peak/end dates are parsed and their month-day
    components are stored for year-shifting at runtime.

    Returns list of dicts, one per row.
    """
    arrivals = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            parts = [p.strip() for p in line.split(",")]
            start_ts = pd.Timestamp(parts[5])
            peak_ts = pd.Timestamp(parts[6])
            end_ts = pd.Timestamp(parts[7])
            arrivals.append(
                {
                    "year": int(parts[0]),
                    "species": parts[1],
                    "reach": parts[2],
                    "number": int(parts[3]),
                    "frac_female": float(parts[4]),
                    "start_month": start_ts.month,
                    "start_day": start_ts.day,
                    "peak_month": peak_ts.month,
                    "peak_day": peak_ts.day,
                    "end_month": end_ts.month,
                    "end_day": end_ts.day,
                    "length_min": float(parts[8]),
                    "length_mode": float(parts[9]),
                    "length_max": float(parts[10]),
                }
            )
    return arrivals


def get_arrival_record_for_year(
    arrival_records: List[Dict[str, Any]],
    sim_year: int,
    species: str = None,
    reach: str = None,
) -> List[Dict[str, Any]]:
    """Find arrival records matching the simulation year (and optionally species/reach)."""
    matches = []
    for rec in arrival_records:
        if rec["year"] != sim_year:
            continue
        if species and rec["species"] != species:
            continue
        if reach and rec["reach"] != reach:
            continue
        matches.append(rec)
    return matches


def _triangular_cdf(t: float, peak_t: float, window_days: float) -> float:
    """Triangular CDF on [0, window_days] with mode at peak_t."""
    if window_days <= 0:
        return 1.0
    if t <= 0:
        return 0.0
    if t >= window_days:
        return 1.0
    if t <= peak_t:
        if peak_t == 0:
            return 0.0
        return (t * t) / (window_days * peak_t)
    else:
        tail = window_days - peak_t
        if tail == 0:
            return 1.0
        return 1.0 - ((window_days - t) ** 2) / (window_days * tail)


def compute_daily_arrivals(
    arrival_record: Dict[str, Any],
    current_date: pd.Timestamp,
    arrived_so_far: int = 0,
) -> int:
    """Compute number of adults arriving on a given date.

    Uses the triangular CDF across the arrival window (start, peak, end)
    to determine cumulative expected arrivals by today, then subtracts
    what has already arrived.

    Parameters
    ----------
    arrival_record : dict
        Record from read_adult_arrivals.
    current_date : pd.Timestamp
        Current simulation date.
    arrived_so_far : int
        Number of adults from this record that have already arrived
        in previous days. Used to avoid rounding drift.

    Returns 0 if current_date is outside the arrival window.
    """
    sim_year = current_date.year
    start = pd.Timestamp(
        sim_year, arrival_record["start_month"], arrival_record["start_day"]
    )
    peak = pd.Timestamp(
        sim_year, arrival_record["peak_month"], arrival_record["peak_day"]
    )
    end = pd.Timestamp(sim_year, arrival_record["end_month"], arrival_record["end_day"])
    total = arrival_record["number"]

    if current_date < start or current_date > end:
        return 0

    window_days = float((end - start).days)
    if window_days <= 0:
        return max(0, total - arrived_so_far) if current_date == start else 0

    # Days elapsed since start (use end-of-day: t+1 for CDF)
    t = float((current_date - start).days) + 1.0
    peak_t = float((peak - start).days)
    peak_t = max(0.0, min(peak_t, window_days))

    cumulative_expected = int(round(total * _triangular_cdf(t, peak_t, window_days)))
    n_today = max(0, cumulative_expected - arrived_so_far)
    return n_today
