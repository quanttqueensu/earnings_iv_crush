"""
build_broad_oos_2025.py
Price the 2025-2026 broad-universe earnings block as a clean out-of-sample test.

The Databento headline sample (2019-2024, 45 mega-cap names, N=192 gated trades at
the term-only q=0.80 gate) sits at a per-trade Sharpe of +0.116 with a bootstrap
lower bound of -0.023 and a one-sided p of 0.055. It fails the conventional bar by
a margin of about eleven trades. This script builds the sample that settles it.

The block is announcements from ``START`` onward in
``events_master_broad.parquet``: roughly 2,055 events across 348 names, with no
overlap against the Databento window and no overlap against the 2024 Alpaca cache
that the (killed) skew gate was searched on. The gate specification is read from
``StrategyConfig`` and is NOT re-tuned here. That is the whole point: a locked
specification applied to unseen data is an out-of-sample test, and the same
specification re-optimised on this block would be one more trial family charged
against an already-fragile deflated Sharpe.

WHAT THIS CAN AND CANNOT SHOW. Alpaca's historical chain endpoint serves a daily
bar close, so bid equals ask on every row. This block therefore measures the GROSS
signal at the mid and nothing else. It cannot re-measure transaction costs, and no
result from it may be quoted net. Costs are already measured properly on the
Databento NBBO sample (11.6% of premium round-trip break-even; 3.07% entry and
8.55% exit measured half-cross) and do not need redoing here.

Builds one name at a time and checkpoints after each, so an interrupted run resumes
from the last completed name rather than restarting. Free: Alpaca's options data is
covered by the existing key, and no metered provider is touched.

Run: ``python scripts/build/build_broad_oos_2025.py [--limit N] [--start YYYY-MM-DD]``
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import alpaca_options  # noqa: E402
from earnings_iv_crush.data.equities import fetch_equity_ohlcv  # noqa: E402
from earnings_iv_crush.data.options import CHAIN_COLUMNS  # noqa: E402
from earnings_iv_crush.data.real_events import build_execution_events  # noqa: E402

CALENDAR_PATH = Path("outputs/research/events_master_broad.parquet")
OUT_PATH = Path("outputs/research/events_broad_oos_2025.parquet")
START = "2025-01-01"  # first announcement date with no Databento/Alpaca-cache overlap


def _fetch_chain(ticker: str, asof: str, **kwargs: object) -> pd.DataFrame:
    """Alpaca chain fetcher that degrades to an empty frame instead of raising.

    A name with no chain on a given session must skip that event, not abort the
    whole build. The skip funnel is reported at the end so a silent collapse in
    coverage is visible rather than inferred from a small N.
    """
    try:
        return alpaca_options.fetch_option_chain(ticker, asof, **kwargs)  # type: ignore[arg-type]
    except Exception:
        return pd.DataFrame(columns=CHAIN_COLUMNS)


def _fetch_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Spot history, falling back to Alpaca bars when yfinance cannot resolve the symbol.

    yfinance intermittently 404s on symbols that plainly exist (BK and CMA both
    failed on the first pass, and both are liquid large-caps with options). Without
    a fallback those names contribute zero events and the sample shrinks silently,
    which is the exact failure the funnel reporting exists to catch. Alpaca serves
    the same daily bars under the key already in use, so the fallback costs nothing.
    """
    empty = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    try:
        px = fetch_equity_ohlcv(ticker, start, end)
        if px is not None and not px.empty:
            return px
    except Exception:
        pass
    try:
        px = alpaca_options.fetch_underlying_ohlcv(ticker, start, end)
        if px is not None and not px.empty:
            print(f"    (spot for {ticker} via Alpaca fallback)", flush=True)
            return px
    except Exception:
        pass
    return empty


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=START, help=f"first announcement date (default {START})")
    ap.add_argument("--limit", type=int, default=0, help="max names this run (0 = all)")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    out_path = Path(args.out)
    cal = pd.read_parquet(CALENDAR_PATH)
    cal["announce_date"] = pd.to_datetime(cal["announce_date"])
    cal = cal[cal["announce_date"] >= pd.Timestamp(args.start)].reset_index(drop=True)

    done: set[str] = set()
    priced: list[pd.DataFrame] = []
    if out_path.exists():
        prior = pd.read_parquet(out_path)
        priced = [prior]
        done = set(prior["ticker"].unique())

    names = [t for t in sorted(cal["ticker"].unique()) if t not in done]
    if args.limit:
        names = names[: args.limit]

    print(f"Block: {len(cal)} events, {cal['ticker'].nunique()} names, from {args.start}.")
    print(f"Already priced: {len(done)} names. To build this run: {len(names)}.")
    print("Gross/mid marks only (Alpaca serves bar closes, bid == ask). Not a cost read.\n")

    t0 = time.time()
    for i, ticker in enumerate(names, start=1):
        sub = cal[cal["ticker"] == ticker]
        try:
            ev = build_execution_events(
                sub, fetch_chain=_fetch_chain, fetch_prices=_fetch_prices, progress=False
            )
        except Exception as exc:
            print(f"  [{i}/{len(names)}] {ticker}: build failed ({type(exc).__name__}), skipped.")
            continue
        if not ev.empty:
            priced.append(ev)
        if priced:
            pd.concat(priced, ignore_index=True).to_parquet(out_path, index=False)
        n_total = sum(len(p) for p in priced)
        elapsed = time.time() - t0
        rate = elapsed / i
        eta = rate * (len(names) - i) / 60.0
        print(
            f"  [{i}/{len(names)}] {ticker}: +{len(ev)} events "
            f"(total {n_total}) | {elapsed/60:.1f}m elapsed, ~{eta:.0f}m left",
            flush=True,
        )

    if not priced:
        raise SystemExit("No events priced. Check the Alpaca key and the calendar window.")
    out = pd.concat(priced, ignore_index=True)
    out.to_parquet(out_path, index=False)
    print(f"\nDone. {len(out)} priced events, {out['ticker'].nunique()} names -> {out_path}")
    print(f"Calendar candidates in block: {len(cal)}. Priced share: {len(out)/len(cal):.1%}.")


if __name__ == "__main__":
    main()
