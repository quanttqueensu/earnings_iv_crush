"""
diag_r3.py
Descriptive diagnosis (discovery block only, no new trial) of the at-mid candidates 1905, 1906,
1908, 1910 and 1912: what the picks look like against their cell, whether one year or a few
events carry the excess, and whether the rankings agree with each other.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/diag_r3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

COLS = ["implied_move", "dte", "front_iv", "iv_term_spread", "jump_share", "skew_25d",
        "rv_20d", "ret_20d", "max_abs_ret_60d", "hist_abs_mean", "me", "half_spread"]
p = pd.read_parquet(HERE / "panel.parquet",
                    columns=["ticker", "entry_date", "H_mid", "m0", "mid0"] + COLS[:-1])
runs = {}
for tid in ("1905", "1906", "1908", "1910", "1912"):
    f = next((HERE / "oos").glob(f"{tid}_*_discovery.parquet"))
    r = pd.read_parquet(f).merge(p, on=["ticker", "entry_date"], how="left", validate="1:1")
    r["y_mid"] = r["H_mid"] * r["m0"] / r["mid0"]
    runs[tid] = r
    s = r[r["sel"]]
    print(f"\n{f.stem}: selected {len(s)} of {len(r)}")
    # picks against their cell: median within-cell percentile of each feature
    pct = {c: r.groupby("qcell")[c].rank(pct=True)[r["sel"]].median() for c in COLS}
    print("  picks' median within-cell percentile: "
          + ", ".join(f"{c} {v:.2f}" for c, v in pct.items()))
    for drop in (2017, 2020):
        k = s[s["announce_date"].dt.year != drop]
        e = date_clustered_ci(k["ym_ex"].to_numpy(float), k["announce_date"].to_numpy(), np.mean)
        print(f"  excess at mid without {drop}: {e.point:+.4f} [{e.low:+.4f}, {e.high:+.4f}], "
              f"N {e.n}")
    v = s["ym_ex"].to_numpy(float)
    w = np.clip(v, *np.quantile(r["ym_ex"], [0.01, 0.99]))
    print(f"  excess at mid, outcome winsorised at the block's 1/99%: {w.mean():+.4f}; "
          f"median pick {np.median(v):+.4f} vs median unselected "
          f"{np.median(r.loc[~r['sel'], 'ym_ex']):+.4f}")
    print(f"  loss beyond premium (y_mid < -1) share: picks {(s['y_mid'] < -1).mean():.3f} "
          f"vs rest {(r.loc[~r['sel'], 'y_mid'] < -1).mean():.3f}")
    print("  by tenor: " + ", ".join(
        f"{t}:{len(g)}/{g['ym_ex'].mean():+.3f}" for t, g in s.groupby(s["qcell"].str[-1])))
    top = s.sort_values("ym_ex").iloc[[0, 1, 2, -3, -2, -1]]
    print("  extreme picks (ticker, date, excess at mid): " + "; ".join(
        f"{a} {b.date()} {c:+.2f}" for a, b, c in zip(top["ticker"], top["entry_date"],
                                                       top["ym_ex"], strict=True)))
ids = list(runs)
print("\nrank agreement of predictions (Spearman, same events):")
for i, a in enumerate(ids):
    for b in ids[i + 1:]:
        x = runs[a].set_index(["ticker", "entry_date"])["pred"]
        y = runs[b].set_index(["ticker", "entry_date"])["pred"].reindex(x.index)
        print(f"  {a} vs {b}: {spearmanr(x, y).statistic:+.3f}; pick overlap "
              f"{(runs[a]['sel'].to_numpy() & runs[b]['sel'].to_numpy()).sum()}")
