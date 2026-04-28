"""Spawn-window temperature distribution at fine granularity for
Tornionjoki — what fraction of days has temp >= 1.0°C (the new
spawn_min_temp threshold)?
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    for reach in ["Mouth", "Lower", "Middle", "Upper"]:
        path = ROOT / f"tests/fixtures/example_tornionjoki/{reach}-TimeSeriesInputs.csv"
        df = pd.read_csv(path, comment=";", header=0)
        df["Date"] = pd.to_datetime(df["Date"])
        df["mmdd"] = df["Date"].dt.strftime("%m-%d")
        spawn = df[(df["mmdd"] >= "10-15") & (df["mmdd"] <= "11-30")]
        t = spawn["temperature"]
        n = len(t)
        n_above_1 = int((t >= 1.0).sum())
        n_above_05 = int((t >= 0.5).sum())
        unique = sorted(t.unique())
        head = unique[:5]
        tail = unique[-3:]
        print(f"{reach}: n={n}, >=1.0: {n_above_1} ({100*n_above_1/n:.1f}%), "
              f">=0.5: {n_above_05} ({100*n_above_05/n:.1f}%), "
              f"first={head}, last={tail}")


if __name__ == "__main__":
    main()
