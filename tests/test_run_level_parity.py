"""Run-level parity: Python inSTREAM vs NetLogo InSALMO 7.3/7.4.

Closes the Sprint-4 deliverable from `docs/NETLOGO_PARITY_ROADMAP.md`:
"behavioral checks beyond unit tests". Until this test, the only
NetLogo parity coverage was *function-level* (17 deterministic-function
tests in tests/test_validation.py); there was no whole-model
comparison against the cached BehaviorSpace tables.

This test loads the cached NetLogo 7.3 example_a BehaviorSpace census
(`netlogo-models/insalmo_exampleA_results.csv`, seed=98, 2011-04-01 →
2013-10-01, 3,658 sub-daily ticks) and asserts that the Python
end-to-end run matches on five stable scalar metrics:

  | # | Metric                                | NetLogo    | Tolerance |
  | 1 | CH-S juvenile abundance peak         | 2,151 @ 2013-01-07 | rtol 0.30 |
  | 2 | CH-S small outmigrant cumulative     | 41,146              | rtol 0.20 |
  | 3 | CH-S adult abundance peak            | 21 @ 2012-07-09    | atol 8    |
  | 4 | CH-S juvenile mean length @ 2012-09-30 | from NL CSV       | rtol 0.10 |
  | 5 | CH-S outmigrant median date (50% CDF) | 2013-01-05        | ±14 days  |

Tolerances are deliberately loose: PCG64 (Python) vs Mersenne Twister
(NetLogo) guarantees individual-level stochastic divergence, and the
cache has only seed=98. Tighten once multiple NetLogo seeds are run.

Marked @pytest.mark.slow — the Python example_a run is ~25 min at
v0.30.2's 36 days/min throughput (912 days). Invoke explicitly:

    micromamba run -n shiny python -m pytest tests/test_run_level_parity.py -v -m slow
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


PROJECT = Path(__file__).resolve().parent.parent
NETLOGO_CSV = (
    PROJECT.parent / "netlogo-models" / "insalmo_exampleA_results.csv"
)


# ---------------------------------------------------------------------------
# NetLogo reference parser
# ---------------------------------------------------------------------------


def _load_netlogo_csv(path: Path) -> pd.DataFrame:
    """Load an InSALMO BehaviorSpace CSV. The first 6 rows are
    NetLogo's BehaviorSpace metadata; actual column headers start on
    row 7 (skiprows=6). The remaining rows are sub-daily ticks with
    population / length / outmigrant series."""
    df = pd.read_csv(path, skiprows=6, quotechar='"', on_bad_lines="skip")
    # `formatted-sim-time` is a string like "4/1/2011 00:00"; parse it so
    # we can slice by calendar date later.
    df["sim_datetime"] = pd.to_datetime(df["formatted-sim-time"],
                                        format="%m/%d/%Y %H:%M",
                                        errors="coerce")
    df["sim_date"] = df["sim_datetime"].dt.date
    return df


def _netlogo_juvenile_peak(df: pd.DataFrame) -> tuple[int, str]:
    s = pd.to_numeric(df["CH-S-juve-abund"], errors="coerce")
    idx = int(s.idxmax())
    return int(s.iloc[idx]), str(df["sim_date"].iloc[idx])


def _netlogo_adult_peak(df: pd.DataFrame) -> tuple[int, str]:
    s = pd.to_numeric(df["CH-S-adult-abund"], errors="coerce")
    idx = int(s.idxmax())
    return int(s.iloc[idx]), str(df["sim_date"].iloc[idx])


def _netlogo_outmigrant_small_total(df: pd.DataFrame) -> int:
    return int(pd.to_numeric(df["CH-S-outmig-small"], errors="coerce").sum())


def _netlogo_outmigrant_median_date(df: pd.DataFrame) -> pd.Timestamp:
    s = pd.to_numeric(df["CH-S-outmig-small"], errors="coerce").fillna(0)
    total = s.sum()
    if total <= 0:
        return pd.NaT
    cumsum = s.cumsum()
    idx = int((cumsum >= total / 2).idxmax())
    return pd.Timestamp(df["sim_datetime"].iloc[idx])


def _netlogo_juve_length_on(df: pd.DataFrame, target_date: str) -> float:
    """Mean juvenile length on or closest before target_date (YYYY-MM-DD)."""
    target = pd.Timestamp(target_date).date()
    mask = pd.to_datetime(df["sim_date"]).dt.date <= target
    s = pd.to_numeric(df.loc[mask, "CH-S-juve-length"], errors="coerce").dropna()
    if s.empty:
        return float("nan")
    return float(s.iloc[-1])


# ---------------------------------------------------------------------------
# Python simulation runner with per-day stage histogram
# ---------------------------------------------------------------------------


def _run_python_example_a() -> dict:
    """Run the Python example_a simulation end-to-end, collecting the
    same metrics NetLogo exports (juvenile/adult/outmigrant counts,
    mean juvenile length) on a per-day basis.

    Returns a dict with:
      'daily': DataFrame of per-day counts (date, juve_count, adult_count,
                 juve_mean_length, small_outmigrants_today)
      'total_small_outmigrants': cumulative at run end
    """
    from instream.model import InSTREAMModel
    from instream.state.life_stage import LifeStage

    CONFIGS = PROJECT / "configs"
    FIXTURES = PROJECT / "tests" / "fixtures"

    model = InSTREAMModel(
        CONFIGS / "example_a.yaml", data_dir=FIXTURES / "example_a",
    )

    juve_stages = {int(LifeStage.FRY), int(LifeStage.PARR)}
    adult_stages = {int(LifeStage.RETURNING_ADULT), int(LifeStage.SPAWNER)}

    rows: list[dict] = []
    prev_outmig = 0
    total_steps = int(model.time_manager.total_steps)

    for _ in range(total_steps):
        model.step()
        if not model.time_manager.is_day_boundary:
            continue
        ts = model.trout_state
        alive = ts.alive_indices()
        if len(alive):
            stages = ts.life_history[alive]
            juve = int(np.isin(stages, list(juve_stages)).sum())
            adult = int(np.isin(stages, list(adult_stages)).sum())
            juve_mask = np.isin(stages, list(juve_stages))
            juve_lens = ts.length[alive][juve_mask]
            juve_mean_len = float(juve_lens.mean()) if len(juve_lens) else 0.0
        else:
            juve = adult = 0
            juve_mean_len = 0.0
        outmig_total = len(getattr(model, "_outmigrants", []))
        rows.append({
            "date": str(model.time_manager.current_date.date()),
            "juve_count": juve,
            "adult_count": adult,
            "juve_mean_length": juve_mean_len,
            "small_outmigrants_today": outmig_total - prev_outmig,
        })
        prev_outmig = outmig_total

    df = pd.DataFrame(rows)
    df["sim_date"] = pd.to_datetime(df["date"]).dt.date
    return {"daily": df, "total_small_outmigrants": prev_outmig}


def _py_juvenile_peak(py: dict) -> tuple[int, str]:
    df = py["daily"]
    idx = int(df["juve_count"].idxmax())
    return int(df["juve_count"].iloc[idx]), str(df["date"].iloc[idx])


def _py_adult_peak(py: dict) -> tuple[int, str]:
    df = py["daily"]
    idx = int(df["adult_count"].idxmax())
    return int(df["adult_count"].iloc[idx]), str(df["date"].iloc[idx])


def _py_outmigrant_median_date(py: dict) -> pd.Timestamp:
    df = py["daily"]
    s = df["small_outmigrants_today"]
    total = int(s.sum())
    if total <= 0:
        return pd.NaT
    cumsum = s.cumsum()
    idx = int((cumsum >= total / 2).idxmax())
    return pd.Timestamp(df["date"].iloc[idx])


def _py_juve_length_on(py: dict, target_date: str) -> float:
    df = py["daily"]
    target = pd.Timestamp(target_date).date()
    mask = df["sim_date"] <= target
    if not mask.any():
        return float("nan")
    return float(df.loc[mask, "juve_mean_length"].iloc[-1])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def netlogo() -> pd.DataFrame:
    if not NETLOGO_CSV.exists():
        pytest.skip(
            f"NetLogo reference CSV not found at {NETLOGO_CSV}. "
            f"Expected BehaviorSpace output from netlogo-models/ at "
            f"repo-root-sibling level."
        )
    return _load_netlogo_csv(NETLOGO_CSV)


# ---------------------------------------------------------------------------
# Fast NetLogo-parser sanity checks (no Python simulation)
#
# These run in ~3 seconds and guard against regressions in the reference
# CSV parser, so a rename in the BehaviorSpace column schema or a tweak
# to _netlogo_* helpers fails loudly in CI without needing the 25-min
# end-to-end test.
# ---------------------------------------------------------------------------


def test_netlogo_csv_loads_expected_shape(netlogo) -> None:
    assert len(netlogo) > 3000, (
        f"NetLogo CSV unexpectedly small: {len(netlogo)} rows "
        f"(expected 3,658 sub-daily ticks for 2.5-year run)"
    )
    expected_cols = {
        "CH-S-juve-abund", "CH-S-adult-abund", "CH-S-juve-length",
        "CH-S-outmig-small", "formatted-sim-time",
    }
    missing = expected_cols - set(netlogo.columns)
    assert not missing, f"NetLogo CSV missing columns: {missing}"


def test_netlogo_juvenile_peak_matches_roadmap_value(netlogo) -> None:
    """Sentinel: the cached BehaviorSpace CSV's juvenile peak is 2,151
    on 2013-01-07 (reported by validation-checker agent, verified by
    parse_results.py). If this drifts, the reference data changed."""
    peak, date = _netlogo_juvenile_peak(netlogo)
    assert peak == 2151 and date == "2013-01-07", (
        f"NetLogo juvenile peak drifted from expected (2151 on 2013-01-07) "
        f"to {peak} on {date}. Either the cached CSV was replaced or the "
        f"parser is extracting different columns."
    )


def test_netlogo_outmigrant_total_matches_roadmap_value(netlogo) -> None:
    """Sentinel: cumulative CH-S small outmigrants = 41,146 in the
    cached seed=98 run."""
    total = _netlogo_outmigrant_small_total(netlogo)
    assert total == 41146, (
        f"NetLogo small outmigrant total drifted from 41146 to {total}."
    )


@pytest.fixture(scope="module")
def python_run() -> dict:
    """Expensive — runs the Python example_a end-to-end (~25 min on
    v0.30.2's Numba backend). Scoped to module so all metric tests
    share one model run."""
    return _run_python_example_a()


@pytest.mark.slow
class TestExampleARunVsNetLogo:
    """End-to-end parity check: Python example_a vs cached NetLogo 7.3
    BehaviorSpace table. See module docstring for metric definitions."""

    def test_juvenile_abundance_peak(self, netlogo, python_run) -> None:
        nl_peak, nl_date = _netlogo_juvenile_peak(netlogo)
        py_peak, py_date = _py_juvenile_peak(python_run)
        rtol = 0.30
        assert abs(py_peak - nl_peak) <= nl_peak * rtol, (
            f"CH-S juvenile peak: NetLogo={nl_peak} on {nl_date}, "
            f"Python={py_peak} on {py_date}. "
            f"Difference {abs(py_peak - nl_peak)} exceeds ±{rtol * 100:.0f}% "
            f"({nl_peak * rtol:.0f})."
        )

    def test_adult_abundance_peak(self, netlogo, python_run) -> None:
        nl_peak, nl_date = _netlogo_adult_peak(netlogo)
        py_peak, py_date = _py_adult_peak(python_run)
        atol = 8
        assert abs(py_peak - nl_peak) <= atol, (
            f"CH-S adult peak: NetLogo={nl_peak} on {nl_date}, "
            f"Python={py_peak} on {py_date}. "
            f"Difference {abs(py_peak - nl_peak)} exceeds ±{atol}."
        )

    def test_outmigrant_cumulative(self, netlogo, python_run) -> None:
        nl_total = _netlogo_outmigrant_small_total(netlogo)
        py_total = python_run["total_small_outmigrants"]
        rtol = 0.20
        assert abs(py_total - nl_total) <= nl_total * rtol, (
            f"CH-S small outmigrant total: NetLogo={nl_total}, "
            f"Python={py_total}. Difference {abs(py_total - nl_total)} "
            f"exceeds ±{rtol * 100:.0f}% ({nl_total * rtol:.0f})."
        )

    def test_juvenile_mean_length(self, netlogo, python_run) -> None:
        snap = "2012-09-30"
        nl_len = _netlogo_juve_length_on(netlogo, snap)
        py_len = _py_juve_length_on(python_run, snap)
        rtol = 0.10
        assert not np.isnan(nl_len), "NetLogo juvenile length missing at snapshot"
        assert not np.isnan(py_len), "Python juvenile length missing at snapshot"
        assert abs(py_len - nl_len) <= nl_len * rtol, (
            f"CH-S juvenile mean length @ {snap}: NetLogo={nl_len:.2f}, "
            f"Python={py_len:.2f}. Difference "
            f"{abs(py_len - nl_len):.2f} exceeds ±{rtol * 100:.0f}% "
            f"({nl_len * rtol:.2f})."
        )

    def test_outmigrant_median_date(self, netlogo, python_run) -> None:
        nl_med = _netlogo_outmigrant_median_date(netlogo)
        py_med = _py_outmigrant_median_date(python_run)
        days_tol = 14
        assert not pd.isna(nl_med), "NetLogo produced no outmigrants"
        assert not pd.isna(py_med), "Python produced no outmigrants"
        delta_days = abs((py_med - nl_med).total_seconds()) / 86400
        assert delta_days <= days_tol, (
            f"CH-S outmigrant median date: NetLogo={nl_med.date()}, "
            f"Python={py_med.date()}. Delta {delta_days:.1f} days "
            f"exceeds ±{days_tol} days."
        )
