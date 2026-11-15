"""
build_databento_calendar.py
Historical earnings calendar for the Databento out-of-sample backtest.

Pulls announcement dates (Yahoo, the historical leg) for a liquid megacap subset
over the pre-2024 window, so the events can be reconstructed against OPRA daily
chains. Cached to ``outputs/research/calendar_databento.parquet``; the event
builder reads it. This step touches no Databento credits.

Run: ``python scripts/build/build_databento_calendar.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data.earnings import fetch_earnings_dates  # noqa: E402
from earnings_iv_crush.data.universe import MEGACAP_50  # noqa: E402

# Full liquid-megacap cross-section over a five-year pre-2024 span (incl. the 2020
# COVID vol shock and the 2022 bear, for regime diversity). The event builder
# scopes names/window to the credit budget; this calendar is the superset it draws
# from. Building it touches no Databento credits.
UNIVERSE = MEGACAP_50
START = "2019-01-01"
END = "2024-12-31"
OUT_PATH = Path("outputs/research/calendar_databento.parquet")


def main() -> None:
    """Build, cache and summarise the historical earnings calendar."""
    cal = fetch_earnings_dates(UNIVERSE, START, END, limit=40)
    cal = cal.sort_values(["ticker", "announce_date"]).reset_index(drop=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cal.to_parquet(OUT_PATH, index=False)

    print(f"calendar: {len(cal)} events, {cal['ticker'].nunique()} names")
    print(f"window:   {cal['announce_date'].min().date()} -> {cal['announce_date'].max().date()}")
    print(f"saved:    {OUT_PATH}")
    per_name = cal.groupby("ticker").size().sort_values(ascending=False)
    print("\nevents per name:")
    print(per_name.to_string())
    if "session" in cal.columns:
        print("\nsession mix:")
        print(cal["session"].value_counts(dropna=False).to_string())
    missing = sorted(set(UNIVERSE) - set(cal["ticker"]))
    if missing:
        print(f"\nunresolved by Yahoo: {missing}")


if __name__ == "__main__":
    main()
