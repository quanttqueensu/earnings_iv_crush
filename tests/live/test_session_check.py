"""
test_session_check.py
Pins the cloud runner's session classifier to the NYSE published calendar.

Every date below is taken from the exchange's holidays and early-close table, so
a regression in the holiday rules or the early-close rules fails here before an
unattended pass queues an order against a closed or post-close book.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parents[2] / "deploy" / "session_check.py"
_spec = importlib.util.spec_from_file_location("session_check", _PATH)
assert _spec is not None and _spec.loader is not None
session_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(session_check)

OPEN, CLOSED, EARLY = session_check.OPEN, session_check.CLOSED, session_check.EARLY


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        # Full closures.
        ("2026-07-03", CLOSED),  # Independence Day observed (Friday)
        ("2026-11-26", CLOSED),  # Thanksgiving
        ("2026-12-25", CLOSED),  # Christmas
        ("2027-07-05", CLOSED),  # Independence Day observed (Monday)
        ("2027-12-24", CLOSED),  # Christmas observed (Friday)
        ("2026-10-10", CLOSED),  # Saturday
        # 13:00 early closes.
        ("2026-11-27", EARLY),  # day after Thanksgiving
        ("2026-12-24", EARLY),  # Christmas Eve (Thursday)
        ("2027-11-26", EARLY),
        ("2028-07-03", EARLY),  # Monday before Independence Day
        # Regular sessions adjacent to the above.
        ("2026-07-02", OPEN),
        ("2026-10-05", OPEN),
        ("2026-12-23", OPEN),
        ("2027-07-02", OPEN),
    ],
)
def test_classify_against_nyse_calendar(day, expected):
    assert session_check.classify(pd.Timestamp(day)) == expected


def test_cli_exit_status():
    assert session_check.main(["--date", "2026-11-27"]) == EARLY
    assert session_check.main(["--date", "2026-11-26"]) == CLOSED
    assert session_check.main(["--date", "2026-10-05"]) == OPEN
