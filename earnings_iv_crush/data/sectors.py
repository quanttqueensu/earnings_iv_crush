"""
sectors.py
Frozen GICS sector map for the backtest universe.

Sector analysis needs a sector label per name, and no provider feed is wired, so
this is a static, point-in-time map. GICS sectors are stable (reclassifications
are rare and announced), so a frozen 2024-01 map carries no material look-ahead;
it is kept here rather than fetched so the cut is reproducible offline.

Coverage is the ``MEGACAP_50`` cohort - the liquidity-clean sample on which the
term+skew edge is validated. Names outside the map resolve to ``"Unknown"`` so a
broader frame degrades gracefully rather than raising.
"""

from __future__ import annotations

import pandas as pd

# GICS sector per megacap name, frozen at 2024-01 (see data/universe.py).
MEGACAP_SECTOR: dict[str, str] = {
    "AAPL": "Information Technology",
    "MSFT": "Information Technology",
    "NVDA": "Information Technology",
    "AVGO": "Information Technology",
    "CRM": "Information Technology",
    "ADBE": "Information Technology",
    "AMD": "Information Technology",
    "ACN": "Information Technology",
    "CSCO": "Information Technology",
    "ORCL": "Information Technology",
    "INTC": "Information Technology",
    "INTU": "Information Technology",
    "QCOM": "Information Technology",
    "IBM": "Information Technology",
    "TXN": "Information Technology",
    "NOW": "Information Technology",
    "GOOGL": "Communication Services",
    "META": "Communication Services",
    "NFLX": "Communication Services",
    "CMCSA": "Communication Services",
    "DIS": "Communication Services",
    "VZ": "Communication Services",
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary",
    "MCD": "Consumer Discretionary",
    "PG": "Consumer Staples",
    "COST": "Consumer Staples",
    "PEP": "Consumer Staples",
    "KO": "Consumer Staples",
    "WMT": "Consumer Staples",
    "BRK-B": "Financials",
    "JPM": "Financials",
    "V": "Financials",
    "MA": "Financials",
    "WFC": "Financials",
    "LLY": "Health Care",
    "UNH": "Health Care",
    "JNJ": "Health Care",
    "MRK": "Health Care",
    "ABBV": "Health Care",
    "TMO": "Health Care",
    "ABT": "Health Care",
    "AMGN": "Health Care",
    "PFE": "Health Care",
    "XOM": "Energy",
    "CVX": "Energy",
    "CAT": "Industrials",
    "GE": "Industrials",
    "LIN": "Materials",
}


def sector_of(ticker: str) -> str:
    """Return the GICS sector for ``ticker``, or ``"Unknown"`` if unmapped."""
    return MEGACAP_SECTOR.get(ticker, "Unknown")


def sector_labels(tickers: list[str] | pd.Index) -> pd.Series:
    """Ticker-indexed GICS sector labels for a list of names."""
    return pd.Series({t: sector_of(t) for t in tickers}, name="sector")
