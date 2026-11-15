"""
pull_index_chains.py
Capped Databento pull of near-the-money, near-dated option quotes for index ETFs (SPY, QQQ, IWM)
at two daily snapshots, 15:59 ET and 10:00 ET, on every NYSE session in a date range.

This builder may spend money. Spend control:

* each (ticker, session, snapshot) request names its contracts explicitly (OCC raw symbols), so
  only the short-dated, near-the-money strip is billed rather than the whole chain;
* every request is priced with ``metadata.get_cost`` (free) and reserved against ``--cap`` under
  a lock before it is sent; the first request that would cross the cap halts the pull;
* without ``--pull`` nothing is requested: the run prices a seeded sample of sessions and prints
  the projected total.

Contract set for session t: every weekday expiry in (t, t + EXPIRY_HORIZON_DAYS] calendar days
(unlisted expiries resolve to nothing and are not billed) crossed with every whole-dollar strike
within STRIKE_BAND of the session's reference price, both calls and puts. The reference price is
the union of the previous and the same-session closing prices (yfinance, unadjusted), used only
to place the request grid; no rule that selects a trade reads it.

Cache: ``data/cache/index_chains/{TICKER}_{YYYY-MM-DD}_{HHMM}.parquet`` (cbbo-1m rows for the
one-minute window). An empty response is cached as a zero-row file so it is not re-billed, and is
counted in the final funnel.

Usage:
    python scripts/build/pull_index_chains.py --price-sample 60          # free estimate
    python scripts/build/pull_index_chains.py --pull --cap 25 --workers 6
"""

from __future__ import annotations

import argparse
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import earnings_iv_crush.research.chains as bf  # noqa: E402
from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402

# ── request design ──────────────────────────────────────────────────────────

TICKERS = ("SPY", "QQQ", "IWM")
SNAPSHOTS = ("15:59", "10:00")  # the book's close mark, and a morning mark for the overnight split
START, END = "2016-01-04", "2026-10-30"  # daily-ish expiries for all three tickers from 2016
EXPIRY_HORIZON_DAYS = 10  # covers the shortest expiry strictly after the next session, any weekday
STRIKE_BAND = 0.05  # +-5% of the reference price: a one-session move beyond this is rare
SEED = 0
CACHE = ROOT / "data" / "cache" / "index_chains"
LEDGER = CACHE / "_cost_ledger.csv"  # one row per billed request, so the cap holds across restarts


def _occ(root: str, expiry: pd.Timestamp, cp: str, strike: float) -> str:
    """OCC 21-character option symbol, as OPRA raw symbology expects."""
    return f"{root:<6}{expiry:%y%m%d}{cp}{int(round(strike * 1000)):08d}"


def _window(day: pd.Timestamp, hhmm: str) -> tuple[str, str]:
    s = pd.Timestamp(f"{day.date()} {hhmm}").tz_localize(bf.EXCHANGE_TZ).tz_convert("UTC")
    return s.isoformat(), (s + pd.Timedelta(minutes=1)).isoformat()


def _closes() -> pd.DataFrame:
    import yfinance as yf

    px = yf.download(
        list(TICKERS),
        start="2015-12-01",
        end=str(pd.Timestamp(END) + pd.Timedelta(days=3))[:10],
        auto_adjust=False,
        progress=False,
    )["Close"]
    px.index = pd.to_datetime(px.index).tz_localize(None)
    missing = [t for t in TICKERS if t not in px.columns or px[t].isna().all()]
    if missing:
        raise RuntimeError(f"no closes for {missing}; refusing to build a request grid blind")
    return px


def _symbols(t: str, day: pd.Timestamp, ref_lo: float, ref_hi: float) -> list[str]:
    exps = pd.bdate_range(day + pd.Timedelta(days=1), day + pd.Timedelta(days=EXPIRY_HORIZON_DAYS))
    k_lo = int(np.floor(ref_lo * (1 - STRIKE_BAND)))
    k_hi = int(np.ceil(ref_hi * (1 + STRIKE_BAND)))
    return [_occ(t, x, cp, k) for x in exps for cp in "CP" for k in range(k_lo, k_hi + 1)]


def jobs() -> list[tuple[str, pd.Timestamp, str, list[str]]]:
    px = _closes()
    days = nyse_sessions(pd.Timestamp(START), pd.Timestamp(END))
    out = []
    n_noref = 0
    for d in days:
        for t in TICKERS:
            prev = px[t].loc[: d - pd.Timedelta(days=1)].dropna()
            same = px[t].loc[d:d].dropna()
            refs = [float(prev.iloc[-1])] if len(prev) else []
            refs += [float(same.iloc[0])] if len(same) else []
            if not refs:
                n_noref += 1
                continue
            syms = _symbols(t, d, min(refs), max(refs))
            if len(syms) > 2000:
                raise RuntimeError(f"{t} {d.date()}: {len(syms)} symbols exceeds the 2,000 limit")
            for hhmm in SNAPSHOTS:
                out.append((t, d, hhmm, syms))
    print(f"  sessions {len(days)}, ticker-sessions without a reference close {n_noref}")
    print(f"  requests {len(out)} ({len(TICKERS)} tickers x {len(SNAPSHOTS)} snapshots)")
    return out


def _path(t: str, d: pd.Timestamp, hhmm: str) -> Path:
    return CACHE / f"{t}_{d.date()}_{hhmm.replace(':', '')}.parquet"


def _cost(cl, syms: list[str], s: str, e: str) -> float:
    return float(
        cl.metadata.get_cost(
            dataset=bf.DATASET,
            symbols=syms,
            stype_in="raw_symbol",
            schema=bf.SCHEMA,
            start=s,
            end=e,
        )
    )


def price_sample(n: int) -> None:
    cl = bf._client()
    js = jobs()
    rng = np.random.default_rng(SEED)
    idx = rng.choice(len(js), size=min(n, len(js)), replace=False)
    costs = []
    for i in idx:
        t, d, hhmm, syms = js[i]
        s, e = _window(d, hhmm)
        c = _cost(cl, syms, s, e)
        costs.append((t, d.year, hhmm, len(syms), c))
    df = pd.DataFrame(costs, columns=["t", "year", "snap", "n_sym", "cost"])
    print(df.groupby(["t", "snap"])["cost"].agg(["mean", "max", "count"]).round(5).to_string())
    proj = df.groupby(["t", "snap"])["cost"].mean() * (len(js) / (len(TICKERS) * len(SNAPSHOTS)))
    print(f"  projected total USD {proj.sum():.2f} over {len(js)} requests (sample n={len(df)})")


def _prior_spend(reserve: float) -> float:
    """Spend already committed: the ledger's rows plus a reserve for runs that predate it."""
    led = float(pd.read_csv(LEDGER)["cost"].sum()) if LEDGER.exists() else 0.0
    return led + reserve


def pull(cap: float, workers: int, reserve: float) -> None:
    cl = bf._client()
    CACHE.mkdir(parents=True, exist_ok=True)
    js = [j for j in jobs() if not _path(j[0], j[1], j[2]).exists()]
    prior = _prior_spend(reserve)
    print(
        f"  to fetch {len(js)} (rest cached); committed before this run USD {prior:.4f}", flush=True
    )
    if not LEDGER.exists():
        LEDGER.write_text("ticker,date,snap,cost" + chr(10), encoding="utf-8")
    state = {"spent": prior, "n": 0, "empty": 0, "err": 0, "halt": False}
    lock = threading.Lock()

    def one(job: tuple[str, pd.Timestamp, str, list[str]]) -> None:
        t, d, hhmm, syms = job
        if state["halt"]:
            return
        s, e = _window(d, hhmm)
        try:
            c = _cost(cl, syms, s, e)
        except Exception as exc:
            with lock:
                state["err"] += 1
            print(f"  [cost-err] {t} {d.date()} {hhmm}: {type(exc).__name__}", flush=True)
            return
        with lock:
            if state["spent"] + c > cap:
                state["halt"] = True
                print(f"  HALT: cap USD {cap:.2f} reached (spent {state['spent']:.4f})", flush=True)
                return
            state["spent"] += c
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(f"{t},{d.date()},{hhmm},{c:.8f}" + chr(10))
        try:
            df = (
                cl.timeseries.get_range(
                    dataset=bf.DATASET,
                    symbols=syms,
                    stype_in="raw_symbol",
                    schema=bf.SCHEMA,
                    start=s,
                    end=e,
                )
                .to_df()
                .reset_index()
            )
        except Exception as exc:
            msg = str(exc)
            if "symbology_invalid_request" in msg or "None of the symbols" in msg:
                df = pd.DataFrame()
            else:
                with lock:
                    state["err"] += 1
                print(f"  [pull-err] {t} {d.date()} {hhmm}: {msg[:100]}", flush=True)
                return
        keep = [
            c for c in ("ts_recv", "symbol", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00")
        ]
        df = df[[c for c in keep if c in df.columns]] if len(df) else pd.DataFrame(columns=keep)
        df.to_parquet(_path(t, d, hhmm))
        with lock:
            state["n"] += 1
            state["empty"] += int(len(df) == 0)
            if state["n"] % 250 == 0:
                print(
                    f"  progress {state['n']}/{len(js)} spent USD {state['spent']:.3f} "
                    f"empty {state['empty']} err {state['err']}",
                    flush=True,
                )

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, js))
    print(
        f"  DONE fetched {state['n']} empty {state['empty']} errors {state['err']} "
        f"halted {state['halt']} estimated spend USD {state['spent']:.4f}",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--price-sample", type=int, default=0)
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--cap", type=float, default=0.0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument(
        "--reserve",
        type=float,
        default=0.0,
        help="USD committed by runs that predate the cost ledger, counted against --cap",
    )
    a = ap.parse_args()
    if a.pull:
        if a.cap <= 0:
            raise SystemExit("--pull needs a positive --cap")
        pull(a.cap, a.workers, a.reserve)
    else:
        price_sample(a.price_sample or 60)


if __name__ == "__main__":
    main()
