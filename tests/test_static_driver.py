import numpy as np
from datetime import date
from instream.io.env_drivers.static_driver import StaticDriver
from instream.state.zone_state import ZoneState


def test_static_driver_interpolates():
    config = {"estuary": {"temperature": {1: 2.0, 7: 18.0}}}
    driver = StaticDriver(config, ["estuary"], {"estuary": 50.0})
    zs = driver.get_zone_conditions(date(2025, 4, 1))
    assert isinstance(zs, ZoneState)
    assert 2.0 < zs.temperature[0] < 18.0
    assert zs.area_km2[0] == 50.0


def test_static_driver_multiple_zones():
    config = {
        "estuary": {"temperature": {1: 2.0, 7: 18.0}},
        "coastal": {"temperature": {1: 3.0, 7: 15.0}},
    }
    driver = StaticDriver(config, ["estuary", "coastal"],
                          {"estuary": 50, "coastal": 5000})
    zs = driver.get_zone_conditions(date(2025, 1, 15))
    assert zs.temperature.shape == (2,)
