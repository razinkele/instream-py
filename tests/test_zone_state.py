import numpy as np
from instream.state.zone_state import ZoneState


def test_zone_state_creation():
    zs = ZoneState.zeros(4)
    assert zs.temperature.shape == (4,)
    assert np.all(zs.temperature == 0.0)


def test_zone_state_update():
    zs = ZoneState.zeros(3)
    zs.temperature[:] = [8.0, 10.0, 12.0]
    assert zs.temperature[1] == 10.0
