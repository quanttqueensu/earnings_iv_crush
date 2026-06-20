"""Tests for earnings_iv_crush.data.options: yfinance chain normalisation + ATM windowing."""

from __future__ import annotations

import pandas as pd

from earnings_iv_crush.data import options


def _yf_leg(strikes, iv):
    """A yfinance-style calls/puts frame (only the columns we read)."""
    return pd.DataFrame(
        {
            "strike": strikes,
            "bid": [s / 100 for s in strikes],
            "ask": [s / 100 + 0.1 for s in strikes],
            "impliedVolatility": [iv] * len(strikes),
            "openInterest": [100] * len(strikes),
        }
    )


def _raw():
    strikes = [70, 80, 90, 100, 110, 120, 130]
    return 100.0, [
        ("2026-06-05", _yf_leg(strikes, 0.5), _yf_leg(strikes, 0.55)),
        ("2026-07-03", _yf_leg(strikes, 0.4), _yf_leg(strikes, 0.45)),
    ]


def test_normalize_schema_and_fields(monkeypatch):
    monkeypatch.setattr(options, "_fetch_raw", lambda *a, **k: _raw())
    df = options.fetch_option_chain("AAPL", "2026-05-29", strike_window=1.0)  # no filtering

    assert list(df.columns) == options.CHAIN_COLUMNS
    assert set(df["right"]) == {"C", "P"}
    assert set(df["expiry"]) == {pd.Timestamp("2026-06-05"), pd.Timestamp("2026-07-03")}
    # impliedVolatility -> iv, openInterest -> open_interest
    call_front = df[(df["right"] == "C") & (df["expiry"] == pd.Timestamp("2026-06-05"))]
    assert (call_front["iv"] == 0.5).all()
    assert (df["open_interest"] == 100).all()


def test_strike_window_keeps_atm_only(monkeypatch):
    monkeypatch.setattr(options, "_fetch_raw", lambda *a, **k: _raw())
    df = options.fetch_option_chain("AAPL", "2026-05-29", strike_window=0.15)  # 85..115

    assert df["strike"].min() == 90.0
    assert df["strike"].max() == 110.0


def test_empty_raw_returns_typed_empty(monkeypatch):
    monkeypatch.setattr(options, "_fetch_raw", lambda *a, **k: (None, []))
    df = options.fetch_option_chain("AAPL", "2026-05-29")
    assert list(df.columns) == options.CHAIN_COLUMNS
    assert df.empty
