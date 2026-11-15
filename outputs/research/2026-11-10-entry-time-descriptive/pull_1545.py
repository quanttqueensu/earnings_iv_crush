"""
pull_1545.py
Capped Databento pull of the 15:45 ET option chain on the entry day of every hedged-hold event
with an entry date in 2013-2024. Data only: no outcome is computed here.

Each request is one (date, up to 50 tickers) batch of OPRA cbbo-1m for the 15:45 minute, priced
with the free ``metadata.get_cost`` and reserved against the cap under a lock before it is sent.
Chains land in ``data/cache/entry_1545_chains/{ticker}_{date}.parquet`` (gitignored).

Usage
-----
    python outputs/research/2026-11-10-entry-time-descriptive/pull_1545.py --cap 15
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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import earnings_iv_crush.research.chains as bf  # noqa: E402

LEDGER = ROOT / "outputs/research/2026-11-10-nonprice-selectors-hedged-hold/events.parquet"
CACHE = ROOT / "data/cache/entry_1545_chains"
MINUTE = "15:45"
BATCH = 50
MAX_CAP = 15.0
SEED = 0


def _window(day: pd.Timestamp) -> tuple[str, str]:
    s = pd.Timestamp(f"{day.date()} {MINUTE}").tz_localize(bf.EXCHANGE_TZ).tz_convert("UTC")
    return s.isoformat(), (s + pd.Timedelta(minutes=1)).isoformat()


def _path(t: str, d: pd.Timestamp) -> Path:
    return CACHE / f"{t}_{pd.Timestamp(d).date()}.parquet"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--cap", type=float, required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if not 0 < a.cap <= MAX_CAP:
        raise SystemExit(f"refusing to pull: --cap must be in (0, {MAX_CAP}]")
    ev = pd.read_parquet(LEDGER, columns=["ticker", "entry_date", "status"])
    ev["entry_date"] = pd.to_datetime(ev["entry_date"]).dt.normalize()
    n0 = len(ev)
    ev = ev[(ev["status"] == "ok") & (ev["entry_date"].dt.year <= 2024)]
    ev = ev.drop_duplicates(["ticker", "entry_date"])
    print(f"funnel: ledger {n0}, ok with entry in 2013-24 {len(ev)}", flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    need: dict[pd.Timestamp, list[str]] = {}
    for t, d in zip(ev["ticker"], ev["entry_date"], strict=True):
        if not _path(t, d).exists():
            need.setdefault(d, []).append(str(t))
    dates = sorted(need)
    np.random.default_rng(SEED).shuffle(dates)
    batches = [(d, sorted(need[d])[i : i + BATCH]) for d in dates for i in range(0, len(need[d]), BATCH)]
    print(f"  {sum(len(v) for v in need.values())} chains in {len(batches)} batches", flush=True)
    cl = bf._client()
    lock = threading.Lock()
    st = {"spent": 0.0, "batches": 0, "chains": 0, "fail": 0, "stop": False, "t0": time.time()}

    def one(job: tuple[pd.Timestamp, list[str]]) -> None:
        d, ts = job
        if st["stop"]:
            return
        s, e = _window(d)
        kw = dict(dataset=bf.DATASET, stype_in="parent", schema=bf.SCHEMA, start=s, end=e)
        syms = [f"{t}.OPT" for t in ts]
        try:
            price = float(cl.metadata.get_cost(symbols=syms, **kw))
        except Exception as exc:  # noqa: BLE001
            with lock:
                st["fail"] += 1
                if st["fail"] <= 5:
                    print(f"  [cost-err] {d.date()} {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            return
        with lock:
            if st["stop"] or st["spent"] + price > a.cap:
                st["stop"] = True
                return
            st["spent"] += price
        try:
            df = cl.timeseries.get_range(symbols=syms, **kw).to_df()
        except Exception as exc:  # noqa: BLE001
            with lock:
                st["fail"] += 1
                if st["fail"] <= 5:
                    print(f"  [pull-err] {d.date()} {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            return
        root = df["symbol"].astype(str).str[:6].str.strip() if not df.empty else None
        for t in ts:
            (df[root == t] if root is not None else df).to_parquet(_path(t, d))
        with lock:
            st["batches"] += 1
            st["chains"] += len(ts)
            if st["batches"] % 200 == 0:
                print(
                    f"  {st['batches']}/{len(batches)} batches, {st['chains']} chains, spent "
                    f"${st['spent']:.4f} of ${a.cap:.2f}, {st['fail']} failed, "
                    f"{time.time() - st['t0']:.0f}s",
                    flush=True,
                )

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, batches))
    tag = "HALTED AT CAP" if st["stop"] else "PULL DONE"
    files = list(CACHE.glob("*.parquet"))
    empty = sum(f.stat().st_size < 4000 and pd.read_parquet(f).empty for f in files)
    print(
        f"  {tag}: {st['batches']} batches, {st['chains']} chains, estimated spend "
        f"${st['spent']:.4f} (cap ${a.cap:.2f}), {st['fail']} failed batches; "
        f"cache holds {len(files)} files, {empty} empty",
        flush=True,
    )


if __name__ == "__main__":
    main()
