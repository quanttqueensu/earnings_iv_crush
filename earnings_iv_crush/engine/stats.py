"""stats.py
Performance and significance statistics for the trade book.

Pure functions over return / P&L series - no orchestration, no I/O - so they
are unit-tested in isolation and reused by ``engine.backtester`` and the
research tearsheet. Covers the strategy's success metrics (Sharpe, Sortino,
profit factor, win/loss ratio, drawdown duration) and the research-grade
significance tools needed to defend a *selected* strategy against the
unfiltered control: bootstrap confidence intervals, the Probabilistic Sharpe
Ratio, and the Deflated Sharpe Ratio that penalises filter-threshold tuning.

This module implements:

* ``sharpe`` / ``sortino_ratio``          - annualised risk-adjusted return.
* ``nyse_sessions`` / ``calendar_sharpe`` - Sharpe on the exchange calendar with
  idle sessions zero-filled (the capital-allocation basis).
* ``profit_factor`` / ``win_loss_ratio``  - gross-win/-loss diagnostics.
* ``max_drawdown_duration``               - longest peak-to-recovery span.
* ``bootstrap_sharpe_ci``                 - resampled Sharpe confidence interval.
* ``probabilistic_sharpe_ratio``          - P(true Sharpe > benchmark).
* ``expected_max_sharpe`` / ``deflated_sharpe_ratio`` - multiple-testing
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
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
    sunday_to_monday,
)
from scipy import stats as _sps

EULER_MASCHERONI = 0.5772156649015329

# Unscheduled full-day NYSE closures inside the project's 2013-2024 sample.
# Hurricane Sandy (2012) predates it; the Carter funeral (2025) postdates it.
NYSE_AD_HOC_CLOSURES = ("2018-12-05",)


# ─────────────────────────────────────────────────────────────────────────────
# Risk-adjusted return
# ─────────────────────────────────────────────────────────────────────────────


def infer_periods_per_year(index: pd.Index) -> float:
    """
    Observations-per-year implied by a dated series' own calendar span.

    The frequency-consistent annualisation base. A book that records ``n``
    distinct dated observations across a span of ``span`` years realises
    ``n / span`` periods a year, so annualising its per-period Sharpe by
    ``sqrt(n / span)`` neither inflates a sparse event book to a daily cadence
    (the ``sqrt(252)`` artefact) nor deflates a dense one.

    Parameters
    ----------
    index : pd.Index
        Index of the return series being annualised, ideally a ``DatetimeIndex``.

    Returns
    -------
    float
        Observations per year. Falls back to ``252.0`` when the index is not
        datetime-like, has fewer than two points, or spans no calendar time.
    """
    try:
        idx = pd.DatetimeIndex(index)
    except (TypeError, ValueError):
        return 252.0
    if len(idx) < 2:
        return 252.0
    span_days = (idx.max() - idx.min()).days
    if span_days <= 0:
        return 252.0
    return float(len(idx) * 365.25 / span_days)


def sharpe(returns: pd.Series, periods_per_year: float = 252) -> float:
    """
    Annualised Sharpe ratio of a per-trade or per-day return series.

    Parameters
    ----------
    returns : pd.Series
        Periodic (e.g. daily) returns, already net of costs.
    periods_per_year : float
        Annualisation factor. Defaults to ``252`` trading days. For a sparse
        event book pass the realised observations-per-year from
        :func:`infer_periods_per_year` so the figure is not inflated.

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


class _NYSECalendar(AbstractHolidayCalendar):
    """NYSE holiday rules. Federal calendar less Columbus Day and Veterans Day,
    plus Good Friday, plus Juneteenth from its first observance in 2022.

    Saturday observance is not uniform, which is why New Year's carries a
    different rule from the rest: the exchange closes the preceding Friday for a
    Saturday Christmas or Independence Day, but not for a Saturday New Year's
    (31 December 2021 was a full session). ``nearest_workday`` rolls back in all
    three cases, so New Year's uses ``sunday_to_monday`` instead and a Saturday
    occurrence simply falls off the weekday index.
    """

    rules = [
        Holiday("NewYears", month=1, day=1, observance=sunday_to_monday),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-06-20", observance=nearest_workday),
        Holiday("Independence", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


def nyse_sessions(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """
    NYSE trading sessions between two dates, inclusive.

    Weekdays less the exchange holiday calendar and the unscheduled closures in
    :data:`NYSE_AD_HOC_CLOSURES`. Half-days (the 1pm closes around Independence
    Day, Thanksgiving and Christmas) are full sessions for this purpose: the
    book either has a mark on them or it does not.

    Parameters
    ----------
    start, end : pd.Timestamp
        Inclusive bounds.

    Returns
    -------
    pd.DatetimeIndex
        Session dates, ascending.
    """
    days = pd.bdate_range(start, end)
    holidays = _NYSECalendar().holidays(start, end)
    return days.difference(holidays).difference(pd.to_datetime(list(NYSE_AD_HOC_CLOSURES)))


def calendar_sharpe(daily_return: pd.Series, periods_per_year: float = 252) -> float:
    """
    Annualised Sharpe on the exchange calendar, idle sessions zero-filled.

    Reindexes a dated return series onto every NYSE session in its own span and
    charges a zero return to each day the book does not trade, then annualises
    by ``sqrt(252)``. This is the capital-allocation basis: it measures what a
    dollar committed to the book earns per unit of risk over a year, including
    the days that dollar sits idle. Idle days contribute exactly zero because
    the Sharpe numerator is an excess return and cash earns the risk-free rate
    it is measured against, so no cash-return assumption is needed at any level
    of rates.

    Relation to :func:`infer_periods_per_year`. For a book that trades one
    position at a time, zero-filling and scaling by ``sqrt(252)`` is
    algebraically the same as scaling the per-trade Sharpe by
    ``sqrt(trades per year)``, to first order in mean/sd. The two diverge when
    positions overlap: earnings cluster into four windows a year, so several
    straddles share exit dates and diversify against each other within a day.
    That effect is in the daily series and is not in the trade count, which is
    why this is the better basis for a clustered event book.

    Do not confuse either figure with the per-trade Sharpe, which is a
    signal-detection statistic for whether the gate selects, not a claim about
    what the capital earns.

    Parameters
    ----------
    daily_return : pd.Series
        Date-indexed returns on the funded account, net of costs. A non-datetime
        index is scored as-is, with no zero-filling.
    periods_per_year : float
        Annualisation factor for the zero-filled series. Defaults to ``252``,
        which is the whole point of this function; override only for a non-daily
        calendar.

    Returns
    -------
    float
        Annualised Sharpe, or ``0.0`` for an empty or zero-dispersion series.
    """
    r = pd.Series(daily_return, dtype=float)
    if len(r) == 0:
        return 0.0
    if isinstance(r.index, pd.DatetimeIndex):
        idx = r.index
    elif r.index.dtype == object:
        # Date strings are fine; anything else is positional and must not be
        # coerced. ``pd.DatetimeIndex`` reads an integer index as nanoseconds
        # since the epoch rather than raising, which would silently zero-fill a
        # positional series across 1970 and return a meaningless 0.0.
        try:
            idx = pd.DatetimeIndex(r.index)
        except (TypeError, ValueError):
            return sharpe(r, periods_per_year)
    else:
        return sharpe(r, periods_per_year)
    r = r.groupby(idx).sum()
    r = r.reindex(nyse_sessions(idx.min(), idx.max()), fill_value=0.0)
    return sharpe(r, periods_per_year)


def sortino_ratio(returns: pd.Series, periods_per_year: float = 252, target: float = 0.0) -> float:
    """
    Annualised Sortino ratio (downside-deviation risk adjustment).

    Like the Sharpe ratio but the denominator penalises only returns below
    ``target``, so symmetric upside volatility is not charged as risk.

    Parameters
    ----------
    returns : pd.Series
        Periodic returns, net of costs.
    periods_per_year : float
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
    dd = np.sqrt((downside**2).mean())
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


def bootstrap_sharpe_ci(
    returns: pd.Series,
    periods_per_year: int = 252,
    n_boot: int = 2000,
    ci: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
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


def probabilistic_sharpe_ratio(returns: pd.Series, sr_benchmark_per_period: float = 0.0) -> float:
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
    denom = np.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr**2)
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
    term = (1 - EULER_MASCHERONI) * norm.ppf(1 - 1.0 / n_trials) + EULER_MASCHERONI * norm.ppf(
        1 - 1.0 / (n_trials * e)
    )
    return float(sr_trials_std * term)


def deflated_sharpe_ratio(
    returns: pd.Series, n_trials: int = 1, sr_trials_std: float = 0.0
) -> float:
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
