"""Time management for inSTREAM simulations.

Provides TimeManager for daily time stepping, census day detection,
and YearShuffler for stochastic input year resampling.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np
import pandas as pd


class TimeManager:
    """Manages simulation time advancement and environmental condition lookup.

    Parameters
    ----------
    start_date : str
        Simulation start date (e.g. "2011-04-01").
    end_date : str
        Simulation end date (e.g. "2013-09-30").
    time_series : dict[str, pd.DataFrame]
        Mapping of reach name to DataFrame with DatetimeIndex and columns
        including flow, temperature, turbidity.
    """

    def __init__(
        self,
        start_date: str,
        end_date: str,
        time_series: Dict[str, pd.DataFrame],
    ) -> None:
        self._start_date = pd.Timestamp(start_date)
        self._end_date = pd.Timestamp(end_date)
        self._current_date = pd.Timestamp(start_date)
        self._time_series = time_series

    @property
    def current_date(self) -> pd.Timestamp:
        """Current simulation date."""
        return self._current_date

    @property
    def julian_date(self) -> int:
        """Day of year (1-365/366) for the current date."""
        return self._current_date.day_of_year

    def advance(self) -> float:
        """Advance simulation by one day.

        Returns
        -------
        float
            Step length in days (1.0 for daily mode).
        """
        self._current_date += pd.Timedelta(days=1)
        return 1.0

    def is_done(self) -> bool:
        """Return True when the simulation has passed the end date."""
        return self._current_date > self._end_date

    def get_conditions(self, reach_name: str) -> Dict[str, float]:
        """Look up environmental conditions for a reach at the current date.

        Uses nearest-date lookup (method='nearest') from the time-series
        DataFrame to handle potential time mismatches (e.g. noon vs midnight).

        Parameters
        ----------
        reach_name : str
            Name of the reach to look up.

        Returns
        -------
        dict[str, float]
            Dictionary with keys like 'flow', 'temperature', 'turbidity'.
        """
        df = self._time_series[reach_name]
        idx = df.index.get_indexer([self._current_date], method="nearest")[0]
        if idx < 0:
            raise ValueError(
                f"No matching date for {self._current_date} in reach {reach_name}"
            )
        nearest_date = df.index[idx]
        gap_days = abs((nearest_date - self._current_date).total_seconds()) / 86400.0
        if gap_days > 1.5:
            raise ValueError(
                f"Nearest date {nearest_date} is {gap_days:.1f} days from "
                f"{self._current_date} for reach {reach_name} — "
                f"date is outside time-series range"
            )
        row = df.iloc[idx]
        return {col: float(row[col]) for col in df.columns}

    def formatted_time(self) -> str:
        """Return a human-readable string of the current date."""
        return self._current_date.strftime("%Y-%m-%d")


def is_census(
    date: pd.Timestamp,
    census_days: List[str],
    years_to_skip: int,
    start_date: pd.Timestamp,
) -> bool:
    """Check whether *date* is a census day.

    Parameters
    ----------
    date : pd.Timestamp
        The date to check.
    census_days : list of str
        Census day specifications as "month/day" strings (e.g. ["6/15", "9/30"]).
    years_to_skip : int
        Number of years from start_date during which census is suppressed.
    start_date : pd.Timestamp
        Simulation start date (used to compute skip window).

    Returns
    -------
    bool
    """
    # Check skip window: census suppressed if date is within years_to_skip
    # of start_date.
    if years_to_skip > 0:
        skip_until = start_date + pd.DateOffset(years=years_to_skip)
        if date < skip_until:
            return False

    # Check if date matches any census day (month/day)
    for spec in census_days:
        month, day = (int(x) for x in spec.split("/"))
        if date.month == month and date.day == day:
            return True

    return False


class YearShuffler:
    """Maps simulation years to randomly selected input years.

    Parameters
    ----------
    available_years : sequence of int
        Years available in the input data.
    seed : int
        Random seed for reproducibility.
    """

    def __init__(self, available_years: Sequence[int], seed: int) -> None:
        self._available_years = list(available_years)
        self._rng = np.random.default_rng(seed)
        self._cache: Dict[int, int] = {}

    def get_year(self, sim_year: int) -> int:
        """Return the mapped input year for a given simulation year.

        The mapping is computed lazily and cached so that repeated calls
        for the same sim_year return the same result.

        Parameters
        ----------
        sim_year : int
            The simulation year to map.

        Returns
        -------
        int
            A year drawn from available_years.
        """
        if sim_year not in self._cache:
            self._cache[sim_year] = self._rng.choice(self._available_years)
        return self._cache[sim_year]
