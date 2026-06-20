"""Tests for the historical calendar builder (synthetic providers, no network)."""

from __future__ import annotations

import pandas as pd

from earnings_iv_crush.data import calendar_build
from earnings_iv_crush.data.universe import MEGACAP_50


def _events(ticker, start, end):
    if ticker not in ("AAPL", "MSFT"):
        return pd.DataFrame(columns=[c for c in calendar_build.CALENDAR_COLUMNS if c != "cohort"])
    return pd.DataFrame(
        [
            {
                "ticker": ticker,
                "announce_date": pd.Timestamp("2025-05-01"),
                "session": "amc",
                "session_source": "yahoo",
                "eps_estimate": 1.0,
                "eps_actual": 1.1,
            }
        ]
    )


def _no_8ks(ticker):
    return pd.DataFrame(columns=["accession", "acceptance", "session"])


def _agreeing_8ks(ticker):
    return pd.DataFrame(
        {
            "accession": ["x"],
            "acceptance": [pd.Timestamp("2025-05-01 16:35")],
            "session": ["amc"],
        }
    )


def _disagreeing_8ks(ticker):
    return pd.DataFrame(
        {
            "accession": ["x"],
            "acceptance": [pd.Timestamp("2025-05-01 08:00")],
            "session": ["bmo"],
        }
    )


def test_build_calendar_schema_and_cohort():
    cal = calendar_build.build_calendar(
        ["AAPL", "MSFT", "ZZZZ"],
        "2025-01-01",
        "2025-12-31",
        fetch_events=_events,
        fetch_8ks=_no_8ks,
    )
    assert list(cal.columns) == calendar_build.CALENDAR_COLUMNS
    assert len(cal) == 2
    assert (cal["cohort"] == "megacap").all()
    assert "AAPL" in MEGACAP_50


def test_every_event_has_resolved_session():
    cal = calendar_build.build_calendar(
        ["AAPL", "MSFT"],
        "2025-01-01",
        "2025-12-31",
        fetch_events=_events,
        fetch_8ks=_no_8ks,
    )
    assert cal["session"].isin(["bmo", "amc", "ambiguous"]).all()
    assert cal["session"].notna().all()


def test_edgar_agreement_upgrades_source():
    cal = calendar_build.build_calendar(
        ["AAPL"],
        "2025-01-01",
        "2025-12-31",
        fetch_events=_events,
        fetch_8ks=_agreeing_8ks,
    )
    assert cal.iloc[0]["session_source"] == "yahoo+edgar"
    assert cal.iloc[0]["session"] == "amc"


def test_edgar_bmo_overrides_yahoo_amc():
    # Pre-09:30 acceptance proves the news was out pre-market.
    cal = calendar_build.build_calendar(
        ["AAPL"],
        "2025-01-01",
        "2025-12-31",
        fetch_events=_events,
        fetch_8ks=_disagreeing_8ks,
    )
    assert cal.iloc[0]["session"] == "bmo"
    assert cal.iloc[0]["session_source"] == "edgar_override"


def test_edgar_amc_does_not_override_yahoo_bmo():
    # Late filings prove nothing: BMO announcers routinely file mid-afternoon.
    def bmo_events(ticker, start, end):
        df = _events(ticker, start, end)
        df["session"] = "bmo"
        return df

    cal = calendar_build.build_calendar(
        ["AAPL"],
        "2025-01-01",
        "2025-12-31",
        fetch_events=bmo_events,
        fetch_8ks=_agreeing_8ks,  # edgar says amc
    )
    assert cal.iloc[0]["session"] == "bmo"
    assert cal.iloc[0]["session_source"] == "conflict"


def test_empty_universe_returns_empty_schema():
    cal = calendar_build.build_calendar(
        ["ZZZZ"],
        "2025-01-01",
        "2025-12-31",
        fetch_events=_events,
        fetch_8ks=_no_8ks,
    )
    assert cal.empty
    assert list(cal.columns) == calendar_build.CALENDAR_COLUMNS
