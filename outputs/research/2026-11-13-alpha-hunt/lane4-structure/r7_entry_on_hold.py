"""r7_entry_on_hold.py: entry-side levers on top of the hedged and naked holds (real data).

H and naked come from the 2026-11-02 hedged-event-hold tables (15:59 chain marks, m0 = 0.20 x forward
+ 15:59 bid premium). The entry lift is added per event on the same contract and the same m0:
  E45   (15:45 bid - 15:59 bid) / m0
  PKs   (15:45 mid - 0.391 x 15:45 half-spread - 15:59 bid) / m0, fill probability p, else 15:59 touch.
15:45 quotes: tick panel for 2025-26 and megacap 2023-24; data/cache/entry_1545_chains for 2013-24.

Usage
-----
    python r7_entry_on_hold.py [--log]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import ROOT, ci, fmt, load_ticks, log_trial, tstat

RES = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
C45 = ROOT / "data" / "cache" / "entry_1545_chains"
PK = 0.391  # frozen discovery share of the half-spread (freeze_2026-11-13.md)


def q45_chain(tk: str, d: pd.Timestamp, strike: float, expiry: pd.Timestamp) -> tuple[float, float] | None:
    p = C45 / f"{tk}_{d:%Y-%m-%d}.parquet"
    if not p.exists():
        return None
    c = pd.read_parquet(p, columns=["bid_px_00", "ask_px_00", "symbol"]).groupby("symbol").tail(1)
    s = c["symbol"].str.strip()
    c = c[(s.str[-15:-9] == f"{expiry:%y%m%d}") & (s.str[-8:].astype(int) == int(round(strike * 1000)))]
    if len(c) != 2 or not ((c["bid_px_00"] > 0) & (c["ask_px_00"] > c["bid_px_00"])).all():
        return (np.nan, np.nan)
    return (float(c["bid_px_00"].sum()), float(c["ask_px_00"].sum()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args()
    parts = [pd.read_parquet(RES / f).assign(src=f) for f in ("events.parquet", "events_confirm_2025_26.parquet", "events_megacap.parquet")]
    e = pd.concat(parts, ignore_index=True)
    e = e[(e["status"] == "ok") & e["B"].notna() & e["H"].notna()].copy()
    e["uni"] = np.where(e["src"].str.contains("megacap"), "megacap", "broad")
    e = e.drop_duplicates(["uni", "ticker", "entry_date"])
    e["block"] = np.where(e["entry_date"] < "2020-01-01", "2013-19", np.where(e["entry_date"] < "2025-01-01", "2020-24", "2025-26"))
    t = load_ticks()
    t["uni"] = np.where(t["block"].str.startswith("megacap"), "megacap", "broad")
    t = t[t["en_two_15:45"]][["uni", "ticker", "entry_date", "strike", "expiry", "en_bid_15:45", "en_ask_15:45", "en_bid_15:59"]]
    t["expiry"] = pd.to_datetime(t["expiry"])
    e = e.merge(t, on=["uni", "ticker", "entry_date"], how="left", suffixes=("", "_t"))
    same = (e["strike"] == e["strike_t"]) & (e["expiry"] == e["expiry_t"])
    e["b45"] = e["en_bid_15:45"].where(same)
    e["a45"] = e["en_ask_15:45"].where(same)
    e["q_src"] = np.where(e["b45"].notna(), "ticks", "none")
    need = e["b45"].isna() & (e["entry_date"] < "2025-01-01")
    n_file = 0
    for i in e.index[need]:
        r = e.loc[i]
        q = q45_chain(r["ticker"], r["entry_date"], r["strike"], r["expiry"])
        if q is None:
            continue
        n_file += 1
        if np.isfinite(q[0]):
            e.loc[i, ["b45", "a45"]] = q
            e.loc[i, "q_src"] = "chain1545"
    print("funnel by universe x block: events with H and B | tick join | tick same contract | 15:45 chain file | usable 15:45 quote")
    for (u, b), g in e.groupby(["uni", "block"]):
        print(f"  {u:8s} {b}: {len(g):5d} | {int(g['strike_t'].notna().sum()):5d} | {int((g['q_src']=='ticks').sum()):5d} | "
              f"{int((g['q_src']=='chain1545').sum()):5d} (chain) | {int(g['b45'].notna().sum()):5d}")
    k = e[e["b45"].notna()].copy()
    # outcome dependence of the 15:45 coverage
    for (u, b), g in e.groupby(["uni", "block"]):
        c = g["b45"].notna()
        if c.sum() >= 30 and (~c).sum() >= 30:
            print(f"  coverage check {u} {b}: H with quote {100*g.loc[c,'H'].mean():+.2f}, without {100*g.loc[~c,'H'].mean():+.2f}")
    mid45, hs45 = (k["b45"] + k["a45"]) / 2, (k["a45"] - k["b45"]) / 2
    k["e45"] = (k["b45"] - k["s0"]) / k["m0"]
    k["pk"] = (mid45 - PK * hs45 - k["s0"]) / k["m0"]
    # sanity: tick 15:59 bid against the table's s0
    chk = k[k["q_src"] == "ticks"]
    print("reconciliation: tick 15:59 bid vs table s0, median abs rel diff", round(float(((chk["en_bid_15:59"] - chk["s0"]).abs() / chk["s0"]).median()), 4),
          "| share within 2%", round(float((((chk["en_bid_15:59"] - chk["s0"]).abs() / chk["s0"]) < 0.02).mean()), 3))
    tid = 1737
    for (u, b), g in k.groupby(["uni", "block"]):
        if len(g) < 30:
            print(f"\n=== {u} {b}: N={len(g)} too few, skipped")
            continue
        dt = g["exit_date"]
        print(f"\n=== {u} {b}: N={len(g)} (15:45 source {g['q_src'].value_counts().to_dict()})")
        print(f"  entry lifts: E45 {fmt(ci(g['e45'], dt))} | package fill 1 {fmt(ci(g['pk'], dt))}")
        arms = {"B": g["B"], "H": g["H"], "NK": g["naked"], "H+E45": g["H"] + g["e45"], "NK+E45": g["naked"] + g["e45"]}
        for p in (0.25, 0.5, 1.0):
            arms[f"H+PK p{p}"] = g["H"] + p * g["pk"]
            arms[f"NK+PK p{p}"] = g["naked"] + p * g["pk"]
        for nm, x in arms.items():
            print(f"  {nm:12s} level {fmt(ci(x, dt)):34s} sd {100*x.std():5.2f} | vs B {fmt(ci(x - g['B'], dt)):34s} | vs H {fmt(ci(x - g['H'], dt))}")
        if a.log:
            for j, nm in enumerate(("H+E45", "H+PK p0.5", "NK+E45", "NK+PK p0.5")):
                log_trial(tid + j, f"level of {nm} (entry lever on the hold)", "holding removes the exit cross; entry levers attack the remaining crossing",
                          f"{u}_{b}", arms[nm], dt, "level, fraction of m0, net, per trade" + ("" if "PK" not in nm else "; package share 0.391 extrapolated, fill 0.5 assumed"),
                          "exploratory (blocks viewed)")


if __name__ == "__main__":
    main()
