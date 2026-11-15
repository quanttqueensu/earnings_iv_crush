"""
pull.py
Lane I (entry day): cache the free DoltHub end-of-day chains for the sessions zero to ten before
each event's standard entry session, for the earlier-entry hedged-hold study.

DoltHub snapshots exist almost only on Mondays, Wednesdays and Fridays (inventory of the run-up
cache: 6,990 non-empty of 7,961 tried M/W/F dates against 118 of 3,828 Tue/Thu dates), so only
M/W/F sessions are requested; any cached Tue/Thu snapshot is still used downstream. Every call pins
an exact date (``lookback_days=0``), so a snapshot can never stand in for a different session.

Existing chains are read from ``data/cache/dolthub_runup`` (read only); new ones are written to this
lane's ``dolthub/`` folder.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/pull.py --set discovery
    python outputs/research/2026-11-13-alpha-hunt-2/laneI-entry-day/pull.py --set heldout
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402

RUNUP_CACHE = ROOT / "data" / "cache" / "dolthub_runup"
OWN_CACHE = HERE / "dolthub"
HOLD = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"
K_MAX = 10  # deepest entry offset in sessions, from the lane question
HORIZON_DAYS = 70  # same expiry window as the run-up cache, so cached and new chains match
FIRST_DATE = pd.Timestamp("2019-02-20")  # DoltHub coverage starts in February 2019
SPLIT_TICKER = "CHD"  # run-up cache covers A to CHD: discovery names <= CHD, held-out above
HELDOUT_N = 900  # sampled held-out events, seeded; sized for about 5,000 calls
SEED = 20261113
PULL_WEEKDAYS = (0, 2, 4)

NYSE = nyse_sessions(pd.Timestamp("2018-06-01"), pd.Timestamp("2025-03-31"))


def shift(day: pd.Timestamp, n: int) -> pd.Timestamp:
    """The NYSE session ``n`` sessions after ``day`` (negative for before)."""
    i = int(np.searchsorted(NYSE.values, np.datetime64(pd.Timestamp(day))))
    if NYSE[i] != pd.Timestamp(day):
        raise ValueError(f"{day} is not an NYSE session")
    return NYSE[i + n]


def events(which: str) -> pd.DataFrame:
    """Hedged-hold events with status ok in DoltHub coverage, for one name set."""
    h = pd.read_parquet(HOLD)
    h["entry_date"] = pd.to_datetime(h["entry_date"])
    n0 = len(h)
    h = h[h["status"] == "ok"]
    n1 = len(h)
    h = h[h["entry_date"] >= FIRST_DATE]
    n2 = len(h)
    if which == "discovery":
        h = h[h["ticker"] <= SPLIT_TICKER]
    else:
        h = h[h["ticker"] > SPLIT_TICKER]
        h = h.sample(n=min(HELDOUT_N, len(h)), random_state=SEED)
    print(f"  funnel {which}: all {n0} -> ok {n1} -> in DoltHub span {n2} -> set {len(h)}")
    return h.sort_values(["entry_date", "ticker"]).reset_index(drop=True)


def cached(ticker: str, day: pd.Timestamp) -> Path | None:
    for d in (RUNUP_CACHE, OWN_CACHE):
        p = d / f"{ticker}_{day.date()}.parquet"
        if p.exists():
            return p
    return None


def targets(ev: pd.DataFrame) -> list[tuple[str, pd.Timestamp]]:
    out = set()
    for _, r in ev.iterrows():
        for k in range(K_MAX + 1):
            d = shift(r["entry_date"], -k)
            if d.dayofweek in PULL_WEEKDAYS and cached(r["ticker"], d) is None:
                out.add((r["ticker"], d))
    return sorted(out)


def pull(which: str, workers: int) -> None:
    from earnings_iv_crush.data.dolthub_options import fetch_option_chain

    OWN_CACHE.mkdir(exist_ok=True)
    ev = events(which)
    ev[["ticker", "entry_date"]].to_csv(HERE / f"events_{which}.csv", index=False)
    todo = targets(ev)
    print(f"  {len(todo)} chains to fetch", flush=True)
    st = {"n": 0, "fail": 0, "empty": 0, "t0": time.time()}
    lock = threading.Lock()

    def one(job: tuple[str, pd.Timestamp]) -> None:
        t, d = job
        try:
            ch = fetch_option_chain(t, str(d.date()), horizon_days=HORIZON_DAYS, lookback_days=0)
            ch.to_parquet(OWN_CACHE / f"{t}_{d.date()}.parquet")
            empty = ch.empty
        except Exception as exc:  # noqa: BLE001  counted and printed, never swallowed silently
            with lock:
                st["fail"] += 1
                if st["fail"] <= 10:
                    print(f"  FAIL {t} {d.date()}: {exc}", flush=True)
            empty = False
        with lock:
            st["n"] += 1
            st["empty"] += int(empty)
            if st["n"] % 250 == 0:
                print(
                    f"  {st['n']}/{len(todo)} fail={st['fail']} empty={st['empty']} "
                    f"{time.time() - st['t0']:.0f}s",
                    flush=True,
                )

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    print(f"PULL DONE {which} n={len(todo)} fail={st['fail']} empty={st['empty']}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Cache DoltHub chains for lane I")
    ap.add_argument("--set", choices=["discovery", "heldout"], required=True)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    pull(a.set, a.workers)


if __name__ == "__main__":
    main()
