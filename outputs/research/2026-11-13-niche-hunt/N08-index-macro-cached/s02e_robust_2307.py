"""s02e_robust_2307.py: trial 2,307 robustness on block D only (by year, leave-one-year-out, tail).

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N08-index-macro-cached/s02e_robust_2307.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from earnings_iv_crush.research.protocol import date_clustered_ci

H = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location("disc", H / "s02_discovery.py")
disc = importlib.util.module_from_spec(s)
s.loader.exec_module(disc)
df = pd.concat([pd.read_parquet(H / "trades_all.parquet"),
                pd.read_parquet(H / "trades_round2.parquet")], ignore_index=True)
df = df[(df.block == "D") & (df.dte <= 3) & (df.family == "T4") & (df.ticker == "SPY")
        & (df.status == "ok")]
assert df.entry.max() < pd.Timestamp("2025-01-01")
ev = df[(df.ev_cpi | df.ev_nfp).to_numpy()]
pool = df[disc.is_clean(df)]
e = disc.matched(ev, pool, "short_net")
e = e[e.n_ctl >= 5].copy()
e["diff"] = e.short_net - e.ctl
e["y"] = e.event_date.dt.year
g = e.groupby("y").agg(n=("diff", "size"), book=("short_net", "mean"), diff=("diff", "mean"))
print(g.round(3).to_string())
print("years with diff>0:", int((g["diff"] > 0).sum()), "of", len(g))
for y in sorted(e.y.unique()):
    x = e[e.y != y]
    iv = date_clustered_ci(x["diff"].to_numpy(), x.event_date.to_numpy(), stat=np.mean)
    print(f"  drop {y}: diff {iv}")
k = max(1, int(round(0.01 * len(e))))
w = e.nsmallest(k, "short_net")
print(f"worst 1% ({k}) share of total book P&L: {w.short_net.sum() / e.short_net.sum():+.2f}; "
      f"skew {e.short_net.skew():+.2f}; sd {e.short_net.std():.3f}")
