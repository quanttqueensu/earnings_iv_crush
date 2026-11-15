"""
lib.py
Scoring helpers for the lane5-niche alpha hunt: within-cell treated-minus-control contrast on the
hedged event hold, date-clustered bootstrap, cell-matched random null, balance table, trial log.

The held-out block is refused unless a frozen note for the hypothesis exists in this folder.

Usage
-----
    import lib; d = lib.load(); lib.score(d, flag, defined, "discovery", trial_id=1749, ...)
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TRIALS = HERE / "trials.csv"
BLOCKS = {
    "discovery": (2013, 2018),
    "heldout": (2019, 2024),
    "viewed_2025_26": (2025, 2026),  # read by many earlier trials: exploratory only
}
N_BOOT = 5000
SEED = 0
MIN_SIDE = 2  # events per side for a cell to contribute, as in the frozen nonprice scorer
FIELDS = [
    "trial_id", "hypothesis", "mechanism", "block", "n_scored", "n_treated", "effect", "ci_low",
    "ci_high", "t", "null_pct", "ri_delta", "ri_ci_low", "ri_ci_high", "treated_H_mean",
    "verdict", "label",
]


def load() -> pd.DataFrame:
    d = pd.read_parquet(HERE / "features.parquet")
    d["year"] = d["announce_date"].dt.year
    return d


def _delta(y: np.ndarray, f: np.ndarray, c: np.ndarray) -> float:
    """Treated-count-weighted mean of within-cell treated-minus-control differences."""
    num = den = 0.0
    for u in np.unique(c):
        m = c == u
        k = int((f & m).sum())
        if k >= MIN_SIDE and int((~f & m).sum()) >= MIN_SIDE:
            num += k * (y[f & m].mean() - y[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def _boot(y: np.ndarray, f: np.ndarray, c: np.ndarray, keys: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    uniq, inv = np.unique(keys, return_inverse=True)
    members = [np.flatnonzero(inv == k) for k in range(uniq.size)]
    out = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = np.concatenate([members[k] for k in rng.integers(0, uniq.size, uniq.size)])
        out[b] = _delta(y[idx], f[idx], c[idx])
    return out


def _sharpe(x: np.ndarray) -> float:
    s = x.std(ddof=1)
    return float(x.mean() / s) if s > 0 else float("nan")


def _null_pct(h: np.ndarray, f: np.ndarray, c: np.ndarray) -> float:
    """Percentile of the treated per-trade Sharpe of H among same-count draws within cell."""
    rng = np.random.default_rng(SEED)
    groups = [np.flatnonzero(c == u) for u in np.unique(c)]
    counts = [int(f[g].sum()) for g in groups]
    obs = _sharpe(h[f])
    draws = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = np.concatenate(
            [rng.choice(g, k, replace=False) for g, k in zip(groups, counts, strict=True) if k]
        )
        draws[b] = _sharpe(h[idx])
    return float(100.0 * (draws < obs).mean())


def _frozen(hyp: str) -> bool:
    return (HERE / f"freeze_{hyp}.md").exists()


def score(
    d: pd.DataFrame,
    flag: pd.Series,
    defined: pd.Series,
    block: str,
    *,
    hyp: str,
    trial_id: int | None = None,
    mechanism: str = "",
    cell_col: str = "cell",
    label: str = "exploratory",
    quiet: bool = False,
) -> dict:
    """Score one treated flag on one block and, if `trial_id` is given, log the trial."""
    if block not in BLOCKS:
        raise ValueError(f"unknown block {block}")
    if block == "heldout" and not _frozen(hyp):
        raise PermissionError(f"held-out block refused: no freeze_{hyp}.md in {HERE}")
    lo, hi = BLOCKS[block]
    ok = defined.to_numpy(bool) & (d["im_bin"] >= 0).to_numpy() & d["year"].between(lo, hi).to_numpy()
    b = d[ok]
    f = flag.to_numpy(bool)[ok]
    res: dict = {"hyp": hyp, "block": block, "n_scored": int(len(b)), "n_treated": int(f.sum())}
    if f.sum() < 20 or (~f).sum() < 20:
        raise ValueError(f"{hyp} {block}: {int(f.sum())} treated of {len(b)}: too few to score")
    c = b[cell_col].to_numpy(float)
    keys = b["announce_date"].to_numpy()
    y = b["y"].to_numpy(float)
    res["delta"] = _delta(y, f, c)
    draws = _boot(y, f, c, keys)
    res["ci"] = [float(np.nanpercentile(draws, 2.5)), float(np.nanpercentile(draws, 97.5))]
    res["t"] = float(res["delta"] / np.nanstd(draws, ddof=1))
    res["null_pct"] = _null_pct(b["H"].to_numpy(float), f, c)
    ri = b["ri"].to_numpy(float)
    res["ri_delta"] = _delta(ri, f, c)
    rd = _boot(ri, f, c, keys)
    res["ri_ci"] = [float(np.nanpercentile(rd, 2.5)), float(np.nanpercentile(rd, 97.5))]
    res["yb_delta"] = _delta(b["yb"].to_numpy(float), f, c)
    res["treated_H"] = float(b.loc[f, "H"].mean())
    res["control_H"] = float(b.loc[~f, "H"].mean())
    res["n_names"] = int(b.loc[f, "ticker"].nunique())
    res["top_name_share"] = float(b.loc[f, "ticker"].value_counts(normalize=True).iloc[0])
    bal = {}
    for col in ("implied_move", "dte", "half_spread", "me"):
        bal[col] = [float(b.loc[f, col].median()), float(b.loc[~f, col].median())]
    res["balance_median_treated_control"] = bal
    if not quiet:
        print(
            f"{hyp} [{block} {lo}-{hi}] scored {len(b)}, treated {int(f.sum())} "
            f"({res['n_names']} names, top name {res['top_name_share']:.1%})\n"
            f"   Delta y (residual value per unit premium, within im-tercile x tenor cell) "
            f"{res['delta']:+.4f} [{res['ci'][0]:+.4f}, {res['ci'][1]:+.4f}] t {res['t']:+.2f}; "
            f"null pct {res['null_pct']:.1f}\n"
            f"   Delta realised/implied {res['ri_delta']:+.4f} [{res['ri_ci'][0]:+.4f}, "
            f"{res['ri_ci'][1]:+.4f}]; Delta buy-back per premium {res['yb_delta']:+.4f}; "
            f"H on m0 treated {res['treated_H']:+.4f} control {res['control_H']:+.4f}\n"
            f"   medians treated|control: implied move {bal['implied_move'][0]:.4f}|"
            f"{bal['implied_move'][1]:.4f}, days to expiry {bal['dte'][0]:.0f}|{bal['dte'][1]:.0f}, "
            f"half-spread {bal['half_spread'][0]:.4f}|{bal['half_spread'][1]:.4f}, "
            f"mkt cap USDm {bal['me'][0]:,.0f}|{bal['me'][1]:,.0f}"
        )
    if trial_id is not None:
        passed = res["ci"][0] > 0 and res["null_pct"] >= 95 and (block != "heldout" or res["t"] >= 3)
        res["verdict"] = "pass" if passed else "fail"
        new = not TRIALS.exists()
        with TRIALS.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow(
                {
                    "trial_id": trial_id, "hypothesis": hyp, "mechanism": mechanism,
                    "block": f"{block} {lo}-{hi}", "n_scored": len(b), "n_treated": int(f.sum()),
                    "effect": round(res["delta"], 5), "ci_low": round(res["ci"][0], 5),
                    "ci_high": round(res["ci"][1], 5), "t": round(res["t"], 3),
                    "null_pct": round(res["null_pct"], 1), "ri_delta": round(res["ri_delta"], 5),
                    "ri_ci_low": round(res["ri_ci"][0], 5), "ri_ci_high": round(res["ri_ci"][1], 5),
                    "treated_H_mean": round(res["treated_H"], 5), "verdict": res["verdict"],
                    "label": label,
                }
            )
        if not quiet:
            print(f"   trial {trial_id}: {res['verdict'].upper()} ({label})")
    return res


def causal_quantile_bins(v: np.ndarray, dates: pd.Series, n_bins: int, min_prior: int = 200) -> np.ndarray:
    """Bin 0..n_bins-1 from quantiles of strictly earlier dates; -1 if unassigned."""
    v = np.asarray(v, float)
    dd = pd.to_datetime(dates).dt.normalize().to_numpy()
    out = np.full(v.size, -1, int)
    order = np.argsort(dd, kind="stable")
    qs = np.linspace(0, 1, n_bins + 1)[1:-1]
    seen: list[float] = []
    i = 0
    while i < order.size:
        j = i
        while j < order.size and dd[order[j]] == dd[order[i]]:
            j += 1
        idx = order[i:j]
        if len(seen) >= min_prior:
            cuts = np.quantile(np.asarray(seen), qs)
            for k in idx:
                if np.isfinite(v[k]):
                    out[k] = int(np.searchsorted(cuts, v[k], side="right"))
        seen.extend(float(x) for x in v[idx] if np.isfinite(x))
        i = j
    return out
