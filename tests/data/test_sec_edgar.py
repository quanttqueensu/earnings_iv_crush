"""Tests for earnings_iv_crush.data.sec_edgar: CIK map, session inference, 8-Ks, EPS."""

from __future__ import annotations

import pytest

from earnings_iv_crush.data import sec_edgar
from tests.data.conftest import FakeResponse

_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
}

_SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["8-K", "8-K", "10-Q", "8-K"],
            "items": ["2.02,9.01", "5.02", "", "2.02"],
            "acceptanceDateTime": [
                "2026-01-30T16:30:00.000Z",  # earnings, after close -> amc
                "2026-02-15T10:00:00.000Z",  # not earnings (5.02)
                "2026-03-01T12:00:00.000Z",  # 10-Q, excluded
                "2026-04-25T08:00:00.000Z",  # earnings, before open -> bmo
            ],
            "accessionNumber": ["a-1", "a-2", "a-3", "a-4"],
        }
    }
}

_CONCEPT = {
    "units": {
        "USD/shares": [
            {"end": "2026-03-31", "val": 2.5, "filed": "2026-04-25", "form": "10-Q"},
            {"end": "2025-12-31", "val": 2.4, "filed": "2026-01-30", "form": "8-K"},
        ]
    }
}


def _router(url, headers=None, timeout=None, **kwargs):
    if "company_tickers.json" in url:
        return FakeResponse(json_data=_TICKERS)
    if "companyconcept" in url:
        return FakeResponse(json_data=_CONCEPT)
    if "submissions" in url:
        return FakeResponse(json_data=_SUBMISSIONS)
    raise AssertionError(f"unexpected URL {url}")


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    # CIK map is lru_cached; clear so each test starts clean.
    sec_edgar.cik_map.cache_clear()
    monkeypatch.setattr(sec_edgar, "SEC_USER_AGENT", "Tester tester@example.com")
    monkeypatch.setattr(sec_edgar.requests, "get", _router)


def test_cik_map_zero_pads_to_ten_digits():
    assert sec_edgar.cik_map()["AAPL"] == "0000320193"
    assert sec_edgar.get_cik("aapl") == "0000320193"  # case-insensitive


def test_get_cik_unknown_raises():
    with pytest.raises(KeyError):
        sec_edgar.get_cik("NOPE")


def test_headers_require_user_agent(monkeypatch):
    monkeypatch.setattr(sec_edgar, "SEC_USER_AGENT", "")
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        sec_edgar._headers()


@pytest.mark.parametrize(
    "acceptance,expected",
    [
        ("2026-01-30T16:30:00.000Z", "amc"),
        ("2026-04-25T08:00:00.000Z", "bmo"),
        ("2026-04-25T12:00:00.000Z", "ambiguous"),
        ("2026-04-25 17:00:00", "amc"),  # naive timestamp path
    ],
)
def test_infer_session(acceptance, expected):
    assert sec_edgar.infer_session(acceptance) == expected


def test_earnings_8ks_filters_to_item_202():
    df = sec_edgar.earnings_8ks("AAPL")
    # Only the two Item-2.02 8-Ks survive; 5.02 and the 10-Q are dropped.
    assert list(df["accession"]) == ["a-1", "a-4"]
    assert list(df["session"]) == ["amc", "bmo"]


def test_reported_eps_sorted_by_period_end():
    df = sec_edgar.reported_eps("AAPL")
    assert list(df["val"]) == [2.4, 2.5]  # sorted by 'end' ascending
    assert df["end"].is_monotonic_increasing
