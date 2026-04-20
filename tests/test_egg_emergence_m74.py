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


def test_redd_emergence_respects_m74_forcing(tmp_path: Path):
    """redd_emergence with m74_forcing_csv set reduces fry count vs unforced.

    Runs redd_emergence twice with the same RNG seed — once with 80% YSFM
    forcing, once without — and asserts the forced run produces strictly
    fewer alive fry than the baseline.
    """
    import numpy as np
    from instream.modules.spawning import redd_emergence
    from instream.state.trout_state import TroutState
    from instream.state.redd_state import ReddState

    def make_states(n_eggs: int):
        cap = n_eggs + 100
        rs = ReddState.zeros(capacity=10)
        rs.alive[0] = True
        rs.species_idx[0] = 0
        rs.frac_developed[0] = 1.0
        rs.num_eggs[0] = n_eggs
        rs.reach_idx[0] = 0
        rs.cell_idx[0] = 0
        rs.emerge_days[0] = 9  # last emergence day so 100% of eggs emerge
        ts = TroutState.zeros(capacity=cap)
        return rs, ts

    csv = tmp_path / "m74.csv"
    csv.write_text(
        "year,river,ysfm_fraction,source\n"
        "2011,Simojoki,0.80,test\n"
    )

    rs1, ts1 = make_states(n_eggs=1000)
    redd_emergence(
        rs1, ts1, np.random.default_rng(42),
        3.0, 3.5, 4.0, 0.0077, 3.05,
        species_index=0, superind_max_rep=10,
    )
    baseline_alive = int(ts1.alive.sum())

    rs2, ts2 = make_states(n_eggs=1000)
    redd_emergence(
        rs2, ts2, np.random.default_rng(42),
        3.0, 3.5, 4.0, 0.0077, 3.05,
        species_index=0, superind_max_rep=10,
        m74_forcing_csv=csv,
        current_year=2011,
        river_name_by_reach_idx=["Simojoki"],
    )
    forced_alive = int(ts2.alive.sum())

    assert forced_alive < baseline_alive, (
        f"M74 forcing should reduce surviving fry; "
        f"baseline={baseline_alive}, forced={forced_alive}"
    )
