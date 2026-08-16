"""
real_events.py
Assemble execution-ready earnings events from real market data.

``data_pipeline.build_event_dataset`` produces the *filter* features for each
event but not the *execution* columns the ledger needs (exit IV, exit spot,
realised move). This module closes that gap: for each earnings announcement it
pulls the option chain and price at entry (the last close before the report)
and at exit (the first close after the implied-vol crush prints), then emits a
single row carrying everything the strategy, the backtester and the Agent 0
control consume - the same schema ``engine.simulate.simulate_events``
fabricates, minus the synthetic ``is_rich`` flag (unknown for real data).

Entry and exit are *session-aware*: an after-close (``amc``) report crushes at
the next open, so the trade is entered at the announce-date close and exited the
following close; a before-open (``bmo``) report crushes at that day's open, so
the trade is entered the prior close and exited that day's close. The executed
expiry is the nearest one that still has live time value at exit, so the short
is marked on the vega crush rather than settling at intrinsic.

Providers are injected (defaulting to the ``data_intake`` facade with the Alpaca
historical chain), so this is unit-tested offline against synthetic chains and
runs live by passing nothing. IV is whatever the chain carries; with the Alpaca
adapter that is the locally inverted vol (see ``alpaca_options``).
"""

from __future__ import annotations

import pandas as pd
from pandas.tseries.offsets import BDay

from ..config import STRATEGY
from ..util.progress import progress_iter
from . import data_intake, features

# Columns the downstream strategy/backtester/agent0 path consumes. Mirrors the
# execution + filter columns of engine.simulate.simulate_events.
EVENT_COLUMNS = [
    "ticker",
    "announce_date",
    "entry_date",
    "exit_date",
    "spot_entry",
    "spot_exit",
    "strike",
    "t_entry",
    "t_exit",
    "iv_entry",
    "iv_exit",
    "front_atm_iv",
    "back_atm_iv",
    "iv_term_spread",
    "iv_term_spread_nearest",
    "implied_move",
    "trailing_rv",
    "skew_25d",
    "vol_premium",
    "variance_risk_premium",
    "bkm_skew",
    "bkm_kurt",
    "realised_move",
]


def _last_close_on_or_before(prices: pd.DataFrame, asof: pd.Timestamp) -> float:
    """Most recent close at or before ``asof`` from an OHLCV frame."""
    if prices is None or prices.empty or "close" not in prices:
        return float("nan")
    p = prices.copy()
    p["date"] = pd.to_datetime(p["date"]) if "date" in p else pd.to_datetime(p.index)
    p = p[p["date"] <= asof].sort_values("date")
    if p.empty:
        return float("nan")
    close = pd.to_numeric(p["close"], errors="coerce").dropna()
    return float(close.iloc[-1]) if not close.empty else float("nan")


def _resolve_session(raw, default_session: str) -> tuple[str, bool]:
    """Normalise a calendar session value to ``amc``/``bmo``/``dmh``.

    ``None``, NaN, empty strings and the string ``"nan"`` all fall back to
    ``default_session``. NaN must be handled explicitly: it is truthy, so the
    old ``raw or default`` idiom let it through and ``entry_exit_dates`` then
    silently routed the event down the non-amc (bmo) branch - one day early.

    Returns
    -------
    tuple of (str, bool)
        The resolved session and whether the default was applied.
    """
    if raw is None or (isinstance(raw, float) and raw != raw):
        return default_session, True
    text = str(raw).strip().lower()
    # "ambiguous" is the EDGAR cross-check's unknown marker; anything not
    # explicitly amc/bmo/dmh must take the default, not the bmo branch.
    if text in ("", "nan", "none", "nat", "ambiguous"):
        return default_session, True
    return text, False


def entry_exit_dates(announce, session: str = "amc"):
    """(entry, exit) business-day closes bracketing a single overnight crush.

    The crush is realised at the first market open after the report, so the
    trade is a one-overnight hold: enter at the last close *before* the report,
    exit at the first close *after* the crush.

    * ``amc`` (after close, the modal session) - the report lands after the
      announce-date close, the crush prints at the next open, so
      ``entry = announce close`` and ``exit = next business close``.
    * ``bmo`` (before open) - the report lands before the announce-date open,
      the crush prints at that open, so ``entry = prior business close`` and
      ``exit = announce close``.
    * ``dmh`` / anything else - treated as ``bmo`` (the conservative read: the
      move is already underway intraday).

    Parameters
    ----------
    announce : datetime-like
        The earnings announcement date.
    session : str, optional
        ``"amc"``, ``"bmo"`` or ``"dmh"``. Defaults to ``"amc"``.

    Returns
    -------
    tuple of pd.Timestamp
        ``(entry, exit)`` business-day timestamps with ``exit > entry``.
    """
    announce = pd.Timestamp(pd.to_datetime(announce))
    if str(session).lower() == "amc":
        return announce, announce + BDay(1)
    # bmo / dmh: crush at the announce-day open.
    return announce - BDay(1), announce


def build_execution_events(
    calendar: pd.DataFrame,
    *,
    fetch_chain=None,
    fetch_prices=None,
    min_exit_dte_days: int = STRATEGY.min_exit_dte_days,
    default_session: str = STRATEGY.default_session,
    lookback_days: int = 60,
    rv_window: int = 20,
    r: float = 0.0,
    max_overnight_move: float = 0.40,
    progress: bool = False,
) -> pd.DataFrame:
    """One execution-ready row per earnings event, from real entry/exit data.

    Entry and exit are session-aware (see :func:`entry_exit_dates`): a one-
    overnight hold spanning the implied-vol crush. The executed expiry is the
    nearest one that still has at least ``min_exit_dte_days`` trading days of
    life at exit, so ``t_exit > 0`` and the short is marked on the crush in
    ``iv_exit`` rather than settling at intrinsic.

    Events whose entry chain, executed expiry or spots cannot be resolved are
    skipped, so one thin name never sinks the build.

    Parameters
    ----------
    calendar : pd.DataFrame
        Earnings calendar with ``ticker`` and ``announce_date``; an optional
        ``session`` (or ``hour``) column of ``amc``/``bmo``/``dmh`` flags sets
        the per-event timing, falling back to ``default_session``.
    fetch_chain : callable, optional
        ``fetch_chain(ticker, 'YYYY-MM-DD') -> chain``. Defaults to the Alpaca
        historical provider via ``data_intake.fetch_historical_option_chain``.
    fetch_prices : callable, optional
        ``fetch_prices(ticker, start, end) -> OHLCV``. Defaults to
        ``data_intake.fetch_equity_ohlcv``.
    min_exit_dte_days : int, optional
        Minimum trading days of option life remaining at exit; the executed
        expiry is rolled out until it qualifies. Defaults to the configured
        ``STRATEGY.min_exit_dte_days``.
    default_session : str, optional
        Session assumed when the calendar carries no flag. Defaults to the
        configured ``STRATEGY.default_session`` (``"amc"``).
    lookback_days : int, optional
        Calendar days of price history pulled before entry for realised vol.
        Defaults to ``60``.
    rv_window : int, optional
        Trailing-return window for realised vol, in observations. Defaults to
        ``20``.
    r : float, optional
        Risk-free rate passed to the feature maths. Defaults to ``0.0``.
    max_overnight_move : float, optional
        Events whose absolute entry->exit underlying move exceeds this fraction
        are dropped as corporate actions rather than earnings gaps: the smallest
        common bonus/split halves the raw price (~50%), far above any real
        overnight earnings move on an F&O-eligible name. Defaults to ``0.40``.
        Only bites on raw-price feeds (e.g. the NSE bhavcopy); split-adjusted
        feeds never trip it.
    progress : bool, optional
        Whether to render a progress bar over events. Defaults to ``False``.

    Returns
    -------
    pd.DataFrame
        One row per resolvable event with ``EVENT_COLUMNS``; empty (correctly
        typed) when the calendar is empty.
    """
    fetch_chain = fetch_chain or data_intake.fetch_historical_option_chain
    fetch_prices = fetch_prices or data_intake.fetch_equity_ohlcv

    if calendar is None or len(calendar) == 0:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    rows = []
    drops = {
        "session_defaulted": 0,  # not a drop; counted so the funnel shows it
        "no_entry_chain": 0,
        "no_entry_spot": 0,
        "no_executable_expiry": 0,
        "no_exit_spot": 0,
        "iv_exit_fallback": 0,  # not a drop; exit marked at entry IV (no crush)
        "corp_action_move": 0,
    }
    records = [ev for _, ev in calendar.iterrows()]
    for ev in progress_iter(records, total=len(records), label="events", enabled=progress):
        ticker = ev["ticker"]
        announce = pd.Timestamp(pd.to_datetime(ev["announce_date"]))
        session, defaulted = _resolve_session(ev.get("session", ev.get("hour")), default_session)
        if defaulted:
            drops["session_defaulted"] += 1
        entry, exit_ = entry_exit_dates(announce, session)

        entry_chain = fetch_chain(ticker, entry.strftime("%Y-%m-%d"))
        if entry_chain is None or len(entry_chain) == 0:
            drops["no_entry_chain"] += 1
            continue

        entry_prices = fetch_prices(
            ticker,
            (entry - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d"),
            entry.strftime("%Y-%m-%d"),
        )
        spot_entry = _last_close_on_or_before(entry_prices, entry)
        if not (spot_entry and spot_entry == spot_entry):
            drops["no_entry_spot"] += 1
            continue

        # Executed expiry: the nearest one that brackets the event AND still has
        # >= min_exit_dte_days of trading life left at exit, so the exit is
        # marked on live time value (the crush) rather than at intrinsic. The
        # term-structure features below are measured on this SAME expiry, so the
        # filter signal and the traded instrument stay self-consistent.
        front, back = features.select_execution_expiry(
            entry_chain, announce, exit_, min_dte_days=min_exit_dte_days
        )
        if front is None:
            drops["no_executable_expiry"] += 1
            continue
        strike = features.nearest_strike(entry_chain, front, spot_entry)
        t_entry = (front - entry).days / 365.0
        iv_entry = features.atm_iv(entry_chain, front, strike)

        # Panel-definition spread at entry: nearest expiries as-of the entry day,
        # the same rule ``historical_surfaces.build_surface_panel`` applies to
        # every trailing day. The executed-expiry spread below is what the trade
        # actually carries, but gating it against a nearest-expiry distribution
        # compares different definitions (measured ~0.22 vol pts apart), so the
        # panel gate must use THIS column.
        n_front, n_back = features.nearest_expiries(entry_chain, entry)
        spread_nearest = float("nan")
        if n_front is not None and n_back is not None:
            k_f = features.nearest_strike(entry_chain, n_front, spot_entry)
            k_b = features.nearest_strike(entry_chain, n_back, spot_entry)
            iv_f = features.atm_iv(entry_chain, n_front, k_f)
            iv_b = features.atm_iv(entry_chain, n_back, k_b)
            if iv_f == iv_f and iv_b == iv_b:
                spread_nearest = iv_f - iv_b

        feats = features.event_features(
            entry_chain,
            spot_entry,
            announce,
            entry,
            entry_prices,
            r=r,
            rv_window=rv_window,
            front=front,
            back=back,
        )

        # Exit leg: same executed expiry, IV re-read post-event (the crush).
        exit_prices = fetch_prices(
            ticker, entry.strftime("%Y-%m-%d"), (exit_ + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
        )
        spot_exit = _last_close_on_or_before(exit_prices, exit_)
        if not (spot_exit and spot_exit == spot_exit):
            drops["no_exit_spot"] += 1
            continue
        t_exit = (front - exit_).days / 365.0
        exit_chain = fetch_chain(ticker, exit_.strftime("%Y-%m-%d"))
        # Mark the held straddle at the post-event *at-the-money* IV (the strike
        # nearest the exit spot), not at the original entry strike. After a large
        # earnings move the entry strike is deep ITM/OTM, and inverting IV from a
        # near-expiry off-ATM daily close explodes (300%+), which would massively
        # overstate the buy-back cost. The exit ATM IV is the stable post-crush vol
        # level; repricing the held strike at it via BS gives ~intrinsic + fair time
        # value, the real mark. Fall back to entry IV only if the exit chain lacks it.
        if exit_chain is not None and len(exit_chain):
            exit_atm_strike = features.nearest_strike(exit_chain, front, spot_exit)
            iv_exit = features.atm_iv(exit_chain, front, exit_atm_strike)
        else:
            iv_exit = float("nan")
        if iv_exit != iv_exit:
            drops["iv_exit_fallback"] += 1
            iv_exit = iv_entry

        realised_move = abs(spot_exit - spot_entry) / spot_entry
        if realised_move > max_overnight_move:
            drops["corp_action_move"] += 1  # bonus/split between entry and exit
            continue

        rows.append(
            {
                "ticker": ticker,
                "announce_date": announce,
                "entry_date": entry.strftime("%Y-%m-%d"),
                "exit_date": exit_.strftime("%Y-%m-%d"),
                "spot_entry": spot_entry,
                "spot_exit": spot_exit,
                "strike": strike,
                "t_entry": t_entry,
                "t_exit": t_exit,
                "iv_entry": iv_entry,
                "iv_exit": iv_exit,
                "front_atm_iv": feats["front_atm_iv"],
                "back_atm_iv": feats["back_atm_iv"],
                "iv_term_spread": feats["iv_term_spread"],
                "iv_term_spread_nearest": spread_nearest,
                "implied_move": feats["implied_move"],
                "trailing_rv": feats["trailing_rv"],
                "skew_25d": feats["skew_25d"],
                "vol_premium": feats["vol_premium"],
                "variance_risk_premium": feats["variance_risk_premium"],
                "bkm_skew": feats["bkm_skew"],
                "bkm_kurt": feats["bkm_kurt"],
                "realised_move": realised_move,
            }
        )

    # Exclusion funnel: every event in the calendar must be accounted for, so a
    # silently shrinking sample is visible in the run log (calendar N -> usable N).
    n_dropped = sum(
        v for k, v in drops.items() if k not in ("session_defaulted", "iv_exit_fallback")
    )
    print(
        f"real_events funnel: calendar {len(records)} -> usable {len(rows)} "
        f"(dropped {n_dropped})"
    )
    for reason, count in drops.items():
        if count:
            print(f"  {reason:22s} {count}")
    if drops["session_defaulted"]:
        print(
            f"  note: {drops['session_defaulted']} event(s) had no BMO/AMC stamp and used "
            f"the '{default_session}' default; their entry/exit window is an assumption."
        )
    if drops["iv_exit_fallback"]:
        print(
            f"  note: {drops['iv_exit_fallback']} event(s) could not invert an exit IV and "
            f"were marked at ENTRY IV (no crush booked); their P&L is conservative/wrong."
        )
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)
