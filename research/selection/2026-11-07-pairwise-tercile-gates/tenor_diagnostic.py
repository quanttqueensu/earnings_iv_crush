"""
tenor_diagnostic.py
Descriptive diagnostic, no trial: is the pairwise-gate residual-value pass carried by days to expiry?

Runs after study.py. Prints feature and outcome rank correlations with days to expiry at exit, the
selected-minus-unselected residual value within tenor buckets, buy-back (B) and hedged-hold (H) P&L
per trade on m0 against the matched null, and the P&L lift within tenor buckets.

Usage
-----
    python research/selection/2026-11-07-pairwise-tercile-gates/tenor_diagnostic.py
"""

import importlib.util
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, ".")
p = "research/selection/2026-11-07-pairwise-tercile-gates/study.py"
s = importlib.util.spec_from_file_location("pt", p)
m = importlib.util.module_from_spec(s)
sys.modules["pt"] = m
s.loader.exec_module(m)
from earnings_iv_crush.research.protocol import date_clustered_ci, matched_random_null  # noqa: E402

d = m.load_base()
mk = pd.read_parquet(m.OUT / "exit_marks.parquet")
mk["entry_date"] = pd.to_datetime(mk["entry_date"]).dt.normalize()
d = d.merge(mk, on=["ticker", "entry_date"], how="left").reset_index(drop=True)
d["dte_exit"] = (pd.to_datetime(d["expiry"]) - pd.to_datetime(d["exit_date"])).dt.days
print("Spearman with days-to-expiry at exit:")
for f in m.FAVOURABLE:
    ok = d[f].notna()
    print(f"  {f:24s} {spearmanr(d.loc[ok, f], d.loc[ok, 'dte_exit'])[0]:+.3f}")
print(f"  residual_value           {spearmanr(d['residual_value'], d['dte_exit'])[0]:+.3f}")
bins = {f: m.causal_bins(d[f].to_numpy(float), d["announce_date"], 3, 200) for f in m.FAVOURABLE}
d["tenor"] = pd.cut(d["dte_exit"], [-1, 1, 4, 9, 1000], labels=["0-1d", "2-4d", "5-9d", "10d+"])
print("\nmedian dte at exit, all events:", d["dte_exit"].median())
for a, b in [
    ("iv_term_spread", "variance_risk_premium"),
    ("iv_term_spread", "entry_half_spread"),
    ("variance_risk_premium", "entry_half_spread"),
    ("variance_risk_premium", "bkm_kurt"),
]:
    sc = (bins[a] >= 0) & (bins[b] >= 0)
    sel = sc & (bins[a] == m.FAVOURABLE[a]) & (bins[b] == m.FAVOURABLE[b])
    print(
        f"\n{a} x {b}: selected median dte {d.loc[sel, 'dte_exit'].median()}, unselected {d.loc[sc & ~sel, 'dte_exit'].median()}"
    )
    print("  within tenor bucket, residual value selected minus unselected (N sel / N unsel):")
    for t, g in d[sc].groupby("tenor", observed=True):
        gs = sel[g.index]
        if gs.sum() >= 10 and (~gs).sum() >= 10:
            print(
                f"    {t:5s} {g.loc[gs, 'residual_value'].mean() - g.loc[~gs, 'residual_value'].mean():+.4f}  ({int(gs.sum())}/{int((~gs).sum())})"
            )
    print("  economic outcomes per trade on m0, selected vs matched null over scored events:")
    for name, (y0, y1) in m.BLOCKS.items():
        inb = d["year"].between(y0, y1).to_numpy()
        for col in ("B", "H"):
            pool = sc & inb & d[col].notna().to_numpy()
            msk = sel[pool]
            vals = d.loc[pool, col].to_numpy(float)
            ci = date_clustered_ci(vals[msk], d.loc[pool, "announce_date"].to_numpy()[msk], np.mean)
            nl = matched_random_null(vals, msk, stat=np.mean)
            print(
                f"    {name:12s} {col}: selected mean {ci.point:+.4f} [{ci.low:+.4f}, {ci.high:+.4f}] N={ci.n}, all-scored {vals.mean():+.4f}, null pct {nl.percentile:.1f}"
            )

print("\n=== P&L by tenor bucket, all events (per trade on m0) ===")
for name, (y0, y1) in m.BLOCKS.items():
    b = d[d["year"].between(y0, y1)]
    print(
        name,
        b.groupby("tenor", observed=True)[["B", "H"]]
        .agg(["mean", "count"])
        .round(4)
        .to_string()
        .replace("\n", "\n  "),
    )
a, bb = "iv_term_spread", "entry_half_spread"
sc = (bins[a] >= 0) & (bins[bb] >= 0)
sel = sc & (bins[a] == 2) & (bins[bb] == 0)
print(f"\n=== {a} x {bb}: lift within tenor bucket (selected minus unselected), per block ===")
for name, (y0, y1) in m.BLOCKS.items():
    inb = d["year"].between(y0, y1).to_numpy()
    for t in ["0-1d", "2-4d"]:
        g = sc & inb & (d["tenor"] == t).to_numpy()
        s1, s0 = g & sel, g & ~sel
        print(
            f"  {name:12s} {t}: B {d.loc[s1,'B'].mean()-d.loc[s0,'B'].mean():+.4f}  H {d.loc[s1,'H'].mean()-d.loc[s0,'H'].mean():+.4f}  (N {int(s1.sum())}/{int(s0.sum())})"
        )
