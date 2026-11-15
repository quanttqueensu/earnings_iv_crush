"""check_roll.py: which trading day of the month does EIA's contract 1 roll on? No event outcome used.

For each candidate offset k (roll day = k-th last trading day of the month), compare the mean
squared return on candidate roll days computed naively (C1_t/C1_{t-1}) and spliced
(C1_t/C2_{t-1}). At the true roll day splicing removes the calendar-spread jump; elsewhere it adds one.

Usage: python -I scripts/check_roll.py <lane_dir>
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

lane = Path(sys.argv[1])
f = pd.read_csv(lane / "data" / "futures_daily.csv", parse_dates=["date"]).set_index("date").dropna(subset=["c1", "c2"])
f = f[f.index >= "2002-01-01"]
idx = f.index
g = pd.Series(idx, index=idx).groupby([idx.year, idx.month])
for k in range(1, 7):
    days = pd.DatetimeIndex(g.apply(lambda x: x.iloc[-k] if len(x) >= k else pd.NaT).dropna().values)
    pos = idx.get_indexer(days)
    pos = pos[pos > 0]
    naive = np.log(f["c1"].values[pos] / f["c1"].values[pos - 1])
    spl = np.log(f["c1"].values[pos] / f["c2"].values[pos - 1])
    print(f"k={k} (k-th last day): n={len(pos)} mean naive^2={np.mean(naive**2):.5f} mean spliced^2={np.mean(spl**2):.5f} spliced smaller {np.mean(np.abs(spl)<np.abs(naive)):.1%}")
r = np.log(f["c1"] / f["c1"].shift(1))
print("largest |naive C1| days:"); print(r.abs().sort_values(ascending=False).head(6))
