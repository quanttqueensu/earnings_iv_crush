"""
data_intake.py
Raw data intake facade - one import surface for the whole pipeline.

Provider choices follow a free-first stack. Each public function delegates to a
provider module so swapping a provider is a
one-line change here. Provider modules:
    vix.py        -> FRED VIX (no key)
    equities.py   -> yfinance OHLCV (no key)
    options.py    -> yfinance option chains (no key, current snapshot)
    sec_edgar.py  -> SEC EDGAR filings (no key, needs SEC_USER_AGENT)
    earnings.py   -> Finnhub earnings calendar (needs FINNHUB_API_KEY)

fetch_option_chain is the keyless yfinance fallback (current snapshot only), used
for live/development work. fetch_historical_option_chain is the Alpaca-backed
provider (needs ALPACA_KEY/SECRET) that serves dated chains back to ~Feb 2024 with
a locally inverted IV, for the backtest; it is a drop-in with the same schema and
is the one to inject as `fetch_chain` into the historical-surface builder.

fetch_dolthub_option_chain is a keyless coarse-surface provider (public DoltHub
database); it is a ~3-sessions/week, monthly-expiry snapshot, so it suits
cross-sectional surface work but cannot bracket an event-timed straddle.

fetch_databento_option_chain is the multi-year historical provider (needs
DATABENTO_API_KEY) backed by OPRA daily bars and definitions to 2013, with the
full weekly/monthly expiry ladder. It is the one to inject as `fetch_chain` for
the pre-2024 out-of-sample backtest; it marks off the daily close with locally
inverted IV (no NBBO pre-2023) and no open interest (see databento_options).

fetch_analyst_dispersion follows the same free-first stack: Finnhub's
eps-estimate endpoint when the plan allows it (403 on the free tier), then a
yfinance analyst-estimate snapshot. The snapshot is current-only, so for past
events the dispersion is a per-ticker constant proxy rather than a
point-in-time value; the ``source`` column records which leg served each row
so coverage and caveats stay documentable. WRDS/IBES replaces both legs when
access lands.
"""

from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from .alpaca_options import fetch_option_chain as fetch_historical_option_chain
from .alpaca_options import fetch_underlying_ohlcv as fetch_historical_equity_ohlcv
from .config import FINNHUB_API_KEY
from .databento_options import fetch_option_chain as fetch_databento_option_chain
from .dolthub_options import fetch_option_chain as fetch_dolthub_option_chain
from .earnings import fetch_earnings_calendar
from .equities import fetch_equity_ohlcv
from .options import fetch_option_chain
from .vix import fetch_index_vol

__all__ = [
    "fetch_earnings_calendar",
    "fetch_equity_ohlcv",
    "fetch_historical_equity_ohlcv",
    "fetch_index_vol",
    "fetch_option_chain",
    "fetch_historical_option_chain",
    "fetch_dolthub_option_chain",
    "fetch_databento_option_chain",
    "fetch_analyst_dispersion",
]


_logger = logging.getLogger(__name__)

_FINNHUB_EPS_URL = "https://finnhub.io/api/v1/stock/eps-estimate"
_FINNHUB_MIN_INTERVAL = 1.1  # seconds; free tier allows 60 calls/min
_last_finnhub_call = 0.0

_DISPERSION_COLUMNS = [
    "ticker",
    "announce_date",
    "eps_mean",
    "eps_std",
    "n_estimates",
    "source",
]


def _throttle_finnhub() -> None:
    """Keep Finnhub calls under the free-tier 60/min limit."""
    global _last_finnhub_call
    wait = _FINNHUB_MIN_INTERVAL - (time.monotonic() - _last_finnhub_call)
    if wait > 0:
        time.sleep(wait)
    _last_finnhub_call = time.monotonic()


def _dispersion_from_finnhub(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Per-quarter dispersion from Finnhub eps-estimate (paid plans; 403 on free)."""
    import requests

    _throttle_finnhub()
    r = requests.get(
        _FINNHUB_EPS_URL,
        params={"symbol": ticker, "freq": "quarterly", "token": FINNHUB_API_KEY},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json().get("data", []) or []
    rows = []
    for d in data:
        period = pd.Timestamp(d.get("period"))
        if not (pd.Timestamp(start) <= period <= pd.Timestamp(end)):
            continue
        n = d.get("numberAnalysts")
        lo, hi, avg = d.get("epsLow"), d.get("epsHigh"), d.get("epsAvg")
        # Range/4 approximates the std of the analyst distribution.
        std = (hi - lo) / 4.0 if lo is not None and hi is not None else np.nan
        rows.append(
            {
                "ticker": ticker,
                "announce_date": period,
                "eps_mean": avg,
                "eps_std": std,
                "n_estimates": n,
                "source": "finnhub",
            }
        )
    return pd.DataFrame(rows, columns=_DISPERSION_COLUMNS)


def _dispersion_from_yfinance(ticker: str) -> pd.DataFrame:
    """Current-quarter analyst estimate snapshot from yfinance.

    Snapshot only: for past events this serves as a per-ticker constant proxy,
    not a point-in-time value. The ``source`` column flags it.
    """
    import yfinance as yf  # lazy, matching equities.py / options.py

    est = yf.Ticker(ticker).earnings_estimate
    if est is None or len(est) == 0 or "0q" not in est.index:
        return pd.DataFrame(columns=_DISPERSION_COLUMNS)
    row = est.loc["0q"]
    lo, hi = row.get("low"), row.get("high")
    std = (hi - lo) / 4.0 if pd.notna(lo) and pd.notna(hi) else np.nan
    return pd.DataFrame(
        [
            {
                "ticker": ticker,
                "announce_date": pd.NaT,
                "eps_mean": row.get("avg"),
                "eps_std": std,
                "n_estimates": row.get("numberOfAnalysts"),
                "source": "yfinance_snapshot",
            }
        ],
        columns=_DISPERSION_COLUMNS,
    )


def fetch_analyst_dispersion(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Analyst EPS forecast dispersion, free-first.

    Tries Finnhub's eps-estimate endpoint (per-quarter history, paid plans
    only; the free tier returns 403), then falls back to a yfinance analyst
    snapshot for the current quarter. Both legs approximate the estimate std
    as (high - low) / 4. Returns an empty, correctly-typed frame when neither
    source yields data, so callers can attach the feature unconditionally.

    Parameters
    ----------
    ticker : str
        Underlying symbol.
    start, end : str
        Inclusive date window in ``YYYY-MM-DD`` form (Finnhub leg only; the
        snapshot leg carries ``announce_date = NaT``).

    Returns
    -------
    pandas.DataFrame
        Columns ``ticker``, ``announce_date``, ``eps_mean``, ``eps_std``,
        ``n_estimates`` and ``source``.
    """
    if FINNHUB_API_KEY:
        try:
            df = _dispersion_from_finnhub(ticker, start, end)
            if not df.empty:
                return df
        except Exception as exc:  # 403 on free tier, rate limits, outages
            _logger.debug("finnhub dispersion unavailable for %s: %s", ticker, exc)
    try:
        return _dispersion_from_yfinance(ticker)
    except Exception as exc:
        _logger.warning("no dispersion source for %s: %s", ticker, exc)
        return pd.DataFrame(columns=_DISPERSION_COLUMNS)
