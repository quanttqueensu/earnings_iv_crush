"""
cohorts.py
Per-cohort performance comparison: does size/liquidity carry the edge?

The backtest runs two frozen universes (megacap vs broad; see
``data/universe.py``). This module cuts one trade ledger by cohort label and
tests whether per-trade economics differ between the liquidity-clean megacap
book and the broad-only remainder — the cleanest free-data read on whether the
filtered IV-crush edge survives outside the most liquid names.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import GLOBAL
from .backtester import daily_return_series
from .stats import sharpe


def _max_drawdown(daily: pd.Series) -> float:
    """Worst peak-to-trough drawdown of a daily return series."""
    if daily is None or len(daily) == 0:
        return 0.0
    equity = (1 + daily).cumprod()
    return float((equity / equity.cummax() - 1).min())


COHORT_METRICS = [
    "cohort",
    "n_trades",
    "total_pnl",
    "mean_pnl",
    "hit_rate",
    "sharpe",
    "max_drawdown",
]


def cohort_table(ledger: pd.DataFrame, account: float = GLOBAL.account_size) -> pd.DataFrame:
    """Per-cohort summary of a trade ledger carrying a ``cohort`` column."""
    if ledger is None or ledger.empty or "cohort" not in ledger.columns:
        return pd.DataFrame(columns=COHORT_METRICS)
    rows = []
    for cohort, grp in ledger.groupby("cohort"):
        daily = daily_return_series(grp, account)
        rows.append(
            {
                "cohort": cohort,
                "n_trades": len(grp),
                "total_pnl": float(grp["pnl"].sum()),
                "mean_pnl": float(grp["pnl"].mean()),
                "hit_rate": float((grp["pnl"] > 0).mean()),
                "sharpe": sharpe(daily),
                "max_drawdown": _max_drawdown(daily),
            }
        )
    return pd.DataFrame(rows, columns=COHORT_METRICS)


def compare_cohorts(
    ledger: pd.DataFrame,
    a: str = "megacap",
    b: str = "broad-only",
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Bootstrap test of the per-trade P&L difference between two cohorts.

    Resamples each cohort's per-trade P&L independently and reports the CI on
    the difference in means (a - b). With free daily-close data per-trade P&L
    is the honest unit; daily Sharpe differences on thin cohort books are
    mostly noise.

    Returns
    -------
    dict
        ``mean_pnl_a``, ``mean_pnl_b``, ``mean_diff``, ``diff_ci_low``,
        ``diff_ci_high``, ``n_a``, ``n_b``, ``significant`` (CI excludes 0).
    """
    out = {
        "mean_pnl_a": float("nan"),
        "mean_pnl_b": float("nan"),
        "mean_diff": float("nan"),
        "diff_ci_low": float("nan"),
        "diff_ci_high": float("nan"),
        "n_a": 0,
        "n_b": 0,
        "significant": False,
    }
    if ledger is None or ledger.empty or "cohort" not in ledger.columns:
        return out
    pnl_a = ledger.loc[ledger["cohort"] == a, "pnl"].to_numpy(dtype=float)
    pnl_b = ledger.loc[ledger["cohort"] == b, "pnl"].to_numpy(dtype=float)
    out["n_a"], out["n_b"] = len(pnl_a), len(pnl_b)
    if len(pnl_a) == 0 or len(pnl_b) == 0:
        return out
    out["mean_pnl_a"] = float(pnl_a.mean())
    out["mean_pnl_b"] = float(pnl_b.mean())
    out["mean_diff"] = out["mean_pnl_a"] - out["mean_pnl_b"]

    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        diffs[i] = (
            rng.choice(pnl_a, size=len(pnl_a), replace=True).mean()
            - rng.choice(pnl_b, size=len(pnl_b), replace=True).mean()
        )
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    out["diff_ci_low"], out["diff_ci_high"] = float(lo), float(hi)
    out["significant"] = bool(lo > 0 or hi < 0)
    return out
