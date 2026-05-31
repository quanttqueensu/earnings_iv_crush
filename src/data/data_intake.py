"""Raw data intake facade - one import surface for the whole pipeline.

Provider choices follow a free-first stack. Each public function delegates to a
provider module so swapping a provider is a
one-line change here. Provider modules:
    vix.py        -> FRED VIX (no key)
    equities.py   -> yfinance OHLCV (no key)
    options.py    -> yfinance option chains (no key, current snapshot)
    sec_edgar.py  -> SEC EDGAR filings (no key, needs SEC_USER_AGENT)
    earnings.py   -> Finnhub earnings calendar (needs FINNHUB_API_KEY)

fetch_option_chain currently uses the keyless yfinance fallback (current
snapshot only); IBKR / Alpaca / OptionMetrics replace it for live/historical
work as those accounts land.

Still pending (implemented when the access lands):
    fetch_analyst_dispersion  -> IBES via WRDS, fallback Finnhub/FMP/Zacks
"""
from __future__ import annotations

import pandas as pd

from .earnings import fetch_earnings_calendar
from .equities import fetch_equity_ohlcv
from .options import fetch_option_chain
from .vix import fetch_index_vol

__all__ = [
    "fetch_earnings_calendar",
    "fetch_equity_ohlcv",
    "fetch_index_vol",
    "fetch_option_chain",
    "fetch_analyst_dispersion",
]


def fetch_analyst_dispersion(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Analyst EPS forecast dispersion (IBES via WRDS; fallback Finnhub/FMP).

    Columns: ticker, announce_date, eps_mean, eps_std, n_estimates.
    """
    raise NotImplementedError("Pending WRDS access.")
