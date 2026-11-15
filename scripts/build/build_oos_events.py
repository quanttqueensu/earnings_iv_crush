"""
build_oos_events.py
Reconstruct the event set from the cached Databento chains, with live progress.

This is the cache-only build stage: it reads the chains already pulled to
``data/processed/databento`` (no network, no credits) and assembles the per-event
feature/execution table the backtest consumes. It builds one name at a time and
prints a progress line after every name.

Outputs:
* ``events_megacap_databento.parquet``     - the full set (2019-2024).
* ``events_megacap_databento_oos.parquet`` - the pre-2024 subset, i.e. the clean
  out-of-sample sample (2024 overlaps the Alpaca in-sample, so it is excluded from
  the OOS test and kept only as a labelled in-sample cross-check).

Run: ``python scripts/build/build_oos_events.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.data.equities import fetch_equity_ohlcv  # noqa: E402
from earnings_iv_crush.data.options import CHAIN_COLUMNS  # noqa: E402
from earnings_iv_crush.data.real_events import build_execution_events  # noqa: E402
from scripts.build.build_databento_events import CALENDAR_PATH, EVENTS_PATH, _scoped  # noqa: E402

OOS_PATH = Path("outputs/research/events_megacap_databento_oos.parquet")
OOS_LAST_YEAR = 2023  # 2024+ overlaps the Alpaca in-sample, excluded from the OOS test


def _cached_only(ticker: str, asof: str, **_: object) -> pd.DataFrame:
    """Chain fetcher that only ever reads the disk cache (never bills/network)."""
    path = dbo._cache_path(ticker, pd.Timestamp(asof).normalize())
    return pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=CHAIN_COLUMNS)


def _raw_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Underlying OHLCV lifted to the *unadjusted* basis the OPRA strikes use.

    yfinance returns split-adjusted closes, but the cached Databento chains carry
    raw historical strikes (and IV inverted at the raw spot). Feeding the event
    builder adjusted spots against raw strikes mis-selects the ATM strike for any
    name that split in-sample (AAPL 4:1, AMZN/GOOGL 20:1, ...). Multiplying each
    day's price by its post-date split factor puts spot and strikes on one basis.
    """
    px = fetch_equity_ohlcv(ticker, start, end)
    if px is None or px.empty:
        return px
    px = px.copy()
    dates = pd.to_datetime(px["date"]).dt.normalize()
    factors = np.array([dbo._split_factor(ticker, d) for d in dates], dtype=float)
    for col in ("open", "high", "low", "close"):
        if col in px.columns:
            px[col] = px[col].astype(float) * factors
    return px


def main() -> None:
    cal = _scoped(pd.read_parquet(CALENDAR_PATH))
    names = sorted(cal["ticker"].unique())
    frames = []
    for i, ticker in enumerate(names, start=1):
        sub = cal[cal["ticker"] == ticker]
        ev = build_execution_events(
            sub, fetch_chain=_cached_only, fetch_prices=_raw_prices, progress=False
        )
        if not ev.empty:
            frames.append(ev)
        print(f"[{i}/{len(names)}] {ticker} ({len(ev)} events)", flush=True)

    events = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["ticker", "entry_date"])
    )
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(EVENTS_PATH, index=False)

    entry_year = pd.to_datetime(events["entry_date"]).dt.year
    oos = events[entry_year <= OOS_LAST_YEAR].reset_index(drop=True)
    oos.to_parquet(OOS_PATH, index=False)

    print(f"\nFULL: {len(events)} events, {events['ticker'].nunique()} names -> {EVENTS_PATH.name}")
    print("by entry year:")
    print(entry_year.value_counts().sort_index().to_string())
    print(
        f"\nOOS (<= {OOS_LAST_YEAR}): {len(oos)} events, {oos['ticker'].nunique()} names "
        f"-> {OOS_PATH.name}; skew_25d non-null {int(oos['skew_25d'].notna().sum())}"
    )


if __name__ == "__main__":
    main()
