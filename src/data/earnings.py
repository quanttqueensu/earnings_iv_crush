"""Earnings calendar via Finnhub free tier. Requires FINNHUB_API_KEY.

Cross-check the 'hour' field (bmo/amc/dmh) against SEC EDGAR acceptance times
and Yahoo before trusting the session (the 2-of-3 rule).
"""
from __future__ import annotations

import pandas as pd
import requests

from .config import require

_URL = "https://finnhub.io/api/v1/calendar/earnings"


def fetch_earnings_calendar(start: str, end: str) -> pd.DataFrame:
    """Scheduled earnings between start and end (YYYY-MM-DD).

    Columns (when present): ticker, announce_date, hour, eps_estimate,
    eps_actual, revenue_estimate, revenue_actual, quarter, year.
    Finnhub 'hour' is 'bmo' / 'amc' / 'dmh' (during market hours).
    """
    key = require("FINNHUB_API_KEY")
    r = requests.get(_URL, params={"from": start, "to": end, "token": key},
                     timeout=30)
    r.raise_for_status()
    data = r.json().get("earningsCalendar", []) or []
    df = pd.DataFrame(data)
    if df.empty:
        return df
    rename = {"symbol": "ticker", "date": "announce_date",
              "epsEstimate": "eps_estimate", "epsActual": "eps_actual",
              "revenueEstimate": "revenue_estimate",
              "revenueActual": "revenue_actual"}
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
