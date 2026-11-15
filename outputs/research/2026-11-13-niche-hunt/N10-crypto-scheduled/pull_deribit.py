"""
pull_deribit.py
Pull free Deribit public market data for lane N10: option trade windows before each entry time,
daily delivery prices, and the DVOL index. No key, at most one request a second.

Trade windows are cached as ``cache/<CCY>_trades_<YYYYmmddTHHMM>.parquet`` (window end = entry
time). Rebuild by rerunning; the cache is skipped where a file already exists.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/pull_deribit.py --pilot b
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/pull_deribit.py --pilot a
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/pull_deribit.py --delivery
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/pull_deribit.py --dvol
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
HIST = "https://history.deribit.com/api/v2/public"
LIVE = "https://www.deribit.com/api/v2/public"
UA = {"User-Agent": "research-client"}
MIN_INTERVAL_S = 1.0  # brief: at most one request a second per host
WINDOW = pd.Timedelta(hours=4)
_last: dict[str, float] = {}


# ── events ───────────────────────────────────────────────────────────────────

PILOT_B_START = pd.Timestamp("2020-01-01", tz="UTC")
PILOT_B_END = pd.Timestamp("2026-10-31", tz="UTC")
ENTRY_HOUR_B = 9  # Thursday 09:00 UTC, one hour after the Thursday daily expiry

# (name, currency, release time UTC); fixed in diagnosis.log before any outcome
CATALYSTS: list[tuple[str, str, str]] = [
    ("halving3", "BTC", "2020-05-11 19:23:43"),
    ("taproot", "BTC", "2021-11-14 05:15:27"),
    ("btc_spot_etf", "BTC", "2024-01-10 21:00:00"),
    ("halving4", "BTC", "2024-04-20 00:09:27"),
    ("berlin", "ETH", "2021-04-15 10:07:03"),
    ("london", "ETH", "2021-08-05 12:33:42"),
    ("altair", "ETH", "2021-10-27 10:56:23"),
    ("bellatrix", "ETH", "2022-09-06 11:34:47"),
    ("merge", "ETH", "2022-09-15 06:42:42"),
    ("shapella", "ETH", "2023-04-12 22:27:35"),
    ("dencun", "ETH", "2024-03-13 13:55:35"),
    ("eth_etf_19b4", "ETH", "2024-05-23 21:00:00"),
    ("pectra", "ETH", "2025-05-07 10:05:11"),
    ("fusaka", "ETH", "2025-12-03 21:49:11"),
]
CATALYST_LEAD = pd.Timedelta(hours=2)
CONTROL_WEEKS_A = (1, 2)


def pilot_b_entries() -> list[pd.Timestamp]:
    thursdays = pd.date_range(PILOT_B_START, PILOT_B_END, freq="W-THU")
    return [t + pd.Timedelta(hours=ENTRY_HOUR_B) for t in thursdays]


def pilot_a_entries() -> list[tuple[str, pd.Timestamp]]:
    out = []
    for _, ccy, t in CATALYSTS:
        e = pd.Timestamp(t, tz="UTC") - CATALYST_LEAD
        out.append((ccy, e))
        for w in CONTROL_WEEKS_A:
            out.append((ccy, e - pd.Timedelta(weeks=w)))
    return out


# ── http ─────────────────────────────────────────────────────────────────────


def _get(base: str, path: str, **params: object) -> dict:
    host = base.split("/")[2]
    for attempt in range(6):
        wait = MIN_INTERVAL_S - (time.monotonic() - _last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.monotonic()
        try:
            r = requests.get(f"{base}/{path}", params=params, headers=UA, timeout=60)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()["result"]
        except requests.RequestException as exc:
            print(f"  retry {attempt + 1}: {exc}", flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Deribit request failed repeatedly: {path} {params}")


# ── pulls ────────────────────────────────────────────────────────────────────


def trades_window(ccy: str, end: pd.Timestamp) -> pd.DataFrame:
    """All option trades on ``ccy`` in [end - WINDOW, end], cached by window end."""
    f = CACHE / f"{ccy}_trades_{end:%Y%m%dT%H%M}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    lo, hi = int((end - WINDOW).timestamp() * 1000), int(end.timestamp() * 1000)
    out: list[dict] = []
    start = lo
    while True:
        r = _get(
            HIST,
            "get_last_trades_by_currency_and_time",
            currency=ccy,
            kind="option",
            start_timestamp=start,
            end_timestamp=hi,
            count=1000,
            sorting="asc",
        )
        tr = r.get("trades", [])
        out += tr
        if not r.get("has_more") or not tr:
            break
        start = tr[-1]["timestamp"] + 1
    df = pd.DataFrame(out).drop_duplicates("trade_id") if out else pd.DataFrame()
    keep = [
        c
        for c in (
            "timestamp",
            "trade_id",
            "price",
            "mark_price",
            "iv",
            "instrument_name",
            "index_price",
            "direction",
            "amount",
            "block_trade_id",
        )
        if c in df.columns
    ]
    df = df[keep] if len(df) else df
    df.to_parquet(f)
    return df


def delivery(index_name: str) -> Path:
    f = CACHE / f"delivery_{index_name}.json"
    rows: list[dict] = []
    off = 0
    while True:
        r = _get(LIVE, "get_delivery_prices", index_name=index_name, offset=off, count=1000)
        rows += r["data"]
        off += len(r["data"])  # the API caps a page at 100 regardless of count
        if not r["data"] or off >= r["records_total"]:
            break
    f.write_text(json.dumps(rows))
    print(f"  {index_name}: {len(rows)} delivery prices", flush=True)
    return f


def dvol(ccy: str) -> Path:
    """Hourly DVOL (Deribit 30-day implied volatility index) from 2021-03 to now."""
    f = CACHE / f"dvol_{ccy}_1h.parquet"
    start = pd.Timestamp("2021-03-01", tz="UTC")
    end = pd.Timestamp.now(tz="UTC")
    rows: list[list[float]] = []
    t = start
    step = pd.Timedelta(hours=999)
    while t < end:
        hi = min(t + step, end)
        r = _get(
            LIVE,
            "get_volatility_index_data",
            currency=ccy,
            start_timestamp=int(t.timestamp() * 1000),
            end_timestamp=int(hi.timestamp() * 1000),
            resolution="3600",
        )
        rows += r.get("data", [])
        t = hi
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"]).drop_duplicates("ts")
    df.to_parquet(f)
    print(f"  DVOL {ccy}: {len(df)} hours", flush=True)
    return f


def main() -> None:
    ap = argparse.ArgumentParser(description="Deribit public pulls for lane N10")
    ap.add_argument("--pilot", choices=["a", "b"])
    ap.add_argument("--delivery", action="store_true")
    ap.add_argument("--dvol", action="store_true")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    if args.pilot == "b":
        ents = pilot_b_entries()
        print(f"  pilot B: {len(ents)} Thursday windows", flush=True)
        for i, e in enumerate(ents, 1):
            trades_window("BTC", e)
            if i % 25 == 0 or i == len(ents):
                print(f"  {i}/{len(ents)} windows", flush=True)
    if args.pilot == "a":
        ents_a = pilot_a_entries()
        print(f"  pilot A: {len(ents_a)} windows", flush=True)
        for ccy, e in ents_a:
            trades_window(ccy, e)
        print(f"  {len(ents_a)}/{len(ents_a)} windows", flush=True)
    if args.delivery:
        delivery("btc_usd")
        delivery("eth_usd")
    if args.dvol:
        dvol("BTC")
        dvol("ETH")
    print("  PULL DONE", flush=True)


if __name__ == "__main__":
    main()
