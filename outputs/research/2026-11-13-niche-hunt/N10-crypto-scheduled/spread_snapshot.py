"""
spread_snapshot.py
One live snapshot of the quoted touch on the two crypto option venues the lane can see for free:
Deribit BTC options (public book summary, real time) and IBIT options (Cboe public delayed quote
JSON, about 15 minutes late; only computed aggregates are kept). For each of the nearest expiries it reports the ATM straddle's
quoted half-spread as a share of its mid premium, the number the brief asks for. A snapshot is
one moment; it is not a history.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/spread_snapshot.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
UA = {"User-Agent": "research-client"}
DERIBIT = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
CBOE = "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{sym}.json"
OCC = re.compile(r"^(?P<root>[A-Z0-9]+?)(?P<ymd>\d{6})(?P<cp>[CP])(?P<k>\d{8})$")
N_EXPIRIES = 6


def deribit(ccy: str) -> pd.DataFrame:
    r = requests.get(DERIBIT, params={"currency": ccy, "kind": "option"}, headers=UA, timeout=60)
    r.raise_for_status()
    js = r.json()
    (CACHE / f"snapshot_deribit_{ccy}.json").write_text(json.dumps(js))
    d = pd.DataFrame(js["result"])
    p = d["instrument_name"].str.split("-", expand=True)
    d["expiry"] = pd.to_datetime(p[1], format="%d%b%y").dt.tz_localize("UTC") + pd.Timedelta(
        hours=8
    )
    d["strike"] = p[2].astype(float)
    d["cp"] = p[3]
    # quotes are in the coin; the USD value is price times the underlying index
    d["bid_usd"] = d["bid_price"] * d["estimated_delivery_price"]
    d["ask_usd"] = d["ask_price"] * d["estimated_delivery_price"]
    d["spot"] = d["estimated_delivery_price"]
    d["asof"] = pd.Timestamp.now(tz="UTC")
    return d[["expiry", "strike", "cp", "bid_usd", "ask_usd", "spot", "asof"]]


def ibit(sym: str = "IBIT") -> pd.DataFrame:
    r = requests.get(CBOE.format(sym=sym), headers=UA, timeout=60)
    r.raise_for_status()
    js = r.json()
    # raw Cboe quotes are not stored: Cboe terms allow one personal copy, not a retained archive
    spot = float(js["data"]["current_price"])
    rows = []
    for o in js["data"]["options"]:
        m = OCC.match(o["option"])
        if not m or m["root"] != sym:
            continue  # non-standard roots (for example B1BIT) are adjusted or other deliverables
        rows.append(
            {
                "expiry": pd.Timestamp(f"20{m['ymd']}", tz="America/New_York")
                + pd.Timedelta(hours=16),
                "strike": int(m["k"]) / 1000,
                "cp": m["cp"],
                "bid_usd": o["bid"],
                "ask_usd": o["ask"],
                "spot": spot,
                "asof": js["timestamp"],
            }
        )
    return pd.DataFrame(rows)


def atm_table(d: pd.DataFrame, venue: str) -> pd.DataFrame:
    out = []
    for exp in sorted(d["expiry"].unique())[:N_EXPIRIES]:
        x = d[d["expiry"] == exp]
        spot = float(x["spot"].iloc[0])
        piv = x.pivot_table(index="strike", columns="cp", values=["bid_usd", "ask_usd"])
        piv = piv.dropna()
        piv = piv[(piv["bid_usd"] > 0).all(axis=1)]
        if piv.empty:
            continue
        k = min(piv.index, key=lambda s: abs(s - spot))
        bid = float(piv.loc[k, ("bid_usd", "C")] + piv.loc[k, ("bid_usd", "P")])
        ask = float(piv.loc[k, ("ask_usd", "C")] + piv.loc[k, ("ask_usd", "P")])
        mid = (bid + ask) / 2
        out.append(
            {
                "venue": venue,
                "expiry": pd.Timestamp(exp).tz_convert("UTC"),
                "hours": (
                    pd.Timestamp(exp).tz_convert("UTC") - pd.Timestamp.now(tz="UTC")
                ).total_seconds()
                / 3600,
                "spot": spot,
                "strike": k,
                "straddle_mid": mid,
                "mid_over_spot": mid / spot,
                "half_spread_over_mid": (ask - bid) / 2 / mid,
            }
        )
    return pd.DataFrame(out)


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    tabs = [atm_table(deribit("BTC"), "Deribit BTC")]
    time.sleep(1.2)
    tabs.append(atm_table(ibit("IBIT"), "IBIT (Cboe delayed)"))
    res = pd.concat(tabs, ignore_index=True)
    res["snapshot_utc"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M")
    print(res.to_string(float_format=lambda v: f"{v:.4f}"))
    f = HERE / "spread_snapshot.csv"
    res.to_csv(f, mode="a", header=not f.exists(), index=False)


if __name__ == "__main__":
    main()
