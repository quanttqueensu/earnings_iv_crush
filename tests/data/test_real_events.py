"""Tests for src.data.real_events: execution-event assembly from injected data.

Both providers are injected with synthetic builders, so no network is touched.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data import real_events as re
from src.engine.greeks import bs_price


def _chain(asof, spot, sigma=0.4, front_extra_iv=0.0):
    """Two FIXED-date expiries x strikes around spot, IV-consistent prices.

    Real option expiries are fixed calendar dates, so the same front expiry must
    appear in both the entry-day and exit-day chains; the fixture pins them
    rather than offsetting from ``asof`` so the exit IV re-read resolves.
    """
    asof_ts = pd.Timestamp(asof)
    front = pd.Timestamp("2024-06-14")
    back = pd.Timestamp("2024-07-12")
    rows = []
    for exp, extra in ((front, front_extra_iv), (back, 0.0)):
        t = (exp - asof_ts).days / 365.0
        for k in np.arange(round(spot) - 10, round(spot) + 11, 5.0):
            for right in ("C", "P"):
                s = sigma + extra
                rows.append({
                    "expiry": exp, "strike": float(k), "right": right,
                    "bid": bs_price(spot, k, t, 0.0, s, right),
                    "ask": bs_price(spot, k, t, 0.0, s, right),
                    "iv": s, "open_interest": 100,
                })
    return pd.DataFrame(rows)


def _prices(ticker, start, end, level=100.0):
    dates = pd.bdate_range(start, end)
    return pd.DataFrame({"date": dates, "close": [level] * len(dates)})


def test_assembles_execution_columns_offline():
    cal = pd.DataFrame({"ticker": ["AAA"], "announce_date": ["2024-06-10"]})

    def fetch_chain(t, d):
        # Front-week IV elevated pre-event, normal after (a crush).
        pre = pd.Timestamp(d) < pd.Timestamp("2024-06-10")
        return _chain(d, 100.0, sigma=0.4, front_extra_iv=0.5 if pre else 0.0)

    df = re.build_execution_events(
        cal, fetch_chain=fetch_chain,
        fetch_prices=lambda t, s, e: _prices(t, s, e, 100.0))

    assert list(df.columns) == re.EVENT_COLUMNS
    assert len(df) == 1
    row = df.iloc[0]
    # Entry front IV (0.9) richer than exit IV (0.4) -> the crush is captured.
    assert row["iv_entry"] > row["iv_exit"]
    assert row["strike"] == 100.0
    assert row["t_entry"] > row["t_exit"]            # less time left at exit
    assert row["realised_move"] == 0.0                # flat synthetic prices
    assert row["iv_term_spread"] > 0                  # front richer than back


def test_thin_or_missing_chain_is_skipped():
    cal = pd.DataFrame({"ticker": ["AAA", "BBB"], "announce_date": ["2024-06-10", "2024-06-11"]})

    def fetch_chain(t, d):
        return _chain(d, 100.0) if t == "AAA" else pd.DataFrame()

    df = re.build_execution_events(
        cal, fetch_chain=fetch_chain,
        fetch_prices=lambda t, s, e: _prices(t, s, e))
    assert set(df["ticker"]) == {"AAA"}


def test_empty_calendar_returns_typed_frame():
    df = re.build_execution_events(pd.DataFrame(columns=["ticker", "announce_date"]),
                                   fetch_chain=lambda *a: pd.DataFrame(),
                                   fetch_prices=lambda *a: pd.DataFrame())
    assert list(df.columns) == re.EVENT_COLUMNS
    assert df.empty
