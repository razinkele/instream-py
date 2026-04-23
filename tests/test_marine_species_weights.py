"""Regression for model_init.py:516-528.

The try/except:pass around species_weight_A / species_weight_B propagation
silently disabled Arc P seal predation on any config error. After the fix,
(a) the happy path still populates both attributes, and (b) the try/except
wrapper is structurally gone so future refactors can't hide errors.
"""
import inspect
import numpy as np
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_marine_domain_has_species_weights_populated():
    """Happy path: a well-formed Baltic config must end init with
    species_weight_A and species_weight_B populated on the marine domain."""
    from instream.model import InSTREAMModel
    model = InSTREAMModel(
        config_path=str(CONFIGS_DIR / "example_baltic.yaml"),
        data_dir=str(FIXTURES_DIR / "example_baltic"),
    )
    md = getattr(model, "_marine_domain", None)
    if md is None:
        pytest.skip("config has no marine domain")
    assert hasattr(md, "species_weight_A"), (
        "species_weight_A missing on marine domain — Arc P seal predation "
        "would silently return zero mortality"
    )
    assert hasattr(md, "species_weight_B")
    assert md.species_weight_A is not None
    assert len(md.species_weight_A) == len(model.species_order)
    assert (np.asarray(md.species_weight_A) > 0).all()


def test_silent_except_wrapper_removed():
    """Structural regression: the try/except:pass around the species_weight_A
    assignment must be gone. Future refactors shouldn't be able to hide
    Arc P seal-predation failures."""
    from instream import model_init as mi
    src = inspect.getsource(mi)
    needle = "self._marine_domain.species_weight_A = sp_weight_A"
    assert needle in src, (
        f"Expected assignment `{needle}` not found in model_init.py — "
        "the plan's target line has moved or been renamed."
    )
    idx = src.index(needle)
    window = src[idx:idx + 400]
    assert "except Exception" not in window, (
        "try/except:pass still wraps the species_weight_A assignment block "
        "at model_init.py:516-528. Silent Arc P seal-predation failure "
        "would persist."
    )
