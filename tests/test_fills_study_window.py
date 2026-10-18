"""
test_fills_study_window.py
The Stage 3 fills pull must address exchange-local time, not vendor-assumed UTC.

Databento reads a timezone-naive timestamp as UTC. The first run of the fills study
concatenated "15:30" onto a date and passed it through, so it pulled 19:30-20:00 UTC
worth of data from the 15:30 UTC instant instead: a late-morning Eastern window, roughly
four hours from the 15:59 ET mark the book actually transacts at. The level it reported
as the measured closing spread was therefore a measurement of a different session state.

These tests pin the conversion in both daylight-saving regimes and assert the round trip,
because the failure was silent in every other respect: the pull succeeded, the cache
populated, and the statistics computed cleanly on the wrong records.
"""

from __future__ import annotations

import pandas as pd
import pytest

from research.execution.research_fills_study import _assert_window, _request_range

_ET = "America/New_York"


def _round_trip(start: str, end: str) -> tuple[str, str]:
    """The requested UTC instants read back as exchange-local clock times."""
    lo, hi = (pd.Timestamp(s).tz_convert(_ET) for s in (start, end))
    return lo.strftime("%H:%M"), hi.strftime("%H:%M")


def test_summer_session_maps_to_utc_offset_four() -> None:
    """EDT: 15:30-16:00 ET is 19:30-20:00 UTC."""
    start, end = _request_range(pd.Timestamp("2023-07-19"))
    assert start == "2023-07-19T19:30:00Z"
    assert end == "2023-07-19T20:00:00Z"


def test_winter_session_maps_to_utc_offset_five() -> None:
    """EST: the same clock window is an hour later in UTC."""
    start, end = _request_range(pd.Timestamp("2024-01-24"))
    assert start == "2024-01-24T20:30:00Z"
    assert end == "2024-01-24T21:00:00Z"


@pytest.mark.parametrize(
    "day",
    [
        "2023-07-19",  # midsummer
        "2024-01-24",  # midwinter
        "2024-03-08",  # last session before the spring transition
        "2024-03-11",  # first session after it
        "2024-11-01",  # last session before the autumn transition
        "2024-11-04",  # first session after it
    ],
)
def test_round_trip_recovers_the_exchange_local_window(day: str) -> None:
    """Whatever the offset, converting the request back must give 15:30-16:00 local.

    The transition-adjacent sessions are the ones that matter: a hardcoded offset passes
    the midsummer and midwinter cases and fails here.
    """
    assert _round_trip(*_request_range(pd.Timestamp(day))) == ("15:30", "16:00")


def test_request_timestamps_are_timezone_explicit() -> None:
    """A naive string is what caused the defect; the request must never emit one."""
    for stamp in _request_range(pd.Timestamp("2023-10-17")):
        assert stamp.endswith("Z")
        assert pd.Timestamp(stamp).tzinfo is not None


def _cache_frame(times_utc: list[str]) -> pd.DataFrame:
    idx = pd.DatetimeIndex(pd.to_datetime(times_utc, utc=True), name="ts_recv")
    return pd.DataFrame({"price": [1.0] * len(idx)}, index=idx)


def test_assert_window_accepts_a_correctly_placed_pull() -> None:
    frame = _cache_frame(["2023-07-19T19:31:00Z", "2023-07-19T19:59:00Z"])
    _assert_window(frame)  # must not raise


def test_assert_window_rejects_the_superseded_utc_pull() -> None:
    """The exact records the first run cached: 15:30-16:00 UTC, i.e. late morning ET."""
    frame = _cache_frame(["2023-07-19T15:30:00Z", "2023-07-19T15:59:00Z"])
    with pytest.raises(SystemExit, match="outside 15:30-16:00"):
        _assert_window(frame)
