"""
round1.py
Lane C round 1, discovery block only (entry 2013-2018): does a volatility forecast known at the
reaction close predict the post-reaction diffusive premium, and does it make a hold-or-close rule
that beats always holding? Trials 1,841 to 1,846; hypotheses and mechanisms below were written
before this script was first run.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneC-post-event-vrp/round1.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lanec_lib as L

BASIS_RULE = "per trade, fraction of m0, net at touch; rule book minus always-hold, paired"

# (id, name, signal builder, tercile to close, hypothesis, mechanism)
SPECS = [
    (1841, "vrp_har_ex", lambda p: p["iv_pts"] - 100 * np.sqrt(p["har_ex"]), 0,
     "close the event at the reaction close when post-event IV minus HAR(ex-event) forecast is in "
     "the causal bottom tercile, else hold hedged",
     "IV below forecast realised vol means a negative diffusive premium over the remaining days, "
     "larger than the exit half-spread saved by holding"),
    (1842, "vrp_har_in", lambda p: p["iv_pts"] - 100 * np.sqrt(p["har_in"]), 0,
     "as 1841 with the HAR forecast fed the reaction-day squared return",
     "volatility clusters after the jump; a forecast that sees the gap prices the post-event "
     "realised vol better than one that blanks it (S3b blanked it)"),
    (1843, "gap_ratio", lambda p: p["gap_ratio"], 2,
     "close when the reaction gap over the entry implied move is in the causal top tercile",
     "realised vol stays high after large surprises, so the remaining premium is thin or negative"),
    (1844, "vrp_rv22", lambda p: p["iv_pts"] - 100 * np.sqrt(p["rv22"]), 0,
     "close when post-event IV minus trailing 22-day realised vol (ex events) is in the bottom "
     "tercile",
     "a model-free baseline for 1841: the simplest forecast of the remaining realised vol"),
    (1845, "vrp_har_ex_h5", lambda p: p["iv_pts"] - 100 * np.sqrt(p["har_ex"]), 0,
     "1841 restricted to events with 5 or more hedging sessions left",
     "with 1-3 sessions left the diffusive part is tiny next to the exit half-spread, so any "
     "forecast skill can only pay where days remain"),
]


def main() -> None:
    p = L.load()
    print(f"lane-ok events: {len(p)}; by block {p['block'].value_counts().to_dict()}")
    disc = p["block"] == "discovery"
    d0 = p[disc]
    # descriptive decomposition, discovery only
    hb = pd.cut(d0["n_hedge"], [0, 3, 10, 40], labels=["1-3", "4-10", "11+"])
    print("\nDISCOVERY decomposition, per trade, % of m0 (J and D_mid gross at the reaction mid):")
    print((d0.groupby(hb, observed=True)[["J", "D_mid", "D_net", "exit_half", "G", "H", "B"]]
           .mean() * 100).round(3).assign(n=d0.groupby(hb, observed=True).size()))
    print(f"vp_real (IV minus realised over remaining days, vol pts) median "
          f"{d0['vp_real'].median():+.2f}, mean {d0['vp_real'].mean():+.2f}")

    for tid, name, f, close_bin, hyp, mech in SPECS:
        sig = f(p)
        b_all = L.bins(p, sig)
        m = disc & (b_all >= 0)
        if name.endswith("_h5"):
            m &= p["n_hedge"] >= 5
        blk, b = p[m], b_all[m.to_numpy()]
        res = L.hold_or_close(blk, b == close_bin)
        sp_vp = L.tmb(blk, "vp_real", b)
        sp_d = L.tmb(blk, "D_mid", b)
        eff = res["effect"]
        sec = (f"rule level {L.fmt(res['level_rule'])}%; always-hold {L.fmt(res['level_hold'])}%; "
               f"G closed {100 * res['G_closed']:+.3f}% kept {100 * res['G_kept']:+.3f}%; "
               f"top-bottom vp_real {sp_vp[0]:+.2f} [{sp_vp[1]:+.2f}, {sp_vp[2]:+.2f}] vol pts; "
               f"top-bottom D_mid {100 * sp_d[0]:+.3f} [{100 * sp_d[1]:+.3f}, {100 * sp_d[2]:+.3f}]% m0")
        ok = eff["low"] > 0 and res["null_pct"] >= 95
        verdict = "pass discovery" if ok else "fail discovery"
        print(f"\n[{tid}] {name}: effect {L.fmt(eff)}% m0, null pct {res['null_pct']:.1f} -> {verdict}")
        print("   ", sec)
        L.log_trial({"trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": "2013-18",
                     "n": eff["n"], "effect": eff["point"], "ci_low": eff["low"],
                     "ci_high": eff["high"], "t": eff["t"], "null_pct": res["null_pct"],
                     "basis": BASIS_RULE, "verdict": verdict + " (exploratory)", "secondary": sec})

    # 1846: add a fresh unit at the reaction-close bid where the forecast premium is richest
    sig = p["iv_pts"] - 100 * np.sqrt(p["har_ex"])
    b_all = L.bins(p, sig)
    m = disc & (b_all >= 0) & p["A"].notna()
    blk, b = p[m], b_all[m.to_numpy()]
    top = b == 2
    lvl = L.ci(blk.loc[top, "A"], blk.loc[top, "exit_date"])
    nul = L.matched_random_null(blk["A"].to_numpy(float), top, L.mean)
    allA = L.ci(blk["A"], blk["exit_date"])
    verdict = "pass discovery" if lvl["low"] > 0 and nul.percentile >= 95 else "fail discovery"
    sec = f"all-event add-on level {L.fmt(allA)}%"
    print(f"\n[1846] add-on sale, top tercile vrp_har_ex: level {L.fmt(lvl)}% of post-event margin, "
          f"null pct {nul.percentile:.1f} -> {verdict}\n    {sec}")
    L.log_trial({"trial_id": 1846,
                 "hypothesis": "sell one more unit of the held straddle at the reaction-close bid, "
                               "hedged to expiry, only in the top causal tercile of IV minus HAR",
                 "mechanism": "where post-event IV most exceeds forecast realised vol the fresh "
                              "diffusive premium may exceed one entry half-spread",
                 "block": "2013-18", "n": lvl["n"], "effect": lvl["point"], "ci_low": lvl["low"],
                 "ci_high": lvl["high"], "t": lvl["t"], "null_pct": nul.percentile,
                 "basis": "per trade, fraction of post-event margin (0.20 spot + bid), net at touch, "
                          "book level",
                 "verdict": verdict + " (exploratory)", "secondary": sec})


if __name__ == "__main__":
    main()
