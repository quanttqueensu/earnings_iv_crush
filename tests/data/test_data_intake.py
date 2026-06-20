"""Tests for the earnings_iv_crush.data.data_intake facade.

The facade is the single import surface for the pipeline: it re-exports the
working adapters and stubs the not-yet-available sources with a clear error.
"""

from __future__ import annotations

from earnings_iv_crush.data import alpaca_options, data_intake, earnings, equities, options, vix


def test_facade_reexports_working_adapters():
    # Re-exports must be the very same callables, not copies.
    assert data_intake.fetch_earnings_calendar is earnings.fetch_earnings_calendar
    assert data_intake.fetch_equity_ohlcv is equities.fetch_equity_ohlcv
    assert data_intake.fetch_index_vol is vix.fetch_index_vol
    assert data_intake.fetch_option_chain is options.fetch_option_chain
    # The dated/historical chain provider (Alpaca, IV inverted locally).
    assert data_intake.fetch_historical_option_chain is alpaca_options.fetch_option_chain


def test_all_lists_the_public_surface():
    expected = {
        "fetch_earnings_calendar",
        "fetch_equity_ohlcv",
        "fetch_index_vol",
        "fetch_option_chain",
        "fetch_historical_option_chain",
        "fetch_historical_equity_ohlcv",
        "fetch_analyst_dispersion",
    }
    assert set(data_intake.__all__) == expected


def test_dispersion_never_raises(monkeypatch):
    # Dispersion is wired free-first; on total source failure it degrades to an
    # empty, correctly-typed frame instead of raising.
    monkeypatch.setattr(data_intake, "FINNHUB_API_KEY", "")

    def boom(ticker):
        raise RuntimeError("offline")

    monkeypatch.setattr(data_intake, "_dispersion_from_yfinance", boom)
    df = data_intake.fetch_analyst_dispersion("AAPL", "2026-01-01", "2026-06-01")
    assert df.empty
    assert list(df.columns) == data_intake._DISPERSION_COLUMNS
