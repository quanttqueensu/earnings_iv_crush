"""fetch_futures.py: daily continuous front-month ICE softs futures from Yahoo (free, no key).

Writes raw/softs_daily.csv with columns date, root, close, volume. Yahoo's continuous series
splices contracts without back-adjustment, so roll days carry a spurious return; the scorer
deals with that (see diagnosis.log). Usage:
    python scripts/fetch_futures.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

TICKERS = {"CT": "CT=F", "KC": "KC=F", "CC": "CC=F", "SB": "SB=F"}
START = "2000-01-01"


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "raw" / "softs_daily.csv"
    rows = []
    for root, tk in TICKERS.items():
        d = yf.download(tk, start=START, progress=False, auto_adjust=False)
        if d.empty:
            raise RuntimeError(f"{tk}: empty download")
        d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
        f = pd.DataFrame({"date": d.index.date, "root": root, "close": d["Close"].to_numpy(),
                          "volume": d["Volume"].to_numpy()})
        rows.append(f)
        print(f"{root}: {len(f)} rows {f.date.min()} to {f.date.max()}")
    pd.concat(rows).to_csv(out, index=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
