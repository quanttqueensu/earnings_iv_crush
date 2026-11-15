"""discovery_diagnostics.py: per-subperiod and per-season reads of trials 2142-2144, and trial
2145 (short C2), on the discovery block only (2002-05 to 2018-12).

Usage: python -I scripts/discovery_diagnostics.py <lane_dir>
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

lane = Path(sys.argv[1])
sys.path.insert(0, str(lane / "scripts"))
import lib

f = lib.load_futures(lane)
r = lib.same_contract_returns(f)
p, _ = lib.weekly_panel(r)
d = lib.block(p, lib.DISCOVERY)
fmt = lambda v: json.dumps({a: round(b, 5) for a, b in v.items()})
for name, span in (("2002-2010", ("2002-05-01", "2010-12-31")), ("2011-2018", ("2011-01-01", "2018-12-31"))):
    s = lib.block(d, (pd.Timestamp(span[0]), pd.Timestamp(span[1])))
    print(name, "rho_c1", fmt(lib.rho_stats(s, "1")))
    print(name, "short_c1", fmt(lib.short_stats(s)))
wd = d[d["week"].dt.month.isin([11, 12, 1, 2, 3])]
inj = d[~d["week"].dt.month.isin([11, 12, 1, 2, 3])]
print("withdrawal Nov-Mar rho_c1", fmt(lib.rho_stats(wd.reset_index(drop=True), "1")))
print("injection Apr-Oct rho_c1", fmt(lib.rho_stats(inj.reset_index(drop=True), "1")))
# trial 2145: short C2 Wed->Thu, same cost model on the C2 price level (C2 level ~ C1 level; use f1 as proxy)
d2 = d.copy()
d2["r1_thu"], d2["r1_tue"], d2["r1_wed"] = d2["r2_thu"], d2["r2_tue"], d2["r2_wed"]
print("2145_short_c2", fmt(lib.short_stats(d2)))
# robustness of rho to outliers: share of the Thursday excess carried by the top 5 weeks
thu2 = d["r1_thu"] ** 2
ctl2 = 0.5 * (d["r1_tue"] ** 2 + d["r1_wed"] ** 2)
ex = thu2.sum() - ctl2.sum()
print(f"top-5 Thursday weeks carry {thu2.nlargest(5).sum() / thu2.sum():.1%} of Thursday variance; excess {ex:.4f}")
print("median-based ratio med(thu^2)/med(ctl_day^2):", float(np.median(thu2) / np.median(np.r_[d['r1_tue']**2, d['r1_wed']**2])))
