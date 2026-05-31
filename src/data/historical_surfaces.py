"""historical_surfaces.py
Assemble a historical ATM implied-volatility surface panel.

Builds a daily per-ticker surface panel (front/back ATM IV, term spread, skew,
implied move) from an *injected* option-chain provider, then joins it to the
earnings calendar to form the per-event dataset the fair-move model fits on. The
provider is a callable argument (same dependency-injection pattern as
``data_pipeline.build_event_dataset``), so the whole module is unit-tested
against synthetic chains with no network access; a live collector is dropped in
unchanged once historical option access (WRDS/Alpaca) lands.

This module implements:

* ``build_surface_panel``         — daily (ticker, date) ATM surface rows.
* ``join_earnings_to_surfaces``   — pre-event surface + realised move per event.
"""

from __future__ import annotations

import pandas as pd
from pandas.tseries.offsets import BDay

from . import features

PANEL_COLUMNS = [
    "ticker", "date", "spot",
    "front_atm_iv", "back_atm_iv", "iv_term_spread", "skew_25d", "implied_move",
]


def build_surface_panel(tickers, dates, fetch_chain, spot_lookup,
                        r: float = 0.0) -> pd.DataFrame:
    """
    Build the daily ATM-surface panel across tickers and dates.

    Parameters
    ----------
    tickers : sequence of str
        Underlyings to collect.
    dates : sequence of date-like
        As-of dates (one surface snapshot each).
    fetch_chain : callable
        ``fetch_chain(ticker, date) -> option chain DataFrame`` (injected). The
        chain schema matches ``data.features`` (expiry, strike, right, bid, ask,
        iv, open_interest).
    spot_lookup : callable
        ``spot_lookup(ticker, date) -> float`` underlying price as-of the date.
    r : float
        Risk-free rate for the skew calculation. Defaults to ``0.0``.

    Returns
    -------
    pd.DataFrame
        One row per (ticker, date) with ``PANEL_COLUMNS``; snapshots whose chain
        is missing or has no expiry after the date are skipped.
    """
    rows = []
    for ticker in tickers:
        for date in dates:
            asof = pd.Timestamp(pd.to_datetime(date))
            chain = fetch_chain(ticker, asof.strftime("%Y-%m-%d"))
            if chain is None or len(chain) == 0:
                continue
            spot = float(spot_lookup(ticker, asof.strftime("%Y-%m-%d")))
            front, back = features.nearest_expiries(chain, asof)
            if front is None:
                continue
            k_front = features.nearest_strike(chain, front, spot)
            k_back = features.nearest_strike(chain, back, spot) if back is not None else features.NAN
            front_iv = features.atm_iv(chain, front, k_front)
            back_iv = features.atm_iv(chain, back, k_back) if back is not None else features.NAN
            spread = (front_iv - back_iv
                      if (front_iv == front_iv and back_iv == back_iv) else features.NAN)
            t_front = (front - asof).days / 365.0
            rows.append({
                "ticker": ticker,
                "date": asof,
                "spot": spot,
                "front_atm_iv": front_iv,
                "back_atm_iv": back_iv,
                "iv_term_spread": spread,
                "skew_25d": features.skew_25d(chain, front, spot, t_front, r),
                "implied_move": features.implied_move(chain, spot, front, k_front),
            })
    return pd.DataFrame(rows, columns=PANEL_COLUMNS)


def join_earnings_to_surfaces(calendar: pd.DataFrame, panel: pd.DataFrame,
                              realised_move_fn, asof_offset_days: int = 1) -> pd.DataFrame:
    """
    Join each earnings event to its pre-event surface and realised move.

    For every calendar row the most recent panel snapshot on or before
    ``asof_offset_days`` business days before the announcement is taken as the
    entry surface, and the realised post-event move is attached as the fair-move
    target.

    Parameters
    ----------
    calendar : pd.DataFrame
        Earnings calendar with ``ticker`` and ``announce_date``.
    panel : pd.DataFrame
        Surface panel from ``build_surface_panel``.
    realised_move_fn : callable
        ``realised_move_fn(ticker, announce_date) -> float`` absolute post-event
        move as a fraction of spot (the regression target).
    asof_offset_days : int
        Business days before the announcement at which the position is entered.
        Defaults to ``1``.

    Returns
    -------
    pd.DataFrame
        One row per event that has a usable pre-event surface, carrying the
        surface features plus ``announce_date`` and ``realised_move``.
    """
    if calendar is None or len(calendar) == 0 or panel is None or len(panel) == 0:
        return pd.DataFrame(columns=[*PANEL_COLUMNS, "announce_date", "realised_move"])

    panel = panel.assign(date=pd.to_datetime(panel["date"]))
    rows = []
    for _, ev in calendar.iterrows():
        ticker = ev["ticker"]
        announce = pd.Timestamp(pd.to_datetime(ev["announce_date"]))
        asof = announce - BDay(asof_offset_days)
        snaps = panel[(panel["ticker"] == ticker) & (panel["date"] <= asof)]
        if snaps.empty:
            continue
        snap = snaps.sort_values("date").iloc[-1].to_dict()
        snap["announce_date"] = announce
        snap["realised_move"] = float(realised_move_fn(ticker, announce))
        rows.append(snap)

    columns = [*PANEL_COLUMNS, "announce_date", "realised_move"]
    return pd.DataFrame(rows, columns=columns)
