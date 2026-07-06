"""Verify v0.55 calibration values applied correctly to example_tornionjoki.yaml."""
import yaml
from pathlib import Path

cfg_path = Path(__file__).resolve().parents[1] / "configs" / "example_tornionjoki.yaml"
with open(cfg_path) as f:
    cfg = yaml.safe_load(f)

print("=== drift_conc / drift_regen_distance per reach ===")
expected = {
    "Mouth": (4.0e-08, 300),
    "Lower": (2.4e-08, 400),
    "Middle": (3.0e-08, 350),
    "Upper": (1.6e-08, 500),
}
for name, (exp_conc, exp_regen) in expected.items():
    r = cfg["reaches"][name]
    conc = r["drift_conc"]
    regen = r["drift_regen_distance"]
    ok = abs(conc - exp_conc) < 1e-12 and regen == exp_regen
    flag = "OK" if ok else "FAIL"
    print(f"  {name:8s} drift_conc={conc:.2e} (expected {exp_conc:.2e})  "
          f"regen={regen} (expected {exp_regen})  [{flag}]")

expected_capacity = 1500000
actual_capacity = cfg['performance']['trout_capacity']
cap_ok = "OK" if actual_capacity == expected_capacity else "FAIL"
print(f"\ntrout_capacity = {actual_capacity} (expected {expected_capacity})  [{cap_ok}]")

expected_cmax_a = 0.40
actual_cmax_a = cfg['species']['BalticAtlanticSalmon']['cmax_A']
cmax_ok = "OK" if abs(actual_cmax_a - expected_cmax_a) < 1e-9 else "FAIL"
print(f"cmax_A = {actual_cmax_a} (expected {expected_cmax_a})  [{cmax_ok}]")
