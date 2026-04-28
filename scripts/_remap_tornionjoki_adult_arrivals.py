"""v0.52.0 fix: remap TornionjokiExample-AdultArrivals.csv from Baltic
reach names to actual Tornionjoki reaches (Mouth/Lower/Middle/Upper).

The fixture was scaffolded as a Nemunas-template copy in v0.45.0 and
the AdultArrivals CSV was never updated — all 199 records target
Baltic-only reaches (Atmata/Gilija/Leite/Minija/Nemunas/Skirvyte/Sysa)
which don't exist in Tornionjoki. Result: returning adults are loaded
with reach_idx=-1 and never reach spawning cells, so init_cum=0 redds
across a 3-year sim run.

Mapping by spawning weight (Tornionjoki pspc_smolts_per_year):
- Lower (pspc=660,000)   ← Atmata, Sysa, Gilija
- Middle (pspc=990,000)  ← Nemunas, Leite
- Upper (pspc=550,000)   ← Minija, Skirvyte

Per-year totals are preserved (we just redistribute counts across the
3 valid reaches in proportion to original Baltic-reach assignments).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tests/fixtures/example_tornionjoki/TornionjokiExample-AdultArrivals.csv"

REACH_MAP = {
    "Nemunas": "Middle",
    "Leite": "Middle",
    "Atmata": "Lower",
    "Sysa": "Lower",
    "Gilija": "Lower",
    "Minija": "Upper",
    "Skirvyte": "Upper",
}


def main() -> int:
    if not SRC.exists():
        print(f"missing: {SRC}")
        return 1

    lines = SRC.read_text(encoding="utf-8").splitlines()
    out_lines = []
    n_remapped = 0
    n_already_target = 0
    n_unrecognized = 0
    target_set = {"Mouth", "Lower", "Middle", "Upper"}

    for line in lines:
        # Pass through header / comment lines
        if line.startswith(";") or line.startswith("Year,") or not line.strip():
            # rewrite the first comment line so the file no longer
            # advertises itself as Baltic-targeted
            if line.startswith("; Adult arrivals for Baltic example"):
                line = "; Adult arrivals for Tornionjoki example (remapped from Baltic template, v0.52.0)"
            out_lines.append(line)
            continue
        parts = line.split(",")
        if len(parts) < 3:
            out_lines.append(line)
            continue
        old_reach = parts[2]
        if old_reach in REACH_MAP:
            parts[2] = REACH_MAP[old_reach]
            n_remapped += 1
        elif old_reach in target_set:
            n_already_target += 1
        else:
            n_unrecognized += 1
            print(f"  unrecognized reach: {old_reach!r}", file=sys.stderr)
        out_lines.append(",".join(parts))

    SRC.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"wrote {SRC}")
    print(f"  remapped: {n_remapped}")
    print(f"  already-target: {n_already_target}")
    print(f"  unrecognized: {n_unrecognized}")

    # Quick verification
    new_text = SRC.read_text(encoding="utf-8")
    target_counts = {r: new_text.count(f",{r},") for r in target_set}
    print(f"  per-reach record counts: {target_counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
