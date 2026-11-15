"""fetch_free_data.py: download the free public inputs for lane N17 (no keys, no logins).

Sources (both on Cboe's public CDN, which publishes no robots.txt disallow for these paths)
-------------------------------------------------------------------------------------------
- Cboe volatility index daily history CSVs: OVX (USO options), GVZ (GLD options), VXSLV (SLV
  options), VXTLT (TLT options), VXGDX (GDX options), VIX (control).
- ETF daily OHLC (unadjusted) from Cboe's delayed-quote historical chart JSON, for USO, UNG, GLD,
  SLV, TLT, DBA, GDX, SPY. Splits and dividends are handled in the scorer, not here.

An earlier version pulled ETF prices from a Yahoo endpoint whose robots.txt disallows all agents;
those files were deleted on 2026-11-13 and are not used (see diagnosis.log).

Everything is written under ``raw/`` in this lane folder (a few MB). One request a second per host,
User-Agent ``research-client``.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N17-commodity-etf-options/fetch_free_data.py
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
HEADERS = {"User-Agent": "research-client"}
CBOE_IDX = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
CBOE_HIST = "https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/{sym}.json"
VOL_INDICES = ["OVX", "GVZ", "VXSLV", "VXTLT", "VXGDX", "VIX"]
ETFS = ["USO", "UNG", "GLD", "SLV", "TLT", "DBA", "GDX", "SPY"]


def _get(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=60)
    time.sleep(1.1)
    return r


def fetch_indices() -> None:
    for sym in VOL_INDICES:
        r = _get(CBOE_IDX.format(sym=sym))
        if r.status_code != 200:
            print(f"cboe index {sym}: HTTP {r.status_code}")
            continue
        df = pd.read_csv(io.StringIO(r.text))
        df.to_csv(RAW / f"cboe_{sym}.csv", index=False)
        print(f"cboe index {sym}: {len(df)} rows {df.iloc[0, 0]} .. {df.iloc[-1, 0]}")


def fetch_etfs() -> None:
    for sym in ETFS:
        r = _get(CBOE_HIST.format(sym=sym))
        if r.status_code != 200:
            print(f"cboe hist {sym}: HTTP {r.status_code}")
            continue
        df = pd.DataFrame(r.json()["data"])
        df.to_csv(RAW / f"cboehist_{sym}.csv", index=False)
        print(f"cboe hist {sym}: {len(df)} rows {df.date.min()} .. {df.date.max()}")


if __name__ == "__main__":
    RAW.mkdir(exist_ok=True)
    fetch_indices()
    fetch_etfs()
