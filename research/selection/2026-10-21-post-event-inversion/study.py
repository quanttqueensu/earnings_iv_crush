"""
study.py
Inverted post-event term structure predicts the stock's next 20 sessions, tested once on
2019-2024 with a reaction-return control, exactly as frozen in ``prereg.md``.

Usage
-----
    python research/selection/2026-10-21-post-event-inversion/study.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
FEATS = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold"
SOURCE = ROOT / "research" / "selection" / "2026-10-20-post-event-equity" / "study.py"
TEST_BLOCK = (2019, 2024)
N_TRIALS = 1543
SR_TRIALS_STD = 0.127475


def _sibling():
    """The E2 study's return builder, imported so both studies share one valuation path."""
    spec = importlib.util.spec_from_file_location("post_event_equity", SOURCE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clustered_ols(
    y: np.ndarray, x: np.ndarray, groups: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """OLS coefficients and cluster-robust standard errors (Liang-Zeger, small-sample factor)."""
    xc = np.column_stack([np.ones(len(y)), x])
    xtx_inv = np.linalg.inv(xc.T @ xc)
    beta = xtx_inv @ xc.T @ y
    u = y - xc @ beta
    meat = np.zeros((xc.shape[1], xc.shape[1]))
    _, inv = np.unique(groups, return_inverse=True)
    for g in range(inv.max() + 1):
        s = xc[inv == g].T @ u[inv == g]
        meat += np.outer(s, s)
    n, k, m = len(y), xc.shape[1], inv.max() + 1
    factor = m / (m - 1) * (n - 1) / (n - k)
    cov = factor * xtx_inv @ meat @ xtx_inv
    return beta, np.sqrt(np.diag(cov))


def positions(b: pd.DataFrame) -> np.ndarray:
    sign = np.where(b["bin"] == 0, 1.0, -1.0)
    return sign * b["adj_ret"].to_numpy(float) - b["rt_cost"].to_numpy(float)


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    pe = _sibling()
    feat = pd.read_parquet(FEATS / "features.parquet")
    crsp = pd.read_parquet(FEATS / "crsp_paths.parquet")
    cols = ["prc", "ret", "cfacpr", "bid", "ask"]
    crsp[cols] = crsp[cols].astype(float)  # the mirror stores CRSP numerics as Decimal
    y = pd.to_datetime(feat["exit_date"]).dt.year
    ev = feat[(y >= 2013) & (y <= TEST_BLOCK[1])].reset_index(drop=True)
    fr = pe.forward_returns(ev, crsp)
    ev = pd.concat([ev, fr], axis=1)
    ret = crsp.set_index(["permno", "date"])["ret"]
    keys = list(
        zip(ev["permno"].fillna(-1).astype(int), pd.to_datetime(ev["exit_date"]), strict=True)
    )
    ev["react"] = ret.reindex(keys).to_numpy()
    print(f"funnel: {len(ev)} events; {fr['reason'].value_counts().to_dict()}")
    d = ev[(ev["reason"] == "ok") & np.isfinite(ev["post_slope"]) & np.isfinite(ev["react"])]
    d = d.copy()
    d["bin"] = hh.causal_bins(d["post_slope"], d["exit_date"], 10, HEDGED.decile_min_prior)
    d["rbin"] = hh.causal_bins(d["react"].abs(), d["exit_date"], 3, HEDGED.decile_min_prior)
    t = d[pd.to_datetime(d["exit_date"]).dt.year >= TEST_BLOCK[0]]
    t = t[t["bin"] >= 0]

    ls = t[t["bin"].isin([0, 9])]
    pos = positions(ls)
    ci = date_clustered_ci(pos, ls["exit_date"], stat=np.mean)
    res: dict = {
        "prereg_sha256": verify_prereg(PREREG, RECORD),
        "n_positions": int(len(pos)),
        "n_long": int((ls["bin"] == 0).sum()),
        "n_short": int((ls["bin"] == 9).sum()),
        "mean_net_per_position": ci.point,
        "ci": [ci.low, ci.high],
        "per_position_sharpe": per_trade_sharpe(pos),
        "dsr": float(deflated_sharpe_ratio(pd.Series(pos), N_TRIALS, SR_TRIALS_STD)),
        "median_rt_cost": float(ls["rt_cost"].median()),
        "primary_pass": bool(ci.low > 0),
    }
    print(
        f"2019-2024 long lowest-slope / short highest-slope: mean net per 20-day position {ci};"
        f" Sharpe {res['per_position_sharpe']:+.3f}, DSR {res['dsr']:.3f}"
    )
    within = []
    for rb in (0, 1, 2):
        s = ls[ls["rbin"] == rb]
        if (s["bin"] == 0).any() and (s["bin"] == 9).any():
            within.append(float(np.mean(positions(s))))
            print(
                f"  |R| tercile {rb}: {len(s)} positions, mean net {within[-1]:+.4f}"
                f" (long {(s['bin'] == 0).sum()}, short {(s['bin'] == 9).sum()})"
            )
    res["within_abs_r_mean"] = float(np.mean(within)) if within else float("nan")
    beta, se = clustered_ols(
        t["adj_ret"].to_numpy(float),
        np.column_stack([t["bin"].to_numpy(float), t["react"], t["react"].abs()]),
        pd.to_datetime(t["exit_date"]).to_numpy(),
    )
    res["ols_slope_rank_coef"] = float(beta[1])
    res["ols_slope_rank_t"] = float(beta[1] / se[1])
    res["ols_react_coef"] = float(beta[2])
    res["ols_react_t"] = float(beta[2] / se[2])
    res["ols_n"] = int(len(t))
    res["promising"] = bool(
        res["primary_pass"] and res["within_abs_r_mean"] > 0 and res["ols_slope_rank_t"] < -2
    )
    print(
        f"  within-|R| average {res['within_abs_r_mean']:+.4f}; OLS slope-rank coef"
        f" {beta[1]:+.5f} (t {res['ols_slope_rank_t']:+.2f}), reaction coef {beta[2]:+.4f}"
        f" (t {res['ols_react_t']:+.2f}), N={len(t)}"
    )
    dec = t.groupby("bin")["adj_ret"].agg(["size", "mean"])
    print(f"  deciles 2019-2024 (gross market-adjusted):\n{dec.to_string()}")
    res["deciles"] = dec.reset_index().to_dict(orient="records")
    print(
        f"verdict: primary {'PASS' if res['primary_pass'] else 'FAIL'}, promising {res['promising']}"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
