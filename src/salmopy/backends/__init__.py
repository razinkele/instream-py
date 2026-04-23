"""Compute backend factory."""

from salmopy.backends._interface import ComputeBackend


def get_backend(name: str) -> ComputeBackend:
    """Get a compute backend by name."""
    if name == "numpy":
        from salmopy.backends.numpy_backend import NumpyBackend

        return NumpyBackend()
    elif name == "numba":
        from salmopy.backends.numba_backend import NumbaBackend

        return NumbaBackend()
    elif name == "jax":
        try:
            from salmopy.backends.jax_backend import JaxBackend

            return JaxBackend()
        except ImportError:
            raise ImportError(
                "JAX backend requires jax and jaxlib. Install with: pip install instream[jax]"
            )
    else:
        raise ValueError(f"Unknown backend: {name!r}. Choose from: numpy, numba, jax")
