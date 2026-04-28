"""v0.46: enumerate per-reach config differences between Baltic and Tornionjoki.

Loads both YAML configs, walks every (reach, key) pair, prints the
ones that differ. Highlights species-level params + reach-level
params that could explain the FRY collapse.

Usage:
    micromamba run -n shiny python scripts/_compare_baltic_vs_tornionjoki.py
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _walk_dict(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_walk_dict(v, key + "."))
        else:
            out[key] = v
    return out


def main():
    a = yaml.safe_load((ROOT / "configs/example_baltic.yaml").read_text(encoding="utf-8"))
    b = yaml.safe_load((ROOT / "configs/example_tornionjoki.yaml").read_text(encoding="utf-8"))

    flat_a = _walk_dict(a)
    flat_b = _walk_dict(b)
    keys = sorted(set(flat_a) | set(flat_b))

    print(f"{'key':<70} {'baltic':>15} {'tornionjoki':>15}")
    print("-" * 102)
    diffs = 0
    for k in keys:
        va = flat_a.get(k, "<missing>")
        vb = flat_b.get(k, "<missing>")
        if va != vb:
            diffs += 1
            print(f"{k:<70} {str(va)[:15]:>15} {str(vb)[:15]:>15}")
    print()
    print(f"Total differing keys: {diffs}")


if __name__ == "__main__":
    main()
