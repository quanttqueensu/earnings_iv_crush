"""Tests for earnings_iv_crush.data.earnings: Finnhub calendar normalisation and guards."""

from __future__ import annotations

import pytest

from earnings_iv_crush.data import earnings
from tests.data.conftest import FakeResponse

_PAYLOAD = {
    "earningsCalendar": [
        {
            "symbol": "AAPL",
            "date": "2026-06-01",
            "hour": "amc",
            "epsEstimate": 2.1,
            "epsActual": None,
            "revenueEstimate": 1.0e11,
            "revenueActual": None,
            "quarter": 3,
            "year": 2026,
        },
        {
            "symbol": "MSFT",
            "date": "2026-06-02",
            "hour": "bmo",
            "epsEstimate": 3.0,
            "epsActual": None,
            "revenueEstimate": 6.0e10,
            "revenueActual": None,
            "quarter": 4,
            "year": 2026,
        },
    ]
}


def test_fetch_earnings_calendar_renames_columns(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "key")
    monkeypatch.setattr(
        earnings.requests,
        "get",
        lambda url, params=None, timeout=None, **kw: FakeResponse(json_data=_PAYLOAD),
    )
    df = earnings.fetch_earnings_calendar("2026-06-01", "2026-06-05")

    assert {"ticker", "announce_date", "eps_estimate", "revenue_estimate"} <= set(df.columns)
    assert list(df["ticker"]) == ["AAPL", "MSFT"]
    assert list(df["announce_date"]) == ["2026-06-01", "2026-06-02"]
    assert list(df["hour"]) == ["amc", "bmo"]


def test_empty_calendar_returns_empty_frame(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "key")
    monkeypatch.setattr(
        earnings.requests,
        "get",
        lambda url, params=None, timeout=None, **kw: FakeResponse(
            json_data={"earningsCalendar": []}
        ),
    )
    df = earnings.fetch_earnings_calendar("2026-06-01", "2026-06-05")
    assert df.empty


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FINNHUB_API_KEY"):
        earnings.fetch_earnings_calendar("2026-06-01", "2026-06-05")
