"""Phase 2 Task 2.8: respiration Q10 must be anchored to a configurable
reference temperature (default 15 degC), not to cmax_topt."""
import inspect


def test_marine_growth_uses_resp_ref_temp():
    """Q10 exponent must be (t - resp_ref_temp) / 10, not (t - cmax_topt) / 10."""
    from salmopy.marine.growth import marine_growth
    src = inspect.getsource(marine_growth)
    assert "resp_ref_temp" in src, (
        "marine_growth must accept a resp_ref_temp parameter and use it "
        "as the Q10 anchor. Current code anchors on cmax_topt."
    )
    assert "(t - resp_ref_temp)" in src, (
        "Q10 exponent must be computed as (t - resp_ref_temp) / 10.0, "
        "not (t - cmax_topt) / 10.0."
    )


def test_species_params_has_resp_ref_temp():
    """SpeciesParams must expose resp_ref_temp with default 15.0."""
    from salmopy.state.params import SpeciesParams
    p = SpeciesParams(name="test")
    assert hasattr(p, "resp_ref_temp")
    assert p.resp_ref_temp == 15.0


def test_params_from_config_propagates_resp_ref_temp():
    """Round-trip: Pydantic config -> SpeciesParams."""
    import pytest
    from pathlib import Path
    from salmopy.io.config import load_config, params_from_config
    CONFIGS_DIR = Path(__file__).parent.parent / "configs"
    cfg = load_config(CONFIGS_DIR / "example_a.yaml")
    sp_name = next(iter(cfg.species))
    cfg.species[sp_name].resp_ref_temp = 12.5
    species_params, _ = params_from_config(cfg)
    assert species_params[sp_name].resp_ref_temp == pytest.approx(12.5)
