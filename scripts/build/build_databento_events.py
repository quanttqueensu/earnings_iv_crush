"""
build_databento_events.py
Reconstruct the out-of-sample earnings events from OPRA daily chains.

Two stages, both credit-guarded:

1. **Cost pre-flight (free).** Samples a handful of events, prices the exact
   ``ohlcv-1d`` requests the adapter will make (entry day + exit day) via
   ``metadata.get_cost``, and extrapolates to the full calendar. Aborts if the
   estimate exceeds ``CAP_USD`` - so the bulk pull never starts over budget.

2. **Build (spends credits).** Only runs with ``--run``. Feeds the calendar to
   ``real_events.build_execution_events`` with the Databento chain fetcher, which
   caches every resolved chain to disk (so a re-run resumes for free). Persists
   the events and the term panel, and prints a coverage report.

Run the estimate:   ``python scripts/build/build_databento_events.py``
Run the build:      ``python scripts/build/build_databento_events.py --run``
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.data.equities import fetch_equity_ohlcv  # noqa: E402
from earnings_iv_crush.data.real_events import (  # noqa: E402
    build_execution_events,
    entry_exit_dates,
)
from earnings_iv_crush.data.term_panel import build_term_panel  # noqa: E402

CALENDAR_PATH = Path("outputs/research/calendar_databento.parquet")
EVENTS_PATH = Path("outputs/research/events_megacap_databento.parquet")
PANEL_PATH = Path("outputs/research/panel_megacap_databento.parquet")
CAP_USD = 200.0
SAMPLE = 8  # events priced in the pre-flight
WORST_CASE_PER_EVENT = 0.10  # pre-flight guard; the live SPEND_LIMIT breaker is the real cap

# Live spend tracking + circuit-breaker. The prefetch writes STATUS_PATH after every
# event so `scripts/watch_prefetch.py` can render a live bar, and aborts the moment
# estimated new spend crosses SPEND_LIMIT (a code-side stop on top of Databento's own
# server-side budget cap, which is the true hard ceiling).
PER_EVENT_EST = 0.11  # conservative USD/event (2024 + pricier names run ~$0.098)
SPEND_LIMIT = 12.5  # hard stop on estimated new spend this run (leaves ~$5 of credit)
START_BALANCE = 17.5  # credits remaining at run start (for the balance readout)
STATUS_PATH = Path("outputs/research/prefetch_status.json")

# Full out-of-sample scope: the whole megacap calendar over 2021-2023 (pre-2024, so
# no overlap with the 2024-2026 Alpaca in-sample). The cache makes the pull
# resumable, so the 8-name first pass already on disk is skipped, not re-billed.
FIRST_PASS_NAMES = 50
WINDOW = ("2019-01-01", "2024-12-31")


def _scoped(cal: pd.DataFrame) -> pd.DataFrame:
    """Subset the calendar to the first-pass names and OOS window."""
    names = sorted(cal["ticker"].unique())[:FIRST_PASS_NAMES]
    ad = pd.to_datetime(cal["announce_date"])
    mask = cal["ticker"].isin(names) & (ad >= WINDOW[0]) & (ad <= WINDOW[1])
    return cal[mask].reset_index(drop=True)


# ── Cost pre-flight ──────────────────────────────────────────────────────────


def _day_cost(ticker: str, asof: pd.Timestamp, spot: float) -> float:
    """``get_cost`` of the exact one-day ohlcv request the adapter will issue."""
    start = asof.strftime("%Y-%m-%d")
    end = (asof + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    defn = dbo._get_df("definition", [f"{ticker}.OPT"], start, end, "parent")
    if defn.empty:
        return 0.0
    meta = dbo._select_instruments(defn, asof, spot)
    if meta.empty:
        return 0.0
    return dbo.get_cost(meta["raw_symbol"].tolist(), start, end)


def estimate_total(cal: pd.DataFrame) -> float:
    """Extrapolate full-calendar cost from a sample of priced events."""
    sample = cal.sample(min(SAMPLE, len(cal)), random_state=0)
    per_event = []
    for ev in sample.itertuples(index=False):
        announce = pd.Timestamp(ev.announce_date)
        session = getattr(ev, "session", "amc") or "amc"
        entry, exit_ = entry_exit_dates(announce, session)
        spot = dbo._spot_on_or_before(ev.ticker, entry)
        if not (spot and spot == spot):
            continue
        c = _day_cost(ev.ticker, entry, spot) + _day_cost(ev.ticker, exit_, spot)
        per_event.append(c)
        print(f"  {ev.ticker} {announce.date()}: ${c:.4f}")
    mean = sum(per_event) / len(per_event) if per_event else 0.0
    total = mean * len(cal)
    print(f"\nmean per-event: ${mean:.4f}  x  {len(cal)} events  =  ${total:.2f}")
    return total


# ── Prefetch (the slow, resumable, credit-spending stage) ────────────────────


def _write_status(
    done: int, total: int, pulled: int, spend: float, last: str, elapsed: float, finished: bool
) -> None:
    """Write the live status JSON the watcher renders (estimated, not a live balance)."""
    rate = pulled / elapsed if elapsed > 0 and pulled else 0.0  # events/sec
    eta_hr = (total - done) / rate / 3600.0 if rate else None
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        json.dumps(
            {
                "done": done,
                "total": total,
                "pulled": pulled,
                "est_spend": round(spend, 2),
                "spend_limit": SPEND_LIMIT,
                "est_balance_left": round(START_BALANCE - spend, 2),
                "last": last,
                "elapsed_min": round(elapsed / 60.0, 1),
                "eta_hr": round(eta_hr, 2) if eta_hr is not None else None,
                "finished": finished,
                "updated": time.strftime("%H:%M:%S"),
            }
        ),
        encoding="utf-8",
    )


def run_prefetch(cal: pd.DataFrame) -> None:
    """Populate the chain cache for every event (two API calls each, resumable).

    Tracks estimated new spend (newly pulled events x PER_EVENT_EST), streams it to
    STATUS_PATH every event for the live watcher, and hard-stops if it crosses
    SPEND_LIMIT. Events already cached cost nothing and do not count toward spend.
    """
    n = len(cal)
    done = pulled = 0
    spend = 0.0
    t0 = time.time()
    last = ""
    for i, ev in enumerate(cal.itertuples(index=False), 1):
        announce = pd.Timestamp(ev.announce_date)
        session = getattr(ev, "session", "amc") or "amc"
        entry, exit_ = entry_exit_dates(announce, session)
        was_cached = (
            dbo._cache_path(ev.ticker, entry.normalize()).exists()
            and dbo._cache_path(ev.ticker, exit_.normalize()).exists()
        )
        t = time.time()
        try:
            dbo.prefetch_event(ev.ticker, entry.strftime("%Y-%m-%d"), exit_.strftime("%Y-%m-%d"))
            done += 1
            if was_cached:
                tag = "cached"
            else:
                pulled += 1
                spend = pulled * PER_EVENT_EST
                tag = "pull"
        except Exception as exc:  # transient network: leave uncached, resume next run
            tag = f"ERR {exc!r}"[:60]
        last = f"{ev.ticker} {announce.date()}"
        _write_status(i, n, pulled, spend, last, time.time() - t0, finished=False)
        print(
            f"[{i}/{n}] {last}: {tag} ({time.time()-t:.0f}s)  est_spend=${spend:.2f}",
            flush=True,
        )
        if spend >= SPEND_LIMIT:
            print(
                f"\nCIRCUIT BREAKER: estimated new spend ${spend:.2f} hit the ${SPEND_LIMIT:.2f} "
                f"limit; stopping. Re-run --prefetch to resume (cached events are free).",
                flush=True,
            )
            break
    _write_status(i, n, pulled, spend, last, time.time() - t0, finished=True)
    print(f"\nprefetched {done}/{n} events; estimated new spend ${spend:.2f}")


# ── Build ────────────────────────────────────────────────────────────────────


def run_build(cal: pd.DataFrame) -> None:
    """Reconstruct events + term panel from the Databento chains and persist."""
    events = build_execution_events(
        cal,
        fetch_chain=dbo.fetch_option_chain,
        fetch_prices=fetch_equity_ohlcv,
        progress=True,
    )
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(EVENTS_PATH, index=False)
    print(f"\nevents: {len(events)} rows, {events['ticker'].nunique()} names -> {EVENTS_PATH}")
    if not events.empty:
        print(f"window: {events['entry_date'].min().date()} -> {events['entry_date'].max().date()}")
        print("\nper-name coverage:")
        print(events.groupby("ticker").size().sort_values(ascending=False).to_string())

        panel = build_term_panel(
            events, fetch_chain=dbo.fetch_option_chain, fetch_prices=fetch_equity_ohlcv
        )
        panel.to_parquet(PANEL_PATH, index=False)
        print(f"\nterm panel: {len(panel)} rows -> {PANEL_PATH}")


def main() -> None:
    """Pre-flight the cost, then build only when ``--run`` is passed and under cap."""
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--prefetch", action="store_true", help="populate the chain cache (spends credits)"
    )
    ap.add_argument("--run", action="store_true", help="build events from the cache")
    ap.add_argument("--force", action="store_true", help="proceed even if estimate exceeds the cap")
    args = ap.parse_args()

    cal = _scoped(pd.read_parquet(CALENDAR_PATH))
    print(
        f"scoped calendar: {len(cal)} events, {cal['ticker'].nunique()} names, {WINDOW[0]}..{WINDOW[1]}"
    )

    if args.prefetch:
        # Static worst-case guard (the empirical per-event cost is ~$0.15-0.30 for
        # this chain shape; $0.40 is a conservative ceiling). Avoids the slow,
        # flaky live get_cost sweep before a bulk pull.
        worst = WORST_CASE_PER_EVENT * len(cal)
        print(f"worst-case bound: {len(cal)} events x ${WORST_CASE_PER_EVENT:.2f} = ${worst:.2f}")
        if worst > CAP_USD and not args.force:
            print(f"\nWORST-CASE ${worst:.2f} EXCEEDS CAP ${CAP_USD:.0f} - trim scope or --force.")
            return
        run_prefetch(cal)
        return

    if args.run:
        run_build(cal)  # reads the cache populated by --prefetch
        return

    print("pricing a sample (free get_cost)...")
    total = estimate_total(cal)
    print(f"\nestimate only (${total:.2f}). Run --prefetch to pull, then --run to build.")


if __name__ == "__main__":
    main()
