"""
lse_intraday.py
Minute-resolution option marks from the London Strategic Edge vault.

The daily adapter (``lse_options``) marks a contract on its *daily* bar close,
which is the last trade of the session and may be hours stale on a thin strike.
This module pulls the same vault at ``timeframe='1m'`` instead, so a leg can be
marked at a chosen minute with a print behind it, and the staleness of that mark
is measured rather than assumed.

Why this matters: the event pipeline inverts an ATM implied vol from a single
daily close and the P&L layer then *re-prices* the straddle from that vol under
Black-Scholes. A stale close therefore does not merely add noise to a price, it
propagates into an implied vol, and from there into every P&L in the book. The
minute bars let the straddle be marked on the two legs' **traded prices**, which
removes the inversion, the model and the smile assumption from the P&L path.

Coverage (probed 2026-07-12): 1-minute bars run back to at least 2015-07,
covering the full 09:30-16:00 ET session (391 distinct minutes). Bars carry
``open/high/low/close`` and ``volume`` per contract; there is **no bid/ask**, so
these remain trade prices and the spread still lives in ``engine.costs``.

Note the vault's REST endpoint (``option_candles``) is *not* usable here: it
purges expired contracts, so it serves nothing for a historical event. The bulk
export path (``history(dataset='options', timeframe='1m')``) is the archive.

Timestamps arrive in UTC. All marking is done in ``America/New_York`` so the
mark time is a wall-clock session time and daylight saving is handled: 15:55 ET
is 19:55 UTC in summer and 20:55 UTC in winter.

Requires ``LSE_API_KEY`` in ``.env``.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .config import require

_logger = logging.getLogger(__name__)

_CACHE_ROOT = Path("data/processed/lse_1m")
_EXCHANGE_TZ = "America/New_York"

# Vault export jobs are aggressively rate-limited; the daily adapter uses 30s.
_MIN_CALL_INTERVAL = 15.0
_MAX_RETRIES = 6
_BASE_BACKOFF = 20.0

# Ingest filters: keep the pulled window small on disk. The traded strike sits
# at the money at entry, so a +/-25% band comfortably contains it even after a
# large gap, and 60 days of expiry covers the front and back legs.
_STRIKE_BAND = 0.25
_MAX_DTE = 60

_client_cache: Any = None
_last_call: float = 0.0


# ── vault client ────────────────────────────────────────────────────────────


def _client() -> Any:
    global _client_cache
    if _client_cache is None:
        from lse import LSE

        _client_cache = LSE(api_key=require("LSE_API_KEY"))
    return _client_cache


def _throttle() -> None:
    global _last_call
    elapsed = time.monotonic() - _last_call
    if elapsed < _MIN_CALL_INTERVAL:
        time.sleep(_MIN_CALL_INTERVAL - elapsed)
    _last_call = time.monotonic()


def _export(ticker: str, start: str, end: str) -> pd.DataFrame:
    """One vault export of 1m option bars, with backoff on the 429 rate limit."""
    from lse import LSEError

    for attempt in range(_MAX_RETRIES):
        _throttle()
        try:
            df = _client().history(
                ticker,
                dataset="options",
                timeframe="1m",
                start=start,
                end=end,
                dataframe=True,
            )
            return df if df is not None else pd.DataFrame()
        except LSEError as exc:
            if "429" in str(exc) and attempt < _MAX_RETRIES - 1:
                wait = _BASE_BACKOFF * (2**attempt) + random.uniform(0, 1)
                _logger.warning("LSE 429, backing off %.0fs", wait)
                time.sleep(wait)
            else:
                raise
    return pd.DataFrame()


# ── event-window pull ───────────────────────────────────────────────────────


def _cache_path(ticker: str, start: str, end: str) -> Path:
    return _CACHE_ROOT / ticker / f"{start}_{end}.parquet"


def pull_window(
    ticker: str,
    start: str,
    end: str,
    *,
    spot_hint: float | None = None,
) -> pd.DataFrame:
    """1-minute option bars for *ticker* over ``[start, end)``, cached to disk.

    The raw export is filtered to a strike band around ``spot_hint`` and to
    expiries inside ``_MAX_DTE``, which is what keeps the cache small: an
    unfiltered 3-day megacap window is ~120k rows.

    Parameters
    ----------
    ticker : str
        Underlying ticker (yfinance form).
    start, end : str
        ``YYYY-MM-DD``; ``end`` is exclusive of its own session in practice, so
        pad it by a day to include the exit session.
    spot_hint : float or None
        Underlying price used to centre the strike band. No band when None.

    Returns
    -------
    pandas.DataFrame
        Columns ``ts`` (tz-aware, exchange time), ``expiry``, ``opt_type``,
        ``strike``, ``osi``, ``open``, ``high``, ``low``, ``close``, ``volume``.
        Empty when the vault has nothing.
    """
    path = _cache_path(ticker, start, end)
    if path.exists():
        return pd.read_parquet(path)

    raw = _export(ticker, start, end)
    if raw.empty:
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_parquet(path, index=False)
        return pd.DataFrame()

    df = raw.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(_EXCHANGE_TZ)
    df["expiry"] = pd.to_datetime(df["expiry"])
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df = df.dropna(subset=["strike", "close"])
    df = df[df["close"] > 0]

    if spot_hint is not None and spot_hint == spot_hint:
        lo, hi = spot_hint * (1 - _STRIKE_BAND), spot_hint * (1 + _STRIKE_BAND)
        df = df[df["strike"].between(lo, hi)]

    dte = (df["expiry"] - df["ts"].dt.tz_localize(None).dt.normalize()).dt.days
    df = df[(dte >= 0) & (dte <= _MAX_DTE)]

    df = df.reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    _logger.info("cached %d 1m rows -> %s", len(df), path)
    return df


# ── leg marking ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LegMark:
    """One leg's traded mark at a target minute.

    Attributes
    ----------
    price : float
        Bar close of the last print at or before the target minute; NaN when the
        leg never printed inside the lookback window.
    minutes_stale : float
        Minutes between the marking print and the target minute. ``0`` means the
        leg printed in the target minute itself. NaN when unmarked.
    volume : float
        Contracts traded in the marking bar.
    session_volume : float
        Contracts traded in the leg across the whole session, a liquidity read.
    """

    price: float
    minutes_stale: float
    volume: float
    session_volume: float


def mark_leg(
    bars: pd.DataFrame,
    *,
    session: pd.Timestamp,
    expiry: pd.Timestamp,
    strike: float,
    right: str,
    mark_time: str = "15:55",
    lookback_minutes: int = 30,
) -> LegMark:
    """Traded mark for one contract at ``mark_time`` on ``session``.

    Takes the last print **at or before** the target minute, searching back up to
    ``lookback_minutes``, and reports how stale that print is. Returning the
    staleness rather than silently accepting an old price is the point: a mark
    behind a print 27 minutes old is not the same object as one behind a print in
    the marking minute, and the caller must be able to tell them apart.

    A leg that never printed inside the window returns ``price=NaN``. The caller
    must decide what that means; this function will not invent a price.

    Parameters
    ----------
    bars : pd.DataFrame
        Output of :func:`pull_window`.
    session : pd.Timestamp
        Trading date to mark on.
    expiry : pd.Timestamp
        Contract expiry.
    strike : float
        Contract strike, on the vault's raw (unadjusted) basis.
    right : str
        ``"C"`` or ``"P"``.
    mark_time : str, optional
        Target wall-clock exchange time, ``"HH:MM"``. Defaults to ``"15:55"``.
    lookback_minutes : int, optional
        How far back to search for a print. Defaults to ``30``.

    Returns
    -------
    LegMark
    """
    nan = LegMark(float("nan"), float("nan"), float("nan"), 0.0)
    if bars.empty:
        return nan

    want_type = "C" if str(right).upper().startswith("C") else "P"
    leg = bars[
        (bars["expiry"] == pd.Timestamp(expiry))
        & (bars["strike"] == float(strike))
        & (bars["opt_type"].astype(str).str.upper().str[0] == want_type)
    ]
    if leg.empty:
        return nan

    day = pd.Timestamp(session).normalize()
    local = leg["ts"].dt.tz_localize(None)
    leg = leg[local.dt.normalize() == day]
    if leg.empty:
        return nan

    local = leg["ts"].dt.tz_localize(None)
    hh, mm = (int(x) for x in str(mark_time).split(":"))
    target = day + pd.Timedelta(hours=hh, minutes=mm)
    floor = target - pd.Timedelta(minutes=int(lookback_minutes))

    session_volume = float(leg["volume"].sum())
    window = leg[(local <= target) & (local >= floor)]
    if window.empty:
        return LegMark(float("nan"), float("nan"), float("nan"), session_volume)

    wlocal = window["ts"].dt.tz_localize(None)
    last = window.loc[wlocal.idxmax()]
    stale = (target - wlocal.max()).total_seconds() / 60.0

    return LegMark(
        price=float(last["close"]),
        minutes_stale=float(stale),
        volume=float(last["volume"]),
        session_volume=session_volume,
    )


def mark_straddle(
    bars: pd.DataFrame,
    *,
    session: pd.Timestamp,
    expiry: pd.Timestamp,
    strike: float,
    mark_time: str = "15:55",
    lookback_minutes: int = 30,
) -> dict[str, float]:
    """Traded straddle mark: call + put on the same strike and expiry.

    Both legs must print inside the window; a straddle with one unmarked leg is
    returned as NaN rather than half-marked, because a one-legged mark would
    silently understate the buy-back cost of the short.

    Returns
    -------
    dict
        ``price`` (call+put per share), ``call``, ``put``, ``stale`` (the worse
        of the two legs' staleness, in minutes), ``volume`` (the thinner leg's
        marking-bar volume) and ``session_volume`` (the thinner leg's session
        total).
    """
    c = mark_leg(
        bars,
        session=session,
        expiry=expiry,
        strike=strike,
        right="C",
        mark_time=mark_time,
        lookback_minutes=lookback_minutes,
    )
    p = mark_leg(
        bars,
        session=session,
        expiry=expiry,
        strike=strike,
        right="P",
        mark_time=mark_time,
        lookback_minutes=lookback_minutes,
    )
    price = c.price + p.price  # NaN-propagating by design
    return {
        "price": price,
        "call": c.price,
        "put": p.price,
        "stale": max(c.minutes_stale, p.minutes_stale),
        "volume": min(c.volume, p.volume),
        "session_volume": min(c.session_volume, p.session_volume),
    }
