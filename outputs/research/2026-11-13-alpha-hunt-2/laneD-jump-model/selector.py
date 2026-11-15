"""
selector.py
Residual richness (market straddle minus model-fair straddle, in m0) and its scoring as a
selector on within-cell residual value of the hedged hold (y = H m0 / mid0) and of the next-session
buy-back (yb = B m0 / mid0), against the cell-matched (implied-move tercile x tenor) random null.

Usage
-----
    python selector.py --model m2 --trials 1875,1876 [--block discovery]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import lib

MODELS = {
    "m2": ("events_model2.parquet", "model2_history.parquet"),
    "m3": ("events_model3.parquet", "model3_history.parquet"),
}


def richness(e: pd.DataFrame, h: pd.DataFrame, *, ratio_mode: bool = False) -> pd.DataFrame:
    e = e.copy()
    e["t_jump"] = (e["exit_date"] - e["entry_date"]).dt.days / 365.0
    e["t_diff"] = np.maximum(e["front_t"] - e["t_jump"], 0.0)
    ok = (np.isfinite(e["lsig2"]) & e["jsplit_valid"].astype(bool) & np.isfinite(e["jsplit_sd2"])
          & np.isfinite(e["front_fwd"]) & np.isfinite(e["front_strike"]))
    e["model_px"] = np.nan
    for yr, g in e[ok].groupby(e.loc[ok, "entry_date"].dt.year):
        zn = lib.shape_pool(h, int(yr))
        e.loc[g.index, "model_px"] = lib.model_price_shape(
            g["front_fwd"].to_numpy(float), g["front_strike"].to_numpy(float),
            g["t_diff"].to_numpy(float), g["jsplit_sd2"].to_numpy(float),
            np.exp(g["lsig2"].to_numpy(float) / 2), zn)
    e["R"] = (e["front_mid"] - e["model_px"]) / e["m0"]
    e["R_touch"] = (e["s0"] - e["model_px"]) / e["m0"]
    e["R_ratio"] = e["front_mid"] / e["model_px"] - 1.0
    e["yb"] = e["B"] * e["m0"] / e["mid0"]
    return e


def score(e: pd.DataFrame, sig: str, outcome: str, block: str, trial: int | None, *,
          hyp: str, mech: str, label: str = "exploratory", top: int = 2, n_bins: int = 3,
          verbose: bool = True, fixed: float | None = None) -> dict:
    lo, hi = lib.BLOCKS[block]
    e = e.copy()
    if fixed is None:
        e["bin"] = lib.causal_bins(e[sig].to_numpy(float), e["announce_date"], n_bins)
    else:  # an economic threshold, not a quantile: treated when the signal exceeds it
        v = e[sig].to_numpy(float)
        e["bin"] = np.where(np.isfinite(v), (v > fixed).astype(int), -1)
        top = 1
    yr = e["announce_date"].dt.year
    base = yr.between(lo, hi) & (e["im_bin"] >= 0) & np.isfinite(e[outcome])
    n_blk = int(yr.between(lo, hi).sum())
    b = e[base & (e["bin"] >= 0)]
    if verbose:
        print(f"\n[{trial}] {hyp} | {sig} top {'tercile' if n_bins == 3 else f'bin {top} of {n_bins}'}"
              f" -> {outcome}, {block} {lo}-{hi}")
        print(f"  funnel: block {n_blk}, cell+outcome {int(base.sum())}, signal binned {len(b)}")
        cov, unc = e[base & (e["bin"] >= 0)], e[base & (e["bin"] < 0)]
        if len(unc):
            print(f"  attrition: H covered {cov['H'].mean():+.4f} (N {len(cov)}) vs not binned"
                  f" {unc['H'].mean():+.4f} (N {len(unc)}), m0 net at touch")
    f = (b["bin"] >= top).to_numpy()
    c = b["cell"].to_numpy(float)
    res = lib.score_flag(b[outcome].to_numpy(float), f, c, b["announce_date"])
    lvl = lib.level(b.loc[f, "H"].to_numpy(float), b.loc[f, "announce_date"])
    lvlb = lib.level(b.loc[f & np.isfinite(b["B"]).to_numpy(), "B"].to_numpy(float),
                     b.loc[f & np.isfinite(b["B"]).to_numpy(), "announce_date"])
    allh = lib.level(b["H"].to_numpy(float), b["announce_date"])
    res.update({"H_sel": lvl, "B_sel": lvlb, "H_all": allh})
    if verbose:
        print(f"  within-cell delta {outcome} (per unit premium) {res['delta']:+.4f}"
              f" [{res['lo']:+.4f}, {res['hi']:+.4f}] t {res['t']:+.2f}, cell-null pct"
              f" {res['null_pct']:.1f}; N {res['n']}, treated {res['n_treated']}")
        print(f"  level, selected: H {lvl[0]:+.4f} [{lvl[1]:+.4f}, {lvl[2]:+.4f}], B {lvlb[0]:+.4f}"
              f" [{lvlb[1]:+.4f}, {lvlb[2]:+.4f}]; all binned H {allh[0]:+.4f} (m0, net at touch)")
        q = b.groupby("bin").agg(n=(outcome, "size"), out=(outcome, "mean"), H=("H", "mean"),
                                 R=(sig, "median"), im=("implied_move", "median"))
        print(q.round(4).to_string())
    if trial is not None:
        passed = res["lo"] > 0 and res["null_pct"] >= 95
        lib.log_trial({
            "trial_id": trial, "hypothesis": hyp, "mechanism": mech, "block": f"{block} {lo}-{hi}",
            "n": res["n"], "effect": round(res["delta"], 5), "ci_low": round(res["lo"], 5),
            "ci_high": round(res["hi"], 5), "t": round(res["t"], 2),
            "null_pct": round(res["null_pct"], 1),
            "basis": (f"within cell (implied-move tercile x tenor) treated minus control {outcome},"
                      f" per unit premium, net at touch; n_treated {res['n_treated']}; selected H"
                      f" {lvl[0]:+.4f} [{lvl[1]:+.4f}, {lvl[2]:+.4f}] of m0"),
            "verdict": "pass" if passed else "fail", "label": label})
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="m2")
    ap.add_argument("--trials", default="")
    ap.add_argument("--block", default="discovery")
    ap.add_argument("--signals", default="R")
    ap.add_argument("--outcomes", default="y,yb")
    ap.add_argument("--label", default="exploratory")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    ef, hf = MODELS[a.model]
    e = richness(pd.read_parquet(lib.HERE / ef), pd.read_parquet(lib.HERE / hf))
    e.to_parquet(lib.HERE / f"rich_{a.model}.parquet", index=False)
    d = e[e["year"].between(*lib.BLOCKS[a.block])]
    ok = np.isfinite(d["R"])
    print(f"{a.model}: block events {len(d)}, richness defined {int(ok.sum())}")
    print(f"  market mid / model price: median {np.nanmedian(d['front_mid'] / d['model_px']):.3f};"
          f" R median {np.nanmedian(d['R']):+.4f} of m0, R_touch median {np.nanmedian(d['R_touch']):+.4f}")
    pairs = [(s, o) for s in a.signals.split(",") for o in a.outcomes.split(",")]
    tr = [int(x) for x in a.trials.split(",")] if a.trials else [None] * len(pairs)
    assert len(tr) == len(pairs), "one trial id per signal x outcome"
    mech = (f"{a.model} residual richness: the market straddle above the model-fair value is"
            " jump premium the realised move will not pay; higher richness, more residual value")
    for (sg, oc), t in zip(pairs, tr, strict=True):
        score(e, sg, oc, a.block, t, hyp=f"{a.model} top-tercile {sg} -> {oc} residual value{a.note}",
              mech=mech, label=a.label)

if __name__ == "__main__":
    main()


