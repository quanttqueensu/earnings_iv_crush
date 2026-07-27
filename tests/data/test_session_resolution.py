"""
test_session_resolution.py
Session normalisation for the event assembler: a NaN/ambiguous session must take
the configured default, never fall through to the BMO branch (NaN is truthy, so
the old ``raw or default`` idiom shifted unstamped events one day early).
"""

from __future__ import annotations

import pandas as pd

from earnings_iv_crush.data.real_events import _resolve_session, entry_exit_dates


def test_nan_session_takes_default():
    session, defaulted = _resolve_session(float("nan"), "amc")
    assert session == "amc"
    assert defaulted is True


def test_none_and_empty_take_default():
    for raw in (None, "", "nan", "none", "NaT"):
        session, defaulted = _resolve_session(raw, "amc")
        assert session == "amc"
        assert defaulted is True


def test_ambiguous_takes_default():
    session, defaulted = _resolve_session("ambiguous", "amc")
    assert session == "amc"
    assert defaulted is True


def test_explicit_sessions_pass_through():
    for raw in ("amc", "BMO", " dmh "):
        session, defaulted = _resolve_session(raw, "amc")
        assert session == raw.strip().lower()
        assert defaulted is False


def test_nan_session_no_longer_shifts_entry_a_day_early():
    announce = pd.Timestamp("2024-06-10")  # a Monday
    session, _ = _resolve_session(float("nan"), "amc")
    entry, exit_ = entry_exit_dates(announce, session)
    # amc default: enter at the announce close, exit the next close. The old
    # truthy-NaN path routed this through the bmo branch (entry 06-07).
    assert entry == announce
    assert exit_ == announce + pd.tseries.offsets.BDay(1)
