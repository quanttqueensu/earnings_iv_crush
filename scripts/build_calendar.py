"""
build_calendar.py
Build the consolidated historical earnings calendar for a universe.

History comes from Yahoo per ticker (Finnhub's free calendar only serves
future dates) with sessions cross-checked against SEC EDGAR 8-K acceptance
times. Per-ticker results are cached so reruns only fetch missing names.

Usage
-----
From the project root::

    python scripts/build_calendar.py --universe megacap
    python scripts/build_calendar.py --universe broad --no-crosscheck
    python scripts/build_calendar.py --universe broad --refresh

Output: ``outputs/research/events_master_{universe}.parquet`` plus a session
summary printed at the end.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from earnings_iv_crush.config import GLOBAL
from earnings_iv_crush.data import cache, calendar_build
from earnings_iv_crush.data.universe import get_universe

OUT_DIR = Path("outputs") / "research"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--universe", choices=["megacap", "broad"], default=GLOBAL.universe)
    ap.add_argument("--start", default=GLOBAL.start_date)
    ap.add_argument("--end", default=GLOBAL.end_date)
    ap.add_argument("--no-crosscheck", action="store_true", help="skip the EDGAR session check")
    ap.add_argument("--refresh", action="store_true", help="ignore per-ticker caches")
    args = ap.parse_args()

    tickers = get_universe(args.universe)

    def cached_events(ticker: str, start: str, end: str) -> pd.DataFrame:
        key = f"calendar_{ticker}_{start}_{end}"
        if not args.refresh and cache.has_frame(key):
            return cache.read_frame(key)
        df = calendar_build.yahoo_events(ticker, start, end)
        cache.write_frame(df, key)
        return df

    print(f"building calendar for {len(tickers)} names, {args.start} -> {args.end}")
    cal = calendar_build.build_calendar(
        tickers,
        args.start,
        args.end,
        fetch_events=cached_events,
        crosscheck=not args.no_crosscheck,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"events_master_{args.universe}.parquet"
    cal.to_parquet(out_path)

    print(f"\n{len(cal)} events -> {out_path}")
    if not cal.empty:
        print("\nsession breakdown:")
        print(cal["session"].value_counts().to_string())
        print("\nsession source:")
        print(cal["session_source"].value_counts().to_string())
        print(f"\nnames with zero events: {len(set(tickers) - set(cal['ticker']))}")


if __name__ == "__main__":
    main()
