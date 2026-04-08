import numpy as np
from instream.modules.marine_migration import check_maturation, seasonal_zone_movement


def test_maturation_respects_min_sw():
    rng = np.random.default_rng(42)
    mature = check_maturation(
        np.array([70.0, 70.0]), np.array([1.0, 1.0]),
        np.array([0, 1]), rng,
        min_sea_winters=1, prob_by_sw={1: 0.99}, min_length=55.0, min_condition=0.8)
    assert not mature[0]
    assert mature[1]


def test_maturation_min_length():
    rng = np.random.default_rng(42)
    mature = check_maturation(
        np.array([50.0]), np.array([1.0]), np.array([2]), rng,
        min_sea_winters=1, prob_by_sw={2: 1.0}, min_length=55.0, min_condition=0.8)
    assert not mature[0]


def test_zone_movement():
    zones = np.array([0, 1, 2])
    days = np.array([35, 60, 200])
    zone_graph = {0: [1], 1: [0, 2], 2: [1, 3], 3: [2]}
    new = seasonal_zone_movement(zones, days, 7,
                                  zone_graph=zone_graph, max_residence={0: 30, 1: 90})
    assert new[0] == 1
    assert new[1] == 1
