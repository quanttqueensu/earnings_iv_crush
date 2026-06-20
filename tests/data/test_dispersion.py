"""Tests for the free-first analyst dispersion stack in data_intake."""

from __future__ import annotations

import pandas as pd
import pytest

from earnings_iv_crush.data import data_intake


class _FakeEstimate:
    """Stands in for yf.Ticker(...).earnings_estimate."""

    def __init__(self, frame):
        self.earnings_estimate = frame


def test_yfinance_snapshot_path(monkeypatch):
    frame = pd.DataFrame(
        {"avg": [2.0], "low": [1.8], "high": [2.2], "numberOfAnalysts": [30]},
        index=pd.Index(["0q"], name="period"),
    )
    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", lambda t: _FakeEstimate(frame))
    monkeypatch.setattr(data_intake, "FINNHUB_API_KEY", "")

    df = data_intake.fetch_analyst_dispersion("AAPL", "2026-01-01", "2026-06-01")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["source"] == "yfinance_snapshot"
    assert row["eps_mean"] == 2.0
    assert row["eps_std"] == pytest.approx((2.2 - 1.8) / 4)
    assert row["n_estimates"] == 30


def test_returns_empty_frame_when_no_source(monkeypatch):
    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", lambda t: _FakeEstimate(None))
    monkeypatch.setattr(data_intake, "FINNHUB_API_KEY", "")

    df = data_intake.fetch_analyst_dispersion("ZZZZ", "2026-01-01", "2026-06-01")
    assert df.empty
    assert list(df.columns) == data_intake._DISPERSION_COLUMNS


def test_finnhub_failure_falls_through_to_yfinance(monkeypatch):
    frame = pd.DataFrame(
        {"avg": [1.0], "low": [0.8], "high": [1.2], "numberOfAnalysts": [10]},
        index=pd.Index(["0q"], name="period"),
    )
    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", lambda t: _FakeEstimate(frame))
    monkeypatch.setattr(data_intake, "FINNHUB_API_KEY", "some-key")

    def boom(*a, **k):
        raise RuntimeError("403")

    monkeypatch.setattr(data_intake, "_dispersion_from_finnhub", boom)

    df = data_intake.fetch_analyst_dispersion("AAPL", "2026-01-01", "2026-06-01")
    assert len(df) == 1
    assert df.iloc[0]["source"] == "yfinance_snapshot"


@pytest.mark.live
def test_live_dispersion_returns_rows():
    df = data_intake.fetch_analyst_dispersion("AAPL", "2026-01-01", "2026-06-01")
    assert not df.empty
    assert df.iloc[-1]["eps_std"] > 0
