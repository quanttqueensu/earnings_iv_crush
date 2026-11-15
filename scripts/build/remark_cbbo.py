"""
remark_cbbo.py
Re-mark every event's ATM straddle on consolidated 1-minute NBBO (``cbbo-1m``),
replacing the daily-bar last-trade marks the backtest currently runs on.

Why this exists. The book is marked from ``ohlcv-1d`` daily bars, whose close is the
last *trade* print of the session on the single highest-volume venue. Two defects
follow. The prints on the two legs are not synchronous, so the straddle mark is a
sum of two different moments; and an illiquid leg's last print can be hours stale,
which is how 20.1% of gated exit marks came to sit *below intrinsic value* - a
physically impossible price that let the short buy back cheaper than the market
would ever have allowed, concentrated in exactly the big-move events that carry the
tail. ``engine/marks.py`` repairs those violations after the fact. This script
removes the need for a repair by marking on quotes instead of prints.

``cbbo-1m`` is the consolidated best bid/offer, sampled once a minute, across all
OPRA venues. It runs from **2013-04-01**, which covers the whole 2019-2024 sample.
(The oft-cited "OPRA NBBO begins 2023-03-28" limit applies to ``cmbp-1`` and
``tcbbo``, not to ``cbbo-1m``; the entitlement already paid for covers it.)

Marks are taken from the last NBBO bar at or before the 16:00 US/Eastern close on
the entry and exit sessions, so both legs are read at the same timestamp. The mark
is the package mid; the package width (total dollar width over total mid) is
recorded alongside, which is the cost basis ``measure_spread`` now uses.

Two stages, the first free and always run:

1. **Estimate (free).** ``databento.metadata.get_cost`` is summed over every event.
   Nothing is pulled. The script prints the total and stops unless ``--pull`` is
   passed *and* the estimate clears ``CAP_USD``.
2. **Pull (metered, opt-in).** Fetches ``cbbo-1m`` for the two ATM legs across each
   event's entry-to-exit window into the disk cache, with a running spend printed,
   and writes the re-marked table.

Run the estimate:  ``python scripts/build/remark_cbbo.py``
Run the pull:      ``python scripts/build/remark_cbbo.py --pull``
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.research.market_marks import EVENTS_FULL, _prepare  # noqa: E402
from scripts.build.measure_spread import _legs_for  # noqa: E402

SCHEMA = "cbbo-1m"  # consolidated 1-minute NBBO; coverage from 2013-04-01
CAP_USD = 5.00  # hard ceiling: never pull if the estimate exceeds this
CLOSE = pd.Timedelta(hours=16)  # 16:00 US/Eastern regular-session close
OUT_DIR = Path("outputs/research")
CACHE = "{date}_cbbo1m.parquet"

# ``get_cost`` costs ~5.3s per call, so pricing all 1,020 events one at a time would
# burn ~90 minutes of metadata overhead and fetch nothing. It is also unnecessary:
# every two-leg event windows to exactly the same figure because these requests are
# far below Databento's minimum billing unit, so the cost does not scale with the
# name, the date, or the session. The estimator samples to *verify* that flatness
# (and aborts if it does not hold) rather than assuming it.
ESTIMATE_SAMPLE = 15
FLATNESS_TOL = 0.25  # abort if the sample's per-event cost varies by more than this


def _window(e: pd.Series) -> tuple[str, str]:
    """Date range covering the entry and exit sessions (end exclusive, +1 day)."""
    start = pd.Timestamp(e["entry_date"]).strftime("%Y-%m-%d")
    end = (pd.Timestamp(e["exit_date"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return start, end


def estimate(ev: pd.DataFrame, n: int = ESTIMATE_SAMPLE) -> tuple[float, float]:
    """Price a sample of events with Databento's free ``get_cost`` and extrapolate.

    Databento bills these windows at a flat rate **per leg** - they sit far below the
    minimum billing unit, so the figure does not scale with the name, the date or the
    session. The estimate is therefore ``per-leg rate x total legs``. Flatness is
    checked on the *per-leg* cost, not the per-event cost: an event whose chain
    resolves only one of the two ATM legs bills half, which is a leg-count difference
    and not a price difference, and normalising per event would read it as one.

    Returns ``(per_leg_cost, total)``. Raises if the per-leg cost is not flat to
    within ``FLATNESS_TOL``, since the extrapolation is only valid when it is.
    """
    per_leg: list[float] = []
    for _, e in ev.head(n).iterrows():
        legs = _legs_for(e)
        if not legs:
            continue
        start, end = _window(e)
        try:
            per_leg.append(dbo.get_cost(legs, start, end, schema=SCHEMA) / len(legs))
        except Exception as exc:
            print(f"  {e['ticker']:6s} {start}  cost lookup failed: {exc}")
    if not per_leg:
        raise RuntimeError("no events could be priced - cannot estimate, refusing to pull.")

    arr = np.asarray(per_leg, float)
    unit = float(np.median(arr))
    n_legs = int(sum(len(_legs_for(e) or []) for _, e in ev.iterrows()))

    # The guard is deliberately one-sided. Events that bill *below* the unit rate are
    # not a pricing anomaly - they are events whose second ATM leg does not resolve in
    # OPRA (BRK-B), so Databento charges for one leg where two were requested. Those
    # can only make the estimate conservative. Only cost coming in *above* the unit
    # rate can breach a budget, so only that aborts.
    upside = float(arr.max() - unit) / unit if unit > 0 else np.inf
    print(
        f"  sampled {len(arr)} events: ${unit:.6f}/leg  "
        f"(min ${arr.min():.6f}, max ${arr.max():.6f}, upside deviation {upside:.1%})"
    )
    print(f"  {n_legs} legs requested across {len(ev)} events")
    if upside > FLATNESS_TOL:
        raise RuntimeError(
            f"per-leg cost exceeds the unit rate by {upside:.1%} (> {FLATNESS_TOL:.0%}); "
            "extrapolation would understate the bill. Price every event before pulling."
        )
    return unit, unit * n_legs


def _close_quote(df: pd.DataFrame, symbol: str, day: pd.Timestamp) -> tuple[float, float]:
    """Dollar width and mid of the last NBBO bar at or before the close on ``day``.

    Both legs are read at the same cut-off, so the straddle mark is synchronous -
    the property the daily-bar close does not have.
    """
    sub = df[df["symbol"] == symbol]
    if sub.empty:
        return np.nan, np.nan
    ts = (
        pd.to_datetime(sub["ts_event"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    cutoff = day.normalize() + CLOSE
    sub = sub[(ts >= day.normalize()) & (ts <= cutoff)]
    if sub.empty:
        return np.nan, np.nan
    last = sub.iloc[-1]
    bid, ask = float(last["bid_px_00"]), float(last["ask_px_00"])
    mid = 0.5 * (bid + ask)
    if not (mid > 0) or ask < bid:
        return np.nan, np.nan
    return ask - bid, mid


def pull(ev: pd.DataFrame, unit_cost: float, budget: float) -> pd.DataFrame:
    """Fetch cbbo-1m for every event's ATM legs and re-mark entry/exit on the NBBO.

    Spend is tracked against the verified flat per-leg ``unit_cost`` and hard-stopped
    at ``budget``; ``get_cost`` is not re-called per event because it costs ~5.3s and
    would add ~90 minutes to the run without adding information.
    """
    rows: list[dict] = []
    spent, n_cached, n_fetched, n_failed = 0.0, 0, 0, 0
    t0 = time.time()

    for i, (_, e) in enumerate(ev.iterrows(), 1):
        legs = _legs_for(e)
        if legs is None:
            continue
        start, end = _window(e)
        cache = dbo._CACHE_ROOT / e["ticker"] / CACHE.format(date=start)
        if cache.exists():
            df = pd.read_parquet(cache)
            n_cached += 1
        else:
            cost = unit_cost * len(legs)  # unit_cost is per leg
            if spent + cost > budget:
                print(f"\nBUDGET STOP: ${spent:.4f} spent, cap ${budget:.2f}. Halting.")
                break
            try:
                df = dbo._get_df(SCHEMA, legs, start, end, "raw_symbol")
            except Exception as exc:
                n_failed += 1
                print(f"  {e['ticker']:6s} {start}  fetch failed: {exc}", flush=True)
                continue
            spent += cost
            n_fetched += 1
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache, index=False)
        if df.empty:
            continue
        df = df.reset_index()

        rec: dict = {"ticker": e["ticker"], "entry_date": e["entry_date"]}
        ok = True
        for side, day in (("entry", e["entry_date"]), ("exit", e["exit_date"])):
            q = [_close_quote(df, s, pd.Timestamp(day)) for s in legs]
            good = [(w, m) for w, m in q if np.isfinite(w) and np.isfinite(m) and m > 0]
            if len(good) != 2:  # both legs must resolve, or the straddle mark is not a straddle
                ok = False
                break
            tw, tm = sum(w for w, _ in good), sum(m for _, m in good)
            rec[f"{side}_mid"] = tm
            rec[f"{side}_width"] = tw
            rec[f"{side}_spread"] = tw / tm
        if ok:
            rows.append(rec)

        if i % 25 == 0:
            el = time.time() - t0
            eta = (el / i) * (len(ev) - i) / 60.0
            print(
                f"  [{i:4d}/{len(ev)}]  marked {len(rows):4d}  cached {n_cached:4d}  "
                f"fetched {n_fetched:4d}  failed {n_failed:3d}  "
                f"spent ${spent:.4f}  ETA {eta:.0f} min",
                flush=True,
            )

    print(
        f"\ntotal spend this run: ${spent:.4f}  "
        f"(cached {n_cached}, fetched {n_fetched}, failed {n_failed})"
    )
    if n_failed:
        print(f"WARNING: {n_failed} events failed to fetch and are absent from the re-marked set.")
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pull", action="store_true", help="fetch if the estimate clears the cap")
    ap.add_argument("--cap", type=float, default=CAP_USD, help="hard spend ceiling in USD")
    args = ap.parse_args()

    ev, _ = _prepare(EVENTS_FULL)
    print(f"--- cbbo-1m cost estimate over {len(ev)} events (2 ATM legs each) ---")
    unit, total = estimate(ev)
    print(f"\nestimated total: ${total:.4f} for {len(ev)} events   cap ${args.cap:.2f}")

    if not args.pull:
        print("\nestimate only. Re-run with --pull to fetch.")
        return
    if total > args.cap:
        print(f"\nestimate ${total:.4f} exceeds cap ${args.cap:.2f} - not pulling.")
        return

    print(f"\nestimate ${total:.4f} within cap - pulling cbbo-1m (~110 min)...\n")
    marks = pull(ev, unit_cost=unit, budget=args.cap)
    if marks.empty:
        print("no events re-marked.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "nbbo_marks.csv"
    marks.to_csv(out, index=False)
    print(f"\nre-marked {len(marks)} / {len(ev)} events on synchronous NBBO")
    for side in ("entry", "exit"):
        s = marks[f"{side}_spread"]
        print(
            f"  {side:5s} package width: median {s.median():.2%}  "
            f"mean {s.mean():.2%}  IQR [{s.quantile(.25):.2%}, {s.quantile(.75):.2%}]"
        )
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
