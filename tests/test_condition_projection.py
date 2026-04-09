from instream.modules.survival import mean_condition_survival


def test_perfect_condition_no_decline():
    result = mean_condition_survival(1.0, 0.01, 10.0, 0.8, 60)
    assert abs(result - 1.0) < 1e-6


def test_steady_condition():
    s = mean_condition_survival(0.8, 0.0, 10.0, 0.8, 60)
    expected = 2 * 0.8 + 2 * 0.8 - 2 * 0.8 * 0.8 - 1  # = 0.92
    assert abs(s - expected) < 0.01


def test_declining_condition_reduces_survival():
    s_declining = mean_condition_survival(0.8, -0.5, 10.0, 0.8, 60)
    s_steady = mean_condition_survival(0.8, 0.0, 10.0, 0.8, 60)
    assert s_declining < s_steady


def test_improving_condition():
    s_improving = mean_condition_survival(0.7, 0.5, 10.0, 0.8, 60)
    s_steady = mean_condition_survival(0.7, 0.0, 10.0, 0.8, 60)
    assert s_improving > s_steady


def test_starving_fish_very_low():
    s = mean_condition_survival(0.6, -2.0, 10.0, 0.8, 60)
    assert s < 0.7


def test_bounded_0_1():
    for dk in [-5.0, -1.0, 0.0, 1.0, 5.0]:
        for k in [0.1, 0.5, 0.8, 1.0]:
            s = mean_condition_survival(k, dk, 10.0, 0.8, 60)
            assert 0.0 <= s <= 1.0, f"s={s} for K={k}, dk={dk}"
