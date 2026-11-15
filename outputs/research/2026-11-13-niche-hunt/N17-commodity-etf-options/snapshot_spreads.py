"""snapshot_spreads.py: one public delayed-quote snapshot of commodity and rates ETF option chains.

Pulls Cboe's public delayed-quote JSON (no key, about fifteen minutes delayed, consolidated NBBO as
published by Cboe) and saves, per ETF, the near-the-money calls and puts for every expiry within
45 days, with bid, ask, implied vol and the quote timestamp. Delayed quotes are not fills; they
measure the width of the quoted touch at that moment, which is all this file is used for.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N17-commodity-etf-options/snapshot_spreads.py TAG
    python .../snapshot_spreads.py TAG CORN,WEAT,SOYB   # any ticker list
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / "raw" / "spreads"
HEADERS = {"User-Agent": "research-client"}
URL = "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{sym}.json"
ETFS = ["USO", "UNG", "GLD", "SLV", "TLT", "DBA", "GDX", "SPY", "XLE", "IAU"]
_OCC = re.compile(r"^(?P<root>[A-Z]+)(?P<exp>\d{6})(?P<cp>[CP])(?P<k>\d{8})$")
MAX_DAYS = 45
MONEYNESS = 0.06  # keep strikes within 6% of spot, enough for ATM straddles and 25-delta wings


def snap(sym: str) -> pd.DataFrame:
    r = requests.get(URL.format(sym=sym), headers=HEADERS, timeout=60)
    time.sleep(1.1)
    r.raise_for_status()
    body = r.json()
    data = body["data"]
    spot = float(data["current_price"])
    rows = []
    for o in data["options"]:
        m = _OCC.match(o["option"])
        if m is None:
            continue
        exp = pd.Timestamp("20" + m["exp"])
        k = int(m["k"]) / 1000.0
        rows.append(
            {
                "sym": sym, "spot": spot, "quote_ts": body.get("timestamp"),
                "expiry": exp, "right": m["cp"], "strike": k,
                "bid": o.get("bid"), "ask": o.get("ask"), "iv": o.get("iv"),
                "volume": o.get("volume"), "oi": o.get("open_interest"),
                "bid_size": o.get("bid_size"), "ask_size": o.get("ask_size"),
            }
        )
    df = pd.DataFrame(rows)
    now = pd.Timestamp.now().normalize()
    keep = (df.expiry - now).dt.days.between(0, MAX_DAYS) & ((df.strike / spot - 1).abs() <= MONEYNESS)
    print(f"{sym}: spot {spot}, {len(df)} contracts, kept {int(keep.sum())}, ts {body.get('timestamp')}")
    if not keep.any():
        raise RuntimeError(f"{sym}: no contracts kept")
    return df[keep]


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.now().strftime("%Y%m%d_%H%M")
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    tickers = sys.argv[2].split(",") if len(sys.argv) > 2 else ETFS
    for s in tickers:
        try:
            frames.append(snap(s))
        except Exception as exc:  # report and continue: one missing ETF must not hide the others
            print(f"{s}: FAILED {exc!r}")
    pd.concat(frames).to_csv(OUT / f"snap_{tag}.csv", index=False)
