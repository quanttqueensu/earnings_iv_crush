"""
round3.py
Lane C round 3, discovery block only (entry 2013-2018). Trials 1,851 and 1,852, written after the
round-2 diagnosis and before this script was first run.

1851  forecast-implied hold-or-close: a walk-forward regression of the diffusive part D_net on
      volatility features known at the reaction close; close only where the forecast D_net is
      below minus the exit half-spread (the closing cost is known at the decision).
1852  name persistence of the post-event premium: at entry, keep names whose earlier events
      (settled before this entry) earned the highest diffusive part; score the event hold H.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneC-post-event-vrp/round3.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import build_panel as bp
import lanec_lib as L
from earnings_iv_crush.research import hedged_hold as hh

FEE = bp.FEE
FEATS = ["iv_pts", "har_pts", "gap_ratio", "log_h", "abs_mny"]
BASIS_RULE = "per trade, fraction of m0, net at touch; rule book minus always-hold, paired"


def features(p: pd.DataFrame) -> pd.DataFrame:
    p = p.copy()
    p["har_pts"] = 100 * np.sqrt(p["har_ex"])
    p["log_h"] = np.log(p["n_hedge"])
    p["abs_mny"] = p["moneyness1"].abs()
    return p


def walk_forward_pred(p: pd.DataFrame, target: str) -> np.ndarray:
    """Annual refit: events of year Y are predicted from events whose expiry precedes 1 Jan Y."""
    pred = np.full(len(p), np.nan)
    yrs = p["exit_date"].dt.year
    for y in sorted(yrs.unique()):
        train = p[(p["expiry"] < pd.Timestamp(f"{y}-01-01"))].dropna(subset=FEATS + [target])
        test = (yrs == y).to_numpy() & p[FEATS].notna().all(axis=1).to_numpy()
        if len(train) < L.MIN_PRIOR or not test.any():
            continue
        x = np.column_stack([np.ones(len(train)), train[FEATS].to_numpy(float)])
        coef, *_ = np.linalg.lstsq(x, train[target].to_numpy(float), rcond=None)
        xt = np.column_stack([np.ones(test.sum()), p.loc[test, FEATS].to_numpy(float)])
        pred[test] = xt @ coef
        print(f"  {y}: trained on {len(train)}, coef "
              + ", ".join(f"{n} {c:+.4f}" for n, c in zip(["c"] + FEATS, coef)))
    return pred


def name_history(e: pd.DataFrame, p: pd.DataFrame, min_hist: int = 3) -> np.ndarray:
    """Mean D_mid of the name's earlier events whose expiry precedes this entry; NaN if too few."""
    by = {t: g.sort_values("expiry") for t, g in p.groupby("ticker")}
    out = np.full(len(e), np.nan)
    for i, (t, d0) in enumerate(zip(e["ticker"], e["entry_date"])):
        g = by.get(t)
        if g is None:
            continue
        prior = g.loc[g["expiry"] < d0, "D_mid"]
        if len(prior) >= min_hist:
            out[i] = float(prior.mean())
    return out


def log(tid: int, hyp: str, mech: str, eff: dict, null_pct: float, basis: str, verdict: str,
        sec: str) -> None:
    print(f"\n[{tid}] {L.fmt(eff)}  null pct {null_pct:.1f} -> {verdict}\n    {sec}")
    L.log_trial({"trial_id": tid, "hypothesis": hyp, "mechanism": mech, "block": "2013-18",
                 "n": eff["n"], "effect": eff["point"], "ci_low": eff["low"],
                 "ci_high": eff["high"], "t": eff["t"], "null_pct": null_pct, "basis": basis,
                 "verdict": verdict + " (exploratory)", "secondary": sec})


def main() -> None:
    p = features(L.load())
    p["pred_D"] = walk_forward_pred(p, "D_net")
    m = (p["block"] == "discovery") & p["pred_D"].notna()
    blk = p[m]
    close = (blk["pred_D"] + blk["exit_half"] + 2 * FEE / blk["m0"] < 0).to_numpy()
    print(f"1851: discovery events with a forecast {len(blk)}, closed {int(close.sum())}")
    corr = np.corrcoef(blk["pred_D"], blk["D_net"])[0, 1]
    if close.sum() == 0:
        print("  the rule closes nothing in discovery; the trial is degenerate")
        L.log_trial({"trial_id": 1851, "hypothesis": "walk-forward forecast hold-or-close",
                     "block": "2013-18", "n": len(blk), "verdict": "fail discovery: closes "
                     "nothing (forecast D_net never below minus the exit half-spread)",
                     "secondary": f"corr(pred, D_net) {corr:+.3f}"})
    else:
        res = L.hold_or_close(blk, close)
        v = "pass discovery" if res["effect"]["low"] > 0 and res["null_pct"] >= 95 else \
            "fail discovery"
        sec = (f"closed {res['n_closed']}; G closed {100 * res['G_closed']:+.3f}% kept "
               f"{100 * res['G_kept']:+.3f}%; rule level {L.fmt(res['level_rule'])}%; "
               f"corr(pred D_net, D_net) {corr:+.3f}")
        log(1851, "walk-forward OLS of D_net on IV, HAR, gap ratio, log days left and moneyness at "
                  "the reaction close (annual refit, expiries before the fit year only); close "
                  "where forecast D_net + exit half-spread + saved fees < 0",
            "combines every volatility feature and uses the known closing cost as the threshold, "
            "so the rule closes only where the forecast loss exceeds what closing costs",
            res["effect"], res["null_pct"], BASIS_RULE, v, sec)

    # ── 1852 name persistence of D at entry, on the full event universe ──
    e = pd.read_parquet(L.HERE / "entry_panel.parquet").sort_values("entry_date")
    e = e.reset_index(drop=True)
    e["hist_D"] = name_history(e, p)
    b = hh.causal_bins(e["hist_D"].to_numpy(float), e["entry_date"], 3, L.MIN_PRIOR)
    md = e["year"].between(2013, 2018).to_numpy() & (b >= 0)
    blk = e[md]
    un = e[e["year"].between(2013, 2018).to_numpy() & (b < 0)]
    print(f"\n1852: discovery assigned {len(blk)} (H {100 * blk['H'].mean():+.3f}%), unassigned "
          f"{len(un)} (H {100 * un['H'].mean():+.3f}%)")
    top = b[md] == 2
    lvl = L.ci(blk.loc[top, "H"], blk.loc[top, "exit_date"])
    nul = L.matched_random_null(blk["H"].to_numpy(float), top, L.mean)
    pt, lo, hi = hh.top_minus_bottom_ci(blk["H"].to_numpy(float), top, b[md] == 0,
                                        blk["exit_date"])
    pdm = p.merge(blk.assign(bin=b[md])[["ticker", "entry_date", "bin"]],
                  on=["ticker", "entry_date"], how="inner")
    dp, dl, dh = hh.top_minus_bottom_ci(pdm["D_mid"].to_numpy(float), pdm["bin"] == 2,
                                        pdm["bin"] == 0, pdm["exit_date"])
    v = "pass discovery" if lvl["low"] > 0 and nul.percentile >= 95 else "fail discovery"
    sec = (f"top-bottom H {100 * pt:+.3f} [{100 * lo:+.3f}, {100 * hi:+.3f}]%; top-bottom D_mid on "
           f"two-sided subset (N={len(pdm)}) {100 * dp:+.3f} [{100 * dl:+.3f}, {100 * dh:+.3f}]%")
    log(1852, "at entry keep names in the causal top tercile of their own mean post-event "
              "diffusive part D_mid over earlier settled events (3 or more); hedged hold",
        "a persistent name-level post-event premium (slow retail unwinding, de Silva, So and Smith "
        "2025) would show up as D persistence; differs from the closed name-persistence overlay by "
        "scoring the post-reaction diffusive part, not the next-session P&L",
        lvl, nul.percentile, "per trade, fraction of m0, net at touch, top-tercile book level", v,
        sec)


if __name__ == "__main__":
    main()
