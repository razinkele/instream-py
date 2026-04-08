import numpy as np
from instream.modules.marine_survival import (
    seal_predation, cormorant_predation, background_mortality,
    temperature_mortality, m74_mortality, post_smolt_vulnerability,
    combined_marine_survival,
)


def test_seal_predation_increases_with_size():
    lengths = np.array([30.0, 50.0, 70.0, 90.0])
    surv = seal_predation(lengths, L1=40.0, L9=80.0)
    assert np.all((surv >= 0) & (surv <= 1))
    assert surv[0] > surv[-1]


def test_seal_predation_realistic_rates():
    surv = seal_predation(np.array([80.0]), L1=40.0, L9=80.0)
    assert surv[0] > 0.97  # max 2% daily mortality


def test_cormorant_targets_small_fish():
    lengths = np.array([12.0, 20.0, 35.0, 60.0])
    zones = np.array([0, 0, 0, 0])
    surv = cormorant_predation(lengths, zones, L1=15.0, L9=40.0,
                                active_zones=[0, 1], max_daily_rate=0.03)
    assert surv[0] < surv[-1]
    assert surv[0] > 0.95  # realistic daily rate


def test_cormorant_inactive_offshore():
    lengths = np.array([12.0])
    zones = np.array([3])
    surv = cormorant_predation(lengths, zones, L1=15.0, L9=40.0,
                                active_zones=[0, 1])
    assert surv[0] == 1.0


def test_m74_zero_means_no_mortality():
    rng = np.random.default_rng(42)
    surv = m74_mortality(100, prob=0.0, rng=rng)
    assert np.all(surv == 1.0)


def test_vulnerability_amplifies_mortality():
    base_survival = np.array([0.95])
    vuln_new = post_smolt_vulnerability(np.array([1]), window=60)
    vuln_old = post_smolt_vulnerability(np.array([90]), window=60)
    assert vuln_new > vuln_old
    surv_new = np.power(base_survival, vuln_new)
    surv_old = np.power(base_survival, vuln_old)
    assert surv_new[0] < surv_old[0]  # new smolts worse off


def test_combined_survival_in_range():
    rng = np.random.default_rng(42)
    surv = combined_marine_survival(
        np.array([50.0]), np.array([1500.0]), np.array([1.0]),
        np.array([10.0]), np.array([0.3]), np.array([0]), np.array([5]),
        rng, seal_L1=40.0, seal_L9=80.0,
        cormorant_L1=15.0, cormorant_L9=40.0, cormorant_zones=[0, 1],
        base_mort=0.001, temp_threshold=20.0, m74_prob=0.0,
        post_smolt_window=60)
    assert 0 < surv[0] < 1
