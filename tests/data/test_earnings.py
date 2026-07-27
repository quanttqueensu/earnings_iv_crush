"""Tests for earnings_iv_crush.data.earnings: Finnhub calendar normalisation and guards."""

from __future__ import annotations

import pandas as pd
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


# ── session-aware trade timing ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("session", "entry", "exit_"),
    [
        ("amc", "2026-07-22", "2026-07-23"),
        ("AMC", "2026-07-22", "2026-07-23"),
        ("bmo", "2026-07-21", "2026-07-22"),
        ("dmh", "2026-07-21", "2026-07-22"),
    ],
)
def test_trade_dates_bracket_the_print(session, entry, exit_):
    """Entry is the last close before the print, exit the first close after it."""
    got = earnings.trade_dates_for_session(pd.Timestamp("2026-07-22"), session)
    assert got == (pd.Timestamp(entry), pd.Timestamp(exit_))


@pytest.mark.parametrize("session", [None, float("nan"), "", "   ", "unknown"])
def test_unknown_session_returns_none(session):
    """An unguessable session must be skipped, not defaulted.

    Defaulting either way is unsafe: a bmo name treated as amc opens after the
    print, an amc name treated as bmo closes before it.
    """
    assert earnings.trade_dates_for_session(pd.Timestamp("2026-07-22"), session) is None


@pytest.mark.parametrize("session", ["amc", "bmo", "dmh"])
def test_hold_is_always_one_session(session):
    """Every bracket spans exactly one business day, matching the backtest."""
    entry, exit_ = earnings.trade_dates_for_session(pd.Timestamp("2026-07-22"), session)
    assert len(pd.bdate_range(entry, exit_)) == 2


def test_bracket_crosses_the_weekend():
    """A Monday bmo print enters the prior Friday, not Sunday."""
    entry, exit_ = earnings.trade_dates_for_session(pd.Timestamp("2026-07-27"), "bmo")
    assert (entry, exit_) == (pd.Timestamp("2026-07-24"), pd.Timestamp("2026-07-27"))


def test_amc_bracket_crosses_the_weekend():
    """A Friday amc print exits the following Monday."""
    entry, exit_ = earnings.trade_dates_for_session(pd.Timestamp("2026-07-24"), "amc")
    assert (entry, exit_) == (pd.Timestamp("2026-07-24"), pd.Timestamp("2026-07-27"))
