"""risk.py
Position sizing, stops and portfolio controls.

Implements the spec §3 risk rules that are testable without live data: size each
position so its worst case is a fixed fraction of NAV, apply the 3x-premium stop
to naked structures, halt new entries on a portfolio drawdown breach, and cap
concentration by ticker and sector. These convert the raw event ledger into a
risk-managed book, which is what separates a tradeable strategy from a backtest
curve.

This module implements:

* ``worst_case_size``        — contracts so worst-case loss = ``risk_frac`` of NAV.
* ``apply_premium_stop``     — floor naked P&L at the 3x-premium stop.
* ``circuit_breaker_breach`` — first date the equity curve breaches the limit.
* ``halt_new_entries``       — drop entries placed after a breach.
* ``cap_concentration``      — enforce one position per ticker, N per sector/day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RISK_FRAC_PER_TRADE = 0.01      # 1.0% NAV worst-case per position
PREMIUM_STOP_MULTIPLE = 3.0     # naked stop at 3x the entry credit
DRAWDOWN_CIRCUIT_BREAKER = 0.15  # 15% portfolio drawdown halts new entries
MAX_PER_SECTOR = 3
CONTRACT_MULTIPLIER = 100


# ─────────────────────────────────────────────────────────────────────────────
# Sizing
# ─────────────────────────────────────────────────────────────────────────────


def worst_case_size(account: float, credit_per_share: float,
                    risk_frac: float = RISK_FRAC_PER_TRADE,
                    stop_multiple: float = PREMIUM_STOP_MULTIPLE,
                    defined_max_loss_per_share: float | None = None,
                    multiplier: int = CONTRACT_MULTIPLIER) -> int:
    """
    Number of straddles so the worst-case loss equals ``risk_frac`` of NAV.

    The worst case is the iron fly's defined wing loss when
    ``defined_max_loss_per_share`` is given, otherwise the naked 3x-premium stop
    (``stop_multiple * credit_per_share``).

    Parameters
    ----------
    account : float
        Net asset value (USD).
    credit_per_share : float
        Straddle credit collected per share (USD).
    risk_frac : float
        Fraction of NAV risked per position. Defaults to ``0.01`` (1%).
    stop_multiple : float
        Premium multiple of the naked stop. Defaults to ``3.0``.
    defined_max_loss_per_share : float, optional
        Defined worst-case loss per share for a capped structure (iron fly).
        When given it overrides the stop-based worst case.
    multiplier : int
        Shares per contract. Defaults to ``100``.

    Returns
    -------
    int
        Contract count (``>= 0``); ``0`` when the worst case is non-positive.
    """
    worst_ps = (defined_max_loss_per_share if defined_max_loss_per_share is not None
                else stop_multiple * credit_per_share)
    worst_per_contract = worst_ps * multiplier
    if worst_per_contract <= 0:
        return 0
    return int((risk_frac * account) // worst_per_contract)


# ─────────────────────────────────────────────────────────────────────────────
# Stops
# ─────────────────────────────────────────────────────────────────────────────


def apply_premium_stop(pnl, entry_credit, stop_multiple: float = PREMIUM_STOP_MULTIPLE):
    """
    Floor naked short-straddle P&L at the 3x-premium stop.

    A naked position is closed once the loss reaches ``stop_multiple`` times the
    entry credit, so realised P&L cannot fall below ``-stop_multiple * credit``.

    Parameters
    ----------
    pnl : float or pd.Series
        Unstopped P&L (USD).
    entry_credit : float or pd.Series
        Entry credit collected (USD), aligned with ``pnl``.
    stop_multiple : float
        Premium multiple of the stop. Defaults to ``3.0``.

    Returns
    -------
    float or pd.Series
        P&L floored at ``-stop_multiple * entry_credit``.
    """
    floor = -stop_multiple * entry_credit
    if isinstance(pnl, pd.Series):
        return pnl.where(pnl > floor, floor)
    return max(float(pnl), float(floor))


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio circuit breaker
# ─────────────────────────────────────────────────────────────────────────────


def circuit_breaker_breach(equity: pd.Series,
                           threshold: float = DRAWDOWN_CIRCUIT_BREAKER,
                           initial_capital: float | None = None):
    """
    First index at which the equity curve draws down past ``threshold``.

    Parameters
    ----------
    equity : pd.Series
        Equity curve (cumulative capital), ordered in time.
    threshold : float
        Drawdown fraction that trips the breaker. Defaults to ``0.15`` (15%).
    initial_capital : float, optional
        Starting NAV. When given, the running peak is floored at this level, so
        a curve that only contains post-trade points still draws down against
        the original capital rather than its own (already-depressed) maximum.

    Returns
    -------
    index label or None
        The index of the first breaching period, or ``None`` if never breached.
    """
    equity = pd.Series(equity, dtype=float)
    if equity.empty:
        return None
    peak = equity.cummax()
    if initial_capital is not None:
        peak = peak.clip(lower=initial_capital)
    drawdown = (equity - peak) / peak
    breaches = drawdown[drawdown <= -threshold]
    return breaches.index[0] if not breaches.empty else None


def halt_new_entries(trades: pd.DataFrame, account: float,
                     threshold: float = DRAWDOWN_CIRCUIT_BREAKER) -> pd.DataFrame:
    """
    Drop trades entered after the portfolio breaches the drawdown limit.

    Builds the equity curve from the ledger (by exit date), finds the first
    drawdown breach, and removes any trade whose ``entry_date`` is strictly after
    that breach date — the strategy halts new entries and re-evaluates.

    Parameters
    ----------
    trades : pd.DataFrame
        Ledger with ``pnl``, ``exit_date`` and ``entry_date``.
    account : float
        Starting capital (USD).
    threshold : float
        Drawdown circuit-breaker level. Defaults to ``0.15``.

    Returns
    -------
    pd.DataFrame
        The ledger with post-breach entries removed (unchanged if no breach).
    """
    if trades is None or len(trades) == 0 or "exit_date" not in trades:
        return trades
    dated = trades.assign(_exit=pd.to_datetime(trades["exit_date"]))
    daily = dated.groupby("_exit")["pnl"].sum().sort_index()
    equity = account + daily.cumsum()
    breach_date = circuit_breaker_breach(equity, threshold, initial_capital=account)
    if breach_date is None:
        return trades
    entry = pd.to_datetime(trades["entry_date"])
    return trades[entry <= breach_date]


# ─────────────────────────────────────────────────────────────────────────────
# Concentration
# ─────────────────────────────────────────────────────────────────────────────


def cap_concentration(events: pd.DataFrame, rank_col: str | None = None,
                      sector_col: str = "sector", day_col: str = "entry_date",
                      max_per_sector: int = MAX_PER_SECTOR) -> pd.DataFrame:
    """
    Enforce one position per ticker and at most ``max_per_sector`` per sector/day.

    Keeps the highest-ranked events first when ``rank_col`` is supplied (e.g. the
    implied-vs-fair richness), otherwise preserves input order. The ticker rule
    keeps a name's first (best) occurrence; the sector rule caps simultaneous
    same-sector entries on a given day.

    Parameters
    ----------
    events : pd.DataFrame
        Candidate events; must hold ``ticker``. ``sector`` and the day column
        are used when present.
    rank_col : str, optional
        Column to sort by descending before applying caps. ``None`` keeps order.
    sector_col, day_col : str
        Column names for the sector cap. Sector capping is skipped if
        ``sector_col`` is absent.
    max_per_sector : int
        Maximum concurrent positions per sector per day. Defaults to ``3``.

    Returns
    -------
    pd.DataFrame
        The surviving events, original column set preserved.
    """
    if events is None or len(events) == 0:
        return events
    df = events.copy()
    if rank_col is not None and rank_col in df.columns:
        df = df.sort_values(rank_col, ascending=False, kind="stable")

    df = df.drop_duplicates(subset="ticker", keep="first")

    if sector_col in df.columns and day_col in df.columns:
        df = df.groupby([day_col, sector_col], group_keys=False, sort=False).head(max_per_sector)

    # Restore the original input ordering of the surviving rows.
    keep = set(df.index)
    return events.loc[[i for i in events.index if i in keep]]
