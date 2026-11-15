"""
diag.py
Per-event diagnosis of the round-1 lane-A failures on the discovery block: realised volatility
over the remaining life against the HAR forecast and the reaction-close implied vol, and what
the events where buying back beat holding (B > H) share. Descriptive only; no trial is scored.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneA-hold-exit/diag.py --block 2013 2018
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from simulate import load_crsp  # noqa: E402

FEAT = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"


def realised(d: pd.DataFrame) -> pd.Series:
    crsp = load_crsp()
    f = pd.read_parquet(FEAT)[["ticker", "entry_date", "permno"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    d = d.merge(f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"])
    out = []
    for _, r in d.iterrows():
        sess = nyse_sessions(pd.Timestamp(r["exit_date"]), pd.Timestamp(r["expiry"]))
        g = crsp[int(r["permno"])].reindex(sess)
        lr = np.log1p(g["ret"].to_numpy(float)[1:])
        out.append(float(np.sqrt(np.mean(lr**2) * 252)) if lr.size else np.nan)
    return pd.Series(out, index=d.index), d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--block", type=int, nargs=2, required=True)
    ap.add_argument("--quiet", action="store_true", help="write rvpost only; print no outcome")
    a = ap.parse_args()
    y0, y1 = a.block
    d = pd.read_parquet(HERE / f"sim_{y0}_{y1}.parquet")
    rv, d = realised(d)
    d["rv_post"] = rv
    d[["ticker", "entry_date", "exit_date", "expiry", "n_hedge", "rv_f", "rv_post"]].to_parquet(
        HERE / f"rvpost_{y0}_{y1}.parquet"
    )
    if a.quiet:
        print(f"wrote rvpost_{y0}_{y1}.parquet, N {len(d)}, rv_post missing "
              f"{int(d['rv_post'].isna().sum())}")
        return
    d["BmH"] = d["B"] - d["H"]
    d.to_parquet(HERE / f"diag_{y0}_{y1}.parquet")
    h = d[d["n_hedge"] > 0]
    print(f"events with a hold of at least one session: {len(h)} of {len(d)}")
    for c in ("rv_f", "iv_mid", "iv_ask", "s2_iv"):
        x = h[[c, "rv_post"]].dropna()
        lr = np.log(x["rv_post"] / x[c]).replace([-np.inf, np.inf], np.nan).dropna()
        print(f"  {c:7s} N {len(x)}  median rv_post/{c} {np.exp(lr.median()):.3f}  "
              f"corr(log) {np.corrcoef(np.log(x['rv_post'].clip(1e-4)), np.log(x[c]))[0, 1]:.3f}")
    print("\nB > H events vs the rest (means):")
    cols = ["abs_move", "rv_post", "rv_f", "iv_mid", "iv_ask", "hold_days", "n_hedge", "extr_ask",
            "two_sided", "H", "B", "BmH"]
    h = h.assign(win=h["BmH"] > 0, extr_ask=h["extr_ask"] / h["m0"])
    print(h.groupby("win")[cols].mean().T.to_string())
    print("\nB - H by decile of iv_ask / rv_f (descriptive):")
    q = pd.qcut(h["iv_ask"] / h["rv_f"], 10, duplicates="drop")
    print(h.groupby(q, observed=True).agg(n=("BmH", "size"), BmH=("BmH", "mean"),
          rvpost_over_ivmid=("rv_post", lambda s: float(np.nanmedian(s / h.loc[s.index, "iv_mid"]))),
          H=("H", "mean")).to_string())
    print("\nB - H by hold length (sessions):")
    q = pd.cut(h["n_hedge"], [0, 1, 2, 4, 9, 40])
    print(h.groupby(q, observed=True).agg(n=("BmH", "size"), BmH=("BmH", "mean"),
          win=("win", "mean"), H=("H", "mean"), B=("B", "mean")).to_string())
    print("\nWhere does H lose? H by reaction move / implied move (descriptive):")
    im = h["mid0"] / ((h["m0"] - h["s0"]) / 0.2)
    q = pd.cut(h["abs_move"] / im, [0, 0.5, 1, 1.5, 2, 3, 99])
    print(h.groupby(q, observed=True).agg(n=("H", "size"), H=("H", "mean"), B=("B", "mean"),
          post=("BmH", "mean")).to_string())


if __name__ == "__main__":
    main()
