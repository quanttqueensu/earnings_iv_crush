"""
fit_calib2.py
Model M2 (log-space empirical Bayes with vol elasticity). Hyperparameters on 1997-2012
announcements by the variance of the log-squared-move forecast error; then calibration on the
discovery block's option events (trial 1,873: variance; 1,874: encompassing against the market).

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneD-jump-model/fit_calib2.py
"""

from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

import lib
from fit_calib import FIT, clustered, ratio, slope


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="m2")
    ap.add_argument("--s-col", default="s")
    ap.add_argument("--h-lvl", type=float, default=float("nan"))
    ap.add_argument("--trials", default="1873,1874")
    args = ap.parse_args()
    t_cal, t_enc = (int(x) for x in args.trials.split(","))
    hist = pd.read_parquet(lib.HERE / "history.parquet")
    ev = pd.read_parquet(lib.HERE / "events.parquet")
    grid = list(itertools.product([0.0, 0.25, 0.5, 0.75, 1.0], [1, 2, 4, 8, 16], [4, 8, 16, np.inf],
                                  [3, np.inf], [10, 40]))
    res = []
    for gm, kap, hn, hi, ki in grid:
        hp = lib.HyperLog(gamma=gm, kappa=kap, h_name=hn, h_ind=hi, kappa_ind=ki, s_col=args.s_col, h_lvl=args.h_lvl)
        h = lib.run_model_log(hist, hp)
        m = h["day0"].dt.year.between(*FIT) & np.isfinite(h["xres"])
        res.append({**hp.__dict__, "err_var": float(h.loc[m, "xres"].var()),
                    "err_mean": float(h.loc[m, "xres"].mean()), "n": int(m.sum())})
    g = pd.DataFrame(res).sort_values("err_var")
    print(f"pre-sample {FIT}: forecast-error variance of log r^2 (lower is better)")
    print(g.head(8).drop(columns="name_on").to_string(index=False))
    for gm in (0.0, 0.5, 1.0):
        print(f"  best at gamma {gm}: {g[g['gamma'] == gm]['err_var'].min():.4f}")
    print(f"  industry-only (no name evidence) best: ", end="")
    b0 = g.iloc[0]
    hp = lib.HyperLog(gamma=float(b0.gamma), kappa=float(b0.kappa), h_name=float(b0.h_name),
                      h_ind=float(b0.h_ind), kappa_ind=float(b0.kappa_ind), s_col=args.s_col,
                      h_lvl=args.h_lvl)
    h0 = lib.run_model_log(hist, lib.HyperLog(**{**hp.__dict__, "name_on": False}))
    m = h0["day0"].dt.year.between(*FIT) & np.isfinite(h0["xres"])
    print(f"{h0.loc[m, 'xres'].var():.4f}")
    g.to_csv(lib.HERE / f"hyper_grid_{args.tag}.csv", index=False)
    (lib.HERE / f"hyper_{args.tag}.json").write_text(json.dumps(hp.__dict__, default=float, indent=2))
    print(f"chosen: {hp}")

    h = lib.run_model_log(hist, hp)
    h.to_parquet(lib.HERE / f"model{args.tag[1:]}_history.parquet", index=False)
    cols = ["permno", "day0", "r", "s", "lsig2", "pred_var", "pred_abs", "w_name", "xhat", "c1", "c2"]
    e = ev.merge(h[cols], left_on=["permno", "exit_date"], right_on=["permno", "day0"], how="left")
    assert len(e) == len(ev)
    e["year"] = e["announce_date"].dt.year
    n_days = (e["exit_date"] - e["entry_date"]).dt.days
    e["mkt_var"] = np.where(e["jsplit_valid"].astype(bool),
                            e["jsplit_jump_var"] + e["jsplit_sd2"] * n_days / 365.0, np.nan)
    e.to_parquet(lib.HERE / f"events_model{args.tag[1:]}.parquet", index=False)
    lo, hi = lib.BLOCKS["discovery"]
    d = e[e["year"].between(lo, hi)]
    fin = np.isfinite(d["r"]) & np.isfinite(d["pred_var"]) & np.isfinite(d["mkt_var"])
    print(f"\nfunnel discovery {lo}-{hi}: {len(d)} events, all inputs {int(fin.sum())}")
    d = d[fin].copy()
    keys = d["announce_date"].dt.normalize().to_numpy()
    r2, pv, mv = (d["r"] ** 2).to_numpy(), d["pred_var"].to_numpy(), d["mkt_var"].to_numpy()
    ar, pa = d["r"].abs().to_numpy(), d["pred_abs"].to_numpy()
    p, l_, u_, _ = clustered(ratio, keys, r2, pv)
    pm, lm, um, _ = clustered(ratio, keys, r2, mv)
    pa_, pal, pau, _ = clustered(ratio, keys, ar, pa)
    print(f"realised/predicted variance: model {p:.3f} [{l_:.3f}, {u_:.3f}], market {pm:.3f}"
          f" [{lm:.3f}, {um:.3f}]; realised/predicted mean |r|: model {pa_:.3f} [{pal:.3f}, {pau:.3f}]")
    d["dec"] = pd.qcut(d["pred_var"], 10, labels=False)
    rows = []
    for k, gq in d.groupby("dec"):
        kk = gq["announce_date"].dt.normalize().to_numpy()
        a, b, c, _ = clustered(ratio, kk, (gq["r"] ** 2).to_numpy(), gq["pred_var"].to_numpy())
        a2, b2, c2, _ = clustered(ratio, kk, gq["r"].abs().to_numpy(), gq["pred_abs"].to_numpy())
        rows.append({"decile": int(k), "n": len(gq), "pred_sd": np.sqrt(gq["pred_var"].mean()),
                     "real_sd": np.sqrt((gq["r"] ** 2).mean()), "mkt_sd": np.sqrt(gq["mkt_var"].mean()),
                     "var_ratio": a, "lo": b, "hi": c, "abs_ratio": a2, "abs_lo": b2, "abs_hi": c2})
    cal = pd.DataFrame(rows)
    print("calibration by decile of predicted variance (sd in return units):")
    print(cal.round(4).to_string(index=False))
    mz, mzl, mzh, _ = clustered(slope, keys, r2, pv)
    mza, mzal, mzah, _ = clustered(slope, keys, ar, pa)
    print(f"Mincer-Zarnowitz slope: r^2 on predicted variance {mz:.3f} [{mzl:.3f}, {mzh:.3f}];"
          f" |r| on predicted mean |r| {mza:.3f} [{mzal:.3f}, {mzah:.3f}]")
    calibrated = (l_ <= 1 <= u_) and (cal.iloc[0]["lo"] <= 1 <= cal.iloc[0]["hi"]) and (
        cal.iloc[-1]["lo"] <= 1 <= cal.iloc[-1]["hi"])
    lib.log_trial({
        "trial_id": t_cal, "hypothesis": f"{args.tag} predicted reaction variance is unbiased for realised r^2",
        "mechanism": f"log-space EB of jump size, vol elasticity on {args.s_col}, level-correction half-life {args.h_lvl} y, industry and cross-section shrinkage",
        "block": f"discovery {lo}-{hi}", "n": len(d), "effect": round(p, 4), "ci_low": round(l_, 4),
        "ci_high": round(u_, 4), "t": "", "null_pct": "",
        "basis": f"ratio mean r^2 / mean predicted variance; MZ slope {mz:.3f} [{mzl:.3f}, {mzh:.3f}]; abs ratio {pa_:.3f}",
        "verdict": "calibrated" if calibrated else "not calibrated", "label": "diagnostic"})
    x, yv = pv - mv, r2 - mv
    b, bl, bh, bb = clustered(slope, keys, yv, x)
    tt = b / np.std(bb, ddof=1)
    xa = np.sqrt(pv) - np.sqrt(mv)
    ya = ar - np.sqrt(mv)
    ba, bal, bah, bba = clustered(slope, keys, ya, xa)
    print(f"encompassing (variance) slope {b:.3f} [{bl:.3f}, {bh:.3f}] t {tt:.2f};"
          f" (sd units, |r| - market sd on model sd - market sd) {ba:.3f} [{bal:.3f}, {bah:.3f}]")
    lib.log_trial({
        "trial_id": t_enc, "hypothesis": f"{args.tag} minus market variance predicts realised minus market variance",
        "mechanism": "model information absent from the price forecasts the market's variance error",
        "block": f"discovery {lo}-{hi}", "n": len(d), "effect": round(b, 4), "ci_low": round(bl, 4),
        "ci_high": round(bh, 4), "t": round(tt, 2), "null_pct": "",
        "basis": f"OLS slope, variance units; sd-unit slope {ba:.3f} [{bal:.3f}, {bah:.3f}]",
        "verdict": "pass" if bl > 0 else "fail", "label": "diagnostic"})
    cal.to_csv(lib.HERE / f"calibration_{args.tag}_discovery.csv", index=False)


if __name__ == "__main__":
    main()


