"""
round4.py
Lane C round 4, discovery block only (entry 2013-2018). Trials 1,853 and 1,854, written after the
round-3 diagnosis and before this script was first run. Both are discovery-derived fixes of 1,851.

1853  1,851 with a margin of safety: close only where the forecast hold gain is below -c, with c
      chosen each year from the earlier years' out-of-sample forecasts (grid 0, 0.5, 1, 2% of m0).
1854  1,851 plus the market's volatility state at the entry-session close (VIX, VIX minus SPY
      20-day realised), because the worst diffusive losses clustered on market-wide dates.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneC-post-event-vrp/round4.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lanec_lib as L
import round3 as r3

MACRO = (L.ROOT / "outputs" / "research" / "2026-11-13-alpha-hunt" / "lane1-macro"
         / "macro_daily.parquet")
C_GRID = (0.0, 0.005, 0.01, 0.02)


def gain(blk: pd.DataFrame, close: np.ndarray) -> float:
    return float(np.where(close, blk["B"] - blk["H"], 0.0).mean())


def threshold_rule(p: pd.DataFrame) -> np.ndarray:
    """Close iff pred G < -c_Y, c_Y chosen on strictly earlier years' out-of-sample forecasts."""
    pg = p["pred_D"] + p["exit_half"] + 2 * r3.FEE / p["m0"]
    yrs = p["exit_date"].dt.year
    close = np.zeros(len(p), bool)
    for y in sorted(yrs[pg.notna()].unique()):
        past = p[(yrs < y) & pg.notna() & (p["expiry"] < pd.Timestamp(f"{y}-01-01"))]
        if len(past) < L.MIN_PRIOR:
            c = 0.0
        else:
            c = max(C_GRID, key=lambda c: gain(past, (pg[past.index] < -c).to_numpy()))
        cur = (yrs == y) & pg.notna()
        close[cur.to_numpy()] = (pg[cur] < -c).to_numpy()
        print(f"  {y}: c = {100 * c:.1f}% of m0, closes {int(close[cur.to_numpy()].sum())}")
    return close


def score(tid: int, p: pd.DataFrame, close: np.ndarray, hyp: str, mech: str) -> None:
    m = ((p["block"] == "discovery") & p["pred_D"].notna()).to_numpy()
    blk, cl = p[m], close[m]
    corr = np.corrcoef(blk["pred_D"], blk["D_net"])[0, 1]
    if cl.sum() == 0:
        print(f"[{tid}] closes nothing in discovery")
        L.log_trial({"trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": "2013-18",
                     "n": len(blk), "verdict": "fail discovery: closes nothing (exploratory)",
                     "secondary": f"corr(pred, D_net) {corr:+.3f}"})
        return
    res = L.hold_or_close(blk, cl)
    v = "pass discovery" if res["effect"]["low"] > 0 and res["null_pct"] >= 95 else "fail discovery"
    sec = (f"closed {res['n_closed']}; G closed {100 * res['G_closed']:+.3f}% kept "
           f"{100 * res['G_kept']:+.3f}%; rule level {L.fmt(res['level_rule'])}%; "
           f"corr(pred D_net, D_net) {corr:+.3f}")
    print(f"\n[{tid}] {L.fmt(res['effect'])} null pct {res['null_pct']:.1f} -> {v}\n    {sec}")
    L.log_trial({"trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": "2013-18",
                 "n": res["effect"]["n"], "effect": res["effect"]["point"],
                 "ci_low": res["effect"]["low"], "ci_high": res["effect"]["high"],
                 "t": res["effect"]["t"], "null_pct": res["null_pct"], "basis": r3.BASIS_RULE,
                 "verdict": v + " (exploratory, discovery-derived)", "secondary": sec})


def main() -> None:
    p = r3.features(L.load())
    # closed set of 1851 decomposed (discovery), to see what drives its selection
    p["pred_D"] = r3.walk_forward_pred(p, "D_net")
    m = (p["block"] == "discovery") & p["pred_D"].notna()
    blk = p[m]
    cl = (blk["pred_D"] + blk["exit_half"] + 2 * r3.FEE / blk["m0"] < 0)
    print("1851 closed vs kept (discovery, % of m0):")
    print((blk.groupby(cl)[["G", "D_net", "exit_half", "pred_D"]].mean() * 100).round(3)
          .assign(n=blk.groupby(cl).size(),
                  abs_mny=blk.groupby(cl)["abs_mny"].mean().round(3),
                  n_hedge=blk.groupby(cl)["n_hedge"].mean().round(1)))

    score(1853, p, threshold_rule(p),
          "1851 with a walk-forward safety margin: close only where forecast G < -c, c chosen "
          "yearly from earlier years' out-of-sample forecasts",
          "1851's closed set sat at G +0.19%: forecasts are calibrated but noisy, so only the "
          "deep tail of forecast losses should be closed")

    mac = pd.read_parquet(MACRO)[["vix", "vix_minus_rv20"]]
    mac.index = pd.to_datetime(mac.index).normalize()
    q = p.merge(mac, left_on=p["entry_date"].dt.normalize(), right_index=True, how="left")
    q = q.drop(columns=["key_0"], errors="ignore")
    print(f"\nmacro join: vix present {int(q['vix'].notna().sum())} of {len(q)}")
    r3.FEATS = r3.FEATS + ["vix", "vix_minus_rv20"]
    q["pred_D"] = r3.walk_forward_pred(q, "D_net")
    pg = q["pred_D"] + q["exit_half"] + 2 * r3.FEE / q["m0"]
    score(1854, q, (pg < 0).to_numpy(),
          "1851 plus VIX and VIX minus SPY 20-day realised at the entry-session close",
          "the worst diffusive losses come from market-wide shocks during the hold; index vol "
          "state carries the systematic part of the remaining variance that name HAR cannot")


if __name__ == "__main__":
    main()
