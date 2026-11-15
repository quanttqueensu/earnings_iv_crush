"""r5_hold_hedge.py: exits and hedges on the stored chain-marked event tables (real data, 2013-2026).

Reuses the per-event arms already built by the hedged-event-hold and open-hedge studies (15:59
chain marks, CRSP and Yahoo spot paths). Every block here has been viewed by those studies, so all
rows are descriptive or exploratory. Arms, fractions of that study's m0 (0.20 x forward + bid premium):
  B      buy back at the 15:59 asks on the reaction day (base).
  H      no buy-back; delta-hedge with stock from the reaction close to expiry; settle at intrinsic.
  NK     no buy-back, no hedge, settle at intrinsic.
  CH     conditional: H when the implied move is below the causal 75th percentile, else B.
  B+OH   base plus a delta hedge from the reaction-day open to its close (open-hedge study's term).

Usage
-----
    python r5_hold_hedge.py [--log]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import ROOT, ci, fmt, log_trial, tstat

MIN_HIST = 200
RES = ROOT / "outputs" / "research"


def causal_q(g: pd.DataFrame, col: str, q: float) -> pd.Series:
    g = g.sort_values("entry_date")
    hist: list[float] = []
    thr = {}
    for d, vals in g.groupby("entry_date")[col].apply(list).items():
        thr[d] = float(np.nanquantile(hist, q)) if len(hist) >= MIN_HIST else np.nan
        hist.extend(vals)
    return g["entry_date"].map(thr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args()
    e = pd.concat([pd.read_parquet(RES / "2026-11-02-hedged-event-hold" / "events.parquet"),
                   pd.read_parquet(RES / "2026-11-02-hedged-event-hold" / "events_confirm_2025_26.parquet")], ignore_index=True)
    print("funnel: rows", len(e), "| status", e["status"].value_counts().to_dict())
    e = e[(e["status"] == "ok") & e["B"].notna() & e["H"].notna()].drop_duplicates(["ticker", "entry_date"]).copy()
    e["implied_move"] = e["mid0"] / ((e["m0"] - e["s0"]) / 0.20)
    e["p75"] = causal_q(e, "implied_move", 0.75)
    oh = pd.read_parquet(RES / "2026-11-02-open-hedge" / "events.parquet")[["ticker", "entry_date", "add", "gap", "d_o"]]
    e = e.merge(oh, on=["ticker", "entry_date"], how="left")
    print("funnel: ok and paired", len(e), "| with causal p75", int(e["p75"].notna().sum()), "| with open-hedge term", int(e["add"].notna().sum()))
    e["block"] = np.where(e["entry_date"] < "2020-01-01", "2013-19", np.where(e["entry_date"] < "2025-01-01", "2020-24", "2025-26"))
    for blk, g in e.groupby("block"):
        dt = g["exit_date"]
        print(f"\n=== {blk}: N={len(g)}; hold days median {g['hold_days'].median()}")
        for k in ("B", "H", "naked", "oneshot"):
            print(f"  {k:8s} level {fmt(ci(g[k], dt))} sd {100*g[k].std():.2f} worst1% mean {100*g[k][g[k] <= g[k].quantile(0.01)].mean():.1f}")
        print("  H - B      ", fmt(ci(g["H"] - g["B"], dt)), "t", round(tstat(g["H"] - g["B"], dt), 2))
        print("  NK - B     ", fmt(ci(g["naked"] - g["B"], dt)), "t", round(tstat(g["naked"] - g["B"], dt), 2))
        k = g["p75"].notna()
        low = g["implied_move"] < g["p75"]
        CH = g["H"].where(low, g["B"])[k]
        print(f"  CH (hold below causal p75, N held {int((low & k).sum())} of {int(k.sum())}): level {fmt(ci(CH, dt[k]))} | CH - B {fmt(ci(CH - g.loc[k, 'B'], dt[k]))}"
              f" | CH - H {fmt(ci(CH - g.loc[k, 'H'], dt[k]))}")
        hi = k & ~low
        print("    H - B above p75", fmt(ci((g["H"] - g["B"])[hi], dt[hi])), "| below", fmt(ci((g["H"] - g["B"])[k & low], dt[k & low])))
        o = g["add"].notna()
        boh = (g["B"] + g["add"])[o]
        vr = 1 - boh.var() / g.loc[o, "B"].var()
        print(f"  open delta hedge on the buy-back book (N={int(o.sum())}): carry (mean hedge term) {fmt(ci(g.loc[o, 'add'], dt[o]))}; "
              f"sd B {100*g.loc[o, 'B'].std():.2f} -> B+OH {100*boh.std():.2f}; variance reduction {100*vr:+.1f}%; "
              f"worst 1% mean {100*g.loc[o, 'B'][g.loc[o, 'B'] <= g.loc[o, 'B'].quantile(0.01)].mean():.1f} -> {100*boh[boh <= boh.quantile(0.01)].mean():.1f}")
        print("    stock path: mean |gap at open|", round(100 * g.loc[o, "gap"].abs().mean(), 2), "% vs mean |close-to-close move|",
              round(100 * g.loc[o, "abs_move"].mean(), 2), "%")
        if a.log:
            log_trial(1730, "hedged hold to expiry instead of the buy-back (H - B)", "one option crossing instead of two; stock hedge removes post-event drift exposure",
                      blk, g["H"] - g["B"], dt, "paired diff, fraction of m0, net at touch", "descriptive (block viewed by the 2026-11-02 study)")
            log_trial(1731, "level of the hedged hold H", "is the modified book net positive", blk, g["H"], dt, "level, fraction of m0, net at touch", "descriptive")
            log_trial(1732, "conditional hold: H below causal p75 implied move, else buy back (CH - B)", "large implied moves leave deep in-the-money legs with wide exit spreads either way",
                      blk, CH - g.loc[k, "B"], dt[k], "paired diff, fraction of m0, net at touch", "exploratory")
            log_trial(1733, "unhedged hold to expiry (NK - B)", "saves the exit cross but keeps drift exposure", blk, g["naked"] - g["B"], dt,
                      "paired diff, fraction of m0, net at touch", "descriptive")
            log_trial(1734, "delta hedge from the reaction open to the close: carry term", "removes open-to-close stock exposure; costs if the gap reverses intraday",
                      blk, g.loc[o, "add"], dt[o], "mean hedge P&L, fraction of m0, net of 8 bp", f"descriptive; variance reduction {100*vr:+.1f}%")


if __name__ == "__main__":
    main()
