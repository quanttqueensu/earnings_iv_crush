"""
earnings.py
Earnings calendars: Finnhub free tier (live) and the WRDS R2 mirror (historical).

The Finnhub path requires FINNHUB_API_KEY; cross-check the 'hour' field (bmo/amc/dmh)
against SEC EDGAR acceptance times and Yahoo before trusting the session (the 2-of-3 rule).
The WRDS path takes the announcement date from Compustat ``fundq.rdq`` and the session from
I/B/E/S announcement times, and needs no live key - see ``fetch_earnings_calendar_wrds``.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import requests
from pandas.tseries.offsets import BDay

from . import wrds_r2
from .config import require

_URL = "https://finnhub.io/api/v1/calendar/earnings"

# WRDS session mapping: an IBES announcement time after the close is amc, before the open is
# bmo, during the session is dmh; a missing/00:00 stamp is IBES's unknown marker.
_WRDS_MATCH_DAYS = 3  # max |IBES anndats - Compustat rdq| accepted when attaching a time
_MKT_OPEN, _MKT_CLOSE = dt.time(9, 30), dt.time(16, 0)


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


# ── session-aware trade timing ───────────────────────────────────────────────


def trade_dates_for_session(
    announce_date: pd.Timestamp, session: str | float | None
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """``(entry_date, exit_date)`` bracketing an announcement, or ``None`` if unknown.

    The strategy is short a straddle across one announcement and nothing else, so
    it enters at the last close before the print and exits at the first close
    after it. Which calendar days those are depends on the reporting session:

    ==========  ====================  ====================
    session     entry                 exit
    ==========  ====================  ====================
    ``amc``     announcement day      next business day
    ``bmo``     prior business day    announcement day
    ``dmh``     prior business day    announcement day
    ==========  ====================  ====================

    ``dmh`` (during market hours) shares the ``bmo`` bracket because the only
    close that is reliably ahead of a mid-session print is the previous one.

    An unrecognised or missing session returns ``None`` rather than assuming a
    default. Guessing is unsafe in both directions: treat a ``bmo`` name as
    ``amc`` and the position is opened after the print, short a straddle whose
    crush has already happened; treat an ``amc`` name as ``bmo`` and the exit
    lands before the print, missing the crush entirely. A name whose session is
    unknown cannot be traded on a one-session horizon, so the caller must skip it.

    Parameters
    ----------
    announce_date : pandas.Timestamp
        The announcement date, normalised to midnight.
    session : str or float or None
        ``"amc"``, ``"bmo"`` or ``"dmh"``, case-insensitive. NaN, ``None`` and
        empty strings are all treated as unknown.

    Returns
    -------
    tuple of pandas.Timestamp, or None
        ``(entry_date, exit_date)``, both normalised; ``None`` when the session
        is unknown.

    Examples
    --------
    >>> trade_dates_for_session(pd.Timestamp("2026-07-22"), "amc")
    (Timestamp('2026-07-22 00:00:00'), Timestamp('2026-07-23 00:00:00'))
    >>> trade_dates_for_session(pd.Timestamp("2026-07-22"), "bmo")
    (Timestamp('2026-07-21 00:00:00'), Timestamp('2026-07-22 00:00:00'))
    >>> trade_dates_for_session(pd.Timestamp("2026-07-22"), None) is None
    True
    """
    if session is None or (isinstance(session, float) and session != session):
        return None
    key = str(session).strip().lower()
    day = pd.Timestamp(announce_date).normalize()
    if key == "amc":
        return day, (day + BDay(1)).normalize()
    if key in ("bmo", "dmh"):
        return (day - BDay(1)).normalize(), day
    return None


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
        # Convert to Eastern before stripping tz; stripping a UTC-based stamp
        # keeps UTC digits and misclassifies the BMO/AMC session.
        idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
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


# ── WRDS mirror: historical calendar (Compustat rdq + IBES session) ──────────


def _session_from_ibes_time(t: dt.time | None) -> tuple[str, str]:
    """Map an IBES announcement time to ``(session, source)``.

    After the close -> amc; before the open -> bmo; during the session -> dmh. A missing or
    00:00:00 time (IBES's unknown marker) falls back to amc, flagged ``default_unknown``.
    """
    if not isinstance(t, dt.time) or t == dt.time(0, 0):  # None/NaN/unknown marker
        return "amc", "default_unknown"
    if t >= _MKT_CLOSE:
        return "amc", "ibes_time"
    if t <= _MKT_OPEN:
        return "bmo", "ibes_time"
    return "dmh", "ibes_time"


def _map_names_to_tic(names: list[str], tics: set[str]) -> dict[str, str]:
    """Map event tickers to Compustat ``tic`` values (handles ``-``/``.`` convention drift)."""
    norm = lambda s: s.replace("-", "").replace(".", "")  # noqa: E731
    by_norm: dict[str, str] = {}
    for t in tics:
        by_norm.setdefault(norm(t), t)
    out: dict[str, str] = {}
    for n in names:
        for cand in (n, n.replace("-", "."), n.replace("-", ""), norm(n)):
            if cand in tics:
                out[n] = cand
                break
        else:
            if norm(n) in by_norm:
                out[n] = by_norm[norm(n)]
    return out


def build_wrds_calendar(start: str, end: str, names: list[str] | None = None) -> pd.DataFrame:
    """Earnings calendar from the WRDS mirror, with linking columns retained.

    Announcement date is Compustat ``fundq.rdq``; the bmo/amc session is attached from the
    nearest I/B/E/S ``act_epsus`` announcement time (within ``_WRDS_MATCH_DAYS`` of ``rdq``),
    linked by 8-digit CUSIP. When ``names`` is given, the frame is restricted to those tickers
    (mapped onto Compustat ``tic``); otherwise every firm in the window is returned.

    Returns
    -------
    pandas.DataFrame
        ``ticker``, ``announce_date``, ``session``, ``session_source``, ``gvkey``, ``cusip8``.
    """
    sd, ed = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    fq = wrds_r2.read_table(
        "comp_na_daily_all",
        "fundq",
        columns=["gvkey", "tic", "cusip", "rdq", "datadate", "fqtr"],
        filters=[("rdq", ">=", sd), ("rdq", "<=", ed)],
    )
    fq = fq[fq["rdq"].notna() & fq["cusip"].notna()].copy()
    fq["cusip8"] = fq["cusip"].str.slice(0, 8)

    if names is not None:
        tic_map = _map_names_to_tic(sorted(names), set(fq["tic"].dropna().unique()))
        inv = {v: k for k, v in tic_map.items()}
        fq = fq[fq["tic"].isin(tic_map.values())].copy()
        fq["ticker"] = fq["tic"].map(inv)
    else:
        fq["ticker"] = fq["tic"]
    fq = fq[fq["ticker"].notna()].drop_duplicates(["ticker", "rdq"]).reset_index(drop=True)
    fq["announce_date"] = pd.to_datetime(fq["rdq"])

    # IBES announcement times, one per (cusip, anndats), preferring a real (non-midnight) stamp
    act = wrds_r2.read_table(
        "tr_ibes",
        "act_epsus",
        columns=["cusip", "measure", "anndats", "anntims"],
        filters=[("measure", "=", "EPS"), ("cusip", "in", sorted(fq["cusip8"].unique()))],
    )
    act = act[act["anndats"].notna()].copy()
    act["anndats"] = pd.to_datetime(act["anndats"])
    act["is_real"] = act["anntims"].map(lambda t: bool(t) and t != dt.time(0, 0))
    act = (
        act.sort_values(["cusip", "anndats", "is_real"])
        .drop_duplicates(["cusip", "anndats"], keep="last")
        .rename(columns={"cusip": "cusip8"})[["cusip8", "anndats", "anntims"]]
    )

    # nearest IBES time within tolerance, vectorised by cusip
    left = fq.sort_values("announce_date")
    right = act.sort_values("anndats")
    merged = pd.merge_asof(
        left,
        right,
        left_on="announce_date",
        right_on="anndats",
        by="cusip8",
        direction="nearest",
        tolerance=pd.Timedelta(days=_WRDS_MATCH_DAYS),
    )
    sess = merged["anntims"].map(_session_from_ibes_time)
    merged["session"] = [s for s, _ in sess]
    merged["session_source"] = [src for _, src in sess]

    return (
        merged[["ticker", "announce_date", "session", "session_source", "gvkey", "cusip8"]]
        .sort_values(["ticker", "announce_date"])
        .reset_index(drop=True)
    )


def fetch_earnings_calendar_wrds(
    start: str, end: str, names: list[str] | None = None
) -> pd.DataFrame:
    """WRDS earnings calendar in the canonical ``ticker, announce_date, session`` schema.

    Thin projection of :func:`build_wrds_calendar` for drop-in use where the Finnhub
    :func:`fetch_earnings_calendar` output is expected.
    """
    return build_wrds_calendar(start, end, names)[["ticker", "announce_date", "session"]]
