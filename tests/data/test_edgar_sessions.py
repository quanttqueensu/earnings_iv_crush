"""Tests for earnings_iv_crush.data.edgar_sessions on synthetic fixtures (offline)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from earnings_iv_crush.data import edgar_sessions as es
from tests.data.conftest import FakeResponse

SESSIONS = es.trading_sessions("2025-01-01", "2026-12-31")


# ── timestamp classification ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ts, expected",
    [
        ("2025-04-24 00:00:00", "bmo"),
        ("2025-04-24 06:30:00", "bmo"),
        ("2025-04-24 09:29:59", "bmo"),
        ("2025-04-24 09:30:00", "intraday"),
        ("2025-04-24 12:00:00", "intraday"),
        ("2025-04-24 15:59:59", "intraday"),
        ("2025-04-24 16:00:00", "amc"),
        ("2025-04-24 16:30:28", "amc"),
        ("2025-04-24 23:59:59", "amc"),
    ],
)
def test_classify_time_boundaries(ts: str, expected: str) -> None:
    assert es.classify_time(ts) == expected


@pytest.mark.parametrize(
    "utc_stamp, expected_et, expected_label",
    [
        # Winter (EST, UTC-5) on the Friday before the 2025-03-09 change.
        ("2025-03-07T14:29:59+00:00", "2025-03-07 09:29:59", "bmo"),
        ("2025-03-07T14:30:00+00:00", "2025-03-07 09:30:00", "intraday"),
        ("2025-03-07T21:00:00+00:00", "2025-03-07 16:00:00", "amc"),
        # Summer (EDT, UTC-4) on the Monday after: the same UTC clock is an hour later.
        ("2025-03-10T13:29:59+00:00", "2025-03-10 09:29:59", "bmo"),
        ("2025-03-10T14:29:59+00:00", "2025-03-10 10:29:59", "intraday"),
        ("2025-03-10T20:00:00+00:00", "2025-03-10 16:00:00", "amc"),
        # Autumn change, 2025-11-02: Friday EDT, Monday EST.
        ("2025-10-31T19:59:59+00:00", "2025-10-31 15:59:59", "intraday"),
        ("2025-11-03T20:59:59+00:00", "2025-11-03 15:59:59", "intraday"),
        ("2025-11-03T21:00:00+00:00", "2025-11-03 16:00:00", "amc"),
    ],
)
def test_to_eastern_applies_dst_by_date(
    utc_stamp: str, expected_et: str, expected_label: str
) -> None:
    assert es.to_eastern(utc_stamp) == pd.Timestamp(expected_et)
    assert es.classify_time(utc_stamp) == expected_label


def test_naive_timestamp_is_taken_as_eastern() -> None:
    assert es.to_eastern("2025-07-30 16:30:28") == pd.Timestamp("2025-07-30 16:30:28")


# ── Item 2.02 parsing ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "form, items, expected",
    [
        ("8-K", "2.02,9.01", True),
        ("8-K", "2.02", True),
        ("8-K", " 7.01, 2.02 ,9.01", True),
        ("8-K", "5.02,9.01", False),
        ("8-K", "", False),
        ("8-K", None, False),
        ("8-K/A", "2.02,9.01", False),
        ("10-Q", "2.02", False),
        ("8-K", "12.02", False),
    ],
)
def test_is_earnings_8k(form: str, items: str | None, expected: bool) -> None:
    assert es.is_earnings_8k(form, items) is expected


def test_parse_items_returns_item_numbers_only() -> None:
    assert es.parse_items("2.02,9.01,junk") == frozenset({"2.02", "9.01"})


@pytest.mark.parametrize(
    "ticker, expected", [("brk.b", "BRK-B"), ("BF/B", "BF-B"), (" aapl ", "AAPL")]
)
def test_normalise_ticker(ticker: str, expected: str) -> None:
    assert es.normalise_ticker(ticker) == expected


@pytest.mark.parametrize(
    "html, expected",
    [
        (
            '<div class="infoHead">Accepted</div>\n<div class="info">2026-07-30 16:30:28</div>',
            pd.Timestamp("2026-07-30 16:30:28"),
        ),
        ('<div class="infoHead">Filing Date</div><div class="info">2026-07-30</div>', None),
    ],
)
def test_parse_accepted(html: str, expected: pd.Timestamp | None) -> None:
    assert es.parse_accepted(html) == expected


# ── release slot and reaction session ────────────────────────────────────────


@pytest.mark.parametrize(
    "accepted, filing_date, session, release, reaction, rolled",
    [
        # Pre-market 8-K: reacts the same session.
        ("2025-07-22 06:59:07", "2025-07-22", "bmo", "2025-07-22", "2025-07-22", False),
        # After the close, same filing date: reacts the next session.
        ("2025-07-17 16:04:28", "2025-07-17", "amc", "2025-07-17", "2025-07-18", False),
        # Friday AMC reacts on Monday.
        ("2025-07-25 16:05:00", "2025-07-25", "amc", "2025-07-25", "2025-07-28", False),
        # Accepted after 17:30 and dated forward (the PepsiCo pattern): BMO on filing date.
        ("2025-10-08 19:16:09", "2025-10-09", "bmo", "2025-10-09", "2025-10-09", True),
        # Intraday acceptance reacts the same day.
        ("2025-04-24 12:00:00", "2025-04-24", "intraday", "2025-04-24", "2025-04-24", False),
        # Saturday acceptance: public before Monday's open.
        ("2025-08-02 10:00:00", "2025-08-04", "bmo", "2025-08-04", "2025-08-04", True),
        # Accepted on the 9 January 2025 closure: next session is 10 January.
        ("2025-01-09 08:00:00", "2025-01-09", "bmo", "2025-01-10", "2025-01-10", True),
    ],
)
def test_release_slot(
    accepted: str, filing_date: str, session: str, release: str, reaction: str, rolled: bool
) -> None:
    slot = es.release_slot(accepted, filing_date, SESSIONS)
    assert slot.session == session
    assert slot.release_date == pd.Timestamp(release)
    assert slot.reaction_date == pd.Timestamp(reaction)
    assert slot.rolled is rolled


@pytest.mark.parametrize(
    "announce, session, expected",
    [
        ("2025-07-22", "bmo", "2025-07-22"),
        ("2025-07-17", "amc", "2025-07-18"),
        ("2025-07-25", "amc", "2025-07-28"),
        ("2025-04-17", "amc", "2025-04-21"),  # Good Friday 2025-04-18 closed
        ("2025-07-22", "ambiguous", None),
    ],
)
def test_calendar_reaction(announce: str, session: str, expected: str | None) -> None:
    got = es.calendar_reaction(announce, session, SESSIONS)
    assert got == (pd.Timestamp(expected) if expected else None)


def test_amc_and_forward_dated_evening_filing_share_a_reaction_session() -> None:
    cal = es.calendar_reaction("2025-10-08", "amc", SESSIONS)
    slot = es.release_slot("2025-10-08 18:10:00", "2025-10-09", SESSIONS)
    assert es.compare_reaction(cal, slot.reaction_date) == "agree"


@pytest.mark.parametrize(
    "calendar, edgar, expected",
    [
        ("2025-07-18", "2025-07-18", "agree"),
        ("2025-07-18", "2025-07-17", "edgar_earlier"),
        ("2025-07-17", "2025-07-18", "edgar_later"),
        (None, "2025-07-18", "calendar_ambiguous"),
    ],
)
def test_compare_reaction(calendar: str | None, edgar: str, expected: str) -> None:
    cal = pd.Timestamp(calendar) if calendar else None
    assert es.compare_reaction(cal, pd.Timestamp(edgar)) == expected


# ── nearest-filing matching ──────────────────────────────────────────────────


def _filings(*release_and_accepted: tuple[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "accession": [f"a-{i}" for i in range(len(release_and_accepted))],
            "release_date": pd.to_datetime([r for r, _ in release_and_accepted]),
            "accepted_et": pd.to_datetime([a for _, a in release_and_accepted]),
        }
    )


@pytest.mark.parametrize(
    "announce, expected",
    [
        ("2025-04-24", "a-1"),  # exact
        ("2025-04-23", "a-1"),  # one day off
        ("2025-01-30", "a-0"),
        ("2025-03-01", None),  # nothing within four days
        ("2025-07-25", "a-2"),  # tie at distance one: earlier acceptance wins
    ],
)
def test_match_nearest(announce: str, expected: str | None) -> None:
    f = _filings(
        ("2025-01-30", "2025-01-30 16:30"),
        ("2025-04-24", "2025-04-24 07:00"),
        ("2025-07-24", "2025-07-24 16:05"),
        ("2025-07-26", "2025-07-26 08:00"),
    )
    got = es.match_nearest(f, announce)
    assert (got["accession"] if got is not None else None) == expected


def test_match_nearest_empty_frame() -> None:
    assert es.match_nearest(_filings(), "2025-04-24") is None


@pytest.mark.parametrize("k, n", [(0, 10), (5, 10), (10, 10), (950, 1000)])
def test_wilson_ci_brackets_the_proportion(k: int, n: int) -> None:
    lo, hi = es.wilson_ci(k, n)
    assert 0.0 <= lo <= k / n <= hi <= 1.0


# ── client: throttle, cache, refusal ─────────────────────────────────────────


class _FakeSession:
    def __init__(self, routes: dict[str, FakeResponse]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
        self.calls.append((url, headers))
        for key, resp in self.routes.items():
            if key in url:
                return resp
        raise AssertionError(f"unexpected URL {url}")


_SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["8-K", "8-K", "10-Q", "8-K"],
            "items": ["2.02,9.01", "5.02", "", "2.02"],
            "accessionNumber": ["0001-25-000001", "0001-25-000002", "x", "0001-25-000004"],
            "filingDate": ["2025-07-31", "2025-08-15", "2025-08-01", "2025-10-30"],
            "acceptanceDateTime": [
                "2025-08-01T00:30:00.000Z",
                "2025-08-15T14:00:00.000Z",
                "2025-08-01T16:00:00.000Z",
                "2025-10-31T00:30:00.000Z",
            ],
        },
        "files": [],
    }
}


def _index(ts: str) -> FakeResponse:
    return FakeResponse(text=f'<div class="infoHead">Accepted</div><div class="info">{ts}</div>')


def _client(tmp_path, routes: dict[str, FakeResponse]) -> tuple[es.EdgarClient, list[float]]:
    sleeps: list[float] = []
    clock = iter(float(i) * 0.01 for i in range(10_000))
    client = es.EdgarClient(
        cache_dir=tmp_path,
        user_agent="Tester tester@example.com",
        session=_FakeSession(routes),  # type: ignore[arg-type]
        sleep=sleeps.append,
        clock=lambda: next(clock),
    )
    return client, sleeps


def test_client_throttles_and_sends_user_agent(tmp_path) -> None:
    client, sleeps = _client(
        tmp_path, {"company_tickers": FakeResponse(json_data={"0": {"ticker": "A", "cik_str": 1}})}
    )
    client.get("https://www.sec.gov/files/company_tickers.json")
    client.get("https://www.sec.gov/files/company_tickers.json")
    assert sleeps and all(s <= es.MIN_REQUEST_INTERVAL_S for s in sleeps)
    sess = client.session
    assert all(h["User-Agent"] == "Tester tester@example.com" for _, h in sess.calls)  # type: ignore[attr-defined]


def test_client_raises_on_403(tmp_path) -> None:
    client, _ = _client(tmp_path, {"sec.gov": FakeResponse(status_code=403)})
    with pytest.raises(es.SecAccessRefused):
        client.get("https://www.sec.gov/files/company_tickers.json")


def test_fallback_user_agent_has_no_contact(tmp_path) -> None:
    client = es.EdgarClient(cache_dir=tmp_path, user_agent="")
    assert client.user_agent == es.FALLBACK_USER_AGENT
    assert "@" not in client.user_agent


def test_cache_prevents_second_request(tmp_path) -> None:
    routes = {"company_tickers": FakeResponse(json_data={"0": {"ticker": "brk-b", "cik_str": 7}})}
    client, _ = _client(tmp_path, routes)
    assert client.cik_map() == {"BRK-B": 7}
    fresh, _ = _client(tmp_path, {})  # no routes: any request would fail
    assert fresh.cik_map() == {"BRK-B": 7}
    assert json.loads((tmp_path / "company_tickers.json").read_text())["0"]["cik_str"] == 7


def test_check_calendar_end_to_end(tmp_path) -> None:
    routes = {
        "company_tickers": FakeResponse(json_data={"0": {"ticker": "AAA", "cik_str": 1}}),
        "submissions": FakeResponse(json_data=_SUBMISSIONS),
        "0001-25-000001-index": _index("2025-07-31 16:30:00"),
        "0001-25-000004-index": _index("2025-10-30 16:30:00"),
    }
    client, _ = _client(tmp_path, routes)
    cal = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "AAA", "ZZZ"],
            "announce_date": pd.to_datetime(
                ["2025-07-31", "2025-10-30", "2025-04-24", "2025-07-31"]
            ),
            "session": ["amc", "bmo", "amc", "amc"],
            "session_source": ["yahoo", "yahoo", "yahoo", "yahoo"],
        }
    )
    rows, funnel = es.check_calendar(cal, client, "2025-01-01", "2025-12-31", progress=False)
    by = rows.set_index(rows["announce_date"].dt.strftime("%Y-%m-%d") + rows["ticker"])
    assert by.loc["2025-07-31AAA", "verdict"] == "agree"
    # Calendar says BMO on 10-30 (reacts 10-30); EDGAR says AMC (reacts 10-31): late filing.
    assert by.loc["2025-10-30AAA", "verdict"] == "edgar_later"
    assert by.loc["2025-04-24AAA", "status"] == "no_8k_in_window"
    assert by.loc["2025-07-31ZZZ", "status"] == "no_cik"
    assert funnel["calendar_events_in_window"] == 4
    assert funnel["ticker_mapped_to_cik"] == 3
    assert funnel["matched_8k_2_02_in_window"] == 2
    summary = es.summarise(rows, funnel)
    assert summary["n_comparable"] == 2 and summary["reaction_agree"] == 1
    assert summary["json_offset_hours_counts"] == {"8.0": 2}


def test_check_calendar_raises_on_empty_window(tmp_path) -> None:
    client, _ = _client(tmp_path, {})
    cal = pd.DataFrame(
        {"ticker": ["A"], "announce_date": pd.to_datetime(["2020-01-01"]), "session": ["bmo"]}
    )
    with pytest.raises(ValueError, match="no calendar events"):
        es.check_calendar(cal, client, "2025-01-01", "2025-12-31", progress=False)
