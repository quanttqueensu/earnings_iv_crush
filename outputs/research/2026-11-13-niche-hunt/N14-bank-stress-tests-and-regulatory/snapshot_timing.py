"""snapshot_timing.py: is a DoltHub end-of-day snapshot taken before or after the 16:30 release?

For each cached chain on a name with unadjusted closes, compare the parity forward of the
nearest expiry with the close on the snapshot date and on the next session. A snapshot struck at
the close sits nearer the same-day close; one struck after the release on an event night would
sit nearer the next close. Reads quotes only, no P&L.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
from stage_b_options import forward, pair  # noqa: E402

import dolt  # noqa: E402

c = pd.read_parquet(os.path.join(ROOT, "data/cache/dolthub_p2/closes_unadjusted.parquet"))
px = c.pivot(index="date", columns="ticker", values="close")
cal = pd.read_csv(os.path.join(HERE, "stress_calendar.csv"))
nights = set(pd.to_datetime(cal["night"]))
rows = []
for f in sorted(os.listdir(dolt.CHAINS)):
    t, d = f[:-8].rsplit("_", 1)
    d = pd.Timestamp(d)
    if t not in px.columns or d not in px.index:
        continue
    i = px.index.get_loc(d)
    if i + 1 >= len(px.index):
        continue
    ch = dolt.chain(t, d)
    e = sorted(ch["expiry"].unique())[0]
    fw = forward(pair(ch, e))
    c0, c1 = px[t].iloc[i], px[t].iloc[i + 1]
    rows.append({"ticker": t, "date": d, "event_night": d in nights, "fwd": fw, "close": c0,
                 "next_close": c1, "err_same": abs(np.log(fw / c0)),
                 "err_next": abs(np.log(fw / c1)), "move": abs(np.log(c1 / c0))})
r = pd.DataFrame(rows).dropna()
big = r[r["move"] > 0.02]
print(f"snapshots checked {len(r)}; nearer same-day close {(r.err_same < r.err_next).mean():.3f}; "
      f"median |log(fwd/close)| {r.err_same.median():.4f}")
print(f"next-day move > 2%: N={len(big)}, nearer same-day close "
      f"{(big.err_same < big.err_next).mean():.3f}")
print(r[r["event_night"]].round(4).to_string(index=False))
