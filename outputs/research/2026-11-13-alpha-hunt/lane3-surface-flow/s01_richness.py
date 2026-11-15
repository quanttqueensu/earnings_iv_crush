"""
s01_richness.py
Round 1: richness = log implied move minus the walk-forward forecast of the log absolute move.

Forecast models are refitted each calendar year on events whose exit precedes 1 January, so the
forecast at an event uses strictly earlier events only. Richness cuts are causal as well.

Usage
-----
    python s01_richness.py [--block 2016 2019] [--log]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import lib

HIST_N, HIST_MIN = 8, 4
FIRST_OOS = 2016


def add_history(ev: pd.DataFrame) -> pd.DataFrame:
    hm = np.full(len(ev), np.nan)
    hr = np.full(len(ev), np.nan)
    for _, g in ev.groupby("ticker"):
        exits = g["exit_date"].to_numpy()
        y = g["ylog"].to_numpy()
        ratio = (g["ylog"] - g["log_im"]).to_numpy()
        for idx, dt in zip(g.index, g["entry_date"].to_numpy(), strict=True):
            prior = np.where(exits < dt)[0]
            if len(prior) >= HIST_MIN:
                last = prior[-HIST_N:]
                hm[idx], hr[idx] = y[last].mean(), ratio[last].mean()
    ev["hist_move"], ev["hist_ratio"] = hm, hr
    return ev


def walk_forward(ev: pd.DataFrame, cols: list[str], name: str) -> pd.DataFrame:
    full = ev[cols].notna().all(axis=1)
    ev[name] = np.nan
    for yr in range(FIRST_OOS, int(ev["year"].max()) + 1):
        tr = (ev["exit_date"] < pd.Timestamp(f"{yr}-01-01")) & full
        te = (ev["year"] == yr) & full
        if tr.sum() < 200:
            raise ValueError(f"{name}: training set for {yr} has {int(tr.sum())} events")
        xx = np.column_stack([np.ones(int(tr.sum())), ev.loc[tr, cols].to_numpy(float)])
        beta = np.linalg.lstsq(xx, ev.loc[tr, "ylog"].to_numpy(float), rcond=None)[0]
        ev.loc[te, name] = beta[0] + ev.loc[te, cols].to_numpy(float) @ beta[1:]
        if yr in (FIRST_OOS, int(ev["year"].max())):
            print(f"  {name} {yr}: n_train {int(tr.sum())}, beta {np.round(beta, 3).tolist()}")
    return ev


def build() -> pd.DataFrame:
    d = add_history(lib.load_events())
    d = walk_forward(d, ["log_im", "jump_share"], "f_js")
    d = walk_forward(d, ["log_im", "jump_share", "hist_move", "hist_ratio"], "f_hist")
    d = walk_forward(d, ["log_im"], "f_im")
    d["rich_js"] = d["log_im"] - d["f_js"]
    d["rich_hist"] = d["log_im"] - d["f_hist"]
    d["rich_im"] = d["log_im"] - d["f_im"]
    # the part of richness that is not implied move: residual jump share effect only
    d["neg_jump_share"] = -d["jump_share"]
    # own-history-only richness: log implied move minus the name's mean log move
    d["rich_own"] = d["log_im"] - d["hist_move"]
    print(
        "funnel richness: "
        + ", ".join(f"{c} defined {int(d[c].notna().sum())}" for c in ["rich_js", "rich_hist", "rich_own"])
    )
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", nargs=2, type=int, default=[2016, 2019])
    ap.add_argument("--log", action="store_true", help="append the scored variants to trials.csv")
    a = ap.parse_args()
    blk = (a.block[0], a.block[1])
    d = build()
    d.to_parquet(lib.HERE / "richness_events.parquet")
    m = d["year"].between(*blk)
    print(f"\nblock {blk}: correlations (Spearman) among features")
    cc = ["rich_js", "rich_hist", "rich_own", "log_im", "jump_share", "dte", "iv_term_spread"]
    print(d.loc[m, cc].corr(method="spearman").round(2).to_string())

    specs = [
        (1689, "rich_js", 3, "R1 top causal tercile of richness (log IM minus jump_share forecast)"),
        (1690, "rich_js", 5, "R1b top causal quintile of richness (sell only the richest)"),
        (1691, "rich_hist", 3, "R2 top tercile of richness with name-history forecast"),
        (1692, "rich_own", 3, "R3 top tercile of log IM minus own mean log move (no term structure)"),
        (1693, "neg_jump_share", 3, "R4 bottom tercile of jump_share (the non-IM part of richness)"),
    ]
    mech = (
        "implied move above the out-of-sample forecast move means less expected gap cost per "
        "unit of premium, so the short straddle keeps more of it"
    )
    for tid, col, nb, hyp in specs:
        print(f"\n[{tid}] {hyp}")
        tr, df = lib.top_bin(d, col, nb)
        res = lib.score(d, tr, df & d[col].notna(), blk)
        print(lib.bins_table(d, col, blk, nb).to_string())
        print("  within tenor bucket:")
        print(lib.bins_table(d, col, blk, 3, by="tenor").to_string())
        print("  within implied-move tercile:")
        print(lib.bins_table(d, col, blk, 3, by="im_bin").to_string())
        if a.log:
            ok = (
                res.get("ci_low", -1) > 0
                and res.get("null_pct", 0) >= 95
                and res.get("t", 0) >= 3
            )
            lib.log_trial(tid, hyp, mech, res, "pass discovery" if ok else "fail discovery")


if __name__ == "__main__":
    main()
