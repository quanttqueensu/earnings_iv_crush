"""prep_data.py: convert the EIA natural gas downloads in raw/ to tidy CSVs.

Inputs (free EIA downloads, https://www.eia.gov/dnav/ng/hist_xls/<series>.xls):
  RNGC1d..RNGC4d  NYMEX Henry Hub futures settlement, contracts 1-4, daily, $/MMBtu
  RNGWHHDd        Henry Hub spot, daily (not used in scoring)
  NW2_EPG0_SWO_R48_BCFw  Lower-48 working gas in storage, weekly (week ending Friday), Bcf

Outputs in data/: futures_daily.csv (date, c1..c4), storage_weekly.csv (week_end, bcf).
No outcome is computed here.

Usage:
  python -I scripts/prep_data.py <lane_dir> <xlrd_path>
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    lane = Path(sys.argv[1])
    sys.path.insert(0, sys.argv[2])
    import pandas as pd

    raw = lane / "raw"
    out = lane / "data"
    out.mkdir(exist_ok=True)
    frames = []
    for i in range(1, 5):
        d = pd.read_excel(raw / f"RNGC{i}d.xls", sheet_name="Data 1", skiprows=2)
        d.columns = ["date", f"c{i}"]
        d["date"] = pd.to_datetime(d["date"])
        frames.append(d.set_index("date"))
    fut = pd.concat(frames, axis=1).sort_index()
    print("futures rows", len(fut), fut.index.min().date(), fut.index.max().date())
    print("missing per column", fut.isna().sum().to_dict())
    fut.to_csv(out / "futures_daily.csv")
    s = pd.read_excel(raw / "NW2_EPG0_SWO_R48_BCFw.xls", sheet_name="Data 1", skiprows=2)
    s.columns = ["week_end", "bcf"]
    s["week_end"] = pd.to_datetime(s["week_end"])
    print("storage rows", len(s), s["week_end"].min().date(), s["week_end"].max().date())
    print("week_end weekday counts", s["week_end"].dt.day_name().value_counts().to_dict())
    s.to_csv(out / "storage_weekly.csv", index=False)


if __name__ == "__main__":
    main()
