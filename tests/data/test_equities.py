"""Tests for earnings_iv_crush.data.equities: yfinance normalisation, MultiIndex, empty."""

from __future__ import annotations

import sys
import types

import pandas as pd

from earnings_iv_crush.data import equities


def _raw_frame(multiindex: bool = False) -> pd.DataFrame:
    idx = pd.to_datetime(["2026-05-01", "2026-05-02"])
    idx.name = "Date"
    df = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [10.5, 11.5],
            "Low": [9.5, 10.5],
            "Close": [10.2, 11.2],
            "Adj Close": [10.2, 11.2],
            "Volume": [1000, 2000],
        },
        index=idx,
    )
    if multiindex:
        # Newer yfinance returns (field, ticker) column tuples.
        df.columns = pd.MultiIndex.from_product([df.columns, ["AAPL"]])
    return df


def _install_fake_yf(monkeypatch, frame):
    fake = types.ModuleType("yfinance")
    fake.download = lambda *a, **k: frame
    monkeypatch.setitem(sys.modules, "yfinance", fake)


def test_normalises_single_index(monkeypatch):
    _install_fake_yf(monkeypatch, _raw_frame(multiindex=False))
    df = equities.fetch_equity_ohlcv("AAPL", "2026-05-01", "2026-05-02")

    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df["close"].iloc[0] == 10.2
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_handles_multiindex_columns(monkeypatch):
    _install_fake_yf(monkeypatch, _raw_frame(multiindex=True))
    df = equities.fetch_equity_ohlcv("AAPL", "2026-05-01", "2026-05-02")

    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert df["volume"].iloc[1] == 2000


def test_empty_download_returns_empty_schema(monkeypatch):
    _install_fake_yf(monkeypatch, pd.DataFrame())
    df = equities.fetch_equity_ohlcv("AAPL", "2026-05-01", "2026-05-02")
    assert list(df.columns) == equities._COLS
    assert df.empty
