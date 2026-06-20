"""portfolio.py
Capital-based equity curves and risk-adjusted metrics for an event book.

The frequency-neutral, per-trade statistics in :mod:`engine.backtester` are the
right basis for comparing two *selection* arms with each other, but the wrong basis
for comparing the book against a passive benchmark: a capital allocator does not
experience the strategy one trade at a time. Capital is committed to the book, sits
flat between earnings events, and marks P&L on the days trades exit. This module
builds that allocator's view, a fixed-notional dollar equity curve scored
calendar-day with flat days included, and the standard risk metrics on top.

This module implements:

* ``ledger_daily_pnl`` — realised P&L booked on each trade's exit date.
* ``equity_curve``     — fixed-notional account value from a daily P&L series.
* ``drawdown``         — running peak-to-trough drawdown of an equity curve.
* ``risk_metrics``     — total return, CAGR, vol, Sharpe, max drawdown and, when a
  market series is supplied, beta and correlation to it.

Notes
-----
Sharpe, beta and correlation are invariant to the capital base; only total return
and CAGR scale with it. The capital base therefore changes the return numbers but
never the risk-adjusted comparison.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import GLOBAL

ANN = GLOBAL.trading_days_per_year


# ─────────────────────────────────────────────────────────────────────────────
# Equity construction
# ─────────────────────────────────────────────────────────────────────────────


def ledger_daily_pnl(
    ledger: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    date_col: str = "exit_date",
    pnl_col: str = "pnl",
) -> pd.Series:
    """
    Realised P&L booked on each trade's exit date, reindexed to a calendar.

    Parameters
    ----------
    ledger : pandas.DataFrame
        Per-trade ledger carrying an exit-date column and a P&L column.
    calendar : pandas.DatetimeIndex
        Trading calendar the series is laid onto; days with no exiting trade are
        filled with zero.
    date_col : str
        Column holding the trade exit date. Defaults to ``"exit_date"``.
    pnl_col : str
        Column holding the per-trade P&L in USD. Defaults to ``"pnl"``.

    Returns
    -------
    pandas.Series
        Daily realised P&L indexed by ``calendar`` (zeros on flat days).
    """
    if len(ledger) == 0:
        return pd.Series(0.0, index=calendar)
    booked = ledger.assign(_d=pd.to_datetime(ledger[date_col])).groupby("_d")[pnl_col].sum()
    return booked.reindex(calendar).fillna(0.0)


def equity_curve(daily_pnl: pd.Series, capital: float) -> pd.Series:
    """
    Fixed-notional account value from a daily P&L series.

    Parameters
    ----------
    daily_pnl : pandas.Series
        Daily realised P&L in USD on a trading calendar.
    capital : float
        Starting account value in USD; held fixed (no compounding) so the curve
        is ``capital`` plus cumulative P&L.

    Returns
    -------
    pandas.Series
        Account value on the same index as ``daily_pnl``.
    """
    return capital + daily_pnl.cumsum()


def drawdown(equity: pd.Series) -> pd.Series:
    """Running peak-to-trough drawdown of an equity curve (fraction, <= 0)."""
    return equity / equity.cummax() - 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Risk metrics
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskMetrics:
    """Risk-adjusted summary of a calendar-day return series.

    Attributes
    ----------
    total_return : float
        Cumulative return over the window (equity end / start minus one).
    cagr : float
        Compound annual growth rate implied by the endpoints.
    ann_vol : float
        Annualised standard deviation of the daily return series.
    sharpe : float
        Annualised Sharpe at a zero risk-free rate; ``nan`` if vol is zero.
    max_drawdown : float
        Worst peak-to-trough drawdown (fraction, <= 0).
    beta_vs_market : float
        OLS beta of daily returns on the market series; ``nan`` if no market
        series is supplied or its variance is zero.
    corr_vs_market : float
        Correlation of daily returns with the market series; ``nan`` if absent.
    active_days : int
        Number of calendar days with a non-zero return.
    calendar_days : int
        Length of the return series.
    """

    total_return: float
    cagr: float
    ann_vol: float
    sharpe: float
    max_drawdown: float
    beta_vs_market: float
    corr_vs_market: float
    active_days: int
    calendar_days: int

    def as_dict(self) -> dict:
        """Return the metrics as a plain dict (CSV-friendly)."""
        return {
            "total_return": self.total_return,
            "cagr": self.cagr,
            "ann_vol": self.ann_vol,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "beta_vs_market": self.beta_vs_market,
            "corr_vs_market": self.corr_vs_market,
            "active_days": self.active_days,
            "calendar_days": self.calendar_days,
        }


def risk_metrics(
    returns: pd.Series,
    equity: pd.Series,
    market_returns: pd.Series | None = None,
    ann: int = ANN,
) -> RiskMetrics:
    """
    Risk-adjusted metrics for a calendar-day return series.

    Parameters
    ----------
    returns : pandas.Series
        Daily returns on the capital base (flat days included as zeros).
    equity : pandas.Series
        Account-value curve aligned with ``returns``; used for total return,
        CAGR and the drawdown.
    market_returns : pandas.Series, optional
        Daily market returns over the same calendar for beta and correlation. If
        ``None``, both are reported as ``nan``.
    ann : int
        Trading days per year used to annualise. Defaults to the config value.

    Returns
    -------
    RiskMetrics
        The summary; ``beta_vs_market`` and ``corr_vs_market`` are ``nan`` when
        no market series is given.
    """
    n = len(returns)
    years = n / ann
    sd = returns.std(ddof=1)
    total = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1.0) if years > 0 else np.nan
    vol = float(sd * np.sqrt(ann))
    sharpe = float(returns.mean() / sd * np.sqrt(ann)) if sd > 0 else np.nan
    max_dd = float(drawdown(equity).min())

    beta = corr = np.nan
    if market_returns is not None:
        aligned = pd.concat([returns, market_returns], axis=1).dropna()
        if len(aligned) > 2 and aligned.iloc[:, 1].var(ddof=1) > 0:
            cov = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
            beta = float(cov[0, 1] / cov[1, 1])
            corr = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))

    return RiskMetrics(
        total_return=total,
        cagr=cagr,
        ann_vol=vol,
        sharpe=sharpe,
        max_drawdown=max_dd,
        beta_vs_market=beta,
        corr_vs_market=corr,
        active_days=int((returns != 0).sum()),
        calendar_days=int(n),
    )


def book_equity(
    ledger: pd.DataFrame,
    capital: float,
    calendar: pd.DatetimeIndex,
    date_col: str = "exit_date",
    pnl_col: str = "pnl",
) -> tuple[pd.Series, pd.Series]:
    """
    Convenience wrapper: ledger to ``(daily_return, equity)`` on a calendar.

    Parameters
    ----------
    ledger : pandas.DataFrame
        Per-trade ledger with exit-date and P&L columns.
    capital : float
        Fixed account notional in USD.
    calendar : pandas.DatetimeIndex
        Trading calendar to lay the book onto.
    date_col, pnl_col : str
        Column names for the exit date and P&L.

    Returns
    -------
    tuple of pandas.Series
        ``(daily_return, equity)``; daily return is realised P&L over ``capital``.
    """
    pnl = ledger_daily_pnl(ledger, calendar, date_col=date_col, pnl_col=pnl_col)
    equity = equity_curve(pnl, capital)
    return pnl / capital, equity
