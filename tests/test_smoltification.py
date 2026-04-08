import numpy as np
from instream.modules.smoltification import update_smolt_readiness, check_smolt_trigger


def test_readiness_accumulates():
    readiness = np.array([0.0, 0.5, 0.9])
    lengths = np.array([15.0, 14.0, 13.0])
    new = update_smolt_readiness(readiness, lengths, 10.0, 15.0,
        min_length=12.0, temp_min=6.0, temp_max=16.0,
        photoperiod_threshold=14.0, rate=0.05)
    assert np.all(new > readiness)
    assert np.all(new <= 1.0)


def test_readiness_no_accum_cold():
    readiness = np.array([0.3])
    new = update_smolt_readiness(readiness, np.array([15.0]), 3.0, 15.0,
        min_length=12.0, temp_min=6.0, temp_max=16.0,
        photoperiod_threshold=14.0)
    assert new[0] == 0.3


def test_trigger_inside_window():
    readiness = np.array([0.5, 1.0])
    triggers = check_smolt_trigger(readiness, current_month=5,
                                    window_start_month=4, window_end_month=6)
    assert not triggers[0]
    assert triggers[1]


def test_trigger_outside_window():
    readiness = np.array([1.0])
    triggers = check_smolt_trigger(readiness, current_month=1,
                                    window_start_month=4, window_end_month=6)
    assert not triggers[0]
