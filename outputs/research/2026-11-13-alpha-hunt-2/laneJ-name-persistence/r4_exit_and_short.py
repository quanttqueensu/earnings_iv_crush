"""
r4_exit_and_short.py
Round 4, lane J, discovery 2013-18. Round 3 showed that the persistent name component is where
the extrinsic value sits after the print (reaction-session buy-back versus post-event decay),
and that it moves value between the two exits without changing the total. Two changes follow.

Trials
  2070 J20 name-conditional exit: buy back events whose name is in the causal bottom quintile of
       the EB post-reaction hedged leg (H - B), hold every other event; paired against the
       always-hold book on the same events, m0, net at touch.
  2071 J21 split-half persistence of the hold residual on 0-1 day tenors only, where the hold and
       the buy-back are nearly the same trade and the residual is the event pricing alone.
  2072 J22 EB name effect on 0-1 day residual value (track record from 0-1 day events only), top
       quintile, scored on y within cell, 0-1 day events.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/r4_exit_and_short.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib
from r2_components import attach, split_half
from earnings_iv_crush.research.protocol import date_clustered_ci


def main() -> None:
    d = attach(lib.load())
    d = d[d["im_bin"] >= 0].reset_index(drop=True)
    disc = d.year.between(*lib.BLOCKS["discovery"])

    print("\n== J20 name-conditional exit")
    s = lib.causal_name_effect(d, "hb", "expiry", shrink_to="zero")
    bins = lib.causal_quantile_bins(s["shrunk"].to_numpy(float), d["announce_date"], 5)
    low = bins == 0
    ok = (bins >= 0) & disc.to_numpy()
    b = d[ok]
    sw = low[ok]
    paired = np.where(sw, b["B"] - b["H"], 0.0)  # m0 units: X - H
    iv = date_clustered_ci(paired, b["announce_date"], np.mean)
    lvl = date_clustered_ci(np.where(sw, b["B"], b["H"]), b["announce_date"], np.mean)
    on = date_clustered_ci(b.loc[sw, "B"] - b.loc[sw, "H"], b.loc[sw, "announce_date"], np.mean)
    print(f"  [funnel] defined {int(ok.sum())}, switched to buy-back {int(sw.sum())} "
          f"({b.loc[sw, 'ticker'].nunique()} names)")
    print(f"  paired X - H per event {iv.point:+.5f} [{iv.low:+.5f}, {iv.high:+.5f}] of m0; on "
          f"switched events B - H {on.point:+.5f} [{on.low:+.5f}, {on.high:+.5f}]; book X level "
          f"{lvl.point:+.5f} [{lvl.low:+.5f}, {lvl.high:+.5f}] vs always-hold {b['H'].mean():+.5f}")
    sd = np.std(paired, ddof=1)
    lib.log_trial(2070, {
        "hyp": "J20 name-conditional exit (buy back bottom-quintile EB H-B names)",
        "block": "discovery 2013-2018", "N": int(ok.sum()), "n_treated": int(sw.sum()),
        "n_names": int(b.loc[sw, "ticker"].nunique()), "effect": iv.point, "ci_low": iv.low,
        "ci_high": iv.high, "t": iv.point / (sd / np.sqrt(len(paired))) if sd > 0 else np.nan,
        "null_pct": np.nan, "treated_level": lvl.point, "level_ci_low": lvl.low,
        "level_ci_high": lvl.high, "pool_level": float(b["H"].mean())},
        mechanism="the post-reaction hedged leg is a persistent name property (J11); where a "
        "name's has been lowest, holding past the reaction earns less than the exit spread saved",
        basis="paired per event, conditional book minus always-hold, on m0, net at touch; t uses "
        "iid se (date-clustered CI beside it); a change to the trade, so no selection null",
        label="exploratory", passed=bool(iv.low > 0))

    short = (d["tenor"] == "0-1d").to_numpy()
    ds = d[short].reset_index(drop=True)
    print(f"\n== J21 split-half persistence, 0-1 day tenor only ({len(ds)} events, "
          f"{int(ds.year.between(*lib.BLOCKS['discovery']).sum())} in discovery)")
    r = lib.within_block_residual(ds, "y")
    p = split_half(ds, r)
    print(f"  r {p['r']:+.4f} [{p['ci'][0]:+.4f}, {p['ci'][1]:+.4f}] null pct {p['null_pct']:.1f}; "
          f"names {p['n']}, mean events per half {p['nbar']:.1f}")
    lib.log_trial(2071, {"hyp": "J21 split-half persistence, hold y, 0-1 day tenor",
                         "block": "discovery 2013-15 vs 2016-18", "N": p["n"], "n_treated": "",
                         "n_names": p["n"], "effect": p["r"], "ci_low": p["ci"][0],
                         "ci_high": p["ci"][1], "t": p["r"] / p["null_sd"],
                         "null_pct": p["null_pct"], "treated_level": p["tau_point"],
                         "pool_level": p["tau_upper"]},
                  mechanism="with at most a day of life after the reaction the straddle is the "
                  "event alone; a name whose event is chronically over-priced shows it there",
                  basis="Pearson r of name mean cell x year residual y (H per unit mid premium, "
                  "net at touch), 0-1 day tenor, names with >= 3 events per half",
                  label="descriptive")

    print("\n== J22 EB name effect on 0-1 day residual value")
    s22 = lib.causal_name_effect(ds, "y", "expiry", shrink_to="zero")
    v = s22["shrunk"].to_numpy(float)
    if np.nanstd(v) == 0:
        print("  shrunken signal constant: tau2 = 0 on every date, selector undefined")
        return
    bins = lib.causal_quantile_bins(v, ds["announce_date"], 5, min_prior=100)
    r22 = lib.score(ds, pd.Series(bins == 4), pd.Series(bins >= 0), "discovery",
                    hyp="J22 EB 0-1 day residual value, top quintile", ycol="y", level_col="H")
    lib.log_trial(2072, r22, mechanism="as J21, used causally with EB shrinkage",
                  basis="within-cell treated minus untreated, per trade, y per unit mid premium, "
                  "net at touch, 0-1 day events; level H on m0 net at touch; quintile cuts from "
                  ">= 100 earlier signals", label="exploratory")


if __name__ == "__main__":
    main()
