"""
variants.py
Lane E2: discovery iterations 2,715 to 2,720 (diagnosis.log entry 4). Each run appends its row to
trials.csv; run each trial once.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E2-informed-flow/variants.py --trial 2715
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import lib
import score_discovery as sd
from earnings_iv_crush.research.hedged_hold import causal_bins

DATE = "entry_date"


def causal_resid(d: pd.DataFrame, y: str, x: str, min_prior: int = lib.MIN_PRIOR) -> np.ndarray:
    """y minus its OLS fit on x, coefficients from strictly earlier dates only."""
    out = np.full(len(d), np.nan)
    dates = d[DATE].dt.normalize().to_numpy()
    yy, xx = d[y].to_numpy(float), d[x].to_numpy(float)
    ok = np.isfinite(yy) & np.isfinite(xx)
    for day in np.unique(dates):
        prior = ok & (dates < day)
        now = ok & (dates == day)
        if prior.sum() < min_prior or not now.any():
            continue
        b, a = np.polyfit(xx[prior], yy[prior], 1)
        out[now] = yy[now] - (a + b * xx[now])
    return out


def long_bottom(d: pd.DataFrame, sig: str, outcome: str) -> dict:
    """Long-only the bottom causal quintile; matched null draws the same number of longs."""
    v = d[sig].where(d["n_signed"] >= lib.MIN_SIGNED)
    b = causal_bins(v.to_numpy(), d[DATE], lib.N_BINS, lib.MIN_PRIOR)
    pool = d.assign(bin=b)
    pool = pool[(pool["bin"] >= 0) & pool[outcome].notna()]
    pos = pool[pool["bin"] == 0]
    net = (pos[outcome] - pos["cost"]).to_numpy()
    m = lib.mean_ci(net, pos[DATE])
    sh = lib.sharpe_ci(net, pos[DATE])
    sdb = (m.high - m.low) / (2 * 1.96)
    p_mat = lib.null_matched(pool[outcome].to_numpy(), pool["cost"].to_numpy(), len(pos), 0,
                             m.point)
    p_dir = lib.null_random_direction(None, pos[outcome].to_numpy(), pos["cost"].to_numpy(),
                                      m.point)
    return {"n": len(pos), "n_long": len(pos), "n_short": 0, "pool": len(pool),
            "dropped_no_outcome": 0, "effect": m.point, "ci_low": m.low, "ci_high": m.high,
            "t": m.point / sdb, "sharpe": sh.point, "sharpe_lo": sh.low, "sharpe_hi": sh.high,
            "gross": pos[outcome].mean(), "cost": pos["cost"].mean(),
            "long_gross": pos[outcome].mean(), "short_gross": np.nan, "null_dir_pct": p_dir,
            "null_matched_pct": p_mat, "spearman_pool": np.nan, "clusters": m.clusters}


SPEC = {
    2715: "S residualised on the 15:00-15:50 forward move (causal OLS); long top, short bottom",
    2716: "S from trades >= 10 contracts (floor 10 such contracts); long top, short bottom",
    2717: "premium-weighted S; long top, short bottom",
    2718: "reversed: long bottom quintile of S, short top (price-pressure reading)",
    2719: "long-only bottom quintile of S (post hoc, from the 2,712 quintile table)",
    2720: "15:00-15:50 forward move as reversal: long bottom quintile of the move, short top",
    2721: "reversed book on delta-weighted S (S_delta): long bottom quintile, short top",
    2722: "2,721 restricted to |K/F(15:50) - 1| <= 2% (breakpoints from all events)",
}


def run(tid: int, outcome: str = "R_prim", d: pd.DataFrame | None = None) -> dict:
    d = sd.frame("R_co") if d is None else d
    d["intraday"] = d["f_flow_1550"] / d["f_flow_1500"] - 1
    if tid == 2715:
        d["S_res"] = causal_resid(d, "S", "intraday")
        return sd.score_direction(d, "S_res", outcome)
    if tid == 2716:
        return sd.score_direction(d, "S_big", outcome, min_n="n_big")
    if tid == 2717:
        return sd.score_direction(d, "S_prem", outcome)
    if tid == 2718:
        return sd.score_direction(d, "S", outcome, flip=True)
    if tid == 2719:
        return long_bottom(d, "S", outcome)
    if tid == 2720:
        d["n_all"] = np.where(np.isfinite(d["intraday"]), 1e9, 0.0)
        return sd.score_direction(d, "intraday", outcome, min_n="n_all", flip=True)
    if tid in (2721, 2722):
        d = lib.add_delta_signal(d)
        mask = (d["moneyness"].abs() <= 0.02).to_numpy() if tid == 2722 else None
        return sd.score_direction(d, "S_delta", outcome, flip=True, mask=mask)
    raise ValueError(tid)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trial", type=int, required=True)
    a = ap.parse_args()
    r = run(a.trial)
    sd.show(f"{a.trial} {SPEC[a.trial]}", r)
    v = sd.verdict(r)
    print("  verdict:", v)
    sd.log(a.trial, SPEC[a.trial], r, "discovery iteration (entry 4)", sd.BASIS)


if __name__ == "__main__":
    main()
