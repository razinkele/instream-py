"""Arc N: post-smolt survival time-varying forcing tests."""
from __future__ import annotations
from pathlib import Path
import numpy as np

from instream.marine.survival_forcing import (
    load_post_smolt_forcing,
    annual_survival_for_year,
    daily_hazard_multiplier,
)


def test_load_post_smolt_forcing(tmp_path: Path):
    csv = tmp_path / "ps.csv"
    csv.write_text(
        "year,stock_unit,survival_pct,source\n"
        "2020,sal.27.22-31,0.06,t\n"
        "2020,sal.27.32,0.04,t\n"
    )
    s = load_post_smolt_forcing(csv)
    assert s[(2020, "sal.27.22-31")] == 0.06
    assert s[(2020, "sal.27.32")] == 0.04


def test_annual_survival_lookup(tmp_path: Path):
    csv = tmp_path / "ps.csv"
    csv.write_text(
        "year,stock_unit,survival_pct,source\n"
        "2020,sal.27.22-31,0.06,t\n"
    )
    s = load_post_smolt_forcing(csv)
    assert annual_survival_for_year(s, 2020, "sal.27.22-31") == 0.06
    assert annual_survival_for_year(s, 1999, "sal.27.22-31") is None


def test_daily_hazard_multiplier_inverts_survival():
    """6% annual → apply daily hazard for 365 days → recover 6%."""
    h = daily_hazard_multiplier(annual_survival=0.06, days_per_year=365)
    # (1 - h)^365 = 0.06
    recovered = (1.0 - h) ** 365
    assert abs(recovered - 0.06) < 1e-10
    # Extremes
    assert daily_hazard_multiplier(1.0) == 0.0
    assert daily_hazard_multiplier(0.0) == 1.0


def test_loader_handles_commented_csv():
    """Ship CSV uses # comment lines; loader must skip them."""
    s = load_post_smolt_forcing("data/wgbast/post_smolt_survival_baltic.csv")
    assert (2021, "sal.27.22-31") in s
    assert s[(2021, "sal.27.22-31")] == 0.06  # WGBAST 2021 median


def _minimal_marine_config(**overrides):
    """Build a minimal MarineConfig for hazard-only tests."""
    from instream.marine.config import MarineConfig, ZoneConfig
    base = dict(
        zones=[ZoneConfig(name="Estuary", area_km2=80)],
        marine_mort_base=0.001,
    )
    base.update(overrides)
    return MarineConfig(**base)


def test_marine_survival_respects_post_smolt_forcing(tmp_path):
    """Setting post_smolt_survival_forcing_csv overrides background_hazard
    for fish in the post-smolt window (days_since_ocean_entry < 365)."""
    from instream.marine.survival import marine_survival

    csv = tmp_path / "ps.csv"
    csv.write_text(
        "year,stock_unit,survival_pct,source\n"
        "2020,sal.27.22-31,0.10,t\n"   # 10% annual → high daily hazard
    )
    cfg = _minimal_marine_config(
        post_smolt_survival_forcing_csv=str(csv),
        stock_unit="sal.27.22-31",
    )
    # 4 fish: 2 in post-smolt window (days 30, 100), 2 adult (400, 500)
    length = np.array([20.0, 20.0, 20.0, 20.0])
    zone_idx = np.array([0, 0, 0, 0])
    temperature = np.array([10.0, 10.0, 10.0, 10.0])
    days_since = np.array([30, 100, 400, 500])
    corm_zones = np.array([], dtype=np.int64)

    survival = marine_survival(
        length, zone_idx, temperature, days_since, corm_zones, cfg,
        current_year=2020,
    )
    # Post-smolt fish (0, 1): higher hazard under 10% forcing → lower survival
    # Adult fish (2, 3): use marine_mort_base=0.001 → near-1.0 survival
    assert survival[0] < survival[2] - 1e-4
    assert survival[1] < survival[3] - 1e-4


def test_marine_survival_no_forcing_when_kwarg_missing():
    """Default call (no current_year) preserves existing behavior."""
    from instream.marine.survival import marine_survival

    cfg = _minimal_marine_config()
    length = np.array([20.0, 20.0])
    zone_idx = np.array([0, 0])
    temperature = np.array([10.0, 10.0])
    days_since = np.array([30, 400])
    corm_zones = np.array([], dtype=np.int64)

    s = marine_survival(
        length, zone_idx, temperature, days_since, corm_zones, cfg,
    )
    # No hazard activation — both fish should have near-1.0 daily survival
    assert np.all(s > 0.99)
