"""Tests for Arc L: WGBAST M74 YSFM forcing loader."""
from pathlib import Path
from salmopy.io.m74_forcing import load_m74_forcing, ysfm_for_year_river


def test_load_m74_forcing(tmp_path: Path):
    csv = tmp_path / "m74.csv"
    csv.write_text(
        "year,river,ysfm_fraction,source\n"
        "2010,Simojoki,0.05,Vuorinen2021\n"
        "2011,Simojoki,0.12,Vuorinen2021\n"
        "2011,Tornionjoki,0.08,Vuorinen2021\n"
    )
    s = load_m74_forcing(csv)
    assert s[(2010, "Simojoki")] == 0.05
    assert s[(2011, "Simojoki")] == 0.12
    assert s[(2011, "Tornionjoki")] == 0.08


def test_ysfm_lookup_returns_zero_when_unknown(tmp_path: Path):
    csv = tmp_path / "m74.csv"
    csv.write_text(
        "year,river,ysfm_fraction,source\n"
        "2011,Simojoki,0.10,Vuorinen2021\n"
        "2012,Simojoki,0.20,Vuorinen2021\n"
    )
    s = load_m74_forcing(csv)
    assert ysfm_for_year_river(s, 2011, "Simojoki") == 0.10
    assert ysfm_for_year_river(s, 2099, "Simojoki") == 0.0
    assert ysfm_for_year_river(s, 2011, "UnknownRiver") == 0.0


def test_loader_handles_commented_csv():
    """The shipped CSV at data/wgbast/m74_ysfm_series.csv has # comment lines."""
    s = load_m74_forcing("data/wgbast/m74_ysfm_series.csv")
    # Placeholder values cover 1985-2024 for Simojoki and Tornionjoki
    assert (1994, "Simojoki") in s
    assert s[(1994, "Simojoki")] > 0.5  # 1994 was peak M74 year
    assert (2024, "Tornionjoki") in s
