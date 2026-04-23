"""Phase 2 Tasks 2.1 + 2.2: backend Protocol hardening + JAX multi-species guard."""
import inspect
import pytest

from salmopy.backends._interface import MarineBackend
from salmopy.backends.numpy_backend.marine import NumpyMarineBackend


def test_marine_survival_protocol_matches_implementation():
    proto_sig = inspect.signature(MarineBackend.marine_survival)
    impl_sig = inspect.signature(NumpyMarineBackend.marine_survival)
    proto_params = list(proto_sig.parameters)
    impl_params = list(impl_sig.parameters)
    assert proto_params == impl_params, (
        f"MarineBackend.marine_survival signature drifts from NumpyMarineBackend:\n"
        f"  Protocol: {proto_params}\n  Impl:     {impl_params}\n"
        f"Runtime-checkable Protocols allow isinstance() to pass despite "
        f"signature mismatches; callers get silent wrong-kwarg binding."
    )


def test_jax_growth_rate_raises_on_multi_species():
    """JAX backend's growth_rate hardcodes cmax_temp_table_xs[0]. Until
    per-species dispatch is implemented, the backend must raise rather
    than silently use species 0's table for all fish."""
    try:
        import jax  # noqa: F401
    except ImportError:
        pytest.skip("JAX not installed")

    import numpy as np
    from salmopy.backends.jax_backend import JaxBackend

    backend = JaxBackend()
    params = {
        "prev_consumptions": np.zeros(2),
        "step_length": 1.0,
        "cmax_As": np.array([0.628, 0.5]),
        "cmax_Bs": np.array([0.7, 0.6]),
        "cmax_temp_table_xs": [np.array([0, 5, 10, 15, 20]), np.array([0, 6, 12, 18])],
        "cmax_temp_table_ys": [np.array([0, 0.3, 0.8, 1.0, 0.6]), np.array([0, 0.4, 0.9, 0.5])],
        "react_dist_As": np.array([1.0, 1.0]), "react_dist_Bs": np.array([0.5, 0.5]),
        "turbid_thresholds": np.array([50.0, 50.0]), "turbid_mins": np.array([0.5, 0.5]),
        "turbid_exps": np.array([0.1, 0.1]),
        "light_thresholds": np.array([1.0, 1.0]), "light_mins": np.array([0.5, 0.5]),
        "light_exps": np.array([0.1, 0.1]),
    }
    with pytest.raises(NotImplementedError, match="multi-species"):
        backend.growth_rate(
            lengths=np.array([5.0, 10.0]),
            weights=np.array([1.0, 10.0]),
            temperatures=np.array([12.0, 12.0]),
            velocities=np.array([0.3, 0.3]),
            depths=np.array([0.5, 0.5]),
            **params,
        )
