"""Phase 2 Task 2.1: MarineBackend Protocol signature must match its
numpy implementation so typed callers bind arguments correctly."""
import inspect

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
