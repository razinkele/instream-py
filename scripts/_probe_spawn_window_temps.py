"""Quick probe: temperature distribution during the spawning window
(Oct 15 - Nov 30) for Tornionjoki vs Baltic.

If Tornionjoki autumn temps are below spawn_min_temp=5.0°C, RETURNING_ADULTs
can't trigger spawning — explains why init_cum==0 redds in the B5 probe.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _stats_for_window(csv_path: Path, label: str) -> None:
    df = pd.read_csv(csv_path, comment=";", header=0)
    df["Date"] = pd.to_datetime(df["Date"])
    df["mmdd"] = df["Date"].dt.strftime("%m-%d")
    spawn_mask = (df["mmdd"] >= "10-15") & (df["mmdd"] <= "11-30")
    spawn = df[spawn_mask]
    if "temperature" not in spawn.columns or len(spawn) == 0:
        print(f"{label:<30} no temperature data in spawn window")
        return
    t = spawn["temperature"]
    pct_below_5 = 100.0 * (t < 5.0).sum() / len(t)
    pct_below_3 = 100.0 * (t < 3.0).sum() / len(t)
    print(f"{label:<30} n={len(t):>4}  mean={t.mean():>5.2f}  "
          f"min={t.min():>5.2f}  max={t.max():>5.2f}  "
          f"<5°C: {pct_below_5:>5.1f}%  <3°C: {pct_below_3:>5.1f}%")


def main() -> int:
    print("Spawn-window (Oct 15 - Nov 30) temperature stats:")
    print("-" * 100)
    rivers = [
        ("BALTIC Nemunas", ROOT / "tests/fixtures/example_baltic/Nemunas-TimeSeriesInputs.csv"),
        ("TORNE Mouth", ROOT / "tests/fixtures/example_tornionjoki/Mouth-TimeSeriesInputs.csv"),
        ("TORNE Lower", ROOT / "tests/fixtures/example_tornionjoki/Lower-TimeSeriesInputs.csv"),
        ("TORNE Middle", ROOT / "tests/fixtures/example_tornionjoki/Middle-TimeSeriesInputs.csv"),
        ("TORNE Upper", ROOT / "tests/fixtures/example_tornionjoki/Upper-TimeSeriesInputs.csv"),
    ]
    for label, path in rivers:
        if path.exists():
            _stats_for_window(path, label)
        else:
            print(f"{label:<30} (file missing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
