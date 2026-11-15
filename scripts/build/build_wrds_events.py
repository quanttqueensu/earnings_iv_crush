"""
build_wrds_events.py
Rebuild the earnings calendar (announce date + bmo/amc session) from the WRDS R2 mirror.

The book's event calendar was sourced from Finnhub. This re-sources it off WRDS-grade tables:
the announcement date from Compustat ``fundq.rdq`` and the session from I/B/E/S announcement
times (see ``earnings.build_wrds_calendar``, which holds the linking + session logic). Identifier
linking is by 8-digit CUSIP, which Compustat, IBES and CRSP all carry, so it sidesteps ticker
convention drift.

Outputs:
  * ``outputs/research/calendar_wrds.parquet`` - the same 50 mega-cap names / 2019-2024 window as
    the live Databento calendar, drop-in for ``build_execution_events`` and directly comparable to
    ``calendar_databento.parquet`` (see ``wrds_vs_databento_events.py``).
  * a printed breadth read: how many distinct US quarterly earnings events WRDS carries in the
    window (the candidate universe the mirror unlocks), with a liquidity cut.

The mirror has no options, so this rebuilds only the calendar; the option-derived event columns
still come from the Databento marking pass. No Databento credits are spent here. Read-only.

Run: ``python scripts/build/build_wrds_events.py``
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import wrds_r2 as w  # noqa: E402
from earnings_iv_crush.data.earnings import build_wrds_calendar  # noqa: E402

REF_CALENDAR = Path("outputs/research/calendar_databento.parquet")  # the 50-name reference scope
OUT = Path("outputs/research/calendar_wrds.parquet")
WINDOW = ("2019-01-01", "2024-12-31")

# Earliest date the consolidated one-minute BBO exists on OPRA. Compustat reaches back much
# further, so a calendar can be built for years the marks cannot cover; the window is clamped
# here rather than discovering it as an empty pull.
CBBO_START = "2013-04-01"
MKT_CAP_FLOOR = 300.0  # $m, the breadth-count liquidity cut (mkvaltq is in $m)


def _breadth(window: tuple[str, str]) -> None:
    """Report the full candidate universe the mirror unlocks in the window."""
    fq = w.read_table(
        "comp_na_daily_all",
        "fundq",
        columns=["gvkey", "rdq", "mkvaltq"],
        filters=[
            ("rdq", ">=", pd.Timestamp(window[0]).date()),
            ("rdq", "<=", pd.Timestamp(window[1]).date()),
        ],
    )
    fq = fq[fq["rdq"].notna()].drop_duplicates(["gvkey", "rdq"])
    liquid = fq[fq["mkvaltq"].fillna(0) >= MKT_CAP_FLOOR]
    print(
        f"WRDS candidate universe {window[0][:4]}-{window[1][:4]}: {len(fq):,} quarterly earnings "
        f"events across {fq['gvkey'].nunique():,} firms "
        f"({len(liquid):,} events at >= ${MKT_CAP_FLOOR:.0f}m cap)."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=WINDOW[0])
    ap.add_argument("--end", default=WINDOW[1])
    ap.add_argument("--out", default=str(OUT), help="destination parquet")
    args = ap.parse_args()

    start, end, out = args.start, args.end, Path(args.out)
    if pd.Timestamp(start) < pd.Timestamp(CBBO_START):
        print(
            f"NOTE: {start} precedes the {CBBO_START} start of cbbo-1m on OPRA. The calendar "
            "will be built, but events before that date cannot be quote-marked."
        )

    names = sorted(pd.read_parquet(REF_CALENDAR)["ticker"].unique())
    print(f"reference scope: {len(names)} names, {start}..{end}")
    _breadth((start, end))

    cal = build_wrds_calendar(start, end, names)
    missing = sorted(set(names) - set(cal["ticker"].unique()))
    if missing:
        print(f"WARNING: no Compustat match for {missing} (excluded)")

    out.parent.mkdir(parents=True, exist_ok=True)
    cal.to_parquet(out, index=False)

    print(f"\ncalendar: {len(cal)} events, {cal['ticker'].nunique()} names -> {out}")
    print("session:", cal["session"].value_counts().to_dict())
    timed = (cal["session_source"] == "ibes_time").mean()
    print(f"IBES-timed sessions: {timed:.0%} (rest defaulted to amc)")


if __name__ == "__main__":
    main()
