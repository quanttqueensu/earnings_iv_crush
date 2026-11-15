"""
build_quote_marked_chains.py
Re-mark the mega-cap book on real OPRA consolidated quotes.

Pulls ``cbbo-1m`` for every event already in the Databento book and writes quote-marked
chains alongside the trade-marked ones, so the two can be compared rather than one
overwriting the other. The instrument set comes from the chains already on disk, so no
``definition`` calls are billed.

Spend discipline (the account runs on metered credits):

* every event is priced with ``metadata.get_cost`` before it is pulled, which is free;
* a running total is kept and the run **halts** at ``--cap`` rather than warning;
* an event whose two chains are already cached costs nothing and is skipped, so a
  resumed run retries only what is missing;
* estimate and actual are reconciled at the end, because an estimate that silently
  blows up is a defect rather than a surprise.

Usage
-----
    python scripts/build/build_quote_marked_chains.py --dry-run
    python scripts/build/build_quote_marked_chains.py --cap 40
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402

EVENTS = Path("outputs/research/events_megacap_databento.parquet")
LEDGER = Path("outputs/research/quote_remark_spend.csv")

DEFAULT_CAP = 40.0  # hard stop in USD; the priced estimate for the full book is ~$13


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cap", type=float, default=DEFAULT_CAP, help="hard USD spend ceiling")
    ap.add_argument("--dry-run", action="store_true", help="price everything, pull nothing")
    ap.add_argument("--limit", type=int, default=None, help="only process the first N events")
    ap.add_argument("--workers", type=int, default=6, help="concurrent requests (latency-bound)")
    args = ap.parse_args()

    ev = pd.read_parquet(EVENTS)
    for col in ("entry_date", "exit_date"):
        ev[col] = pd.to_datetime(ev[col])
    ev = ev.sort_values(["entry_date", "ticker"]).reset_index(drop=True)
    if args.limit:
        ev = ev.head(args.limit)

    print(f"{len(ev)} events, {ev['ticker'].nunique()} names, cap ${args.cap:.2f}")
    print("dry run: pricing only, nothing pulled\n" if args.dry_run else "")

    spent = 0.0
    rows: list[dict] = []
    funnel = {"cached": 0, "pulled": 0, "failed": 0, "halted": 0}
    t0 = time.time()
    lock = threading.Lock()

    pending = []
    for _, e in ev.iterrows():
        ticker = str(e["ticker"])
        ep, xp = dq.cache_path(ticker, e["entry_date"]), dq.cache_path(ticker, e["exit_date"])
        if ep.exists() and xp.exists():
            funnel["cached"] += 1
            continue
        pending.append(e)
    print(f"{funnel['cached']} already cached, {len(pending)} to pull\n")

    def _one(e: pd.Series) -> dict:
        """Pull one event. Runs on a worker thread; the network wait is the whole cost."""
        nonlocal spent
        ticker = str(e["ticker"])
        d0 = e["entry_date"].strftime("%Y-%m-%d")
        d1 = e["exit_date"].strftime("%Y-%m-%d")
        try:
            billed = dq.prefetch_event(
                ticker,
                d0,
                d1,
                spot_entry=float(e["spot_entry"]),
                spot_exit=float(e["spot_exit"]),
                dry_run=args.dry_run,
            )
        except Exception as exc:
            with lock:
                funnel["failed"] += 1
            return {
                "ticker": ticker,
                "entry": d0,
                "estimate": 0.0,
                "actual": 0.0,
                "error": str(exc)[:80],
            }

        with lock:
            spent += billed
            funnel["pulled"] += 1
            done = funnel["pulled"]
            if done % 50 == 0:
                rate = done / max(time.time() - t0, 1e-9)
                left = (len(pending) - done) / rate if rate > 0 else 0
                print(
                    f"  {done:4d}/{len(pending)}  ${spent:6.2f}  "
                    f"{rate * 60:.0f} ev/min  ~{left / 60:.0f} min left",
                    flush=True,
                )
        return {"ticker": ticker, "entry": d0, "estimate": billed, "actual": billed}

    # Concurrency: each event is two sequential network round trips and almost no CPU,
    # so the run is latency-bound and widening it is the only thing that shortens it.
    # The cap is still enforced before every submission; with `workers` requests in
    # flight the worst possible overshoot is `workers` events, about $0.10 here, which
    # is why the check leaves a margin rather than aiming at the cap exactly.
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = []
        for e in pending:
            with lock:
                margin = args.workers * max(spent / max(funnel["pulled"], 1), 0.05)
                if spent + margin > args.cap:
                    funnel["halted"] = 1
            if funnel["halted"]:
                print(
                    f"\nHALT: ${spent:.2f} spent, within {args.workers} events of the "
                    f"${args.cap:.2f} cap. Everything pulled so far is cached and will not "
                    "be re-billed; re-run with a higher --cap to continue."
                )
                break
            futures.append(pool.submit(_one, e))
        for fut in as_completed(futures):
            rows.append(fut.result())

    elapsed = (time.time() - t0) / 60
    led = pd.DataFrame(rows)
    if not led.empty:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        # Append rather than overwrite. A resumed run only carries the events it pulled,
        # so writing would discard the earlier legs' per-event audit trail and leave the
        # reconciliation unverifiable for most of the book. This cost the first 815 rows
        # once already.
        led.to_csv(LEDGER, mode="a", header=not LEDGER.exists(), index=False)

    print(f"\n{'dry-run estimate' if args.dry_run else 'run complete'} in {elapsed:.1f} min")
    print(f"  events cached already : {funnel['cached']}")
    print(f"  events pulled         : {funnel['pulled']}")
    if not led.empty and not args.dry_run:
        est, act = led["estimate"].sum(), led["actual"].sum()
        print(f"  estimated  ${est:.4f}")
        print(f"  actual     ${act:.4f}")
        gap = act - est
        note = "matches" if abs(gap) < 0.01 else f"DIVERGED by ${gap:+.4f} - investigate"
        print(f"  reconciliation: {note}")
    else:
        print(f"  total estimate ${spent:.4f}")
    if not led.empty:
        print(f"\nwritten: {LEDGER.resolve()}")


if __name__ == "__main__":
    main()
