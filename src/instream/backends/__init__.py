"""Compute backend factory."""
from instream.backends._interface import ComputeBackend


def get_backend(name: str) -> ComputeBackend:
    """Get a compute backend by name."""
    if name == "numpy":
        from instream.backends.numpy_backend import NumpyBackend
        return NumpyBackend()
    elif name == "numba":
        raise NotImplementedError("Numba backend not yet implemented")
    elif name == "jax":
        raise NotImplementedError("JAX backend not yet implemented")
    else:
        raise ValueError(f"Unknown backend: {name!r}. Choose from: numpy, numba, jax")
