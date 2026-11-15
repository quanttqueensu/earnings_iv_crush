"""
fit_calib.py
Step 1: choose the jump model's hyperparameters on the pre-sample announcements (1997-2012, no
option outcome exists there) by mean Student-t predictive log density. Step 2: calibration of the
predicted reaction-session variance against realised squared returns on the discovery block's
option events (trial 1,871), and forecast encompassing against the market's implied event
variance (trial 1,872).

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneD-jump-model/fit_calib.py
"""

from __future__ import annotations

import itertools
import json

import numpy as np
import pandas as pd

import lib

FIT = (1997, 2012)


def clustered(fn, keys: np.ndarray, *arrays: np.ndarray, n_boot: int = lib.N_BOOT):
    rng = np.random.default_rng(lib.SEED)
    uniq, inv = np.unique(keys, return_inverse=True)
    members = [np.flatnonzero(inv == k) for k in range(uniq.size)]
    out = np.empty(n_boot)
    for b in range(n_boot):
        idx = np.concatenate([members[k] for k in rng.integers(0, uniq.size, uniq.size)])
        out[b] = fn(*(a[idx] for a in arrays))
    return float(fn(*arrays)), float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)), out


def ratio(a: np.ndarray, b: np.ndarray) -> float:
    return float(a.mean() / b.mean())


def slope(y: np.ndarray, x: np.ndarray) -> float:
    xc = x - x.mean()
    return float((xc * (y - y.mean())).sum() / (xc * xc).sum())


def attach(ev: pd.DataFrame, h: pd.DataFrame) -> pd.DataFrame:
    hh = h[["permno", "day0", "r", "s", "Em", "alpha", "beta", "w_name", "pred_var", "m_prior"]]
    e = ev.merge(hh, left_on=["permno", "exit_date"], right_on=["permno", "day0"], how="left")
    assert len(e) == len(ev)
    return e


def main() -> None:
    hist = pd.read_parquet(lib.HERE / "history.parquet")
    ev = pd.read_parquet(lib.HERE / "events.parquet")
    yrs = hist["day0"].dt.year
    fitmask = yrs.between(*FIT).to_numpy()

    # ── step 1: hyperparameters on the pre-sample ──────────────────────────
    grid = list(itertools.product([2, 4, 8, 16, 32, 64], [4, 8, 16, 32, np.inf], [2, 5, np.inf],
                                  [5, 20, 80]))
    res = []
    for kap, hn, hi, ki in grid:
        hp = lib.Hyper(kappa=kap, h_name=hn, h_ind=hi, kappa_ind=ki)
        h = lib.run_model(hist, hp)
        m = h["day0"].dt.year.between(*FIT) & np.isfinite(h["ll"])
        res.append({"kappa": kap, "h_name": hn, "h_ind": hi, "kappa_ind": ki,
                    "ll": float(h.loc[m, "ll"].mean()), "n": int(m.sum())})
    g = pd.DataFrame(res).sort_values("ll", ascending=False)
    print(f"pre-sample fit {FIT}: {int(fitmask.sum())} announcements; top settings by mean log density")
    print(g.head(10).to_string(index=False))
    best = g.iloc[0]
    hp = lib.Hyper(kappa=float(best.kappa), h_name=float(best.h_name), h_ind=float(best.h_ind),
                   kappa_ind=float(best.kappa_ind))
    # reference models on the same pre-sample: industry only, name only (flat cross-section prior)
    for lab, alt in [("industry prior only", lib.Hyper(**{**hp.__dict__, "name_on": False})),
                     ("no industry level", lib.Hyper(**{**hp.__dict__, "ind_on": False}))]:
        h = lib.run_model(hist, alt)
        m = h["day0"].dt.year.between(*FIT) & np.isfinite(h["ll"])
        print(f"  {lab}: mean log density {h.loc[m, 'll'].mean():.4f}")
    g.to_csv(lib.HERE / "hyper_grid.csv", index=False)
    (lib.HERE / "hyper.json").write_text(json.dumps(hp.__dict__, default=float, indent=2))
    print(f"chosen: {hp}")

    # ── step 2: calibration on the discovery block ─────────────────────────
    h = lib.run_model(hist, hp)
    h.to_parquet(lib.HERE / "model_history.parquet", index=False)
    e = attach(ev, h)
    e["year"] = e["announce_date"].dt.year
    n_days = (e["exit_date"] - e["entry_date"]).dt.days
    e["mkt_var"] = np.where(e["jsplit_valid"].astype(bool),
                            e["jsplit_jump_var"] + e["jsplit_sd2"] * n_days / 365.0, np.nan)
    lo, hi = lib.BLOCKS["discovery"]
    d = e[e["year"].between(lo, hi)]
    fin = np.isfinite(d["r"]) & np.isfinite(d["pred_var"]) & np.isfinite(d["mkt_var"])
    print(f"\nfunnel discovery {lo}-{hi}: {len(d)} events, realised return {int(np.isfinite(d['r']).sum())},"
          f" model prediction {int(np.isfinite(d['pred_var']).sum())}, valid split"
          f" {int(np.isfinite(d['mkt_var']).sum())}, all three {int(fin.sum())}")
    print(f"  H of dropped vs kept: {d.loc[~fin, 'H'].mean():+.4f} vs {d.loc[fin, 'H'].mean():+.4f}"
          f" (N {int((~fin).sum())} / {int(fin.sum())}, m0, net at touch)")
    d = d[fin].copy()
    keys = d["announce_date"].dt.normalize().to_numpy()
    r2 = (d["r"] ** 2).to_numpy()
    pv = d["pred_var"].to_numpy()
    mv = d["mkt_var"].to_numpy()

    p, l_, u_, _ = clustered(ratio, keys, r2, pv)
    pm, lm, um, _ = clustered(ratio, keys, r2, mv)
    print(f"\nmean realised r^2 / mean predicted: model {p:.3f} [{l_:.3f}, {u_:.3f}],"
          f" market implied {pm:.3f} [{lm:.3f}, {um:.3f}]  (N {len(d)})")
    d["dec"] = pd.qcut(d["pred_var"], 10, labels=False)
    rows = []
    for k, gq in d.groupby("dec"):
        kk = gq["announce_date"].dt.normalize().to_numpy()
        a, b, c, _ = clustered(ratio, kk, (gq["r"] ** 2).to_numpy(), gq["pred_var"].to_numpy())
        rows.append({"decile": int(k), "n": len(gq), "pred_sd": float(np.sqrt(gq["pred_var"].mean())),
                     "real_sd": float(np.sqrt((gq["r"] ** 2).mean())),
                     "mkt_sd": float(np.sqrt(gq["mkt_var"].mean())), "ratio": a, "lo": b, "hi": c})
    cal = pd.DataFrame(rows)
    print("calibration by decile of predicted variance (sd in return units, ratio = realised/predicted variance):")
    print(cal.round(4).to_string(index=False))
    mz, mzl, mzh, mzb = clustered(slope, keys, r2, pv)
    print(f"Mincer-Zarnowitz slope of r^2 on model prediction {mz:.3f} [{mzl:.3f}, {mzh:.3f}]")
    calibrated = (l_ <= 1 <= u_) and (cal.iloc[0]["lo"] <= 1 <= cal.iloc[0]["hi"]) and (
        cal.iloc[-1]["lo"] <= 1 <= cal.iloc[-1]["hi"])
    lib.log_trial({
        "trial_id": 1871, "hypothesis": "jump model predicted reaction variance is unbiased for realised r^2",
        "mechanism": "conjugate EB jump-variance multiplier with industry and cross-section shrinkage, decayed",
        "block": f"discovery {lo}-{hi}", "n": len(d), "effect": round(p, 4), "ci_low": round(l_, 4),
        "ci_high": round(u_, 4), "t": "", "null_pct": "",
        "basis": "ratio mean realised r^2 / mean predicted variance, reaction session; pass: pooled, bottom and top decile CI cover 1",
        "verdict": "calibrated" if calibrated else "not calibrated", "label": "diagnostic"})

    # encompassing: does the model gap predict the market's forecast error?
    x = pv - mv
    yv = r2 - mv
    b, bl, bh, bb = clustered(slope, keys, yv, x)
    tt = b / np.std(bb, ddof=1)
    print(f"encompassing slope of (r^2 - market) on (model - market): {b:.3f} [{bl:.3f}, {bh:.3f}], t {tt:.2f}")
    lib.log_trial({
        "trial_id": 1872, "hypothesis": "model minus market variance predicts realised minus market variance",
        "mechanism": "if the model holds information the price lacks, its gap to the market forecasts the market's error",
        "block": f"discovery {lo}-{hi}", "n": len(d), "effect": round(b, 4), "ci_low": round(bl, 4),
        "ci_high": round(bh, 4), "t": round(tt, 2), "null_pct": "",
        "basis": "OLS slope, return variance units, date-clustered bootstrap",
        "verdict": "pass" if bl > 0 else "fail", "label": "diagnostic"})
    cal.to_csv(lib.HERE / "calibration_discovery.csv", index=False)
    e.to_parquet(lib.HERE / "events_model.parquet", index=False)


if __name__ == "__main__":
    main()
