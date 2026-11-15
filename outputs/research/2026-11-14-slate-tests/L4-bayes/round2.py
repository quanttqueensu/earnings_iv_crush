"""
round2.py
Lane L4 round 2, chosen after the 2019-24 read and therefore EXPLORATORY, reported on 2025-26
only (L4 iteration protocol, rule 3). Nothing here re-scores 2019-24 or changes the frozen
round-1 numbers.

Two questions the round-1 read raised:

A. Is the density gain the closed spread gate? The frozen champion with the cost features
   (log_half_spread, log_depth) removed, every other setting frozen, scored against the frozen
   baseline on 2025-26 (trial 3,022), with its P(H > 0) > 0.5 book against the date-stratified
   null (trial 3,023). Fixed in advance: no other variant is run.
B. A book-mean monitor. Under the loss-ratio transform the declared intercept gauge reads
   P(the median trade gains), which says nothing about the mean the book earns. From the frozen
   baseline's own posterior after each update date, the predictive mean of a typical trade is
   ``-U E[yj_inv(b0 + u + e)]`` with ``u`` the name effect and ``e`` the scale-mixture error; it
   falls as the intercept ``b0`` rises, so P(book mean > 0) = P(b0 < c*) where ``c*`` solves
   that mean = 0. A monitor, not a trial; its 2025-26 readings are the ones reported.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/round2.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import t as student_t

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import l4iter  # noqa: E402
import l4lib  # noqa: E402
import score_heldout as sh  # noqa: E402

from earnings_iv_crush import config as C  # noqa: E402
from earnings_iv_crush.research import online_bayes as ob  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    N_BOOT,
    SEED,
    date_clustered_ci,
    log_block_view,
)

BLOCK = "2025-26"
COST = ("log_half_spread", "log_depth")
NODES = 4001  # quadrature nodes for the monitor's mean (standard-normal grid, +-8 sd)


def question_a(d: pd.DataFrame, D: l4iter.Design) -> dict[str, Any]:
    cfg = C.ONLINE_BAYES_L4_MODEL  # scored against the frozen baseline run on disk
    names = D.coef_names(cfg)
    keep = [i for i, n in enumerate(names) if n not in COST]
    y = l4lib.target(d, "H_corr", cfg)
    X = D.X(cfg)[:, keep]
    rm = ob.run_online(
        D.frame(cfg, y, "none"), X, cfg, coef_names=[names[i] for i in keep], quiet=False
    )
    run = pd.read_parquet(HERE / "run_H_corr.parquet")
    b_ls = run["b_log_score"].to_numpy()
    full_ls = run["m_log_score"].to_numpy()
    sc = (
        (d["block"] == BLOCK).to_numpy()
        & rm.events["scored"].to_numpy()
        & run["b_scored"].to_numpy(bool)
        & np.isfinite(rm.events["log_score"].to_numpy())
        & np.isfinite(b_ls)
    )
    keys = d["announce_date"].to_numpy()[sc]
    diff = rm.events["log_score"].to_numpy()[sc] - b_ls[sc]
    ci = date_clustered_ci(diff, keys, np.mean)
    lost = date_clustered_ci(full_ls[sc] - rm.events["log_score"].to_numpy()[sc], keys, np.mean)
    sel = rm.events["decide"].to_numpy(bool)[sc]
    yy = y[sc]
    lv = date_clustered_ci(yy[sel], keys[sel], np.mean)
    strat = ob.date_stratified_null(yy, sel, keys, n_draws=N_BOOT, seed=SEED)
    rv = d["residual_value"].to_numpy(float)[sc] * C.ONLINE_BAYES.pct_per_unit
    rvd = sh._diff_ci(rv, sel, keys)
    out = {
        "trial_log_score": 3022,
        "trial_book": 3023,
        "N": ci.n,
        "clusters": ci.clusters,
        "diff_vs_baseline": [ci.point, ci.low, ci.high],
        "full_minus_nocost": [lost.point, lost.low, lost.high],
        "n_selected": int(sel.sum()),
        "selected_mean_H": [lv.point, lv.low, lv.high],
        "null_pct_date_stratified": strat.percentile,
        "null_median": float(np.median(strat.null)),
        "sel_minus_unsel_rv": [rvd.point, rvd.low, rvd.high],
        "final_coefs": dict(zip(rm.coef_names, rm.state.m[: len(keep)].round(4).tolist(),
                                strict=True)),  # fmt: skip
    }
    print(f"[A] EXPLORATORY 2025-26, cost features removed: {json.dumps(out, default=float)}")
    return out


def _mean_y(c: float, s2: float, ku: float, cfg: Any, u: float) -> float:
    """``-U E[yj_inv(c + u + e)]`` with Gaussian ``u + e`` (the mixture at ``lambda = 1``).

    Under the fitted Student-t error the mean is minus infinity at every intercept: on the
    loss-ratio scale with power 0 the loss branch is exponential and a t tail has no moment
    generating function. The Gaussian component is the largest model in the family whose mean
    exists, so the monitor uses it and says so.
    """
    del cfg
    g = np.linspace(-8, 8, NODES)
    wg = np.exp(-0.5 * g * g)
    wg /= wg.sum()
    z = c + np.sqrt(s2 * (1.0 + ku)) * g
    x = ob.yj_inv(z, C.ONLINE_BAYES_L4_BASELINE.yj_power)
    return float(-u * (wg * x).sum())


def question_b(d: pd.DataFrame) -> dict[str, Any]:
    cfg = C.ONLINE_BAYES_L4_BASELINE
    g = pd.read_csv(HERE / "gauge_baseline_H_corr.csv", parse_dates=["date"])
    u_bar = float(np.nanmean(d["c_premium"].to_numpy(float)) * C.ONLINE_BAYES.pct_per_unit)
    rows = []
    for _, r in g.iterrows():
        s2 = float(r["sigma_hat"]) ** 2
        f = lambda c, s2=s2: _mean_y(c, s2, cfg.name_prior_scale, cfg, u_bar)  # noqa: E731
        lo, hi = f(-10.0), f(10.0)
        if not (np.isfinite(lo) and np.isfinite(hi) and lo > 0 > hi):
            # With a large residual scale the exponential branch dominates and the typical
            # trade's mean is negative at every intercept: no root, P(book mean > 0) is zero.
            rows.append({"date": r["date"], "c_star": np.nan, "p_book_mean_pos_deff": 0.0,
                         "mean_at_posterior": f(float(r["intercept"]))})  # fmt: skip
            continue
        c_star = brentq(f, -10.0, 10.0)
        sc = float(r["intercept_scale"]) * np.sqrt(float(r["deff"]))
        p = float(student_t.cdf((c_star - r["intercept"]) / sc, r["df"]))
        rows.append({"date": r["date"], "c_star": c_star, "p_book_mean_pos_deff": p,
                     "mean_at_posterior": f(float(r["intercept"]))})  # fmt: skip
    m = pd.DataFrame(rows)
    m.to_csv(HERE / "round2_mean_monitor.csv", index=False)
    blk = m[m["date"] >= pd.Timestamp("2025-01-01")]
    out = {
        "unit_premium_pct_m0": u_bar,
        "dates_2025_26": int(len(blk)),
        "p_book_mean_pos_2025_26_range": [float(blk["p_book_mean_pos_deff"].min()),
                                          float(blk["p_book_mean_pos_deff"].max())],
        "mean_at_posterior_2025_26_range": [float(blk["mean_at_posterior"].min()),
                                            float(blk["mean_at_posterior"].max())],
        "last": {k: (str(v) if k == "date" else float(v)) for k, v in m.iloc[-1].items()},
    }  # fmt: skip
    print(f"[B] EXPLORATORY monitor: {json.dumps(out)}")
    return out


def main() -> None:
    log_block_view(
        l4lib.BLOCKS_VIEWED,
        panel="base_corrected",
        period=BLOCK,
        outcome_family="hedged_hold_H_corr",
        feature_family="online_bayes_round_2_no_cost",
        viewed_by="L4 round2 (exploratory, after the 2019-24 read)",
        kind="trial",
    )
    d = l4iter.load_all()
    D = l4iter.Design(d)
    res = {"label": "ROUND 2, EXPLORATORY, 2025-26 only", "A": question_a(d, D), "B": question_b(d)}
    (HERE / "round2_results.json").write_text(json.dumps(res, indent=2, default=str) + "\n",
                                              encoding="utf-8")  # fmt: skip
    print("written round2_results.json, round2_mean_monitor.csv")


if __name__ == "__main__":
    main()
