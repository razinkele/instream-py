"""Tests for Arc L: apply_m74_cull at egg-emergence."""
from pathlib import Path
import numpy as np
from instream.modules.egg_emergence_m74 import apply_m74_cull


def test_m74_cull_scales_by_forcing_fraction(tmp_path: Path):
    """A 0.50 YSFM fraction should cull ~50 % of fry from that year's cohort."""
    csv = tmp_path / "m74.csv"
    csv.write_text(
        "year,river,ysfm_fraction,source\n"
        "2011,Simojoki,0.50,test\n"
    )
    n_fry = 10000
    survivors = apply_m74_cull(
        n_fry=n_fry,
        year=2011,
        river="Simojoki",
        forcing_csv=csv,
        rng=np.random.default_rng(42),
    )
    # Binomial with p_survive=0.50, n=10000 → 2-sigma ≈ ±100
    assert 4800 < survivors < 5200, f"got {survivors}"


def test_m74_cull_zero_when_no_match(tmp_path: Path):
    csv = tmp_path / "m74.csv"
    csv.write_text("year,river,ysfm_fraction,source\n")
    survivors = apply_m74_cull(
        n_fry=10000, year=2011, river="UnknownRiver",
        forcing_csv=csv, rng=np.random.default_rng(42),
    )
    assert survivors == 10000


def test_m74_cull_zero_when_csv_none():
    survivors = apply_m74_cull(
        n_fry=10000, year=2011, river="Simojoki",
        forcing_csv=None, rng=np.random.default_rng(42),
    )
    assert survivors == 10000


def test_m74_cull_respects_real_wgbast_csv():
    """Against the shipped placeholder CSV, 1994 (peak) should cull >60 %."""
    survivors = apply_m74_cull(
        n_fry=10000, year=1994, river="Simojoki",
        forcing_csv="data/wgbast/m74_ysfm_series.csv",
        rng=np.random.default_rng(42),
    )
    # 1994 Simojoki placeholder is 0.82, so p_survive=0.18 → ~1800
    assert survivors < 2500, f"got {survivors}; expected <2500 for peak M74 year"


def test_m74_cull_handles_zero_or_negative_n_fry(tmp_path: Path):
    csv = tmp_path / "m74.csv"
    csv.write_text("year,river,ysfm_fraction,source\n2011,Simojoki,0.5,t\n")
    assert apply_m74_cull(0, 2011, "Simojoki", csv, np.random.default_rng(1)) == 0
    assert apply_m74_cull(-5, 2011, "Simojoki", csv, np.random.default_rng(1)) == -5
