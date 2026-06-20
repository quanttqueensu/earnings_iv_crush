"""Tests for earnings_iv_crush.data.term_panel.build_term_panel (offline, injected providers)."""

from __future__ import annotations

import pandas as pd

from earnings_iv_crush.data import term_panel as tp
from earnings_iv_crush.engine.greeks import bs_price


def _chain(asof, spot, sigma=0.4, front_extra=0.0):
    """Two FIXED expiries x ATM-ish strikes, IV-consistent prices."""
    front, back = pd.Timestamp("2024-06-21"), pd.Timestamp("2024-07-19")
    asof_ts = pd.Timestamp(asof)
    rows = []
    for exp, extra in ((front, front_extra), (back, 0.0)):
        t = max((exp - asof_ts).days, 1) / 365.0
        for k in (spot - 5, spot, spot + 5):
            for right in ("C", "P"):
                s = sigma + extra
                rows.append(
                    {
                        "expiry": exp,
                        "strike": float(k),
                        "right": right,
                        "bid": bs_price(spot, k, t, 0.0, s, right),
                        "ask": bs_price(spot, k, t, 0.0, s, right),
                        "iv": s,
                        "open_interest": 100,
                    }
                )
    return pd.DataFrame(rows)


def _prices(ticker, start, end, level=100.0):
    dates = pd.bdate_range(start, end)
    return pd.DataFrame({"date": dates, "close": [level] * len(dates)})


def test_builds_daily_rows_for_trailing_window():
    events = pd.DataFrame({"ticker": ["AAA"], "announce_date": ["2024-06-14"]})
    panel = tp.build_term_panel(
        events,
        fetch_chain=lambda t, d: _chain(d, 100.0, front_extra=0.2),
        fetch_prices=lambda t, s, e: _prices(t, s, e),
        window_days=20,
        asof_offset_days=1,
    )

    assert list(panel.columns) == tp.PANEL_COLUMNS
    assert len(panel) == 20  # one row per trailing trading day
    assert (panel["ticker"] == "AAA").all()
    assert (panel["iv_term_spread"] > 0).all()  # front IV elevated over back


def test_empty_events_returns_typed_frame():
    panel = tp.build_term_panel(
        pd.DataFrame(columns=["ticker", "announce_date"]),
        fetch_chain=lambda *a: pd.DataFrame(),
        fetch_prices=lambda *a: pd.DataFrame(),
    )
    assert list(panel.columns) == tp.PANEL_COLUMNS
    assert panel.empty


def test_dedupes_overlapping_windows_per_ticker():
    # Two close announce dates for the same name -> overlapping trailing windows
    # must not double-count days.
    events = pd.DataFrame({"ticker": ["AAA", "AAA"], "announce_date": ["2024-06-13", "2024-06-14"]})
    panel = tp.build_term_panel(
        events,
        fetch_chain=lambda t, d: _chain(d, 100.0, front_extra=0.2),
        fetch_prices=lambda t, s, e: _prices(t, s, e),
        window_days=20,
        asof_offset_days=1,
    )
    assert panel["date"].is_unique
