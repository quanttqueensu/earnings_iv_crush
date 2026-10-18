"""
session_check.py
Decide whether today's 15:35 ET pass may run, on the NYSE calendar.

The daily pass snapshots the chain and transmits orders at 15:35 ET. On a closed
day those orders would sit until the next open and fill at a price the book never
saw; on a 13:00 early close the snapshot is already the stale post-close book.
Both cases must skip, and say so, rather than trade.

Exit status: 0 regular session, 10 exchange closed, 11 early close.

Usage
-----
    python deploy/session_check.py
    python deploy/session_check.py --date 2026-11-27
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from earnings_iv_crush.engine.stats import nyse_sessions

OPEN, CLOSED, EARLY = 0, 10, 11


def is_early_close(day: pd.Timestamp) -> bool:
    """13:00 ET closes: the day after Thanksgiving, Christmas Eve and 3 July.

    Christmas Eve and 3 July are early closes only when they are themselves
    sessions; 3 July on a Friday is the observed holiday or a full day, never an
    early close.
    """
    if day.month == 11 and day.weekday() == 4 and 23 <= day.day <= 29:
        return True
    if day.month == 12 and day.day == 24:
        return True
    return day.month == 7 and day.day == 3 and day.weekday() <= 3


def classify(day: pd.Timestamp) -> int:
    """Return ``OPEN``, ``CLOSED`` or ``EARLY`` for ``day``."""
    day = pd.Timestamp(day).normalize()
    if day not in nyse_sessions(day, day):
        return CLOSED
    return EARLY if is_early_close(day) else OPEN


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default today, exchange time)")
    args = ap.parse_args(argv)
    day = pd.Timestamp(args.date) if args.date else pd.Timestamp.now(tz="America/New_York")
    day = pd.Timestamp(day.date())
    status = classify(day)
    label = {OPEN: "regular session", CLOSED: "exchange closed", EARLY: "early close"}[status]
    print(f"{day.date()}: {label}")
    return status


if __name__ == "__main__":
    sys.exit(main())
