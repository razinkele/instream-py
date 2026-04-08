import numpy as np
from instream.modules.marine_growth import marine_growth_rate, _temp_dependence

def test_temp_dependence_peaks_at_opt():
    temps = np.array([5.0, 12.0, 22.0])
    frac = _temp_dependence(temps, temp_opt=12.0, temp_max=24.0)
    assert frac[1] > frac[0]
    assert frac[1] > frac[2]
    assert abs(frac[1] - 1.0) < 0.01  # peak = 1.0

def test_temp_dependence_zero_at_freezing():
    frac = _temp_dependence(np.array([0.5]), temp_opt=12.0, temp_max=24.0)
    assert frac[0] == 0.0  # below temp_min=1.0

def test_temp_dependence_zero_at_max():
    frac = _temp_dependence(np.array([24.0]), temp_opt=12.0, temp_max=24.0)
    assert frac[0] == 0.0

def test_marine_growth_increases_weight():
    lengths = np.array([30.0, 50.0, 70.0])
    weights = np.array([300.0, 1500.0, 4000.0])
    temps = np.array([10.0, 10.0, 10.0])
    prey = np.array([0.8, 0.8, 0.8])
    cond = np.array([1.0, 1.0, 1.0])
    growth = marine_growth_rate(
        lengths, weights, temps, prey, cond,
        cmax_A=0.303, cmax_B=-0.275, growth_efficiency=0.50,
        resp_A=0.03, resp_B=-0.25, temp_opt=12.0, temp_max=24.0)
    assert growth.shape == (3,)
    assert np.all(growth > 0)

def test_marine_growth_zero_prey():
    growth = marine_growth_rate(
        np.array([50.0]), np.array([1500.0]), np.array([10.0]),
        np.array([0.0]), np.array([1.0]),
        cmax_A=0.303, cmax_B=-0.275, growth_efficiency=0.50,
        resp_A=0.03, resp_B=-0.25, temp_opt=12.0, temp_max=24.0)
    assert np.all(growth < 0)

def test_marine_growth_temperature_optimum():
    w = np.array([1500.0, 1500.0, 1500.0])
    l = np.array([50.0, 50.0, 50.0])
    temps = np.array([5.0, 12.0, 22.0])
    prey = np.array([0.8, 0.8, 0.8])
    cond = np.array([1.0, 1.0, 1.0])
    growth = marine_growth_rate(
        l, w, temps, prey, cond,
        cmax_A=0.303, cmax_B=-0.275, growth_efficiency=0.50,
        resp_A=0.03, resp_B=-0.25, temp_opt=12.0, temp_max=24.0)
    assert growth[1] > growth[0]
    assert growth[1] > growth[2]

def test_marine_growth_zero_at_freezing():
    growth = marine_growth_rate(
        np.array([50.0]), np.array([1500.0]), np.array([0.5]),
        np.array([0.8]), np.array([1.0]),
        cmax_A=0.303, cmax_B=-0.275, growth_efficiency=0.50,
        resp_A=0.03, resp_B=-0.25, temp_opt=12.0, temp_max=24.0)
    assert growth[0] <= 0
