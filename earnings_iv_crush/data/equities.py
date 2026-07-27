"""
equities.py
Equity OHLCV. Default provider: yfinance (no key required).

Tiingo (keyed) can be added later as a more reliable source; yfinance is fine
for spot reference and realised-vol features in development. ``fetch_equity_ohlcv_crsp``
serves the same schema from the CRSP daily stock file on the WRDS mirror (as-traded, no key).
"""

from __future__ import annotations

import datetime as dt

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


def _permno_for_ticker(ticker: str, asof: dt.date) -> int | None:
    """Resolve a ticker to its CRSP permno active on ``asof`` (handles -/. drift)."""
    from . import wrds_r2

    variants = {ticker, ticker.replace("-", ""), ticker.replace("-", "."), ticker.replace(".", "")}
    nm = wrds_r2.read_table(
        "crsp_a_stock",
        "dsenames",
        columns=["permno", "ticker", "namedt", "nameendt"],
        filters=[("ticker", "in", sorted(variants))],
    )
    if nm.empty:
        return None
    nm["namedt"] = pd.to_datetime(nm["namedt"])
    nm["nameendt"] = pd.to_datetime(nm["nameendt"])
    a = pd.Timestamp(asof)
    live = nm[(nm["namedt"] <= a) & (a <= nm["nameendt"])]
    row = (live if not live.empty else nm.sort_values("nameendt")).iloc[-1]
    return int(row["permno"])


def fetch_equity_ohlcv_crsp(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Daily OHLCV from the CRSP daily stock file (``dsf``) on the WRDS mirror.

    As-traded (unadjusted) prices, matching yfinance's ``auto_adjust=False`` basis, so this is a
    drop-in for :func:`fetch_equity_ohlcv`. CRSP carries a negative ``prc`` when the close is a
    quote midpoint (no trade that day); the sign is dropped. Returns empty (same columns) when the
    ticker cannot be resolved to a permno.
    """
    from . import wrds_r2

    permno = _permno_for_ticker(ticker, pd.Timestamp(start).date())
    if permno is None:
        return pd.DataFrame(columns=_COLS)
    df = wrds_r2.read_table(
        "crsp_a_stock",
        "dsf",
        columns=["date", "openprc", "askhi", "bidlo", "prc", "vol"],
        filters=[
            ("permno", "=", permno),
            ("date", ">=", pd.Timestamp(start).date()),
            ("date", "<=", pd.Timestamp(end).date()),
        ],
    )
    if df.empty:
        return pd.DataFrame(columns=_COLS)
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"]),
            "open": df["openprc"].abs(),
            "high": df["askhi"].abs(),
            "low": df["bidlo"].abs(),
            "close": df["prc"].abs(),
            "volume": df["vol"],
        }
    )
    return out.sort_values("date").reset_index(drop=True)
