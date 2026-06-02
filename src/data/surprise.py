"""
surprise.py
Prior earnings surprise, a fair-move regression feature.

surprise = (eps_actual - eps_estimate) / |eps_estimate|. The feature is the
PRIOR quarter's surprise magnitude - the most recent one already known before
the event - so per ticker we sort by date and lag by one announcement. Computed
straight from the Finnhub earnings calendar, which already carries eps_estimate
and eps_actual, so no extra data source is needed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_REQUIRED = {"ticker", "announce_date", "eps_estimate", "eps_actual"}


def earnings_surprise(eps_actual, eps_estimate) -> pd.Series:
    """Signed earnings surprise = (actual - estimate) / |estimate|."""
    est = pd.to_numeric(pd.Series(eps_estimate), errors="coerce")
    act = pd.to_numeric(pd.Series(eps_actual), errors="coerce")
    denom = est.abs().replace(0, np.nan)
    return (act - est) / denom


def prior_surprise(calendar: pd.DataFrame) -> pd.Series:
    """Per-event prior surprise magnitude, aligned to ``calendar.index``.

    Returns all-NaN (still aligned) when the calendar lacks the estimate/actual
    columns, so callers can attach it unconditionally.

    Parameters
    ----------
    calendar : pandas.DataFrame
        Earnings calendar; needs ``ticker``, ``announce_date``,
        ``eps_estimate`` and ``eps_actual`` for a non-trivial result.

    Returns
    -------
    pandas.Series
        The prior quarter's absolute surprise per event, indexed like
        ``calendar``.
    """
    if not _REQUIRED.issubset(calendar.columns):
        return pd.Series(np.nan, index=calendar.index, dtype=float)

    df = calendar.copy()
    df["_surprise"] = earnings_surprise(df["eps_actual"], df["eps_estimate"]).abs()
    df["_date"] = pd.to_datetime(df["announce_date"], errors="coerce")
    df = df.sort_values(["ticker", "_date"])
    lagged = df.groupby("ticker")["_surprise"].shift(1)
    return lagged.reindex(calendar.index)
