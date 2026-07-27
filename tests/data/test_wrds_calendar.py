"""Offline tests for the WRDS calendar helpers (pure logic, no network)."""

from __future__ import annotations

import datetime as dt

from earnings_iv_crush.data.earnings import _map_names_to_tic, _session_from_ibes_time


def test_session_from_ibes_time_boundaries():
    assert _session_from_ibes_time(dt.time(16, 30)) == ("amc", "ibes_time")
    assert _session_from_ibes_time(dt.time(16, 0)) == ("amc", "ibes_time")  # at the close
    assert _session_from_ibes_time(dt.time(7, 0)) == ("bmo", "ibes_time")
    assert _session_from_ibes_time(dt.time(9, 30)) == ("bmo", "ibes_time")  # at the open
    assert _session_from_ibes_time(dt.time(12, 30)) == ("dmh", "ibes_time")


def test_session_from_ibes_time_unknown_defaults_amc():
    assert _session_from_ibes_time(dt.time(0, 0)) == ("amc", "default_unknown")
    assert _session_from_ibes_time(None) == ("amc", "default_unknown")
    assert _session_from_ibes_time(float("nan")) == ("amc", "default_unknown")


def test_map_names_to_tic_handles_dash_dot_drift():
    tics = {"AAPL", "BRK.B", "GOOGL"}
    got = _map_names_to_tic(["AAPL", "BRK-B", "GOOGL"], tics)
    assert got == {"AAPL": "AAPL", "BRK-B": "BRK.B", "GOOGL": "GOOGL"}


def test_map_names_to_tic_drops_unmatched():
    assert _map_names_to_tic(["ZZZZ"], {"AAPL"}) == {}
