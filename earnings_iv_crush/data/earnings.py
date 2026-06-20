"""
earnings.py
Earnings calendar via Finnhub free tier. Requires FINNHUB_API_KEY.

Cross-check the 'hour' field (bmo/amc/dmh) against SEC EDGAR acceptance times
and Yahoo before trusting the session (the 2-of-3 rule).
"""

from __future__ import annotations

import pandas as pd
import requests

from .config import require

_URL = "https://finnhub.io/api/v1/calendar/earnings"


# ── Finnhub: scheduled calendar ──────────────────────────────────────────────


def fetch_earnings_calendar(start: str, end: str) -> pd.DataFrame:
    """Scheduled earnings between two dates, via Finnhub.

    Finnhub ``hour`` is ``"bmo"`` / ``"amc"`` / ``"dmh"`` (during market hours).

    Parameters
    ----------
    start, end : str
        Inclusive date window in ``YYYY-MM-DD`` form.

    Returns
    -------
    pandas.DataFrame
        Columns (when present) ``ticker``, ``announce_date``, ``hour``,
        ``eps_estimate``, ``eps_actual``, ``revenue_estimate``,
        ``revenue_actual``, ``quarter`` and ``year``. Empty when Finnhub
        returns nothing.
    """
    key = require("FINNHUB_API_KEY")
    r = requests.get(_URL, params={"from": start, "to": end, "token": key}, timeout=30)
    r.raise_for_status()
    data = r.json().get("earningsCalendar", []) or []
    df = pd.DataFrame(data)
    if df.empty:
        return df
    rename = {
        "symbol": "ticker",
        "date": "announce_date",
        "epsEstimate": "eps_estimate",
        "epsActual": "eps_actual",
        "revenueEstimate": "revenue_estimate",
        "revenueActual": "revenue_actual",
    }
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})


# ── Yahoo: historical announcement dates ─────────────────────────────────────


def fetch_earnings_dates(tickers, start: str, end: str, limit: int = 40) -> pd.DataFrame:
    """Historical earnings announcement dates per ticker, via Yahoo (yfinance).

    Finnhub's free calendar only serves current/future dates, so the historical
    backtest takes its dates from Yahoo (the planned fallback leg). Dates are
    normalised to midnight and filtered to ``[start, end]``. Names that yfinance
    cannot resolve are skipped.

    Parameters
    ----------
    tickers : iterable of str
        Underlying symbols to query.
    start, end : str
        Inclusive date window in ``YYYY-MM-DD`` form.
    limit : int, optional
        Maximum announcement dates pulled per ticker. Defaults to ``40``.

    Returns
    -------
    pandas.DataFrame
        Canonical ``ticker``, ``announce_date``, ``session`` schema. ``session``
        is ``"amc"`` / ``"bmo"`` derived from the announcement timestamp's hour
        (after 16:00 -> amc, before 12:00 -> bmo), or NaN when the time is
        absent; downstream the assembler falls back to its default session.
    """
    import yfinance as yf  # lazy, matching equities.py / options.py

    s, e = pd.Timestamp(start), pd.Timestamp(end)
    rows = []
    for ticker in tickers:
        try:
            ed = yf.Ticker(ticker).get_earnings_dates(limit=limit)
        except Exception:
            continue
        if ed is None or len(ed) == 0:
            continue
        idx = pd.to_datetime(ed.index)
        idx = idx.tz_localize(None) if idx.tz is not None else idx
        for d in idx:
            ts = pd.Timestamp(d)
            day = ts.normalize()
            if s <= day <= e:
                rows.append(
                    {"ticker": ticker, "announce_date": day, "session": _session_from_hour(ts)}
                )
    return pd.DataFrame(rows, columns=["ticker", "announce_date", "session"])


def _session_from_hour(ts: pd.Timestamp) -> float | str:
    """Classify an announcement timestamp into a reporting session.

    After the close (>= 16:00) is ``"amc"``; before noon is ``"bmo"``;
    midnight (no time supplied) or mid-afternoon is left as NaN so the caller's
    default session applies.
    """
    hour = ts.hour
    if hour == 0 and ts.minute == 0:
        return float("nan")
    if hour >= 16:
        return "amc"
    if hour < 12:
        return "bmo"
    return float("nan")
