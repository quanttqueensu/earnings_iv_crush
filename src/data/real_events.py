"""Assemble execution-ready earnings events from real market data.

``data_pipeline.build_event_dataset`` produces the *filter* features for each
event but not the *execution* columns the ledger needs (exit IV, exit spot,
realised move). This module closes that gap: for each earnings announcement it
pulls the option chain and price both at entry (a business day before) and at
exit (a few days after), then emits a single row carrying everything the
strategy, the backtester and the Agent 0 control consume - the same schema
``engine.simulate.simulate_events`` fabricates, minus the synthetic ``is_rich``
flag (unknown for real data).

Providers are injected (defaulting to the ``data_intake`` facade with the Alpaca
historical chain), so this is unit-tested offline against synthetic chains and
runs live by passing nothing. IV is whatever the chain carries; with the Alpaca
adapter that is the locally inverted vol (see ``alpaca_options``).
"""
from __future__ import annotations

import pandas as pd
from pandas.tseries.offsets import BDay

from . import data_intake, features
from ..util.progress import progress_iter

# Columns the downstream strategy/backtester/agent0 path consumes. Mirrors the
# execution + filter columns of engine.simulate.simulate_events.
EVENT_COLUMNS = [
    "ticker", "announce_date", "entry_date", "exit_date",
    "spot_entry", "spot_exit", "strike", "t_entry", "t_exit",
    "iv_entry", "iv_exit",
    "front_atm_iv", "back_atm_iv", "iv_term_spread", "implied_move",
    "trailing_rv", "skew_25d", "vol_premium", "variance_risk_premium",
    "bkm_skew", "bkm_kurt", "realised_move",
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


def build_execution_events(
    calendar: pd.DataFrame,
    *,
    fetch_chain=None,
    fetch_prices=None,
    holding_days: int = 2,
    asof_offset_days: int = 1,
    lookback_days: int = 60,
    rv_window: int = 20,
    r: float = 0.0,
    progress: bool = False,
) -> pd.DataFrame:
    """One execution-ready row per earnings event, from real entry/exit data.

    Parameters
    ----------
    calendar : DataFrame with ``ticker`` and ``announce_date``.
    fetch_chain : ``fetch_chain(ticker, 'YYYY-MM-DD') -> chain`` (defaults to the
        Alpaca historical provider via ``data_intake.fetch_historical_option_chain``).
    fetch_prices : ``fetch_prices(ticker, start, end) -> OHLCV`` (defaults to
        ``data_intake.fetch_equity_ohlcv``).
    holding_days : business days held after the announcement (the exit).
    asof_offset_days : business days before the announcement for entry.

    Events whose entry chain, front expiry or spots cannot be resolved are
    skipped, so one thin name never sinks the build.
    """
    fetch_chain = fetch_chain or data_intake.fetch_historical_option_chain
    fetch_prices = fetch_prices or data_intake.fetch_equity_ohlcv

    if calendar is None or len(calendar) == 0:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    rows = []
    records = [ev for _, ev in calendar.iterrows()]
    for ev in progress_iter(records, total=len(records), label="events",
                            enabled=progress):
        ticker = ev["ticker"]
        announce = pd.Timestamp(pd.to_datetime(ev["announce_date"]))
        entry = announce - BDay(asof_offset_days)
        exit_ = announce + BDay(holding_days)

        entry_chain = fetch_chain(ticker, entry.strftime("%Y-%m-%d"))
        if entry_chain is None or len(entry_chain) == 0:
            continue

        entry_prices = fetch_prices(
            ticker, (entry - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d"),
            entry.strftime("%Y-%m-%d"))
        spot_entry = _last_close_on_or_before(entry_prices, entry)
        if not (spot_entry and spot_entry == spot_entry):
            continue

        front, _ = features.nearest_expiries(entry_chain, announce)
        if front is None:
            continue
        strike = features.nearest_strike(entry_chain, front, spot_entry)
        t_entry = (front - entry).days / 365.0
        iv_entry = features.atm_iv(entry_chain, front, strike)

        feats = features.event_features(
            entry_chain, spot_entry, announce, entry, entry_prices, r=r,
            rv_window=rv_window)

        # Exit leg: same front expiry, IV re-read post-event (the crush).
        exit_prices = fetch_prices(
            ticker, entry.strftime("%Y-%m-%d"),
            (exit_ + pd.Timedelta(days=3)).strftime("%Y-%m-%d"))
        spot_exit = _last_close_on_or_before(exit_prices, exit_)
        if not (spot_exit and spot_exit == spot_exit):
            continue
        t_exit = (front - exit_).days / 365.0
        exit_chain = fetch_chain(ticker, exit_.strftime("%Y-%m-%d"))
        iv_exit = features.atm_iv(exit_chain, front, strike) if (
            exit_chain is not None and len(exit_chain)) else float("nan")
        # If the front expiry has lapsed by exit (t_exit<=0) the straddle settles
        # at intrinsic and iv_exit is irrelevant; otherwise fall back to entry IV
        # when the post-event ATM IV is missing so the row stays usable.
        if iv_exit != iv_exit:
            iv_exit = iv_entry

        realised_move = abs(spot_exit - spot_entry) / spot_entry

        rows.append({
            "ticker": ticker, "announce_date": announce,
            "entry_date": entry.strftime("%Y-%m-%d"),
            "exit_date": exit_.strftime("%Y-%m-%d"),
            "spot_entry": spot_entry, "spot_exit": spot_exit, "strike": strike,
            "t_entry": t_entry, "t_exit": t_exit,
            "iv_entry": iv_entry, "iv_exit": iv_exit,
            "front_atm_iv": feats["front_atm_iv"], "back_atm_iv": feats["back_atm_iv"],
            "iv_term_spread": feats["iv_term_spread"], "implied_move": feats["implied_move"],
            "trailing_rv": feats["trailing_rv"], "skew_25d": feats["skew_25d"],
            "vol_premium": feats["vol_premium"],
            "variance_risk_premium": feats["variance_risk_premium"],
            "bkm_skew": feats["bkm_skew"], "bkm_kurt": feats["bkm_kurt"],
            "realised_move": realised_move,
        })

    return pd.DataFrame(rows, columns=EVENT_COLUMNS)
