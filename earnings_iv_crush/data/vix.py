"""
vix.py
VIX level and term structure from FRED - no API key required.

Uses the public fredgraph CSV endpoint, so it runs with zero setup.
Series: VIXCLS (spot VIX), VXVCLS (3-month VIX, a.k.a. VIX3M).
The 9-day VIX (VIX9D) is not carried on FRED; pull it from CBOE later if
needed. Each series is fetched independently so one bad id never breaks the
rest.
"""

from __future__ import annotations

import io
import logging

import pandas as pd
import requests

_logger = logging.getLogger(__name__)

_FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_SERIES = {"vix": "VIXCLS", "vix3m": "VXVCLS"}


def fetch_index_vol(start: str, end: str) -> pd.DataFrame:
    """Daily VIX spot and 3-month level from FRED.

    A term-structure slope is ``vix3m / vix``. Each series is fetched
    independently so one bad id never breaks the rest.

    Parameters
    ----------
    start, end : str
        Inclusive date window in ``YYYY-MM-DD`` form.

    Returns
    -------
    pandas.DataFrame
        Columns ``date``, ``vix`` and ``vix3m``. Empty (same columns) when no
        series could be fetched.
    """
    series = []
    for col, series_id in _SERIES.items():
        try:
            url = f"{_FRED_CSV}?id={series_id}&cosd={start}&coed={end}"
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            date_col = df.columns[0]  # "observation_date" (or older "DATE")
            df = df.rename(columns={date_col: "date", series_id: col})
            df["date"] = pd.to_datetime(df["date"])
            df[col] = pd.to_numeric(df[col], errors="coerce")  # "." -> NaN
            series.append(df.set_index("date")[col])
        except Exception as exc:  # one series failing should not kill the rest
            _logger.warning("could not fetch %s: %s", series_id, exc)
    if not series:
        return pd.DataFrame(columns=["date", *_SERIES.keys()])
    return pd.concat(series, axis=1).reset_index()
