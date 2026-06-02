"""
term_panel.py
Build the per-name daily term-spread panel the term filter gates on.

The spec's term gate compares each event's front-minus-back ATM IV against the
trailing 30-DAY distribution of that name's term spread. That needs a *daily*
surface history per name, not just the entry-day snapshot the event assembler
produces. This module assembles exactly that, covering each event's trailing
window, and is the first concrete consumer of the daily surface collector idea.

It reuses ``historical_surfaces.build_surface_panel`` for the per-day surface
maths but (a) fetches each name's spot series once and serves it from memory
(instead of one network call per day) and (b) uses a tight ATM strike window so
each day pulls only the few contracts the term spread needs. Output columns:
``ticker, date, iv_term_spread`` (plus the rest of the surface panel).

Providers are injected, so it is unit-tested offline; live it defaults to the
Alpaca historical chain and yfinance prices.
"""
from __future__ import annotations

from functools import partial

import pandas as pd
from pandas.tseries.offsets import BDay

from . import alpaca_options, data_intake, historical_surfaces
from ..util.progress import ProgressBar

PANEL_COLUMNS = ["ticker", "date", "iv_term_spread"]


def _trailing_dates(entry: pd.Timestamp, window_days: int) -> list[pd.Timestamp]:
    """The `window_days` trading days strictly before `entry`."""
    return list(pd.bdate_range(end=entry - BDay(1), periods=window_days))


def _spot_lookup_from_series(closes: pd.Series):
    """A spot_lookup(ticker, date) backed by an in-memory close series."""
    def lookup(_ticker, date):
        ts = pd.Timestamp(date)
        s = closes[closes.index <= ts]
        return float(s.iloc[-1]) if len(s) else float("nan")
    return lookup


def build_term_panel(events: pd.DataFrame, *, fetch_chain=None, fetch_prices=None,
                     window_days: int = 30, asof_offset_days: int = 1,
                     strike_window: float = 0.06, horizon_days: int = 70,
                     progress: bool = False) -> pd.DataFrame:
    """Daily term-spread panel covering every event's trailing window.

    For each ticker the union of its events' trailing windows is collected once;
    the name's spot series is fetched a single time and reused across those days.

    Parameters
    ----------
    events : DataFrame with `ticker` and `announce_date`.
    fetch_chain : `fetch_chain(ticker, 'YYYY-MM-DD') -> chain`. Defaults to the
        Alpaca historical provider with a tight ATM strike window.
    fetch_prices : `fetch_prices(ticker, start, end) -> OHLCV`. Defaults to
        `data_intake.fetch_equity_ohlcv`.
    """
    if events is None or len(events) == 0:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    fetch_chain = fetch_chain or partial(
        alpaca_options.fetch_option_chain, strike_window=strike_window,
        horizon_days=horizon_days)
    fetch_prices = fetch_prices or data_intake.fetch_equity_ohlcv

    # Union of trailing-window dates per ticker.
    want: dict[str, set] = {}
    for _, ev in events.iterrows():
        entry = pd.Timestamp(pd.to_datetime(ev["announce_date"])) - BDay(asof_offset_days)
        want.setdefault(ev["ticker"], set()).update(_trailing_dates(entry, window_days))

    total_days = sum(len(d) for d in want.values())
    bar = ProgressBar(total_days, label="term panel", enabled=progress)
    frames = []
    for ticker, date_set in want.items():
        dates = sorted(date_set)
        if not dates:
            continue
        prices = fetch_prices(
            ticker, dates[0].strftime("%Y-%m-%d"),
            (dates[-1] + pd.Timedelta(days=3)).strftime("%Y-%m-%d"))
        if prices is None or prices.empty or "close" not in prices:
            bar.update(len(dates))
            continue
        closes = (prices.assign(date=pd.to_datetime(prices["date"]))
                  .set_index("date")["close"].astype(float).sort_index())
        spot_lookup = _spot_lookup_from_series(closes)
        # One day at a time so the progress bar (and its ETA) is granular. A day
        # that still fails after the provider's own retries is skipped, not fatal
        # - the trailing percentile tolerates a few gaps.
        for d in dates:
            try:
                day = historical_surfaces.build_surface_panel(
                    [ticker], [d.strftime("%Y-%m-%d")],
                    fetch_chain=fetch_chain, spot_lookup=spot_lookup)
            except Exception:
                day = pd.DataFrame()
            if not day.empty:
                frames.append(day[["ticker", "date", "iv_term_spread"]])
            bar.update()
    bar.close()

    if not frames:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    return pd.concat(frames, ignore_index=True)
