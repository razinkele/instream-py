"""Generate synthetic hourly time-series from Example A daily data."""

import pandas as pd
from pathlib import Path


def main():
    FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"
    DAILY_CSV = FIXTURES / "example_a" / "ExampleA-TimeSeriesInputs.csv"
    OUT_DIR = FIXTURES / "subdaily"
    OUT_DIR.mkdir(exist_ok=True)

    # Read daily CSV (skip comment lines starting with ;)
    lines = []
    with open(DAILY_CSV) as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith(";"):
                lines.append(stripped)

    header = lines[0]
    col_names = [c.strip() for c in header.split(",")]

    rows = []
    for line in lines[1:11]:  # first 10 data rows (10 days)
        parts = [p.strip() for p in line.split(",")]
        rows.append(parts)

    # Parse into DataFrame
    df = pd.DataFrame(rows, columns=col_names)
    df["Date"] = pd.to_datetime(df["Date"], format="mixed")
    for col in col_names[1:]:
        df[col] = pd.to_numeric(df[col])

    # Generate hourly: repeat each day's values 24 times
    hourly_rows = []
    for _, row in df.iterrows():
        base_date = row["Date"].normalize()  # midnight
        for hour in range(24):
            ts = base_date + pd.Timedelta(hours=hour)
            hourly_rows.append(
                {
                    "Date": ts.strftime("%m/%d/%Y %H:%M"),
                    "temperature": row["temperature"],
                    "flow": row["flow"],
                    "turbidity": row["turbidity"],
                }
            )
    hourly_df = pd.DataFrame(hourly_rows)
    hourly_df.to_csv(OUT_DIR / "hourly_example_a.csv", index=False)
    print("Generated hourly_example_a.csv ({} rows)".format(len(hourly_df)))

    # Generate peaking (6-hourly): 4 sub-steps per day
    # Steps 1,2 (hours 6,12) get 3x flow (peak), steps 0,3 (hours 0,18) get base flow
    peaking_rows = []
    for _, row in df.iterrows():
        base_date = row["Date"].normalize()
        for step, hour in enumerate([0, 6, 12, 18]):
            ts = base_date + pd.Timedelta(hours=hour)
            flow = row["flow"]
            if step in [1, 2]:  # peak hours
                flow *= 3.0
            peaking_rows.append(
                {
                    "Date": ts.strftime("%m/%d/%Y %H:%M"),
                    "temperature": row["temperature"],
                    "flow": flow,
                    "turbidity": row["turbidity"],
                }
            )
    peaking_df = pd.DataFrame(peaking_rows)
    peaking_df.to_csv(OUT_DIR / "peaking_example_a.csv", index=False)
    print("Generated peaking_example_a.csv ({} rows)".format(len(peaking_df)))


if __name__ == "__main__":
    main()
