"""
equities.py
Equity OHLCV. Default provider: yfinance (no key required).

Tiingo (keyed) can be added later as a more reliable source; yfinance is fine
for spot reference and realised-vol features in development.
"""

from __future__ import annotations

import pandas as pd

_COLS = ["date", "open", "high", "low", "close", "volume"]


def fetch_equity_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Daily OHLCV via yfinance between two dates.

    Parameters
    ----------
    ticker : str
        Underlying symbol to download.
    start, end : str
        Inclusive date window in ``YYYY-MM-DD`` form.

    Returns
    -------
    pandas.DataFrame
        One row per trading day with columns ``date``, ``open``, ``high``,
        ``low``, ``close`` and ``volume``. Empty (same columns) when yfinance
        returns nothing.
    """
    import yfinance as yf  # imported lazily so module import never fails

    df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if df is None or df.empty:
        return pd.DataFrame(columns=_COLS)
    df = df.reset_index()
    # Newer yfinance returns MultiIndex columns even for a single ticker.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    return df[[c for c in _COLS if c in df.columns]]
