"""s00_pull_free.py: free public inputs for lane G (zero spend).

Pulls daily closes (raw and adjusted) for the index ETFs and the eight mega-caps from Yahoo,
VIXCLS from FRED, and asks DoltHub's public SQL endpoint how many snapshot dates it holds for
the sector and index ETFs. Writes into this folder only.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneG-index-event-vol/s00_pull_free.py
"""

from __future__ import annotations

import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
TICKERS = ["QQQ", "SPY", "IWM", "XLK", "SMH", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META",
           "TSLA", "AVGO"]
UA = {"User-Agent": "research-client/1.0"}


def pull_prices() -> None:
    raw = yf.download(TICKERS, start="2014-06-01", end="2026-11-13", auto_adjust=False,
                      progress=False, group_by="column")
    close = raw["Close"]
    adj = raw["Adj Close"]
    out = pd.concat({"close": close, "adj": adj}, axis=1)
    out.columns = [f"{a}_{b}" for a, b in out.columns]
    out.index.name = "date"
    out.to_parquet(HERE / "prices_yahoo.parquet")
    print("prices", out.shape, out.index.min().date(), out.index.max().date())
    print(out.notna().sum().to_string())


def pull_vix() -> None:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
    req = urllib.request.Request(url, headers=UA)
    try:
        txt = urllib.request.urlopen(req, timeout=60).read().decode()
        v = pd.read_csv(io.StringIO(txt))
        v.columns = ["date", "vix"]
        src = "fred"
    except Exception as exc:  # FRED timed out once; Yahoo ^VIX is the Cboe close
        print("FRED failed:", exc, "-> Yahoo ^VIX")
        y = yf.download("^VIX", start="2014-06-01", end="2026-11-13", progress=False)
        v = pd.DataFrame({"date": y.index, "vix": y["Close"].to_numpy().ravel()})
        src = "yahoo"
    print("vix source", src)
    v["date"] = pd.to_datetime(v["date"])
    v["vix"] = pd.to_numeric(v["vix"], errors="coerce")
    v.to_parquet(HERE / "vix_fred.parquet")
    print("vix", v.shape, v["date"].max().date())


def dolthub_count(sym: str) -> dict[str, object]:
    q = (
        "SELECT COUNT(DISTINCT date) AS n_dates, MIN(date) AS first, MAX(date) AS last, "
        f"COUNT(DISTINCT expiration) AS n_exp FROM option_chain WHERE act_symbol = '{sym}'"
    )
    url = ("https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master?q="
           + urllib.parse.quote(q))
    req = urllib.request.Request(url, headers=UA)
    try:
        js = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
        rows = js.get("rows", [])
        return {"symbol": sym, **(rows[0] if rows else {}), "status": js.get("query_execution_status")}
    except Exception as exc:  # report the failure, do not hide it
        return {"symbol": sym, "status": f"error: {exc}"}


def main() -> None:
    if not (HERE / "prices_yahoo.parquet").exists():
        pull_prices()
    pull_vix()
    res = []
    for s in ["XLK", "QQQ", "SMH", "SPY"]:
        res.append(dolthub_count(s))
        print(res[-1])
        time.sleep(2)
    pd.DataFrame(res).to_csv(HERE / "dolthub_etf_coverage.csv", index=False)


if __name__ == "__main__":
    main()

