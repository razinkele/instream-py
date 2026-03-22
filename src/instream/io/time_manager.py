"""Time management for inSTREAM simulations.

Provides TimeManager for daily time stepping, census day detection,
and YearShuffler for stochastic input year resampling.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np
import pandas as pd


def detect_frequency(time_series_df: pd.DataFrame) -> int:
    """Detect time-series row frequency.

    Parameters
    ----------
    time_series_df : pd.DataFrame
        DataFrame with a DatetimeIndex.

    Returns
    -------
    int
        Number of steps per day (1 for daily, 24 for hourly, etc.).
    """
    timestamps = time_series_df.index
    if len(timestamps) < 2:
        return 1
    intervals = np.diff(timestamps.values).astype("timedelta64[m]").astype(float)
    median_minutes = np.median(intervals)
    if median_minutes <= 0:
        return 1
    steps_per_day = max(1, round(1440.0 / median_minutes))
    return steps_per_day


class TimeManager:
    """Manages simulation time advancement and environmental condition lookup.

    Supports both daily and sub-daily time stepping.  The frequency is
    auto-detected from the time-series data.  Daily input behaves exactly
    as before (backward compatible).

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

        # Auto-detect frequency from first reach
        first_df = next(iter(time_series.values()))
        self._steps_per_day: int = detect_frequency(first_df)

        # Sub-daily bookkeeping
        self._substep_index: int = 0
        self._is_day_boundary: bool = True  # start of sim is a day boundary
        self._row_pointers: Dict[str, int] = {rname: 0 for rname in time_series}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_date(self) -> pd.Timestamp:
        """Current simulation date."""
        return self._current_date

    @property
    def julian_date(self) -> int:
        """Day of year (1-365/366) for the current date."""
        return self._current_date.day_of_year

    @property
    def steps_per_day(self) -> int:
        """Number of sub-steps per calendar day."""
        return self._steps_per_day

    @property
    def is_day_boundary(self) -> bool:
        """True when the current sub-step is the last of the calendar day."""
        return self._is_day_boundary

    @property
    def substep_index(self) -> int:
        """Position within the current day (0-based)."""
        return self._substep_index

    # ------------------------------------------------------------------
    # Time advancement
    # ------------------------------------------------------------------

    def advance(self) -> float:
        """Advance simulation by one sub-step.

        Returns
        -------
        float
            Step length as a fraction of a day (1.0 for daily,
            1/24 for hourly, etc.).
        """
        if self._steps_per_day == 1:
            # Daily mode — same as before
            self._current_date += pd.Timedelta(days=1)
            self._is_day_boundary = True
            self._substep_index = 0
            for rname in self._row_pointers:
                self._row_pointers[rname] += 1
            return 1.0

        # Sub-daily mode
        self._substep_index += 1
        for rname in self._row_pointers:
            self._row_pointers[rname] += 1

        # Update current_date from the time-series timestamp
        first_reach = next(iter(self._time_series))
        idx = self._row_pointers[first_reach]
        first_df = self._time_series[first_reach]
        if idx < len(first_df):
            self._current_date = first_df.index[idx]
        # else: keep last date (is_done will trigger)

        # Determine day boundary: is the *next* row a new calendar day?
        next_idx = idx + 1
        if next_idx >= len(first_df):
            self._is_day_boundary = True
        else:
            next_date = first_df.index[next_idx]
            self._is_day_boundary = next_date.date() != self._current_date.date()

        if self._is_day_boundary:
            self._substep_index = 0  # will reset for next day

        step_length = 1.0 / self._steps_per_day
        return step_length

    def is_done(self) -> bool:
        """Return True when the simulation has passed the end date.

        For sub-daily mode, also checks whether all row pointers have
        exceeded the data length.
        """
        if self._steps_per_day == 1:
            return self._current_date > self._end_date

        # Sub-daily: done when current_date is past end AND we've
        # exhausted the data, OR simply past end_date.
        first_reach = next(iter(self._time_series))
        idx = self._row_pointers[first_reach]
        if idx >= len(self._time_series[first_reach]):
            return True
        return self._current_date > self._end_date

    # ------------------------------------------------------------------
    # Condition lookup
    # ------------------------------------------------------------------

    def get_conditions(self, reach_name: str) -> Dict[str, float]:
        """Look up environmental conditions for a reach at the current date.

        For daily mode, uses nearest-date lookup (method='nearest') from
        the time-series DataFrame.  For sub-daily mode, uses exact row
        indexing via the internal row pointer.

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

        if self._steps_per_day == 1:
            # Daily: nearest-neighbor lookup (existing behavior)
            idx = df.index.get_indexer([self._current_date], method="nearest")[0]
            if idx < 0:
                raise ValueError(
                    f"No matching date for {self._current_date} in reach {reach_name}"
                )
            nearest_date = df.index[idx]
            gap_days = (
                abs((nearest_date - self._current_date).total_seconds()) / 86400.0
            )
            if gap_days > 1.5:
                raise ValueError(
                    f"Nearest date {nearest_date} is {gap_days:.1f} days "
                    f"from {self._current_date} for reach {reach_name} — "
                    f"date is outside time-series range"
                )
            row = df.iloc[idx]
        else:
            # Sub-daily: exact row index
            idx = self._row_pointers[reach_name]
            if idx >= len(df):
                idx = len(df) - 1
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
