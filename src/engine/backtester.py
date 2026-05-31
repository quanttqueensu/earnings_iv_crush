"""backtester.py
Event-driven backtester and scoring for the short-straddle book.

Opens a position 1-3 days pre-announcement, closes into the post-event IV
collapse, and books the realised-vs-implied spread net of costs. ``backtest``
scores a finished ledger against the charter's success metrics; ``compare``
runs the strategy-versus-Agent-0 significance tests (Sharpe spread, paired
t-test, bootstrap CI, Deflated Sharpe) that justify the cross-sectional filter.

This module implements:

* ``daily_return_series`` — collapse a ledger to a per-day return series.
* ``backtest``            — full performance-metric dict for one ledger.
* ``compare``             — strategy-vs-control spread statistics and DSR.
* ``sharpe``              — re-exported from ``engine.stats`` for convenience.

References
----------
Khan, W., & Khan, H. (2024). A 17-year backtest of straddles around S&P 500
earnings announcements. *SSRN Working Paper 4832160*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import stats
from .pnl import ACCOUNT_SIZE, COST_PER_CONTRACT  # noqa: F401  (re-exported)
from .stats import sharpe  # noqa: F401  (re-exported for backward compatibility)

_EMPTY_STATS = {
    "n_trades": 0, "total_pnl": 0.0, "total_return": 0.0, "hit_rate": 0.0,
    "avg_pnl": 0.0, "avg_return_on_margin": float("nan"), "sharpe": 0.0,
    "sortino": 0.0, "profit_factor": 0.0, "win_loss_ratio": 0.0,
    "max_drawdown": 0.0, "max_dd_duration": 0, "final_equity": None,
}


# ─────────────────────────────────────────────────────────────────────────────
# Ledger -> return series
# ─────────────────────────────────────────────────────────────────────────────


def daily_return_series(trades: pd.DataFrame, account: float = ACCOUNT_SIZE) -> pd.Series:
    """
    Collapse a trade ledger into a per-day return series on ``account``.

    Trades sharing an exit date are summed into a single daily P&L point (the
    book realises them together), then divided by the account size. Without an
    ``exit_date`` column the per-trade P&L is returned positionally.

    Parameters
    ----------
    trades : pd.DataFrame
        Ledger as produced by ``pnl.build_ledger`` (needs a ``pnl`` column;
        ``exit_date`` recommended).
    account : float
        Account size used to normalise P&L into returns. Defaults to ``250k``.

    Returns
    -------
    pd.Series
        Per-day returns, date-indexed when ``exit_date`` is present. Empty
        series for an empty ledger.
    """
    if trades is None or len(trades) == 0:
        return pd.Series(dtype=float)
    if "exit_date" in trades:
        dated = trades.assign(exit_date=pd.to_datetime(trades["exit_date"]))
        daily_pnl = dated.groupby("exit_date")["pnl"].sum().sort_index()
    else:
        daily_pnl = trades["pnl"].astype(float).reset_index(drop=True)
    return daily_pnl / account


# ─────────────────────────────────────────────────────────────────────────────
# Single-ledger scoring
# ─────────────────────────────────────────────────────────────────────────────


def backtest(trades: pd.DataFrame, account=ACCOUNT_SIZE,
             periods_per_year: int = 252) -> dict:
    """
    Score a trade ledger and return performance statistics.

    Expects a ledger as produced by ``pnl.build_ledger`` (columns include
    ``pnl``, ``return_on_margin``, and ideally ``exit_date``). P&L is aggregated
    by exit date into a daily series; the Sharpe and Sortino ratios are
    annualised from those daily returns, and the drawdown stats are read off the
    equity curve (starting capital ``account``).

    Returns
    -------
    dict
        ``n_trades``, ``total_pnl``, ``total_return``, ``hit_rate``, ``avg_pnl``,
        ``avg_return_on_margin``, ``sharpe``, ``sortino``, ``profit_factor``,
        ``win_loss_ratio``, ``max_drawdown``, ``max_dd_duration``,
        ``final_equity``.
    """
    if trades is None or len(trades) == 0:
        return {**_EMPTY_STATS, "final_equity": float(account)}

    pnl = trades["pnl"].astype(float)
    daily_return = daily_return_series(trades, account)
    daily_pnl = daily_return * account
    equity = account + daily_pnl.cumsum()
    drawdown = (equity - equity.cummax()) / equity.cummax()
    ror = trades["return_on_margin"] if "return_on_margin" in trades else None

    return {
        "n_trades": int(len(trades)),
        "total_pnl": float(pnl.sum()),
        "total_return": float(pnl.sum() / account),
        "hit_rate": float((pnl > 0).mean()),
        "avg_pnl": float(pnl.mean()),
        "avg_return_on_margin": float(ror.mean()) if ror is not None else float("nan"),
        "sharpe": float(stats.sharpe(daily_return, periods_per_year)),
        "sortino": float(stats.sortino_ratio(daily_return, periods_per_year)),
        "profit_factor": float(stats.profit_factor(pnl)),
        "win_loss_ratio": float(stats.win_loss_ratio(pnl)),
        "max_drawdown": float(drawdown.min()),
        "max_dd_duration": int(stats.max_drawdown_duration(equity)),
        "final_equity": float(equity.iloc[-1]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Strategy-vs-control comparison
# ─────────────────────────────────────────────────────────────────────────────


def compare(strategy_trades: pd.DataFrame, agent0_trades: pd.DataFrame,
            account: float = ACCOUNT_SIZE, periods_per_year: int = 252,
            n_trials: int = 1, sr_trials_std: float = 0.0,
            n_boot: int = 2000, ci: float = 0.95, seed: int = 0) -> dict:
    """
    Significance of the filtered strategy over the unfiltered Agent 0 control.

    Aligns both books to a common daily return series (a day a book does not
    trade contributes a zero return), then reports the Sharpe spread, a paired
    t-test on the daily spread, a bootstrap confidence interval on the Sharpe
    spread, and the Deflated Sharpe Ratio of the strategy (which discounts the
    Sharpe for the number of filter configurations effectively tried).

    Parameters
    ----------
    strategy_trades, agent0_trades : pd.DataFrame
        Ledgers for the filtered strategy and the control.
    account : float
        Account size for return normalisation.
    periods_per_year : int
        Annualisation factor. Defaults to ``252``.
    n_trials : int
        Filter configurations effectively tried, fed to the Deflated Sharpe.
    sr_trials_std : float
        Per-period Sharpe dispersion across those trials (see ``stats``).
    n_boot : int
        Bootstrap resamples for the Sharpe-spread interval.
    ci : float
        Central interval mass for the bootstrap CI.
    seed : int
        Seed for reproducibility.

    Returns
    -------
    dict
        ``sharpe_strategy``, ``sharpe_agent0``, ``sharpe_delta``,
        ``sharpe_delta_ci_low``/``_high``, ``spread_tstat``, ``spread_pvalue``,
        ``psr_strategy``, ``dsr_strategy``, ``filter_gate_pass`` (delta >= 0.5).
    """
    s = daily_return_series(strategy_trades, account)
    a = daily_return_series(agent0_trades, account)
    idx = s.index.union(a.index)
    s = s.reindex(idx, fill_value=0.0)
    a = a.reindex(idx, fill_value=0.0)
    spread = s - a

    sr_s = stats.sharpe(s, periods_per_year)
    sr_a = stats.sharpe(a, periods_per_year)
    delta = sr_s - sr_a

    # Paired test on the daily spread (is the strategy reliably above control?).
    if len(spread) >= 2 and spread.std() > 0:
        from scipy import stats as _sps
        t_stat, p_val = _sps.ttest_1samp(spread.to_numpy(), 0.0)
        t_stat, p_val = float(t_stat), float(p_val)
    else:
        t_stat, p_val = float("nan"), float("nan")

    # Paired bootstrap CI on the Sharpe spread.
    lo, hi = _bootstrap_sharpe_delta_ci(
        s.to_numpy(), a.to_numpy(), periods_per_year, n_boot, ci, seed
    )

    return {
        "sharpe_strategy": float(sr_s),
        "sharpe_agent0": float(sr_a),
        "sharpe_delta": float(delta),
        "sharpe_delta_ci_low": lo,
        "sharpe_delta_ci_high": hi,
        "spread_tstat": t_stat,
        "spread_pvalue": p_val,
        "psr_strategy": float(stats.probabilistic_sharpe_ratio(s)),
        "dsr_strategy": float(stats.deflated_sharpe_ratio(s, n_trials, sr_trials_std)),
        "filter_gate_pass": bool(delta >= 0.5),
    }


def _bootstrap_sharpe_delta_ci(s: np.ndarray, a: np.ndarray, periods_per_year: int,
                               n_boot: int, ci: float, seed: int) -> tuple[float, float]:
    """Percentile CI for the paired Sharpe spread (strategy minus control)."""
    n = len(s)
    if n < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    deltas = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, n, size=n)
        ss, aa = s[pick], a[pick]
        sd_s, sd_a = ss.std(ddof=1), aa.std(ddof=1)
        sr_s = ss.mean() / sd_s * np.sqrt(periods_per_year) if sd_s > 0 else 0.0
        sr_a = aa.mean() / sd_a * np.sqrt(periods_per_year) if sd_a > 0 else 0.0
        deltas[b] = sr_s - sr_a
    lo = float(np.nanpercentile(deltas, 100 * (1 - ci) / 2))
    hi = float(np.nanpercentile(deltas, 100 * (1 + ci) / 2))
    return lo, hi
