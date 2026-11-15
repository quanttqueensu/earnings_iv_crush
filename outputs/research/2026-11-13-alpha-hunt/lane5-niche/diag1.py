"""
diag1.py
Discovery-only (2013-18) descriptive cuts behind the round 1 pivots. Cell-residual outcomes.

Usage
-----
    python diag1.py
"""
from __future__ import annotations
import numpy as np, pandas as pd, lib
pd.set_option("display.width", 220)
d = lib.load()
b = d[(d.year.between(2013, 2018)) & (d.im_bin >= 0)].copy()
print("discovery rows", len(b))
for c in ("y", "ri", "yb", "H"):
    b[c + "_r"] = b[c] - b.groupby("cell")[c].transform("mean")
def cut(name, key):
    g = b.groupby(key, observed=True).agg(n=("y", "size"), y_r=("y_r", "mean"), ri_r=("ri_r", "mean"),
        yb_r=("yb_r", "mean"), H=("H", "mean"), im=("implied_move", "median"), dte=("dte", "median"),
        hs=("half_spread", "median"), names=("ticker", "nunique"))
    print(f"\n== {name}"); print(g.round(4).to_string())
cut("peer_share quintile", pd.qcut(b.peer_share, 5, duplicates="drop"))
cut("crowd_all quintile", pd.qcut(b.crowd_all, 5, duplicates="drop"))
cut("fqtr", "fqtr"); cut("sector", "sector"); cut("exit weekday", "exit_wd"); cut("month", "month")
cut("amc", "amc"); cut("tenor", "tenor"); cut("ind_prior==0 (first in gics6)", b.ind_prior.eq(0).where(b.ind_prior.notna()))
cut("peer_week", pd.cut(b.peer_week, [-1, 0, 2, 5, 10, 1000]))
cut("year", "year")
cut("sess_to_expiry", pd.cut(b.sess_to_expiry, [-1, 0, 1, 2, 4, 9, 300]))
# name concentration of the late-reporter loss
late = b[b.peer_share >= b.peer_share.quantile(2/3)]
print("\nlate tercile: worst 10 tickers by summed y_r"); print(late.groupby("ticker").y_r.agg(["size", "sum", "mean"]).sort_values("sum").head(10).round(3).to_string())
print("late tercile ri tail: share with ri>2:", (late.ri > 2).mean().round(3), "vs rest", (b[b.peer_share < b.peer_share.quantile(2/3)].ri > 2).mean().round(3))
print("late tercile by sector count"); print(late.sector.value_counts().to_string())
