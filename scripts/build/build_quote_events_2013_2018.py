"""
build_quote_events_2013_2018.py
Extend the event book backwards to 2013 on quote marks.

The 2019-2024 book was built from OPRA daily trade bars. This builds the earlier block from
consolidated one-minute quotes instead, which is both the better mark and roughly five times
cheaper per event, and it is only possible because ``cbbo-1m`` reaches back to 2013-04-01
rather than the 2023-03-28 the code asserted for two years.

Two stages, deliberately separated so that spending and assembly cannot be confused:

* ``--prefetch`` pulls entry and exit chains under a hard cap. This is the only step that
  spends. Instrument sets come from OPRA definitions, since no trade-marked chain exists to
  borrow them from before 2019.
* ``--build`` assembles events from whatever is cached, reading through
  ``databento_quotes.fetch_option_chain``, which never pulls. An event whose chains are
  missing is dropped rather than silently triggering a fetch.

The term panel is deliberately not built here. The frozen specification gates on the
``term_spread`` column carried by the event table itself, so the rolling panel is not needed,
and building it would fan out into an unbounded number of additional chain-days.

Run: ``python scripts/build/build_quote_events_2013_2018.py --prefetch --cap 25``
     ``python scripts/build/build_quote_events_2013_2018.py --build``
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from earnings_iv_crush.data.equities import fetch_equity_ohlcv  # noqa: E402
from earnings_iv_crush.data.real_events import (  # noqa: E402
    build_execution_events,
    entry_exit_dates,
)

CALENDAR = Path("outputs/research/calendar_wrds_2013_2018.parquet")
EVENTS_OUT = Path("data/processed/events_megacap_quotes_2013_2018.parquet")
LEDGER = Path("outputs/research/quote_events_2013_2018_spend.csv")

DEFAULT_CAP = 25.0  # hard USD stop; the priced estimate for the full block is ~$20
CBBO_START = pd.Timestamp("2013-04-01")  # first date cbbo-1m exists on OPRA

# Measured on a live probe (AAPL 2013-04-23, 134 contracts): $0.0156 for the cbbo-1m window
# plus roughly $0.0019 for the definition call that supplies the instrument set. A dry run
# cannot price this path exactly, because pricing it would require the billed definition
# pull it is trying to avoid, so it extrapolates from this figure and says so.
PROBE_PER_EVENT = 0.0175


def _sessions() -> pd.DatetimeIndex:
    """Actual NYSE trading days, taken from an index ETF's own price history.

    ``entry_exit_dates`` works in plain business days, which count market holidays as
    tradeable. Every MLK Day and Presidents Day in the window therefore resolved to an
    entry with no quotes behind it. Reading the sessions off a real price series is exact
    and needs no holiday calendar to maintain, so it cannot drift out of date the way a
    hardcoded rule list would.
    """
    px = fetch_equity_ohlcv("SPY", "2013-01-01", "2019-06-30")
    if px is None or px.empty:
        raise SystemExit("cannot resolve the trading calendar: SPY history unavailable")
    return pd.DatetimeIndex(pd.to_datetime(px["date"]).sort_values().unique())


def _snap(day: pd.Timestamp, sessions: pd.DatetimeIndex, forward: bool) -> pd.Timestamp:
    """Move ``day`` onto a real session: back for an entry, forward for an exit."""
    day = pd.Timestamp(day).normalize()
    if day in sessions:
        return day
    later = sessions[sessions > day]
    earlier = sessions[sessions < day]
    if forward:
        return later[0] if len(later) else day
    return earlier[-1] if len(earlier) else day


def _plan(cal: pd.DataFrame) -> pd.DataFrame:
    """Entry/exit dates per calendar row, dropping anything before the quote feed starts.

    Entries snap backwards and exits forwards, preserving the one-overnight hold: an entry
    must be the last session before the report, and an exit the first session after the
    crush, so rounding them in opposite directions is what keeps the trade intact rather
    than quietly turning it into a two-day hold or a zero-day one.
    """
    sessions = _sessions()
    rows: list[dict] = []
    for _, e in cal.iterrows():
        entry, exit_ = entry_exit_dates(
            pd.Timestamp(e["announce_date"]), str(e.get("session", "amc"))
        )
        entry = _snap(entry, sessions, forward=False)
        exit_ = _snap(exit_, sessions, forward=True)
        if entry >= exit_ or pd.Timestamp(entry) < CBBO_START:
            continue
        rows.append({"ticker": e["ticker"], "entry": entry, "exit": exit_})
    return pd.DataFrame(rows)


def _spot_lookup(plan: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """One price history per ticker, covering the whole window.

    ``databento_options._spot_on_or_before`` fetches a seven-day window per call, which is
    one network round trip per event. Over this block that is the binding constraint on
    runtime (measured at 7 events/min, roughly two hours), and it re-requests the same
    history dozens of times per name. Pulling each ticker once and slicing locally turns
    1,150 calls into 50.
    """
    out: dict[str, pd.DataFrame] = {}
    lo = (pd.to_datetime(plan["entry"]).min() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    hi = (pd.to_datetime(plan["entry"]).max() + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    names = sorted(plan["ticker"].unique())
    for i, tk in enumerate(names, 1):
        try:
            px = fetch_equity_ohlcv(tk, lo, hi)
        except Exception as exc:  # noqa: BLE001 - a thin name must not stop the build
            print(f"  price history failed for {tk}: {exc!r}")
            continue
        if px is not None and not px.empty:
            out[tk] = px.assign(_d=pd.to_datetime(px["date"])).sort_values("_d")
        if i % 10 == 0:
            print(f"  price history {i}/{len(names)}", flush=True)
    print(f"  price history cached for {len(out)}/{len(names)} names")
    return out


def _spot_from_cache(hist: dict[str, pd.DataFrame], ticker: str, asof: pd.Timestamp) -> float:
    """Raw-basis spot on or before ``asof``, mirroring ``_spot_on_or_before`` exactly.

    The split factor is reapplied here for the same reason it exists there: yfinance closes
    are adjusted to the present, OPRA's historical strikes are not, and centring the strike
    band on an adjusted price selects nothing for any name that has since split.
    """
    px = hist.get(ticker)
    if px is None:
        return float("nan")
    usable = px[px["_d"] <= asof]
    if usable.empty:
        return float("nan")
    return float(usable["close"].iloc[-1]) * dbo._split_factor(ticker, asof)


def _prefetch(plan: pd.DataFrame, cap: float, workers: int, dry_run: bool) -> None:
    if dry_run:
        est = len(plan) * PROBE_PER_EVENT
        print(
            f"\nEXTRAPOLATED estimate: {len(plan)} events x ${PROBE_PER_EVENT:.4f} = ${est:.2f}\n"
            "  Not a per-event get_cost sweep: the instrument set comes from a billed\n"
            "  definition call, so exact pricing would cost what it is pricing. Treat this\n"
            f"  as an order-of-magnitude figure against the ${cap:.2f} cap, not a quote."
        )
        return
    spent = 0.0
    lock = threading.Lock()
    halted = threading.Event()
    rows: list[dict] = []
    errors: list[dict] = []
    t0 = time.time()

    # Drop events whose chains are already on disk before doing anything else. They cost
    # nothing to pull but they are not free to walk: a resumed run was spending its first
    # minutes re-checking hundreds of cached events, and under a bounded run window that
    # overhead is subtracted directly from useful work.
    cached = [
        dq.cache_path(r["ticker"], pd.Timestamp(r["entry"])).exists()
        and dq.cache_path(r["ticker"], pd.Timestamp(r["exit"])).exists()
        for r in plan.to_dict("records")
    ]
    n_cached = int(sum(cached))
    plan = plan[[not c for c in cached]].reset_index(drop=True)
    print(f"  {n_cached} already cached, {len(plan)} to pull")
    if plan.empty:
        print("  nothing to do")
        return

    hist = _spot_lookup(plan)

    def one(rec: dict) -> dict:
        nonlocal spent
        if halted.is_set():
            return {}
        ticker, entry, exit_ = rec["ticker"], rec["entry"], rec["exit"]
        # Spot on the raw unadjusted basis OPRA lists strikes in, needed to centre the
        # strike window when the instrument set comes from definitions.
        spot = _spot_from_cache(hist, ticker, pd.Timestamp(entry))
        # One malformed event must not kill a paid run, and must not be silently cached as
        # empty either: record the failure so the funnel shows it and a rerun retries it.
        try:
            billed = dq.prefetch_event(
                ticker,
                pd.Timestamp(entry).strftime("%Y-%m-%d"),
                pd.Timestamp(exit_).strftime("%Y-%m-%d"),
                allow_definition=True,
                spot_entry=spot,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            with lock:
                errors.append({"ticker": ticker, "entry": entry, "error": repr(exc)[:200]})
            return {}
        with lock:
            spent += billed
            if spent >= cap:
                halted.set()
        return {"ticker": ticker, "entry": entry, "actual": billed}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {}
        for rec in plan.to_dict("records"):
            if halted.is_set():
                break
            # Leave room for every in-flight request to bill its worst observed cost before
            # submitting another, so the cap cannot be overshot by the concurrency itself.
            with lock:
                mean = (spent / max(len(rows), 1)) if rows else 0.02
                if spent + workers * mean >= cap:
                    halted.set()
                    break
            futs[pool.submit(one, rec)] = rec
        for i, fut in enumerate(as_completed(futs), 1):
            out = fut.result()
            if out:
                rows.append(out)
            if i % 50 == 0:
                rate = i / max((time.time() - t0) / 60, 1e-9)
                print(f"  {i:5d}/{len(futs)}  ${spent:6.2f}  {rate:.0f} ev/min", flush=True)

    led = pd.DataFrame(rows)
    if not led.empty:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        led.to_csv(LEDGER, mode="a", header=not LEDGER.exists(), index=False)
    print(f"\n{'dry-run' if dry_run else 'prefetch'} complete in {(time.time()-t0)/60:.1f} min")
    print(f"  events processed : {len(rows)}")
    print(f"  events failed    : {len(errors)}")
    print(f"  actual           : ${spent:.4f}")
    if errors:
        tally = pd.DataFrame(errors)["error"].value_counts()
        print("\n  failure modes:")
        for msg, k in tally.head(5).items():
            print(f"    {k:4d}  {msg}")
    if halted.is_set():
        print(f"  HALTED at the ${cap:.2f} cap; rerun to continue.")


def _raw_prices(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    """Price history lifted onto the raw, unadjusted basis OPRA quotes strikes in.

    yfinance adjusts closes for every subsequent split, so a 2013 Apple close arrives as
    roughly one seventh of the price that traded. OPRA's strikes are the levels that
    actually traded. Feeding the adjusted series into the event build puts spot and strike
    on different bases, and the at-the-money selection then lands a factor of seven away.

    This is not a marginal correction: on the 2013-2018 block it silently refused 24% of
    events, and because the affected names are exactly the ones that split (Apple, Nvidia,
    Amazon, Tesla, Netflix, Broadcom, Alphabet), the loss correlated with realised growth.
    A sample missing its biggest winners is worse than a smaller unbiased one.
    """
    px = fetch_equity_ohlcv(ticker, start, end)
    if px is None or px.empty:
        return px
    out = px.copy()
    dates = pd.to_datetime(out["date"])
    factors = np.array([dbo._split_factor(ticker, d) for d in dates], dtype=float)
    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce") * factors
    return out


def _build(plan: pd.DataFrame) -> None:
    cal = pd.read_parquet(CALENDAR)
    events = build_execution_events(
        cal,
        fetch_chain=dq.fetch_option_chain,  # read-only: assembly cannot spend
        fetch_prices=_raw_prices,
        progress=True,
    )
    if events.empty:
        raise SystemExit(
            "No events assembled. The chain cache is empty or unreadable; run --prefetch first."
        )
    EVENTS_OUT.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(EVENTS_OUT, index=False)
    print(f"\nevents: {len(events)} rows, {events['ticker'].nunique()} names -> {EVENTS_OUT}")
    entry = pd.to_datetime(events["entry_date"])
    print(f"window: {entry.min():%Y-%m-%d} -> {entry.max():%Y-%m-%d}")
    print(f"planned {len(plan)}, assembled {len(events)} ({len(events)/max(len(plan),1):.1%})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prefetch", action="store_true", help="pull chains (spends credits)")
    ap.add_argument("--build", action="store_true", help="assemble events from the cache")
    ap.add_argument("--dry-run", action="store_true", help="price without pulling")
    ap.add_argument("--cap", type=float, default=DEFAULT_CAP, help="hard USD ceiling")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None, help="only the first N events")
    args = ap.parse_args()

    cal = pd.read_parquet(CALENDAR)
    plan = _plan(cal)
    if args.limit:
        plan = plan.head(args.limit)
    dropped = len(cal) - len(_plan(cal))
    print(
        f"calendar {len(cal)} events; {len(plan)} plannable ({dropped} predate {CBBO_START:%Y-%m-%d})"
    )

    if args.prefetch or args.dry_run:
        _prefetch(plan, args.cap, args.workers, args.dry_run)
        return
    if args.build:
        _build(plan)
        return
    print("nothing to do: pass --dry-run, --prefetch or --build")


if __name__ == "__main__":
    main()
