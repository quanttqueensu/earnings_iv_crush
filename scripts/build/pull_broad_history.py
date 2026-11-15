"""
pull_broad_history.py
Capped Databento pull of 15:59 ET option chains for the broad-universe earnings events, 2013-2024.

Each event needs two chains (the entry and exit sessions), pulled in the same cached format as the
2025-2026 block (``data/cache/backfill_chains/{ticker}_{date}.parquet``, OPRA cbbo-1m, the 15:59
minute). Spend control is strict:

* every chain is priced with ``metadata.get_cost`` (free) before it is requested;
* an event's two chains are priced together and reserved against the cap under a lock; if the pair
  would cross the cap the pull stops, so the cache never holds half an event;
* events are processed in a seeded random order, so a pull that stops at the cap still leaves a
  sample spread evenly across years;
* the running estimated spend is printed, and the final line reports it.

Events with an unknown or intraday session are excluded (their entry would be mistimed).

Usage:
    python scripts/build/pull_broad_history.py --price-sample 400        # free cost estimate
    python scripts/build/pull_broad_history.py --pull --cap 40 --workers 4
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import earnings_iv_crush.research.chains as bf  # noqa: E402
from earnings_iv_crush.data.real_events import entry_exit_dates  # noqa: E402

CALENDAR = Path("outputs/research/calendar_broad_2013_2024.parquet")
SEED = 0


def jobs() -> pd.DataFrame:
    cal = pd.read_parquet(CALENDAR)
    n0 = len(cal)
    cal = cal[(cal["session_source"] == "ibes_time") & cal["session"].isin(["amc", "bmo"])]
    rows = []
    for _, r in cal.iterrows():
        e, x = entry_exit_dates(pd.Timestamp(r["announce_date"]), r["session"])
        rows.append(
            {"ticker": r["ticker"], "announce_date": r["announce_date"], "entry": e, "exit": x}
        )
    j = pd.DataFrame(rows).sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    print(f"  calendar {n0}, timed amc/bmo events {len(j)}", flush=True)
    return j


def _path(t: str, d: pd.Timestamp) -> Path:
    return bf.CACHE / f"{t}_{pd.Timestamp(d).date()}.parquet"


def _cost(cl, t: str, d: pd.Timestamp) -> float:
    s, e = bf._window(pd.Timestamp(d))
    return float(
        cl.metadata.get_cost(
            dataset=bf.DATASET,
            symbols=[f"{t}.OPT"],
            stype_in="parent",
            schema=bf.SCHEMA,
            start=s,
            end=e,
        )
    )


def price_sample(n: int) -> None:
    cl = bf._client()
    j = jobs()
    s = j.head(n)
    costs = []
    unresolved = 0
    for _, r in s.iterrows():
        for d in (r["entry"], r["exit"]):
            if not _path(r["ticker"], d).exists():
                try:
                    costs.append((pd.Timestamp(d).year, _cost(cl, r["ticker"], d)))
                except Exception:  # noqa: BLE001
                    unresolved += 1
    c = pd.DataFrame(costs, columns=["year", "cost"])
    todo = sum(
        (not _path(t, a).exists()) + (not _path(t, b).exists())
        for t, a, b in zip(j["ticker"], j["entry"], j["exit"], strict=True)
    )
    per = c["cost"].mean()
    print(f"  unresolved symbol-dates in sample: {unresolved}", flush=True)
    print(c.groupby("year")["cost"].agg(["mean", "count"]).round(5).to_string())
    print(
        f"  sampled {len(c)} chains: mean ${per:.5f}, p90 ${c['cost'].quantile(0.9):.5f}; "
        f"{todo} chains to pull -> estimated ${per * todo:.2f} "
        f"(90% bootstrap of the mean: "
        f"${np.quantile([c['cost'].sample(frac=1, replace=True, random_state=i).mean() for i in range(1000)], 0.05) * todo:.2f}"
        f" to ${np.quantile([c['cost'].sample(frac=1, replace=True, random_state=i).mean() for i in range(1000)], 0.95) * todo:.2f})",
        flush=True,
    )


def pull(cap: float, workers: int) -> None:
    cl = bf._client()
    j = jobs()
    bf.CACHE.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    st = {"spent": 0.0, "events": 0, "chains": 0, "fail": 0, "stop": False, "t0": time.time()}

    def one(r: pd.Series) -> None:
        if st["stop"]:
            return
        need = [d for d in (r["entry"], r["exit"]) if not _path(r["ticker"], d).exists()]
        if not need:
            return
        try:
            price = sum(_cost(cl, r["ticker"], d) for d in need)
        except Exception:  # noqa: BLE001
            with lock:
                st["fail"] += 1
            return
        with lock:
            if st["stop"] or st["spent"] + price > cap:
                st["stop"] = True
                return
            st["spent"] += price
        for d in need:
            s, e = bf._window(pd.Timestamp(d))
            try:
                df = cl.timeseries.get_range(
                    dataset=bf.DATASET,
                    symbols=[f"{r['ticker']}.OPT"],
                    stype_in="parent",
                    schema=bf.SCHEMA,
                    start=s,
                    end=e,
                ).to_df()
                df.to_parquet(_path(r["ticker"], d))
            except Exception:  # noqa: BLE001
                with lock:
                    st["fail"] += 1
                continue
            with lock:
                st["chains"] += 1
        with lock:
            st["events"] += 1
            if st["events"] % 250 == 0:
                print(
                    f"  {st['events']} events, {st['chains']} chains, spent ${st['spent']:.4f} "
                    f"of ${cap:.2f}, {st['fail']} failed, {time.time() - st['t0']:.0f}s",
                    flush=True,
                )

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, [r for _, r in j.iterrows()]))
    tag = "HALTED AT CAP" if st["stop"] else "PULL DONE"
    print(
        f"  {tag}: {st['events']} events, {st['chains']} chains, spent ${st['spent']:.4f} "
        f"(cap ${cap:.2f}), {st['fail']} failed",
        flush=True,
    )


BATCH = 50  # parent symbols per request, all for the same 15:59 minute


def pull_by_date(cap: float, workers: int) -> None:
    """Batched pull: one priced request per (date, up to BATCH tickers), cap enforced per request.

    Each batch is priced with ``get_cost`` and reserved against the cap under a lock before it is
    requested; a batch that would cross the cap stops the pull. Batches run in a seeded random
    order of dates, so a pull stopped at the cap is spread across years. The returned frame is split
    by underlying root into the per-ticker cache files; a requested ticker with no rows is written
    as an empty file so it is never requested again.
    """
    cl = bf._client()
    j = jobs()
    bf.CACHE.mkdir(parents=True, exist_ok=True)
    need: dict[pd.Timestamp, set[str]] = {}
    for t, a, b in zip(j["ticker"], j["entry"], j["exit"], strict=True):
        for d in (a, b):
            if not _path(t, d).exists():
                need.setdefault(pd.Timestamp(d).normalize(), set()).add(t)
    dates = sorted(need)
    rng = np.random.default_rng(SEED)
    rng.shuffle(dates)
    batches = []
    for d in dates:
        ts = sorted(need[d])
        batches += [(d, ts[i : i + BATCH]) for i in range(0, len(ts), BATCH)]
    print(
        f"  {sum(len(v) for v in need.values())} chains in {len(batches)} date batches", flush=True
    )
    lock = threading.Lock()
    st = {"spent": 0.0, "batches": 0, "chains": 0, "fail": 0, "stop": False, "t0": time.time()}

    def one(job: tuple[pd.Timestamp, list[str]]) -> None:
        d, ts = job
        if st["stop"]:
            return
        s, e = bf._window(d)
        kw = dict(dataset=bf.DATASET, stype_in="parent", schema=bf.SCHEMA, start=s, end=e)
        syms = [f"{t}.OPT" for t in ts]
        try:
            price = float(cl.metadata.get_cost(symbols=syms, **kw))
        except Exception:  # noqa: BLE001
            with lock:
                st["fail"] += 1
            return
        with lock:
            if st["stop"] or st["spent"] + price > cap:
                st["stop"] = True
                return
            st["spent"] += price
        try:
            df = cl.timeseries.get_range(symbols=syms, **kw).to_df()
        except Exception:  # noqa: BLE001
            with lock:
                st["fail"] += 1
            return
        root = (
            df["symbol"].astype(str).str[:6].str.strip()
            if not df.empty
            else pd.Series([], dtype=str)
        )
        for t in ts:
            sub = df[root == t] if not df.empty else df
            sub.to_parquet(_path(t, d))
        with lock:
            st["batches"] += 1
            st["chains"] += len(ts)
            if st["batches"] % 100 == 0:
                print(
                    f"  {st['batches']}/{len(batches)} batches, {st['chains']} chains, "
                    f"spent ${st['spent']:.4f} of ${cap:.2f}, {st['fail']} failed, "
                    f"{time.time() - st['t0']:.0f}s",
                    flush=True,
                )

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, batches))
    tag = "HALTED AT CAP" if st["stop"] else "PULL DONE"
    print(
        f"  {tag}: {st['batches']} batches, {st['chains']} chains, spent ${st['spent']:.4f} "
        f"(cap ${cap:.2f}), {st['fail']} failed",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--price-sample", type=int, default=0)
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--by-date", action="store_true")
    ap.add_argument("--cap", type=float, default=0.0)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.price_sample:
        price_sample(a.price_sample)
    if a.pull:
        if not 0 < a.cap <= 40.0:
            raise SystemExit("refusing to pull: --cap must be set and at most 40.00")
        (pull_by_date if a.by_date else pull)(a.cap, a.workers)


if __name__ == "__main__":
    main()
