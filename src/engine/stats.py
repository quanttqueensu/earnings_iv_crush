"""stats.py
Performance and significance statistics for the trade book.

Pure functions over return / P&L series — no orchestration, no I/O — so they
are unit-tested in isolation and reused by ``engine.backtester`` and the
research tearsheet. Covers the charter's success metrics (Sharpe, Sortino,
profit factor, win/loss ratio, drawdown duration) and the research-grade
significance tools needed to defend a *selected* strategy against the
unfiltered control: bootstrap confidence intervals, the Probabilistic Sharpe
Ratio, and the Deflated Sharpe Ratio that penalises filter-threshold tuning.

This module implements:

* ``sharpe`` / ``sortino_ratio``          — annualised risk-adjusted return.
* ``profit_factor`` / ``win_loss_ratio``  — gross-win/-loss diagnostics.
* ``max_drawdown_duration``               — longest peak-to-recovery span.
* ``bootstrap_sharpe_ci``                 — resampled Sharpe confidence interval.
* ``probabilistic_sharpe_ratio``          — P(true Sharpe > benchmark).
* ``expected_max_sharpe`` / ``deflated_sharpe_ratio`` — multiple-testing
  adjusted significance (Bailey & López de Prado).

References
----------
Bailey, D. H., & López de Prado, M. (2014). The deflated Sharpe ratio:
Correcting for selection bias, backtest overfitting, and non-normality.
*Journal of Portfolio Management*, 40(5), 94-107.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as _sps

EULER_MASCHERONI = 0.5772156649015329


# ─────────────────────────────────────────────────────────────────────────────
# Risk-adjusted return
# ─────────────────────────────────────────────────────────────────────────────


def sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
    """
    Annualised Sharpe ratio of a per-trade or per-day return series.

    Parameters
    ----------
    returns : pd.Series
        Periodic (e.g. daily) returns, already net of costs.
    periods_per_year : int
        Annualisation factor. Defaults to ``252`` trading days.

    Returns
    -------
    float
        Annualised Sharpe, or ``0.0`` when the series has zero dispersion.
    """
    returns = pd.Series(returns, dtype=float)
    sd = returns.std()
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(returns.mean() / sd * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: int = 252,
                  target: float = 0.0) -> float:
    """
    Annualised Sortino ratio (downside-deviation risk adjustment).

    Like the Sharpe ratio but the denominator penalises only returns below
    ``target``, so symmetric upside volatility is not charged as risk.

    Parameters
    ----------
    returns : pd.Series
        Periodic returns, net of costs.
    periods_per_year : int
        Annualisation factor. Defaults to ``252``.
    target : float
        Minimum acceptable periodic return. Defaults to ``0.0``.

    Returns
    -------
    float
        Annualised Sortino ratio. ``0.0`` if there is no downside dispersion
        (no returns below ``target``).
    """
    returns = pd.Series(returns, dtype=float)
    downside = returns[returns < target] - target
    if downside.empty:
        return 0.0
    dd = np.sqrt((downside ** 2).mean())
    if dd == 0 or not np.isfinite(dd):
        return 0.0
    return float((returns.mean() - target) / dd * np.sqrt(periods_per_year))


# ─────────────────────────────────────────────────────────────────────────────
# Win / loss diagnostics
# ─────────────────────────────────────────────────────────────────────────────


def profit_factor(pnl: pd.Series) -> float:
    """
    Gross profit divided by gross loss (absolute).

    Parameters
    ----------
    pnl : pd.Series
        Per-trade P&L in currency units.

    Returns
    -------
    float
        Profit factor. ``inf`` when there are no losing trades but some wins;
        ``0.0`` when there are no winning trades.
    """
    pnl = pd.Series(pnl, dtype=float)
    gross_win = pnl[pnl > 0].sum()
    gross_loss = -pnl[pnl < 0].sum()
    if gross_loss == 0:
        return float("inf") if gross_win > 0 else 0.0
    return float(gross_win / gross_loss)


def win_loss_ratio(pnl: pd.Series) -> float:
    """
    Average winning trade divided by the average losing trade (absolute).

    Parameters
    ----------
    pnl : pd.Series
        Per-trade P&L in currency units.

    Returns
    -------
    float
        Avg win / avg loss. ``inf`` if there are wins but no losses; ``0.0``
        if there are no wins.
    """
    pnl = pd.Series(pnl, dtype=float)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    if losses.empty:
        return float("inf") if not wins.empty else 0.0
    if wins.empty:
        return 0.0
    return float(wins.mean() / abs(losses.mean()))


def max_drawdown_duration(equity: pd.Series) -> int:
    """
    Longest run (in periods) the equity curve spends below a prior peak.

    Parameters
    ----------
    equity : pd.Series
        Equity curve (cumulative capital), ordered in time.

    Returns
    -------
    int
        Maximum number of consecutive periods strictly below the running peak.
        ``0`` for a monotonically non-decreasing curve.
    """
    equity = pd.Series(equity, dtype=float).reset_index(drop=True)
    if equity.empty:
        return 0
    peak = equity.cummax()
    underwater = equity < peak
    longest = run = 0
    for under in underwater:
        run = run + 1 if under else 0
        longest = max(longest, run)
    return int(longest)


# ─────────────────────────────────────────────────────────────────────────────
# Significance: bootstrap and (deflated) Sharpe
# ─────────────────────────────────────────────────────────────────────────────


def bootstrap_sharpe_ci(returns: pd.Series, periods_per_year: int = 252,
                        n_boot: int = 2000, ci: float = 0.95,
                        seed: int = 0) -> tuple[float, float]:
    """
    Percentile bootstrap confidence interval for the annualised Sharpe.

    Resamples the return series with replacement ``n_boot`` times and reads the
    central ``ci`` interval off the bootstrap Sharpe distribution.

    Parameters
    ----------
    returns : pd.Series
        Periodic returns, net of costs.
    periods_per_year : int
        Annualisation factor. Defaults to ``252``.
    n_boot : int
        Number of bootstrap resamples. Defaults to ``2000``.
    ci : float
        Central interval mass, e.g. ``0.95`` for a 95% interval.
    seed : int
        Seed for reproducibility.

    Returns
    -------
    tuple of float
        ``(low, high)`` Sharpe bounds. ``(nan, nan)`` if the series has fewer
        than two observations.
    """
    returns = pd.Series(returns, dtype=float).dropna()
    if len(returns) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    arr = returns.to_numpy()
    draws = rng.choice(arr, size=(n_boot, len(arr)), replace=True)
    means = draws.mean(axis=1)
    sds = draws.std(axis=1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        sr = np.where(sds > 0, means / sds * np.sqrt(periods_per_year), 0.0)
    lo = float(np.nanpercentile(sr, 100 * (1 - ci) / 2))
    hi = float(np.nanpercentile(sr, 100 * (1 + ci) / 2))
    return lo, hi


def _per_period_sharpe(returns: np.ndarray) -> float:
    """Non-annualised Sharpe (mean / std, ddof=1) used by the PSR/DSR formulae."""
    sd = returns.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(returns.mean() / sd)


def probabilistic_sharpe_ratio(returns: pd.Series,
                               sr_benchmark_per_period: float = 0.0) -> float:
    """
    Probability that the true Sharpe exceeds a benchmark (Bailey & LdP).

    Accounts for sample length, skewness and kurtosis of the returns: a high
    Sharpe earned over few, fat-tailed observations is discounted.

    Parameters
    ----------
    returns : pd.Series
        Periodic returns, net of costs.
    sr_benchmark_per_period : float
        Benchmark Sharpe in per-period (non-annualised) units. Defaults to
        ``0.0``.

    Returns
    -------
    float
        PSR in ``[0, 1]``. ``nan`` if there are fewer than three observations
        or the returns have zero dispersion.
    """
    r = pd.Series(returns, dtype=float).dropna().to_numpy()
    n = r.size
    if n < 3:
        return float("nan")
    sr = _per_period_sharpe(r)
    sd = r.std(ddof=1)
    if sd == 0:
        return float("nan")
    skew = float(_sps.skew(r, bias=False))
    kurt = float(_sps.kurtosis(r, fisher=False, bias=False))  # normal -> 3
    denom = np.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    if denom == 0 or not np.isfinite(denom):
        return float("nan")
    z = (sr - sr_benchmark_per_period) * np.sqrt(n - 1) / denom
    return float(_sps.norm.cdf(z))


def expected_max_sharpe(n_trials: int, sr_trials_std: float) -> float:
    """
    Expected maximum per-period Sharpe under ``n_trials`` independent trials.

    The selection-bias benchmark of the Deflated Sharpe Ratio: even with no
    real edge, the best of many tried configurations has an inflated Sharpe.

    Parameters
    ----------
    n_trials : int
        Number of strategy configurations effectively tried (e.g. filter-
        threshold grid points). ``<= 1`` returns ``0.0`` (no selection).
    sr_trials_std : float
        Standard deviation of the per-period Sharpe estimates across trials.

    Returns
    -------
    float
        Expected maximum per-period Sharpe attributable to selection alone.
    """
    if n_trials <= 1 or sr_trials_std <= 0:
        return 0.0
    norm = _sps.norm
    e = np.e
    term = ((1 - EULER_MASCHERONI) * norm.ppf(1 - 1.0 / n_trials)
            + EULER_MASCHERONI * norm.ppf(1 - 1.0 / (n_trials * e)))
    return float(sr_trials_std * term)


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int = 1,
                          sr_trials_std: float = 0.0) -> float:
    """
    Deflated Sharpe Ratio: PSR against the selection-bias benchmark.

    Equals ``probabilistic_sharpe_ratio`` evaluated at the expected maximum
    Sharpe a researcher would obtain from ``n_trials`` configurations with no
    true edge. A DSR near 1 says the observed Sharpe is unlikely to be a fluke
    of having tuned the filter thresholds; near 0.5 or below it is consistent
    with overfitting.

    Parameters
    ----------
    returns : pd.Series
        Periodic returns, net of costs.
    n_trials : int
        Number of configurations effectively tried. Defaults to ``1`` (no
        deflation, so DSR reduces to PSR against zero).
    sr_trials_std : float
        Per-period standard deviation of trial Sharpes. Defaults to ``0.0``.

    Returns
    -------
    float
        DSR in ``[0, 1]``; ``nan`` for degenerate input (see
        ``probabilistic_sharpe_ratio``).
    """
    sr_star = expected_max_sharpe(n_trials, sr_trials_std)
    return probabilistic_sharpe_ratio(returns, sr_benchmark_per_period=sr_star)
