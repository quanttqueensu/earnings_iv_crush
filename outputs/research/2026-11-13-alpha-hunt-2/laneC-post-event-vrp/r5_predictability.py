"""
r5_predictability.py
Trial 1,855 (discovery 2013-18): is the post-reaction diffusive part predictable per event at all?
Causal terciles of the walk-forward forecast from 1,851 (IV, HAR, gap ratio, log days left,
|moneyness| at the reaction close); top minus bottom of realised D_net, and the top tercile's mean
D_net against a matched random null. A predictability test, not a book.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneC-post-event-vrp/r5_predictability.py [--block heldout]
"""

from __future__ import annotations

import argparse

import numpy as np

import lanec_lib as L
import round3 as r3
from earnings_iv_crush.research import hedged_hold as hh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", default="discovery", choices=["discovery", "heldout"])
    a = ap.parse_args()
    p = r3.features(L.load())
    p["pred_D"] = r3.walk_forward_pred(p, "D_net")
    b = hh.causal_bins(p["pred_D"].to_numpy(float), p["exit_date"], 3, L.MIN_PRIOR)
    m = ((p["block"] == a.block) & p["pred_D"].notna()).to_numpy() & (b >= 0)
    blk, bb = p[m], b[m]
    pt, lo, hi = hh.top_minus_bottom_ci(blk["D_net"].to_numpy(float), bb == 2, bb == 0,
                                        blk["exit_date"])
    nul = L.matched_random_null(blk["D_net"].to_numpy(float), bb == 2, L.mean)
    se = (hi - lo) / 3.92
    by = (blk.groupby(bb)[["D_net", "D_mid", "G", "exit_half"]].mean() * 100).round(3)
    print(by.assign(n=blk.groupby(bb).size()))
    print(f"[1855 {a.block}] top-bottom D_net {100 * pt:+.3f} [{100 * lo:+.3f}, {100 * hi:+.3f}]% "
          f"m0, N={len(blk)}, t={pt / se:+.2f}, null pct {nul.percentile:.1f}")
    ok = lo > 0 and nul.percentile >= 95 and pt / se >= 3
    tag = "2013-18" if a.block == "discovery" else "2019-24"
    v = ("pass" if ok else "fail") + (" discovery" if a.block == "discovery" else " held-out")
    L.log_trial({"trial_id": 1855, "hypothesis": "causal top tercile of the walk-forward D_net "
                 "forecast (1851 model) earns a larger realised diffusive part than the bottom",
                 "mechanism": "the remaining diffusive premium is set by the option's own state at "
                 "the reaction close (IV level, moneyness, days left), which the forecast reads",
                 "block": tag, "n": len(blk), "effect": pt, "ci_low": lo, "ci_high": hi,
                 "t": pt / se, "null_pct": nul.percentile,
                 "basis": "per trade, fraction of m0, D_net net of equity costs at the reaction-close "
                          "mid; top minus bottom tercile (predictability, not a book)",
                 "verdict": v + (" (exploratory)" if a.block == "discovery" else ""),
                 "secondary": "tercile table: " + by.to_dict().__repr__()})


if __name__ == "__main__":
    main()
