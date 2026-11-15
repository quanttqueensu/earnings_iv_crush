"""
lib.py
Shared statistics for the lane1-macro alpha hunt: within-cell treated-minus-untreated Delta,
date-clustered and month-clustered bootstrap intervals, the cell-matched random null, a
date-shift placebo null for regime variables, and the trial log.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TRIALS = HERE / "trials.csv"
SEED = 0
DISCOVERY = (2013, 2018)
HOLDOUT = (2019, 2024)
VIEWED = (2025, 2026)
FIELDS = ["trial_id", "hypothesis", "mechanism", "block", "outcome", "n_scored", "n_treated",
          "n_dates_treated", "n_months_treated", "effect", "ci_low", "ci_high", "ci_month_low",
          "ci_month_high", "t", "null_pct_cell", "null_pct_shift", "verdict"]


def load(block: tuple[int, int] | None = None) -> pd.DataFrame:
    d = pd.read_parquet(HERE / "panel.parquet")
    d = d[d["im_bin"] >= 0].copy()
    if block is not None:
        d = d[d["entry_date"].dt.year.between(*block)].copy()
    return d.reset_index(drop=True)


def delta(y: np.ndarray, f: np.ndarray, c: np.ndarray) -> float:
    """Treated-count-weighted mean of within-cell treated-minus-untreated differences."""
    num = den = 0.0
    for u in np.unique(c):
        m = c == u
        k = int((f & m).sum())
        if k >= 2 and int((~f & m).sum()) >= 2:
            num += k * (y[f & m].mean() - y[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def _groups(keys: np.ndarray) -> list[np.ndarray]:
    _, inv = np.unique(keys, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    cuts = np.flatnonzero(np.diff(inv[order])) + 1
    return np.split(order, cuts)


def boot(y: np.ndarray, f: np.ndarray, c: np.ndarray, keys: np.ndarray, n_boot: int = 2000,
         seed: int = SEED) -> tuple[float, float, float]:
    """Cluster bootstrap of Delta: returns (low, high, se)."""
    g = _groups(keys)
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        idx = np.concatenate([g[i] for i in rng.integers(0, len(g), len(g))])
        out[b] = delta(y[idx], f[idx], c[idx])
    out = out[np.isfinite(out)]
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)), float(out.std(ddof=1))


def null_cell(y: np.ndarray, f: np.ndarray, c: np.ndarray, n: int = 2000) -> float:
    """Percentile of Delta among count-matched random selections within cell."""
    rng = np.random.default_rng(SEED)
    obs = delta(y, f, c)
    groups = [np.flatnonzero(c == u) for u in np.unique(c)]
    counts = [int(f[g].sum()) for g in groups]
    draws = np.empty(n)
    for b in range(n):
        ff = np.zeros(len(y), bool)
        for g, k in zip(groups, counts, strict=True):
            if k:
                ff[rng.choice(g, k, replace=False)] = True
        draws[b] = delta(y, ff, c)
    return float(100.0 * (draws < obs).mean())


def null_shift(y: np.ndarray, f: np.ndarray, c: np.ndarray, dates: np.ndarray,
               min_shift: int = 40) -> float:
    """Placebo for a date-level treatment: rotate the date-to-treatment map by every shift.

    Preserves the serial dependence of the regime variable and the within-date event structure.
    Only meaningful when the treatment is constant within a date.
    """
    ud, inv = np.unique(dates, return_inverse=True)
    tr_date = np.zeros(len(ud), bool)
    tr_date[inv[f]] = True
    obs = delta(y, f, c)
    draws = []
    for k in range(min_shift, len(ud) - min_shift, max(1, (len(ud) - 2 * min_shift) // 400)):
        ff = np.roll(tr_date, k)[inv]
        v = delta(y, ff, c)
        if np.isfinite(v):
            draws.append(v)
    return float(100.0 * (np.array(draws) < obs).mean()) if len(draws) >= 50 else float("nan")


def score(d: pd.DataFrame, treated: np.ndarray, outcome: str = "yB", defined: np.ndarray | None = None,
          date_level: bool = True, n_boot: int = 2000, label: str = "") -> dict:
    """Full read of one treatment on one block."""
    ok = d[outcome].notna().to_numpy() & (np.ones(len(d), bool) if defined is None else defined)
    b = d[ok]
    f = np.asarray(treated, bool)[ok]
    y = b[outcome].to_numpy(float)
    c = b["cell"].to_numpy(float)
    keys = b["entry_date"].to_numpy()
    months = b["entry_date"].dt.to_period("M").astype(str).to_numpy()
    res = {"outcome": outcome, "n_scored": len(b), "n_treated": int(f.sum()),
           "n_dates_treated": int(pd.Series(keys[f]).nunique()),
           "n_months_treated": int(pd.Series(months[f]).nunique())}
    if f.sum() < 20 or (~f).sum() < 20:
        raise ValueError(f"{label}: too few to score, treated {int(f.sum())} of {len(b)}")
    res["effect"] = delta(y, f, c)
    lo, hi, se = boot(y, f, c, keys, n_boot)
    mlo, mhi, _ = boot(y, f, c, months, n_boot)
    res.update(ci_low=lo, ci_high=hi, ci_month_low=mlo, ci_month_high=mhi, t=res["effect"] / se,
               null_pct_cell=null_cell(y, f, c),
               null_pct_shift=null_shift(y, f, c, keys) if date_level else float("nan"),
               treated_mean=float(y[f].mean()), untreated_mean=float(y[~f].mean()))
    return res


def fmt(r: dict) -> str:
    return (f"N={r['n_scored']} treated={r['n_treated']} ({r['n_dates_treated']} dates, "
            f"{r['n_months_treated']} months) Delta {r['effect']:+.4f} [{r['ci_low']:+.4f}, "
            f"{r['ci_high']:+.4f}] month-clustered [{r['ci_month_low']:+.4f}, "
            f"{r['ci_month_high']:+.4f}] t {r['t']:+.2f} null cell {r['null_pct_cell']:.1f} "
            f"shift {r['null_pct_shift']:.1f} | treated mean {r['treated_mean']:+.4f} "
            f"untreated {r['untreated_mean']:+.4f}")


def log_trial(trial_id: int | str, hypothesis: str, mechanism: str, block: str, r: dict,
              verdict: str) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        row = {k: (f"{v:.5f}" if isinstance(v, float) else v) for k, v in r.items()}
        row.update(trial_id=trial_id, hypothesis=hypothesis, mechanism=mechanism, block=block,
                   verdict=verdict)
        w.writerow(row)
    print(f"[trial {trial_id}] {hypothesis} | {block} | {fmt(r)} | {verdict}")
