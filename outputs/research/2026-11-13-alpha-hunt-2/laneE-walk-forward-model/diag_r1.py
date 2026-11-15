"""
diag_r1.py
Descriptive diagnosis of the round 1 out-of-sample selections (discovery block only; no new
trial): how much of the top-quintile excess is the mechanical entry half-spread, how it splits
by causal half-spread tercile, and which events carry it.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/diag_r1.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

p = pd.read_parquet(HERE / "panel.parquet", columns=["ticker", "entry_date", "H_mid", "m0",
                                                       "mid0", "s0", "me", "dolvol_126d"])
for f in sorted((HERE / "oos").glob("19*_discovery.parquet")):
    r = pd.read_parquet(f).merge(p, on=["ticker", "entry_date"], how="left", validate="1:1")
    r["y_mid"] = r["H_mid"] * r["m0"] / r["mid0"]
    r["ym_ex"] = r["y_mid"] - r.groupby("qcell")["y_mid"].transform("mean")
    r["hs_ex"] = r["half_spread"] - r.groupby("qcell")["half_spread"].transform("mean")
    s = r[r["sel"]]
    d = s["announce_date"].to_numpy()
    em = date_clustered_ci(s["ym_ex"].to_numpy(float), d, np.mean)
    print(f"\n{f.stem}: selected {len(s)}")
    print(f"  excess at touch {s['y_ex'].mean():+.4f}; excess at mid (H_mid per premium) "
          f"{em.point:+.4f} [{em.low:+.4f}, {em.high:+.4f}]; selected half-spread minus cell mean "
          f"{s['hs_ex'].mean():+.4f}")
    print("  by causal half-spread tercile (0 tight): share of picks, excess touch, excess mid")
    for t, g in s.groupby("hs_t"):
        print(f"    t{t}: {len(g) / len(s):.2f}  {g['y_ex'].mean():+.4f}  {g['ym_ex'].mean():+.4f}")
    # concentration: share of the summed excess from the top 5% of picks
    v = s["y_ex"].sort_values(ascending=False).to_numpy()
    print(f"  sum excess {v.sum():+.2f}; from top 5% of picks {v[: max(1, len(v) // 20)].sum():+.2f};"
          f" median pick excess {np.median(v):+.4f}; unselected mean excess "
          f"{r.loc[~r['sel'], 'y_ex'].mean():+.4f}")
    # bottom quintile (tail avoidance vs. picking winners)
    r["pq"] = r.groupby("q")["pred"].rank(pct=True)
    print("  excess by within-quarter prediction quintile (touch | mid): "
          + ", ".join(f"Q{int(k)}:{g['y_ex'].mean():+.3f}|{g['ym_ex'].mean():+.3f}"
                      for k, g in r.groupby(np.ceil(r["pq"] * 5).clip(1, 5))))
    print("  share of events with y < -1 (loss above premium) by quintile: "
          + ", ".join(f"Q{int(k)}:{(g['y'] < -1).mean():.3f}"
                      for k, g in r.groupby(np.ceil(r["pq"] * 5).clip(1, 5))))
