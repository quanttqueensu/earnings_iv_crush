"""
backfill_forward_window.py
Score the short earnings straddle over a recent window on quote-marked OPRA chains.

This is a BACKTEST, not paper trading. The entry decisions were made after the outcomes
were knowable, so it carries none of the inferential weight of a forward book and every
artifact it writes says so. It exists to give the recent window a measured read while the
live recorder (scripts/paper_radar.py) accrues an honest one.

Method, matching the live radar so the two are comparable:

  entry   the last consolidated quote at or before 15:59 ET on the session-aware entry
          day gives the ATM straddle mid and the implied move, im = straddle / spot.
  exit    the same strike and expiry, marked off the exit session's own chain. The
          straddle is bought back, not expired, so the close costs intrinsic plus the
          premium still in the contract.
  score   pnl = straddle_entry - straddle_exit, reported both on premium and on Reg-T
          margin, net of the 11.6%-of-premium round trip.

Spend discipline (metered credits):

* every pull is priced with ``metadata.get_cost`` first, which is free;
* a running total halts the run at ``--cap`` rather than warning past it;
* chains are cached per ticker-day, so a resumed run retries only what is missing;
* estimate and actual are reconciled at the end.

Usage:
    python scripts/backfill_forward_window.py --dry-run
    python scripts/backfill_forward_window.py --start 2026-07-21 --end 2026-08-11 --cap 5
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import numpy as np  # noqa: E402
import yfinance as yf  # noqa: E402

from earnings_iv_crush.data import earnings, universe  # noqa: E402

DATASET = "OPRA.PILLAR"
SCHEMA = "cbbo-1m"
EXCHANGE_TZ = "America/New_York"
SNAPSHOT = "15:59"
COST = 0.116

# Kept as literals rather than imported from scripts/paper_radar.py so the two entry
# points stay independent; they are pinned equal by the provenance tests.
MARK_QUOTE = "quote"
BACKFILL = "backfill"

CACHE = Path("data/cache/backfill_chains")
OUT_LEDGER = Path("outputs/research/backfill_ledger.csv")
OUT_SUMMARY = Path("outputs/research/backfill_summary.csv")
RICH_SEED = Path("data/rich_set.csv")


def _client():
    import os

    import databento as db

    key = os.environ.get("DATABENTO_API_KEY", "")
    if not key:
        raise RuntimeError("DATABENTO_API_KEY missing from .env")
    return db.Historical(key)


def _window(day: pd.Timestamp) -> tuple[str, str]:
    """The 15:59-16:00 ET minute on ``day`` as explicit UTC instants.

    Built by localising and converting, never string concatenation: Databento reads a
    naive timestamp as UTC, which lands the mark an hour out for half the year.
    """
    s = pd.Timestamp(f"{day.date()} {SNAPSHOT}").tz_localize(EXCHANGE_TZ).tz_convert("UTC")
    e = s + pd.Timedelta(minutes=1)
    return s.isoformat(), e.isoformat()


def _events(start: str, end: str) -> pd.DataFrame:
    """Earnings events in the window, chunked past the vendor's 1500-row response cap.

    A single wide request silently returns only the tail of the window, which understated
    this window by an order of magnitude the first time it was counted.
    """
    names = set(universe.get_universe("broad"))
    frames = []
    for d in pd.date_range(start, end, freq="3D"):
        a = d.strftime("%Y-%m-%d")
        b = (d + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        c = earnings.fetch_earnings_calendar(a, b)
        if len(c) >= 1500:
            print(f"  WARNING: {a}..{b} hit the 1500-row cap; shorten the chunk")
        frames.append(c)
    cal = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ticker", "announce_date"])
    cal = cal[cal["ticker"].isin(names)]
    cal = cal[(cal["announce_date"] >= start) & (cal["announce_date"] <= end)]
    col = "session" if "session" in cal.columns else "hour"

    rows = []
    for _, e in cal.iterrows():
        a = pd.Timestamp(e["announce_date"])
        dates = earnings.trade_dates_for_session(a, e.get(col))
        if dates is None:
            continue
        rows.append(
            {
                "ticker": e["ticker"],
                "announce_date": a.date(),
                "entry_date": dates[0].date(),
                "exit_date": dates[1].date(),
            }
        )
    return pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)


def _spot_table(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """One batched adjusted-close panel for every name, indexed by session.

    Fetching per ticker-day cost two sequential HTTP calls per event and dominated
    the runtime at roughly 1.8 events/minute. One batch download over the whole
    window is the same data in seconds. Adjusted closes put entry and exit on a
    single split basis, which is also the corporate-action guard.
    """
    lo = (pd.Timestamp(start) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    hi = (pd.Timestamp(end) + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    px = yf.download(
        tickers,
        start=lo,
        end=hi,
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    if px is None or px.empty:
        raise RuntimeError("batched price download returned nothing - refusing to proceed")
    close = px["Close"] if isinstance(px.columns, pd.MultiIndex) else px[["Close"]]
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close


def _spot_at(table: pd.DataFrame, ticker: str, day: pd.Timestamp) -> float | None:
    """Last close at or before ``day``, or None when the name has no usable history."""
    if ticker not in table.columns:
        return None
    s = table[ticker].dropna()
    s = s[s.index <= pd.Timestamp(day).normalize()]
    if s.empty:
        return None
    v = float(s.iloc[-1])
    return v if np.isfinite(v) and v > 0 else None


def _chain(cl, ticker: str, day: pd.Timestamp, cap_state: dict, dry: bool, lock=None):
    """Quote-marked chain for one ticker-day, cached. Returns None when skipped."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{ticker}_{day.date()}.parquet"
    if path.exists():
        return pd.read_parquet(path)

    start, end = _window(day)
    try:
        price = cl.metadata.get_cost(
            dataset=DATASET,
            symbols=[f"{ticker}.OPT"],
            stype_in="parent",
            schema=SCHEMA,
            start=start,
            end=end,
        )
    except Exception as exc:
        print(f"  [cost-err] {ticker} {day.date()}: {type(exc).__name__}")
        return None

    # Reserve against the cap before pulling. Under the thread pool this must be
    # atomic or two workers can both see headroom and jointly overshoot.
    ctx = lock if lock is not None else contextlib.nullcontext()
    with ctx:
        cap_state["estimated"] += price
        if cap_state["spent"] + price > cap_state["cap"]:
            raise RuntimeError(
                f"cap ${cap_state['cap']:.2f} would be exceeded "
                f"(spent ${cap_state['spent']:.4f}, next ${price:.4f}) - halting"
            )
        cap_state["spent"] += price
    if dry:
        return None

    try:
        data = cl.timeseries.get_range(
            dataset=DATASET,
            symbols=[f"{ticker}.OPT"],
            stype_in="parent",
            schema=SCHEMA,
            start=start,
            end=end,
        )
        df = data.to_df()
    except Exception as exc:
        print(f"  [pull-err] {ticker} {day.date()}: {type(exc).__name__}: {str(exc)[:90]}")
        return None

    df.to_parquet(path)
    return df


def _prefetch(cl, jobs: list[tuple[str, pd.Timestamp]], cap_state: dict, workers: int) -> None:
    """Pull every missing chain concurrently into the cache before scoring.

    Serial pulls ran at 3.0 chains/minute because each ``get_range`` round trip
    dominates; the work is IO-bound and parallelises cleanly. Cap accounting is
    lock-protected so a concurrent overshoot cannot slip past the reservation, and
    the pool stops submitting once the cap is reached.
    """
    todo = [(t, d) for t, d in jobs if not (CACHE / f"{t}_{d.date()}.parquet").exists()]
    if not todo:
        print("  all chains already cached")
        return
    print(f"  fetching {len(todo)} chains with {workers} workers...")

    lock = threading.Lock()
    done = {"n": 0, "halted": False}

    def one(job: tuple[str, pd.Timestamp]) -> None:
        tkr, day = job
        with lock:
            if done["halted"]:
                return
        try:
            _chain(cl, tkr, day, cap_state, dry=False, lock=lock)
        except RuntimeError as stop:
            with lock:
                if not done["halted"]:
                    done["halted"] = True
                    print(f"\n  {stop}")
            return
        with lock:
            done["n"] += 1
            if done["n"] % 25 == 0:
                print(f"    {done['n']}/{len(todo)} fetched  spent=${cap_state['spent']:.4f}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))
    print(f"  prefetch complete: {done['n']}/{len(todo)}  spent=${cap_state['spent']:.4f}")


def _parse_chain(df: pd.DataFrame) -> pd.DataFrame | None:
    """Explode a raw OPRA slice into strike/expiry/right/mid, last quote per contract."""
    if df is None or df.empty or "symbol" not in df.columns:
        return None
    d = df.copy()
    # OSI: root(6) + yymmdd(6) + C/P + strike(8, thousandths)
    sym = d["symbol"].astype(str).str.replace(" ", "", regex=False)
    body = sym.str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    d = d.dropna(subset=["strike", "expiry"])
    if d.empty:
        return None

    bid = pd.to_numeric(d.get("bid_px_00"), errors="coerce")
    ask = pd.to_numeric(d.get("ask_px_00"), errors="coerce")
    d["mid"] = (bid + ask) / 2.0
    d = d[(bid > 0) & (ask > 0) & d["mid"].notna()]
    if d.empty:
        return None
    return d.sort_values("ts_recv").groupby(["strike", "expiry", "right"], as_index=False).last()


def _legs(d: pd.DataFrame, strike: float, expiry: pd.Timestamp) -> float | None:
    """Straddle mid at one strike and expiry, or None if either leg is unquoted."""
    leg = d[(d["strike"] == strike) & (d["expiry"] == expiry)]
    call = leg[leg["right"] == "C"]["mid"]
    put = leg[leg["right"] == "P"]["mid"]
    if call.empty or put.empty:
        return None
    straddle = float(call.iloc[0] + put.iloc[0])
    return straddle if straddle > 0 else None


def _straddle(df: pd.DataFrame, spot: float) -> tuple[float, float, float, pd.Timestamp] | None:
    """ATM straddle mid, implied move, and the strike and expiry actually sold."""
    d = _parse_chain(df)
    if d is None or spot <= 0:
        return None
    expiry = d["expiry"].min()
    d = d[d["expiry"] == expiry]
    strikes = d["strike"].unique()
    if not len(strikes):
        return None
    k = float(strikes[np.argmin(np.abs(strikes - spot))])
    straddle = _legs(d, k, expiry)
    if straddle is None:
        return None
    return straddle, straddle / spot, k, expiry


def _mark(df: pd.DataFrame, strike: float, expiry: pd.Timestamp) -> float | None:
    """Mid of the *same* contract that was sold, priced off a later session's chain.

    A short straddle closed before expiry is bought back at intrinsic plus the premium
    still in the contract. Substituting intrinsic for this mark leaves that premium
    uncharged: on the 912-event canonical ledger it averages 55.1% of the entry credit
    and turns a mean return on margin of -0.1142 into +0.1928.
    """
    d = _parse_chain(df)
    if d is None:
        return None
    return _legs(d, strike, expiry)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2026-07-21")
    ap.add_argument("--end", default="2026-08-11")
    ap.add_argument("--cap", type=float, default=5.0, help="hard USD spend cap")
    ap.add_argument("--workers", type=int, default=6, help="concurrent chain fetches")
    ap.add_argument("--dry-run", action="store_true", help="price everything, pull nothing")
    args = ap.parse_args()

    print(f"=== backfill {args.start} .. {args.end}  (BACKTEST, not paper trading) ===")
    ev = _events(args.start, args.end)
    print(f"events in the broad universe: {len(ev)}")
    if ev.empty:
        raise SystemExit("no events resolved - refusing to write an empty ledger")

    rich: set[str] = set()
    if RICH_SEED.exists():
        seed = pd.read_csv(RICH_SEED)
        rich = set(seed.loc[seed["is_rich"].astype(bool), "ticker"].astype(str))
    print(f"richness seed: {len(rich)} rich names")

    print("fetching prices (one batched download)...")
    spots = _spot_table(sorted(ev["ticker"].astype(str).unique()), args.start, args.end)
    print(f"  price panel: {spots.shape[0]} sessions x {spots.shape[1]} names")

    cl = _client()
    cap_state = {"cap": args.cap, "spent": 0.0, "estimated": 0.0}
    rows, skips = [], []

    if not args.dry_run:
        print("prefetching chains...")
        # Both sessions, because the exit leg has to be marked rather than assumed.
        _prefetch(
            cl,
            [(str(e["ticker"]), pd.Timestamp(e["entry_date"])) for _, e in ev.iterrows()]
            + [(str(e["ticker"]), pd.Timestamp(e["exit_date"])) for _, e in ev.iterrows()],
            cap_state,
            args.workers,
        )

    for i, e in ev.iterrows():
        tkr = str(e["ticker"])
        entry_d = pd.Timestamp(e["entry_date"])
        exit_d = pd.Timestamp(e["exit_date"])

        # Both legs come from the same adjusted series, so a split between entry and
        # exit is already on one basis. That is the corporate-action guard: marking a
        # live entry snapshot against retroactively adjusted history is what booked a
        # 2-for-1 split as a 52% earnings move in the live radar.
        spot_in = _spot_at(spots, tkr, entry_d)
        spot_out = _spot_at(spots, tkr, exit_d)
        if spot_in is None or spot_out is None:
            skips.append("no spot")
            continue

        try:
            chain = _chain(cl, tkr, entry_d, cap_state, args.dry_run)
        except RuntimeError as stop:
            print(f"\n{stop}")
            break
        if chain is None:
            skips.append("no chain")
            continue

        st = _straddle(chain, spot_in)
        if st is None:
            skips.append("no ATM straddle")
            continue
        straddle, im, strike, expiry = st
        if im < 0.02:
            skips.append("implied move below floor")
            continue

        # Mark the close off the exit session's own chain. Without this the buy-back is
        # priced at intrinsic, which hands the book every dollar of remaining premium and
        # inverts the sign of the result.
        try:
            exit_chain = _chain(cl, tkr, exit_d, cap_state, args.dry_run)
        except RuntimeError as stop:
            print(f"\n{stop}")
            break
        if exit_chain is None:
            skips.append("no exit chain")
            continue
        straddle_out = _mark(exit_chain, strike, expiry)
        if straddle_out is None:
            skips.append("exit leg unquoted")
            continue

        rm = abs(spot_out / spot_in - 1.0)
        pnl_ps = straddle - straddle_out
        margin_ps = 0.20 * spot_in + straddle
        ret = pnl_ps / straddle
        rom = pnl_ps / margin_ps
        rows.append(
            {
                "ticker": tkr,
                "announce_date": e["announce_date"],
                "entry_date": e["entry_date"],
                "exit_date": e["exit_date"],
                "spot_entry": spot_in,
                "spot_exit": spot_out,
                "strike": strike,
                "expiry": expiry.date(),
                "straddle_entry": straddle,
                "straddle_exit": straddle_out,
                "implied_move": im,
                "realised_move": rm,
                "ret": ret,
                "net_ret": ret - COST,
                "ret_on_margin": rom,
                "net_ret_on_margin": (pnl_ps - COST * straddle) / margin_ps,
                # The retired estimator, kept only so the two stay comparable.
                "ret_intrinsic_proxy": 1.0 - rm / im,
                "in_rich_set": str(tkr in rich).lower(),
                # Provenance travels on the row, not on the directory it happens to sit
                # in. A file moved or concatenated loses its folder; these two columns
                # are what keeps a backtested row from being read as forward evidence,
                # and they match the live ledger's schema so the failure is visible
                # rather than structural. Every row here is quote-marked by
                # construction: an unquoted exit leg is skipped, never filled at
                # intrinsic.
                "mark_source": MARK_QUOTE,
                "source": BACKFILL,
            }
        )
        if (i + 1) % 25 == 0:
            print(
                f"  {i + 1}/{len(ev)} processed  booked={len(rows)}  "
                f"spent=${cap_state['spent']:.4f}"
            )

    print(f"\nestimated ${cap_state['estimated']:.4f}   actual ${cap_state['spent']:.4f}")
    if skips:
        print(
            "  skips: " + ", ".join(f"{k} x{v}" for k, v in pd.Series(skips).value_counts().items())
        )
    if args.dry_run:
        print("(dry-run: nothing pulled, nothing written)")
        return
    if not rows:
        raise SystemExit("no events scored - refusing to write an empty ledger")

    led = pd.DataFrame(rows)
    OUT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    led.to_csv(OUT_LEDGER, index=False)

    # Report both bases. Return on margin is the one the settled verdict is quoted in and
    # is therefore the only figure comparable to it; return on premium is carried because
    # the forward report uses it. The retired intrinsic proxy is reported alongside solely
    # so the size of the marking error stays visible.
    bases = [
        ("net_ret_on_margin", "return on margin, net of 11.6% of premium"),
        ("net_ret", "return on premium, net of 11.6% round trip"),
        ("ret_intrinsic_proxy", "RETIRED intrinsic-exit proxy, not a return"),
    ]
    out = []
    for lbl, book in [("all", led), ("rich", led[led["in_rich_set"] == "true"])]:
        if book.empty:
            continue
        for col, basis in bases:
            x = book[col].astype(float).to_numpy()
            s = x.std(ddof=1) if len(x) > 1 else np.nan
            se = s / np.sqrt(len(x)) if len(x) > 1 else np.nan
            out.append(
                {
                    "book": lbl,
                    "basis": f"BACKTEST per-trade {basis}",
                    "n": len(x),
                    "n_names": book["ticker"].nunique(),
                    "net_mean": x.mean(),
                    "hit": (x > 0).mean(),
                    "sd": s,
                    "per_trade_sharpe": x.mean() / s if s and np.isfinite(s) else np.nan,
                    "ci_lo": x.mean() - 1.96 * se if np.isfinite(se) else np.nan,
                    "ci_hi": x.mean() + 1.96 * se if np.isfinite(se) else np.nan,
                }
            )
    summ = pd.DataFrame(out)
    summ.to_csv(OUT_SUMMARY, index=False)
    print(f"\n{summ.to_string(index=False)}")
    print(f"\nwrote {OUT_LEDGER.resolve()}")
    print(f"wrote {OUT_SUMMARY.resolve()}")
    print(
        "\nThese are BACKTEST figures. Do not present them alongside the live book as one record."
    )


if __name__ == "__main__":
    main()
