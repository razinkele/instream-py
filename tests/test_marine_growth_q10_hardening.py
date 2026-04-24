"""Phase 2 Task 2.8: respiration Q10 must be anchored to a configurable
reference temperature (default 15 degC), not to cmax_topt."""


def test_marine_growth_q10_anchored_to_resp_ref_temp_not_cmax_topt():
    """Behavioral check: vary cmax_topt while holding resp_ref_temp fixed.
    Respiration uses Q10 anchored on resp_ref_temp; the Q10-temperature
    dependence must NOT inherit the cmax_topt shift — true iff Q10 is
    anchored on resp_ref_temp (Phase-2 Task 2.8 fix).

    Strategy: compute growth at T=25 (well above both topts) for two
    cmax_topt values and two resp_Q10 strengths. If Q10 is anchored on
    resp_ref_temp (correct), the respiration term is the SAME for both
    cmax_topts, so the `delta(cmax_topt)` at strong-Q10 must equal the
    `delta(cmax_topt)` at weak-Q10. If Q10 were anchored on cmax_topt
    (the bug), the deltas would differ.
    """
    import numpy as np
    from salmopy.marine.growth import marine_growth

    common = dict(
        weights=np.array([500.0]),
        prey_indices=np.array([0.5]),
        conditions=np.array([1.0]),
        cmax_A=0.5, cmax_B=-0.3, cmax_tmax=25.0,
        resp_A=0.01, resp_B=-0.2,
        growth_efficiency=0.6,
        resp_ref_temp=15.0,
    )

    def g(temp, cmax_topt, resp_q10):
        return float(marine_growth(
            temperatures=np.array([temp]),
            cmax_topt=cmax_topt,
            resp_Q10=resp_q10,
            **common,
        )[0])

    # Consumption-only sanity: at T=resp_ref_temp=15 the respiration Q10
    # multiplier = 1, so growth differs between cmax_topts ONLY through
    # consumption response. Must be non-trivial.
    delta_cons_only = g(15.0, 15.0, 1.0) - g(15.0, 12.0, 1.0)
    assert abs(delta_cons_only) > 1e-6, (
        "consumption response should differ between cmax_topt=15 and 12; "
        "fixture is too insensitive to detect the regression"
    )

    # Anchor invariance: at T=25, the delta(cmax_topt) must be the SAME
    # at resp_Q10=4.0 and at resp_Q10=1.0 (anchor is shared, so
    # respiration contributes identically to both cmax_topt values).
    delta_at_strong_q10 = g(25.0, 15.0, 4.0) - g(25.0, 12.0, 4.0)
    delta_at_weak_q10 = g(25.0, 15.0, 1.0) - g(25.0, 12.0, 1.0)

    assert abs(delta_at_strong_q10 - delta_at_weak_q10) < 1e-9, (
        f"Respiration leaks cmax_topt dependence: delta(strong-Q10) "
        f"= {delta_at_strong_q10}, delta(weak-Q10) = {delta_at_weak_q10}. "
        f"If Q10 were anchored on cmax_topt instead of resp_ref_temp, "
        f"these two deltas would differ."
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
