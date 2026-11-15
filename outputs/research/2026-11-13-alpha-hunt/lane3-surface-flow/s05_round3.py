"""
s05_round3.py
Round 3: the round 1 and 2 bins showed signal only where the straddle is a pure event bet
(at most one day to expiry after the exit). This round scores event richness and smile
concavity inside that tenor, one two-feature combination, and decomposes event richness into
gap cost and residual extrinsic value of the contract actually held.

Usage
-----
    python s05_round3.py [--block 2016 2019] [--log]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import lib

EXIT = lib.ROOT / "outputs/research/2026-11-07-pairwise-tercile-gates/exit_marks.parquet"


def build() -> pd.DataFrame:
    d = pd.read_parquet(lib.HERE / "all_features.parquet")
    x = pd.read_parquet(EXIT, columns=["ticker", "entry_date", "fwd_exit"])
    x["entry_date"] = pd.to_datetime(x["entry_date"]).dt.normalize()
    d = d.merge(x, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    # held contract at exit: intrinsic on the exit parity forward, the rest is extrinsic
    intr = (d["fwd_exit"] - d["strike"]).abs()
    d["gap_cost"] = intr / d["mid0"]
    d["extrinsic"] = (d["exit_px"] - intr) / d["mid0"]
    print(f"funnel decomposition: exit forward present {int(d['fwd_exit'].notna().sum())} of {len(d)}")
    d["short"] = d["tenor"] == "0-1d"
    for col, sign in (("rich_event", 1), ("wing_curv", -1)):
        s = d[d["short"]]
        tr, df = lib.top_bin(s, col, 3, sign)
        d[f"{col}_short_tr"] = tr.reindex(d.index, fill_value=False)
        d[f"{col}_short_def"] = (df & s[col].notna()).reindex(d.index, fill_value=False)
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", nargs=2, type=int, default=[2016, 2019])
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args()
    blk = (a.block[0], a.block[1])
    d = build()
    d.to_parquet(lib.HERE / "all_features.parquet")
    r_tr, r_def = lib.top_bin(d, "rich_event", 3)
    r_def &= d["rich_event"].notna()
    q_tr, q_def = lib.top_bin(d, "rich_event", 5)
    c_tr, c_def = lib.top_bin(d, "wing_curv", 3, -1)
    c_def &= d["wing_curv"].notna()
    specs = [
        (1703, d["rich_event_short_tr"], d["rich_event_short_def"],
         "R5s event richness, top tercile, tenor 0-1d only",
         "with at most a day left after exit the straddle is the event; richness against own "
         "history is cleanest there"),
        (1704, d["wing_curv_short_tr"], d["wing_curv_short_def"],
         "H6s concave smile, bottom tercile of wing over ATM IV, tenor 0-1d only",
         "the front smile is the event density only when little diffusive time is left"),
        (1705, q_tr, q_def & d["rich_event"].notna(),
         "R5q event richness, top causal quintile, all tenors",
         "selling only the richest events concentrates the effect if it is monotone"),
        (1706, r_tr & c_tr, r_def & c_def,
         "R5 x H6: rich against own history and concave smile",
         "two independent readings that the event premium exceeds the event distribution"),
    ]
    for tid, tr, df, hyp, mech in specs:
        print(f"\n[{tid}] {hyp}")
        res = lib.score(d, tr, df, blk)
        if a.log:
            ok = res.get("ci_low", -1) > 0 and res.get("null_pct", 0) >= 95 and res.get("t", 0) >= 3
            lib.log_trial(tid, hyp, mech, res, "pass discovery" if ok else "fail discovery")
    # ── decomposition of R5 (not a trial: same selection, other outcome columns) ──
    print("\nR5 decomposition, top tercile minus rest within cell (fractions of premium collected):")
    for col in ("y_gross", "gap_cost", "extrinsic", "mv_ratio", "im", "dte", "entry_spread"):
        r = lib.score(d, r_tr, r_def & d["fwd_exit"].notna(), blk, ycol=col, n_boot=1000, quiet=True)
        print(f"  {col:13s} {r['effect']:+.4f} [{r['ci_low']:+.4f}, {r['ci_high']:+.4f}] N {r['n_scored']}")
    b = d[r_def & d["year"].between(*blk) & (d["im_bin"] >= 0)]
    print("\nR5 terciles by year (mean y demeaned within cell, treated minus rest):")
    b = b.assign(y_dm=b["y"] - b.groupby("cell")["y"].transform("mean"), tr=r_tr.loc[b.index])
    print(b.groupby(["year", "tr"])["y_dm"].agg(["size", "mean"]).round(4).unstack().to_string())
    print("\nR5 treated: loss concentration (share of events with y < -1, i.e. loss above the premium)")
    print(b.groupby("tr")["y"].agg(n="size", mean="mean", median="median", p05=lambda s: s.quantile(0.05),
                                  tail=lambda s: (s < -1).mean()).round(4).to_string())


if __name__ == "__main__":
    main()
