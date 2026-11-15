"""s00_snap_touch.py: public delayed-quote snapshot of GLD and SLV option touches.

Pulls Cboe's public delayed-quote JSON (no key; quotes about fifteen minutes delayed) for GLD and
SLV, keeps every expiry within 45 calendar days and strikes within 6% of spot, and writes one CSV
per run. Delayed quotes are not fills: the file measures how wide the quoted touch is, which is
the only use made of it (the half-spread as a share of straddle premium by days to expiry).

Usage:
    python outputs/research/2026-11-13-niche-hunt/N12-metals-macro/scripts/s00_snap_touch.py TAG
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "raw" / "touch"
HEADERS = {"User-Agent": "research-client"}
URL = "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{sym}.json"
SYMS = ("GLD", "SLV")
_OCC = re.compile(r"^(?P<root>[A-Z]+)(?P<exp>\d{6})(?P<cp>[CP])(?P<k>\d{8})$")
MAX_DAYS = 45  # event straddles use the shortest expiry after the release; 45 days covers controls
MONEYNESS = 0.06  # ATM straddle strikes only


def snap(sym: str) -> pd.DataFrame:
    r = requests.get(URL.format(sym=sym), headers=HEADERS, timeout=60)
    time.sleep(1.2)  # at most one request a second per host
    r.raise_for_status()
    body = r.json()
    data = body["data"]
    spot = float(data["current_price"])
    rows = []
    for o in data["options"]:
        m = _OCC.match(o["option"])
        if m is None:
            continue
        rows.append(
            {
                "sym": sym,
                "spot": spot,
                "quote_ts": body.get("timestamp"),
                "expiry": pd.Timestamp("20" + m["exp"]),
                "right": m["cp"],
                "strike": int(m["k"]) / 1000.0,
                "bid": o.get("bid"),
                "ask": o.get("ask"),
                "iv": o.get("iv"),
                "volume": o.get("volume"),
                "oi": o.get("open_interest"),
                "bid_size": o.get("bid_size"),
                "ask_size": o.get("ask_size"),
            }
        )
    df = pd.DataFrame(rows)
    today = pd.Timestamp.now().normalize()
    keep = (df.expiry - today).dt.days.between(0, MAX_DAYS) & (
        (df.strike / spot - 1).abs() <= MONEYNESS
    )
    print(f"{sym}: spot {spot}, {len(df)} contracts, kept {int(keep.sum())}, ts {body.get('timestamp')}")
    if not keep.any():
        raise RuntimeError(f"{sym}: no contracts kept")
    return df[keep]


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.now().strftime("%Y%m%d_%H%M")
    OUT.mkdir(parents=True, exist_ok=True)
    frames = [snap(s) for s in SYMS]
    pd.concat(frames).to_csv(OUT / f"touch_{tag}.csv", index=False)
