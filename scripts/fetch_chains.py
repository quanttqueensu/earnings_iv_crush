"""
fetch_chains.py
Pre-warm the chain snapshot cache for a universe's earnings events.

Enumerates every (ticker, date, variant) snapshot the backtest will need —
entry (T-1) and exit (T+holding) chains per event, plus the trailing 30
trading days per event for the term panel (deduplicated per ticker) — and
fetches them through the disk-cached Alpaca fetcher. Progress is tracked in a
manifest parquet (status per snapshot: pending/done/empty/error), so the run
can be killed and resumed at any point; cached snapshots cost nothing on
resume.

Usage
-----
From the project root::

    python scripts/fetch_chains.py --universe megacap
    python scripts/fetch_chains.py --universe broad --limit 5000 --shuffle
    python scripts/fetch_chains.py --universe megacap --rebuild-manifest

Run megacap first end to end before launching broad: it validates the whole
pipeline at ~15% of the request volume.
"""

from __future__ import annotations

import argparse
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from earnings_iv_crush.config import GLOBAL, STRATEGY
from earnings_iv_crush.data import cache
from earnings_iv_crush.data.chain_cache import cached_chain_fetcher, chain_key
from earnings_iv_crush.data.real_events import entry_exit_dates
from earnings_iv_crush.data.term_panel import _trailing_dates

OUT_DIR = Path("outputs") / "research"


def build_manifest(events: pd.DataFrame) -> pd.DataFrame:
    """All (ticker, date, variant) snapshots the backtest needs, deduplicated."""
    rows: set[tuple[str, str, str]] = set()
    for _, ev in events.iterrows():
        ticker = ev["ticker"]
        announce = pd.Timestamp(ev["announce_date"])
        # Session-aware entry/exit, matching real_events.build_execution_events,
        # so the cached snapshots cover the dates the assembler actually reads.
        session = ev.get("session", ev.get("hour")) or STRATEGY.default_session
        entry, exit_ = entry_exit_dates(announce, session)
        rows.add((ticker, entry.strftime("%Y-%m-%d"), "entry"))
        rows.add((ticker, exit_.strftime("%Y-%m-%d"), "entry"))
        for d in _trailing_dates(entry, STRATEGY.trailing_window):
            rows.add((ticker, d.strftime("%Y-%m-%d"), "panel"))
    mf = pd.DataFrame(sorted(rows), columns=["ticker", "date", "variant"])
    mf["status"] = "pending"
    # Alpaca's free history starts at GLOBAL.start_date; earlier trailing-window
    # dates can never resolve, so skip them rather than burn requests.
    mf.loc[mf["date"] < GLOBAL.start_date, "status"] = "skipped"
    # Snapshots already cached from earlier runs are done before we start.
    cached = mf.apply(
        lambda r: cache.has_frame(chain_key(r["ticker"], r["date"], r["variant"])), axis=1
    )
    mf.loc[cached, "status"] = "done"
    return mf


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--universe", choices=["megacap", "broad"], default="megacap")
    ap.add_argument("--limit", type=int, default=0, help="max snapshots this run (0 = all)")
    ap.add_argument("--shuffle", action="store_true", help="randomise fetch order")
    ap.add_argument("--rebuild-manifest", action="store_true")
    ap.add_argument(
        "--workers",
        type=int,
        default=8,
        help="parallel fetch threads; ~4 requests per snapshot, keep "
        "workers x rate under Alpaca's 200 req/min",
    )
    args = ap.parse_args()

    events_path = OUT_DIR / f"events_master_{args.universe}.parquet"
    manifest_path = OUT_DIR / f"fetch_manifest_{args.universe}.parquet"
    if not events_path.exists():
        raise SystemExit(f"{events_path} not found - run scripts/build_calendar.py first")

    if manifest_path.exists() and not args.rebuild_manifest:
        mf = pd.read_parquet(manifest_path)
    else:
        mf = build_manifest(pd.read_parquet(events_path))
        mf.to_parquet(manifest_path)

    fetchers = {v: cached_chain_fetcher(v) for v in ("entry", "panel")}
    todo = mf.index[mf["status"].isin(["pending", "error"])].tolist()
    if args.shuffle:
        random.shuffle(todo)
    if args.limit:
        todo = todo[: args.limit]

    counts = mf["status"].value_counts().to_dict()
    print(f"{args.universe}: {len(mf)} snapshots total, {counts}; fetching {len(todo)}")

    def fetch_one(idx):
        row = mf.loc[idx]
        df = fetchers[row["variant"]](row["ticker"], row["date"])
        return idx, ("done" if len(df) else "empty")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, idx): idx for idx in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            idx = futures[fut]
            try:
                _, status = fut.result()
                mf.at[idx, "status"] = status
            except Exception as exc:
                mf.at[idx, "status"] = "error"
                row = mf.loc[idx]
                print(f"  error {row['ticker']} {row['date']} {row['variant']}: {exc}")
            if i % 25 == 0 or i == len(todo):
                mf.to_parquet(manifest_path)
                print(f"  {i}/{len(todo)} ({mf['status'].value_counts().to_dict()})", flush=True)

    mf.to_parquet(manifest_path)
    print("final:", mf["status"].value_counts().to_dict())


if __name__ == "__main__":
    main()
