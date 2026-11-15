"""s02c_diag.py: N08 discovery diagnosis (trial 2,306, descriptive splits on block D only).

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N08-index-macro-cached/s02c_diag.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("disc", HERE / "s02_discovery.py")
disc = importlib.util.module_from_spec(_s)
_s.loader.exec_module(disc)

a = pd.read_parquet(HERE / "trades_all.parquet")
b = pd.read_parquet(HERE / "trades_round2.parquet")
df = pd.concat([a, b], ignore_index=True)
df = df[(df["block"] == "D") & (df["ticker"] == "SPY") & (df["status"] == "ok")].copy()
vix = a[a["family"] == "T1"].drop_duplicates(["ticker", "entry"]).set_index(["ticker", "entry"])["vix_prev"]
df["vix_prev"] = pd.MultiIndex.from_frame(df[["ticker", "entry"]]).map(vix.to_dict().get)
assert df["entry"].max() < pd.Timestamp("2025-01-01")
for fam in ("T1", "T4", "T2"):
    d = df[df["family"] == fam]
    m = d["ev_fomc"] if fam == "T2" else (d["ev_cpi"] | d["ev_nfp"])
    ev = d[m.to_numpy()]
    pool = d[disc.is_clean(d)]
    e = disc.matched(ev, pool, "short_net")
    e = e[e["n_ctl"] >= 5].copy()
    e["diff"] = e["short_net"] - e["ctl"]
    em = disc.matched(ev, pool, "short_mid")
    e["diff_mid"] = (em["short_mid"] - em["ctl"]).reindex(e.index)
    e["year"] = e["event_date"].dt.year
    e["kind"] = np.where(e["ev_cpi"], "cpi", np.where(e["ev_nfp"], "nfp", "fomc"))
    e["vixq"] = pd.qcut(e["vix_prev"], 3, labels=["lowVIX", "midVIX", "highVIX"])
    print(f"\n{fam} SPY by year (net book, net diff, mid diff, N):")
    g = e.groupby("year")[["short_net", "diff", "diff_mid"]].mean().round(3)
    g["n"] = e.groupby("year").size()
    print(g.to_string())
    print(e.groupby(["kind"])[["short_net", "diff", "diff_mid"]].mean().round(3).to_string())
    print(e.groupby(["vixq"], observed=True)[["short_net", "diff", "diff_mid"]].mean().round(3)
          .to_string())
    print(e.groupby(["dte"])[["short_net", "diff", "diff_mid"]].agg(["mean", "size"]).round(3)
          .to_string())
