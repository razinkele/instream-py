"""v0.43.5 Task A2: SpeciesConfig must reject probability values outside
[0,1] and negative length/distance values."""
import pytest
from pydantic import ValidationError

from salmopy.io.config import SpeciesConfig


PROB_FIELDS = [
    "spawn_prob",
    "spawn_egg_viability",
    "mort_strand_survival_when_dry",
]


@pytest.mark.parametrize("field", PROB_FIELDS)
def test_probability_field_rejects_above_one(field):
    with pytest.raises(ValidationError):
        SpeciesConfig(**{field: 1.5})


@pytest.mark.parametrize("field", PROB_FIELDS)
def test_probability_field_rejects_negative(field):
    with pytest.raises(ValidationError):
        SpeciesConfig(**{field: -0.1})


@pytest.mark.parametrize("field", PROB_FIELDS)
def test_probability_field_accepts_boundary(field):
    SpeciesConfig(**{field: 0.0})
    SpeciesConfig(**{field: 1.0})


# NOTE: length-field validators were considered but dropped — several
# length fields use negative sentinels like -9.0 to mean "no minimum".
# Imposing >=0 broke the shipped example_a.yaml config. Probability-only
# validation is the v0.43.5 scope; a separate pass would need to audit
# each length field for its true domain.
