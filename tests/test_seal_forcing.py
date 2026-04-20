"""Arc P: HELCOM grey-seal abundance forcing tests."""
from __future__ import annotations
from pathlib import Path
import numpy as np

from instream.marine.seal_forcing import (
    load_seal_abundance,
    abundance_for_year,
    seal_hazard_multiplier,
)


def test_load_seal_abundance(tmp_path: Path):
    csv = tmp_path / "seal.csv"
    csv.write_text(
        "year,sub_basin,population_estimate,method\n"
        "2003,main_basin,15600,aerial\n"
        "2015,main_basin,32000,aerial\n"
    )
    s = load_seal_abundance(csv)
    assert s[(2003, "main_basin")] == 15600
    assert s[(2015, "main_basin")] == 32000


def test_abundance_for_year_returns_none_when_unknown(tmp_path: Path):
    csv = tmp_path / "seal.csv"
    csv.write_text(
        "year,sub_basin,population_estimate,method\n"
        "2003,main_basin,15600,aerial\n"
    )
    s = load_seal_abundance(csv)
    assert abundance_for_year(s, 2003, "main_basin") == 15600
    assert abundance_for_year(s, 1999, "main_basin") is None
    assert abundance_for_year(s, 2003, "unknown") is None


def test_seal_hazard_multiplier_saturates():
    """Holling Type II with default k_half=2.0, anchored at 1.0."""
    # Anchor: exactly 1.0 at reference
    assert abs(seal_hazard_multiplier(30000, 30000) - 1.0) < 1e-9
    # r=2: exact value is 1.5
    m_2x = seal_hazard_multiplier(60000, 30000)
    assert abs(m_2x - 1.5) < 0.01
    # r=10: exact value is 2.5
    m_10x = seal_hazard_multiplier(300000, 30000)
    assert abs(m_10x - 2.5) < 0.05
    # r → ∞: asymptote at k+1 = 3.0
    m_inf = seal_hazard_multiplier(1e9, 30000)
    assert abs(m_inf - 3.0) < 0.01
    # r = 0: multiplier is 0
    assert seal_hazard_multiplier(0, 30000) == 0.0


def test_loader_handles_commented_csv():
    """Shipped CSV uses # comment lines; loader must skip them."""
    s = load_seal_abundance("data/helcom/grey_seal_abundance_baltic.csv")
    assert (2014, "main_basin") in s
    assert s[(2014, "main_basin")] == 32019  # Lai 2021 HELCOM figure


def test_seal_hazard_scales_with_year(tmp_path):
    """Arc P integration: seal_hazard scales via HELCOM abundance."""
    from instream.marine.config import MarineConfig, ZoneConfig
    from instream.marine.survival import seal_hazard

    csv = tmp_path / "seal.csv"
    csv.write_text(
        "year,sub_basin,population_estimate,method\n"
        "1988,main_basin,2800,t\n"
        "2021,main_basin,40000,t\n"
    )
    cfg = MarineConfig(
        zones=[ZoneConfig(name="Estuary", area_km2=80)],
        seal_abundance_csv=str(csv),
        seal_reference_abundance=30000.0,
        seal_sub_basin="main_basin",
        seal_saturation_k_half=2.0,
    )
    lengths = np.array([50.0, 60.0, 70.0])
    h_1988 = seal_hazard(lengths, cfg, current_year=1988)
    h_2021 = seal_hazard(lengths, cfg, current_year=2021)
    # Holling II with k=2: m(2800/30000=0.093) ≈ 0.15; m(40000/30000=1.33) ≈ 1.22
    # Ratio ≈ 1.22 / 0.15 ≈ 8× (bounded by saturation vs. linear 14.3×)
    ratio = h_2021[0] / h_1988[0]
    assert 4.0 < ratio < 10.0, f"got ratio {ratio}"
    # Baseline unchanged when current_year=None
    h_default = seal_hazard(lengths, cfg, current_year=None)
    h_legacy = seal_hazard(lengths, cfg)  # same thing, no kwarg
    assert np.allclose(h_default, h_legacy)
