"""r6_strangle_index.py: strangle against the straddle, and the ceiling on an index hedge.

Strangle (discovery block only, broad events entered in 2025): call at the listed strike nearest
K + straddle mid, put nearest K - straddle mid (one implied move out), same expiry, sold at the 15:59
bids and bought back at the 15:59 asks of the reaction day, from the cached 15:59 chains. A zero bid
at exit is kept (the buy-back needs only an ask). Paired against the straddle on the same events and
the same margin m0. Index hedge: an ATM straddle has no delta at entry, so a beta-sized index
position cannot offset the overnight market move linearly; the script reports the in-sample R-squared
of the base P&L on the SPY return over the holding day, which bounds any linear hedge from above.
Real data.

Usage
-----
    python r6_strangle_index.py [--log]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import COMM, ROOT, ci, fmt, load_ticks, log_trial, split_ticks, tstat

CH = ROOT / "data" / "cache" / "backfill_chains"


def chain(ticker: str, date: pd.Timestamp, expiry: str) -> pd.DataFrame | None:
    p = CH / f"{ticker}_{date:%Y-%m-%d}.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["bid_px_00", "ask_px_00", "bid_sz_00", "symbol"])
    d = d.groupby("symbol").tail(1)
    s = d["symbol"].str.strip()
    d = d.assign(exp=s.str[-15:-9], right=s.str[-9], k=s.str[-8:].astype(int) / 1000.0)
    return d[d["exp"] == pd.Timestamp(expiry).strftime("%y%m%d")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args()
    R = load_ticks()
    g = split_ticks(R)["disc_broad_2025"]
    g = g[g["en_two_15:59"] & g["ex_ask_15:59"].notna()]
    fun = {"events": len(g), "no_entry_chain": 0, "no_exit_chain": 0, "no_wing_strike": 0, "wing_not_two_sided": 0,
           "wing_missing_at_exit": 0, "ok": 0}
    rows = []
    for r in g.itertuples():
        c0, c1 = chain(r.ticker, r.entry_date, r.expiry), chain(r.ticker, r.exit_date, r.expiry)
        if c0 is None or c0.empty:
            fun["no_entry_chain"] += 1
            continue
        if c1 is None or c1.empty:
            fun["no_exit_chain"] += 1
            continue
        legs = {}
        for right, tgt in (("C", r.strike + r.mid0), ("P", r.strike - r.mid0)):
            q = c0[(c0["right"] == right) & ((c0["k"] > r.strike) if right == "C" else (c0["k"] < r.strike))]
            if q.empty:
                break
            legs[right] = q.iloc[(q["k"] - tgt).abs().argmin()]
        if len(legs) < 2:
            fun["no_wing_strike"] += 1
            continue
        if not all(v["bid_px_00"] > 0 and v["ask_px_00"] > v["bid_px_00"] for v in legs.values()):
            fun["wing_not_two_sided"] += 1
            continue
        ex = {}
        for right, v in legs.items():
            q = c1[(c1["right"] == right) & (c1["k"] == v["k"]) & (c1["ask_px_00"] > 0)]
            if len(q):
                ex[right] = q.iloc[0]
        if len(ex) < 2:
            fun["wing_missing_at_exit"] += 1
            continue
        fun["ok"] += 1
        sb = sum(v["bid_px_00"] for v in legs.values())
        sa = sum(v["ask_px_00"] for v in legs.values())
        xb = sum(max(v["bid_px_00"], 0.0) for v in ex.values())
        xa = sum(v["ask_px_00"] for v in ex.values())
        rows.append(dict(ticker=r.ticker, exit_date=r.exit_date, m0=r.m0, dte=r.dte,
                         STG=(sb - xa - 4 * COMM) / r.m0, STG_mid=((sb + sa) / 2 - (xb + xa) / 2) / r.m0,
                         STD=(getattr(r, "_asdict")()["en_bid_15:59"] if False else np.nan), sb=sb, sa=sa, xb=xb, xa=xa,
                         kc=legs["C"]["k"], kp=legs["P"]["k"], strike=r.strike, mid0=r.mid0,
                         wing_bsz=min(legs["C"]["bid_sz_00"], legs["P"]["bid_sz_00"])))
    s = pd.DataFrame(rows)
    base = g.set_index(["ticker", "exit_date"])
    j = s.join(base[["en_bid_15:59", "ex_ask_15:59", "ex_bid0_15:59", "hs0"]], on=["ticker", "exit_date"])
    j["STD"] = (j["en_bid_15:59"] - j["ex_ask_15:59"] - 4 * COMM) / j["m0"]
    j["STD_mid"] = (j["mid0"] - (j["ex_bid0_15:59"] + j["ex_ask_15:59"]) / 2) / j["m0"]
    dt = j["exit_date"]
    print("strangle funnel:", fun)
    dropped = g[~g.set_index(["ticker", "exit_date"]).index.isin(j.set_index(["ticker", "exit_date"]).index)]
    b_all = (g["en_bid_15:59"] - g["ex_ask_15:59"] - 4 * COMM) / g["m0"]
    print("attrition check: straddle B0 on kept", round(100 * j["STD"].mean(), 2), "on dropped", round(100 * b_all.loc[dropped.index].mean(), 2))
    print("straddle  net touch", fmt(ci(j["STD"], dt)), "| mid", fmt(ci(j["STD_mid"], dt)), "| sd", round(100 * j["STD"].std(), 2))
    print("strangle  net touch", fmt(ci(j["STG"], dt)), "| mid", fmt(ci(j["STG_mid"], dt)), "| sd", round(100 * j["STG"].std(), 2))
    d = j["STG"] - j["STD"]
    print("strangle minus straddle, net touch", fmt(ci(d, dt)), "t", round(tstat(d, dt), 2), "| at mid", fmt(ci(j["STG_mid"] - j["STD_mid"], dt)))
    print("premium: strangle bid / straddle bid median", round((j["sb"] / j["en_bid_15:59"]).median(), 3),
          "| strangle half-spread % of its mid, entry median", round(100 * ((j["sa"] - j["sb"]) / (j["sa"] + j["sb"])).median(), 2),
          "exit", round(100 * ((j["xa"] - j["xb"]) / (j["xa"] + j["xb"])).median(), 2),
          "| straddle entry", round(100 * j["hs0"].median(), 2), "| round-trip cost % of m0: strangle",
          round(100 * (j["STG_mid"] - j["STG"]).mean(), 2), "straddle", round(100 * (j["STD_mid"] - j["STD"]).mean(), 2))
    print("worst 1% mean: straddle", round(100 * j["STD"][j["STD"] <= j["STD"].quantile(0.01)].mean(), 1), "strangle",
          round(100 * j["STG"][j["STG"] <= j["STG"].quantile(0.01)].mean(), 1), "| wing bid size median", j["wing_bsz"].median())
    if a.log:
        log_trial(1735, "strangle one implied move out vs ATM straddle", "moves the gamma away from spot; cheaper legs carry wider relative spreads",
                  "disc_broad_2025", d, dt, "paired diff, fraction of straddle m0, net at touch", "scored")
    # ── index hedge ceiling ──
    y = pd.read_parquet(ROOT / "data" / "cache" / "yahoo_adj" / "adj_close.parquet")["SPY"].dropna()
    ret = np.log(y / y.shift(1))
    allb = R[(R["block"] == "broad_2025_2026") & R["en_two_15:59"] & R["ex_ask_15:59"].notna()].copy()
    allb["B0"] = (allb["en_bid_15:59"] - allb["ex_ask_15:59"] - 4 * COMM) / allb["m0"]
    allb["spy"] = allb["exit_date"].map(ret)
    k = allb["spy"].notna()
    print(f"\nindex hedge ceiling, broad 2025-26, N={int(k.sum())} of {len(allb)} with an SPY return on the reaction day")
    x, b = allb.loc[k, "spy"], allb.loc[k, "B0"]
    r_lin = float(np.corrcoef(x, b)[0, 1])
    r_abs = float(np.corrcoef(x.abs(), b)[0, 1])
    print("  corr(B0, SPY return)", round(r_lin, 3), "-> best linear index hedge removes at most", round(100 * r_lin**2, 2), "% of variance (in sample, ex post)")
    print("  corr(B0, |SPY return|)", round(r_abs, 3), "-> convex index exposure (long index straddle) at most", round(100 * r_abs**2, 2), "%")
    if a.log:
        log_trial(1736, "index hedge of the overnight market move: variance ceiling", "an ATM straddle has no delta at entry, so the market move enters through gamma, not linearly",
                  "broad_2025_26", None, None, "squared correlation of B0 with the SPY reaction-day return", "descriptive: no usable hedge",
                  override=(r_lin**2, np.nan, np.nan, int(k.sum()), np.nan))


if __name__ == "__main__":
    main()
