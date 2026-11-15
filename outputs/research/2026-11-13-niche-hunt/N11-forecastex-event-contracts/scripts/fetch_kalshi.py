"""fetch_kalshi.py: Kalshi markets and hourly candles for series that twin ForecastEx macro products.

Public Kalshi API, no key, one request a second, User-Agent research-client. Settled events
closing from 2025-01-01 (ForecastEx macro products start then). Candles: 60-minute bars over the
49 hours before each market's close. Output data/kalshi_markets.parquet, data/kalshi_candles.parquet.
Rebuild: python scripts/fetch_kalshi.py
"""
from __future__ import annotations

import json
import urllib.error
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

API = "https://api.elections.kalshi.com/trade-api/v2"
OUT = Path(__file__).resolve().parents[1] / "data"
SERIES = ["KXFEDDECISION", "KXFED", "KXCPIYOY", "KXCPICOREYOY", "KXU3", "KXJOBLESSCLAIMS",
          "KXPAYROLLS"]
START = pd.Timestamp("2025-01-01", tz="UTC")
WINDOW_H = 49


def _get(path: str, **params: object) -> dict:
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for attempt in range(5):
        time.sleep(1.05)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-client"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {}
            print("retry", attempt, url, exc, flush=True)
            time.sleep(5 * (attempt + 1))
        except Exception as exc:  # transient network failure: back off and retry, then raise
            print("retry", attempt, url, exc, flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(url)


def _paged(path: str, key: str, **params: object) -> list[dict]:
    out: list[dict] = []
    cursor = None
    while True:
        p = dict(params, limit=200)
        if cursor:
            p["cursor"] = cursor
        r = _get(path, **p)
        out += r.get(key, [])
        cursor = r.get("cursor")
        if not cursor:
            return out


def main() -> None:
    cutoff = pd.Timestamp(_get("/historical/cutoff")["market_settled_ts"])
    markets: list[dict] = []
    for s in SERIES:
        evs = _paged("/events", "events", series_ticker=s, status="settled")
        # ticker year code after the hyphen; events before Dec 2024 cannot close in 2025
        tickers = sorted({e["event_ticker"] for e in evs
                          if e["event_ticker"].split("-")[1][:2] >= "25"
                          or e["event_ticker"].split("-")[1][:5] == "24DEC"})
        print(s, "events", len(tickers), flush=True)
        for et in tickers:
            ms = _paged("/markets", "markets", event_ticker=et)
            if not ms:
                ms = _paged("/historical/markets", "markets", event_ticker=et)
            for m in ms:
                m["series"] = s
            markets += [m for m in ms if pd.Timestamp(m["close_time"]) >= START]
    mk = pd.DataFrame(markets)
    mk.astype(str).to_parquet(OUT / "kalshi_markets.parquet")
    print("markets", len(mk), flush=True)
    rows = []
    for i, m in mk.iterrows():
        ct = int(pd.Timestamp(m["close_time"]).timestamp())
        params = {"start_ts": ct - WINDOW_H * 3600, "end_ts": ct, "period_interval": 60}
        if pd.Timestamp(m["close_time"]) < cutoff:
            path = f"/historical/markets/{m['ticker']}/candlesticks"
        else:
            path = f"/series/{m['series']}/markets/{m['ticker']}/candlesticks"
        for c in _get(path, **params).get("candlesticks", []):
            rows.append({
                "ticker": m["ticker"], "ts": c["end_period_ts"],
                "bid": (c.get("yes_bid") or {}).get("close_dollars", (c.get("yes_bid") or {}).get("close")),
                "ask": (c.get("yes_ask") or {}).get("close_dollars", (c.get("yes_ask") or {}).get("close")),
                "volume": c.get("volume_fp", c.get("volume")),
            })
        if i % 100 == 0:
            print("candles", i, len(mk), len(rows), flush=True)
    pd.DataFrame(rows).astype(str).to_parquet(OUT / "kalshi_candles.parquet")
    print("DONE candles", len(rows), flush=True)


if __name__ == "__main__":
    main()
