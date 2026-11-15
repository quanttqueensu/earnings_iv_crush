"""
r3_decompose.py
Round 3, lane J, discovery 2013-18. Tests whether the one discovery pass (J14, trial 2,064: names
with the least extrinsic value left at the exit mark) is the closed spread gate or the closed
term-structure jump gate under another name, and whether the persistent post-reaction hedged leg
lifts the hold.

Trials
  2065 J15 J14 signal, contrast within cell x causal jump-share tercile, scored on yb
  2066 J16 J14 signal scored on yb_mid (both legs at the mid, exit mid defined only)
  2067 J17 EB on mid-only extrinsic (two-sided exit mid), bottom quintile, scored on yb
  2068 J18 split-half persistence of extrinsic after spread / implied move / dte / jump share
  2069 J19 EB on the post-reaction hedged leg (H - B), top quintile, scored on the hold y
Unlogged: decomposition of J14's contrast into extrinsic, gap cost and cost-and-fee parts.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/r3_decompose.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib
from r2_components import attach, split_half

BY = ("within-cell treated minus untreated, per trade, {o} per unit mid premium, {b}; "
      "level {l} on m0 net at touch")


def quint(d: pd.DataFrame, s: pd.DataFrame, sign: int) -> tuple[pd.Series, pd.Series]:
    bins = lib.causal_quantile_bins(sign * s["shrunk"].to_numpy(float), d["announce_date"], 5)
    return pd.Series(bins == 4, index=d.index), pd.Series(bins >= 0, index=d.index)


def main() -> None:
    d = attach(lib.load())
    d = d[d["im_bin"] >= 0].reset_index(drop=True)
    intr = (d["fwd_exit"] - d["strike"]).abs()
    d["extr_mid"] = np.where(np.isfinite(d["exit_mid"]), (d["exit_mid"] - intr) / d["mid0"], np.nan)
    d["neg_extr"] = -d["extrinsic"]
    d["neg_gap"] = -d["gap_cost"]
    d["cost_part"] = d["yb"] - (1 - d["extrinsic"] - d["gap_cost"])
    jb = lib.causal_quantile_bins(d["jump_share"].to_numpy(float), d["announce_date"], 3)
    d["jcell"] = np.where(jb >= 0, d["cell"] * 10 + jb, -1)
    disc = d.year.between(*lib.BLOCKS["discovery"])
    print(f"[funnel] discovery {int(disc.sum())}; jump share tercile assigned "
          f"{int((disc & (jb >= 0)).sum())}; two-sided exit mid {int((disc & d.extr_mid.notna()).sum())}")

    s14 = lib.causal_name_effect(d, "extrinsic", "exit_date", shrink_to="zero")
    f14, def14 = quint(d, s14, -1)

    print("\n-- decomposition of J14 (2,064), within cell, discovery (not trials)")
    for col in ("yb", "neg_extr", "neg_gap", "cost_part"):
        r = lib.score(d, f14, def14, "discovery", hyp=f"J14 parts {col}", ycol=col,
                      level_col="B", quiet=True)
        print(f"  Delta {col:9s} {r['effect']:+.4f} [{r['ci_low']:+.4f}, {r['ci_high']:+.4f}]")
    blk = d[def14 & disc]
    print("  treated vs untreated medians: half_spread, exit mid missing share, jump_share, im, dte")
    for k, g in blk.groupby(f14[def14 & disc]):
        print(f"    {'treated' if k else 'rest   '} {g.half_spread.median():.4f} "
              f"{g.exit_mid.isna().mean():.3f} {g.jump_share.median():.3f} "
              f"{g.implied_move.median():.4f} {g.dte.median():.0f}")

    print()
    r = lib.score(d, f14, def14 & (d["jcell"] >= 0), "discovery", hyp="J15 J14 within jump-share "
                  "tercile", ycol="yb", level_col="B", cellcol="jcell")
    lib.log_trial(2065, r, mechanism="as J14; if low retained extrinsic is only a high event "
                  "share of the premium (the closed jump gate), the contrast inside jump-share "
                  "terciles vanishes", basis=BY.format(o="yb", b="net at touch", l="B") +
                  "; cell = implied-move tercile x tenor x causal jump-share tercile",
                  label="exploratory")
    r = lib.score(d, f14, def14, "discovery", hyp="J16 J14 at the mid", ycol="yb_mid",
                  level_col="B")
    lib.log_trial(2066, r, mechanism="as J14; at the mid the exit spread cannot carry it",
                  basis=BY.format(o="1 - exit mid / entry mid", b="gross at the mid", l="B"),
                  label="exploratory")
    s17 = lib.causal_name_effect(d, "extr_mid", "exit_date", shrink_to="zero")
    f17, def17 = quint(d, s17, -1)
    r = lib.score(d, f17, def17, "discovery", hyp="J17 EB mid-only extrinsic, bottom quintile",
                  ycol="yb", level_col="B")
    lib.log_trial(2067, r, mechanism="as J14 with the track record built only from events with a "
                  "two-sided exit mid, so exit quote quality cannot enter the signal",
                  basis=BY.format(o="yb", b="net at touch", l="B"), label="exploratory")

    print("\n== J18 split-half persistence of extrinsic after controls")
    res = lib.within_block_residual(d, "extrinsic", ["half_spread", "log_im", "dte", "jump_share"])
    p = split_half(d, res)
    print(f"  r {p['r']:+.4f} [{p['ci'][0]:+.4f}, {p['ci'][1]:+.4f}] null pct {p['null_pct']:.1f}; "
          f"names {p['n']}; implied name sd {p['tau_point']:.4f}")
    lib.log_trial(2068, {"hyp": "J18 split-half persistence, extrinsic after controls",
                         "block": "discovery 2013-15 vs 2016-18", "N": p["n"], "n_treated": "",
                         "n_names": p["n"], "effect": p["r"], "ci_low": p["ci"][0],
                         "ci_high": p["ci"][1], "t": p["r"] / p["null_sd"],
                         "null_pct": p["null_pct"], "treated_level": p["tau_point"],
                         "pool_level": p["tau_upper"]},
                  mechanism="the extrinsic a name keeps after its print is a name property beyond "
                  "its spread, implied move, tenor and event share of the premium",
                  basis="Pearson r of name means of extrinsic at exit per unit entry mid, cell x "
                  "year residual less OLS on half-spread, log implied move, dte, jump share",
                  label="descriptive")

    print()
    s19 = lib.causal_name_effect(d, "hb", "expiry", shrink_to="zero")
    f19, def19 = quint(d, s19, 1)
    r = lib.score(d, f19, def19, "discovery", hyp="J19 EB post-reaction hedged leg, top quintile",
                  ycol="y", level_col="H")
    lib.log_trial(2069, r, mechanism="a persistent post-event variance premium (J11) earns the "
                  "hold more on names where it has been high, unless the buy-back part offsets",
                  basis=BY.format(o="y", b="net at touch", l="H"), label="exploratory")
    for col in ("yb", "hb"):
        q = lib.score(d, f19, def19, "discovery", hyp=f"J19 parts {col}", ycol=col,
                      level_col="H", quiet=True)
        print(f"  J19 part Delta {col} {q['effect']:+.4f} [{q['ci_low']:+.4f}, {q['ci_high']:+.4f}]")


if __name__ == "__main__":
    main()
