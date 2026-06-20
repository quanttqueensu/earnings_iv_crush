"""
calendar_build.py
Historical earnings calendar for the backtest window.

Finnhub's free calendar only serves future dates, so history comes from Yahoo
(yfinance ``get_earnings_dates``), which carries the announcement timestamp in
Eastern wall-clock plus the EPS estimate and actual. The session (BMO/AMC) is
inferred from that timestamp and cross-checked against SEC EDGAR 8-K (Item
2.02) acceptance times where available; disagreements are logged, not silently
overwritten, because a flipped session moves the entry/exit windows and
corrupts P&L without any visible error.

Output schema (one row per event):
    ticker, announce_date, session, session_source, eps_estimate, eps_actual,
    cohort
"""

from __future__ import annotations

import logging

import pandas as pd

from .sec_edgar import earnings_8ks, infer_session
from .universe import cohort_labels

_logger = logging.getLogger(__name__)

CALENDAR_COLUMNS = [
    "ticker",
    "announce_date",
    "session",
    "session_source",
    "eps_estimate",
    "eps_actual",
    "cohort",
]


def yahoo_events(ticker: str, start: str, end: str, limit: int = 24) -> pd.DataFrame:
    """Per-ticker events from yfinance with a timestamp-inferred session.

    Returns the canonical calendar columns minus ``cohort``; empty on any
    provider failure so one bad name never sinks the build.
    """
    import yfinance as yf  # lazy, matching the other providers

    cols = [c for c in CALENDAR_COLUMNS if c != "cohort"]
    try:
        ed = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    except Exception as exc:
        _logger.warning("yahoo earnings dates failed for %s: %s", ticker, exc)
        return pd.DataFrame(columns=cols)
    if ed is None or len(ed) == 0:
        return pd.DataFrame(columns=cols)

    s, e = pd.Timestamp(start), pd.Timestamp(end)
    rows = []
    for ts, row in ed.iterrows():
        ts = pd.Timestamp(ts)
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)  # keep Eastern wall-clock digits
        day = ts.normalize()
        if not (s <= day <= e):
            continue
        rows.append(
            {
                "ticker": ticker,
                "announce_date": day,
                "session": infer_session(ts),
                "session_source": "yahoo",
                "eps_estimate": row.get("EPS Estimate"),
                "eps_actual": row.get("Reported EPS"),
            }
        )
    return pd.DataFrame(rows, columns=cols)


def crosscheck_sessions(events: pd.DataFrame, fetch_8ks=earnings_8ks) -> pd.DataFrame:
    """Cross-check Yahoo sessions against EDGAR 8-K acceptance times.

    For each ticker, EDGAR earnings 8-Ks within one calendar day of an event
    vote on the session. The evidence is asymmetric: an acceptance before
    09:30 ET proves the news was out pre-market, but a late acceptance proves
    nothing because companies routinely file the 8-K hours after the press
    release (PepsiCo announces BMO and files mid-afternoon). So EDGAR ``bmo``
    overrides anything, EDGAR ``amc`` only resolves a Yahoo ``ambiguous``,
    and a yahoo=bmo / edgar=amc conflict keeps Yahoo with source
    ``conflict`` and a logged warning. Agreement upgrades the source to
    ``yahoo+edgar``.
    """
    if events.empty:
        return events
    out = events.copy()
    for ticker, grp in out.groupby("ticker"):
        try:
            filings = fetch_8ks(ticker)
        except Exception as exc:
            _logger.warning("EDGAR 8-K lookup failed for %s: %s", ticker, exc)
            continue
        if filings is None or filings.empty:
            continue
        acceptance = filings["acceptance"]
        if acceptance.dt.tz is not None:
            acceptance = acceptance.dt.tz_localize(None)  # EDGAR's Z is wall-clock
        filing_days = acceptance.dt.normalize()
        for idx, ev in grp.iterrows():
            near = filings[(filing_days - ev["announce_date"]).abs() <= pd.Timedelta(days=1)]
            if near.empty:
                continue
            edgar_session = near.iloc[0]["session"]
            if edgar_session == "ambiguous":
                continue
            if edgar_session == ev["session"]:
                out.at[idx, "session_source"] = "yahoo+edgar"
            elif edgar_session == "bmo" or ev["session"] == "ambiguous":
                out.at[idx, "session"] = edgar_session
                out.at[idx, "session_source"] = "edgar_override"
            else:  # yahoo=bmo vs edgar=amc: late filing proves nothing, keep Yahoo
                _logger.warning(
                    "session conflict for %s %s: yahoo=%s edgar=%s (yahoo kept)",
                    ticker,
                    ev["announce_date"].date(),
                    ev["session"],
                    edgar_session,
                )
                out.at[idx, "session_source"] = "conflict"
    return out


def build_calendar(
    tickers: list[str],
    start: str,
    end: str,
    *,
    fetch_events=yahoo_events,
    crosscheck: bool = True,
    fetch_8ks=earnings_8ks,
) -> pd.DataFrame:
    """Assemble the consolidated event calendar for a universe.

    Parameters
    ----------
    tickers : list[str]
        Universe membership (see ``universe.get_universe``).
    start, end : str
        Inclusive window in ``YYYY-MM-DD`` form.
    fetch_events : callable, optional
        ``fetch_events(ticker, start, end) -> frame``; injectable for testing.
    crosscheck : bool, optional
        Run the EDGAR session cross-check. Defaults to ``True``.
    fetch_8ks : callable, optional
        EDGAR 8-K fetcher; injectable for testing.

    Returns
    -------
    pandas.DataFrame
        ``CALENDAR_COLUMNS``, sorted by date then ticker. Ambiguous sessions
        are kept (downstream treats them as AMC, the conservative default for
        entry timing) and remain identifiable via the ``session`` column.
    """
    frames = [fetch_events(t, start, end) for t in tickers]
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=CALENDAR_COLUMNS)
    cal = pd.concat(frames, ignore_index=True)
    cal["announce_date"] = pd.to_datetime(cal["announce_date"])  # cached CSV round-trips as str
    if crosscheck:
        cal = crosscheck_sessions(cal, fetch_8ks=fetch_8ks)
    labels = cohort_labels()
    cal["cohort"] = cal["ticker"].map(labels)
    return cal.sort_values(["announce_date", "ticker"]).reset_index(drop=True)[CALENDAR_COLUMNS]
