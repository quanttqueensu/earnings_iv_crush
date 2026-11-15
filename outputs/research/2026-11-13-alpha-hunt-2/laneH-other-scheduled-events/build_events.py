"""build_events.py: assemble the scheduled-event list (FDA AdComm + megacap product events).

AdComm rows come from adcomm_events.csv (Federal Register). Product-event dates are transcribed
from the Wikipedia pages saved in this folder (wiki_*.txt, fetched 2026-11-13): Apple event and
WWDC keynote days from section headings, Nvidia GTC first conference day from the table, Google
I/O and Microsoft Build first day from the year paragraphs. Earnings dates per ticker come from
yfinance (free) and are cached to earnings_dates.parquet.

Output: events.csv (one row per ticker-event), earnings_dates.parquet.
"""
from __future__ import annotations

import time

import pandas as pd
import yfinance as yf

# Diversified large pharma, medtech and tobacco groups: a single committee rarely moves these.
# Fixed before any outcome was computed (hypothesis H-A3).
DIVERSIFIED = {"PFE", "MRK", "BMY", "JNJ", "AZN", "GSK", "NVS", "NVO", "SNY", "TAK", "LLY", "AMGN",
               "ABT", "MDT", "MO", "BTI", "GILD", "ABBV", "VTRS", "CELG"}

PRODUCT = [
    # Apple events and WWDC keynotes, List_of_Apple_Inc._media_events
    ("AAPL", "2019-03-25", "apple"), ("AAPL", "2019-06-03", "wwdc"), ("AAPL", "2019-09-10", "apple"),
    ("AAPL", "2020-06-22", "wwdc"), ("AAPL", "2020-09-15", "apple"), ("AAPL", "2020-10-13", "apple"),
    ("AAPL", "2020-11-10", "apple"), ("AAPL", "2021-04-20", "apple"), ("AAPL", "2021-06-07", "wwdc"),
    ("AAPL", "2021-09-14", "apple"), ("AAPL", "2021-10-18", "apple"), ("AAPL", "2022-03-08", "apple"),
    ("AAPL", "2022-06-06", "wwdc"), ("AAPL", "2022-09-07", "apple"), ("AAPL", "2023-06-05", "wwdc"),
    ("AAPL", "2023-09-12", "apple"), ("AAPL", "2023-10-30", "apple"), ("AAPL", "2024-05-07", "apple"),
    ("AAPL", "2024-06-10", "wwdc"), ("AAPL", "2024-09-09", "apple"),
    # Nvidia GTC (spring and autumn main events), Nvidia_GTC table
    ("NVDA", "2019-03-18", "gtc"), ("NVDA", "2020-10-05", "gtc"), ("NVDA", "2021-04-12", "gtc"),
    ("NVDA", "2022-03-21", "gtc"), ("NVDA", "2022-09-19", "gtc"), ("NVDA", "2023-03-20", "gtc"),
    ("NVDA", "2024-03-18", "gtc"),
    # Google I/O first day, Google_I/O (2020 cancelled)
    ("GOOGL", "2021-05-18", "io"), ("GOOGL", "2022-05-11", "io"), ("GOOGL", "2023-05-10", "io"),
    ("GOOGL", "2024-05-14", "io"),
    # Microsoft Build first day, Microsoft_Build
    ("MSFT", "2019-05-06", "build"), ("MSFT", "2021-05-25", "build"), ("MSFT", "2022-05-24", "build"),
    ("MSFT", "2023-05-23", "build"),
]


def main() -> None:
    ad = pd.read_csv("adcomm_events.csv")
    n0 = len(ad)
    ad = ad[ad["lead_days"] >= 2].copy()
    print(f"AdComm ticker-meetings 2019-01..2024-11: {n0}; notice >= 2 days ahead: {len(ad)}")
    # one event per ticker per meeting run (multi-day meetings collapse to the first day)
    ad["meeting_date"] = pd.to_datetime(ad["meeting_date"])
    ad = ad.sort_values(["ticker", "meeting_date"])
    gap = ad.groupby("ticker")["meeting_date"].diff().dt.days
    ad = ad[(gap.isna()) | (gap > 7)]
    print(f"after collapsing multi-day meetings: {len(ad)}")
    ad = pd.DataFrame({"ticker": ad["ticker"], "event_date": ad["meeting_date"],
                       "category": "adcomm", "sub": ad["committee"].str[:40],
                       "material": ~ad["ticker"].isin(DIVERSIFIED)})
    pr = pd.DataFrame(PRODUCT, columns=["ticker", "event_date", "sub"])
    pr["event_date"] = pd.to_datetime(pr["event_date"])
    pr["category"] = "product"
    pr["material"] = True
    ev = pd.concat([ad, pr], ignore_index=True)
    ev["event_id"] = [f"{c[:2]}{i:03d}" for i, c in enumerate(ev["category"])]

    rows = []
    for t in sorted(ev["ticker"].unique()):
        for attempt in range(3):
            try:
                d = yf.Ticker(t).get_earnings_dates(limit=60)
                break
            except Exception as exc:  # free source, transient failures: retry then record
                print("retry", t, exc)
                time.sleep(3)
                d = None
        if d is None or len(d) == 0:
            print(f"WARNING no earnings dates for {t}; its windows cannot be screened")
            continue
        for ts in d.index:
            rows.append({"ticker": t, "edate": pd.Timestamp(ts).tz_localize(None).normalize()})
    ed = pd.DataFrame(rows)
    ed.to_parquet("earnings_dates.parquet")
    print("earnings dates for", ed["ticker"].nunique(), "of", ev["ticker"].nunique(), "tickers")
    ev.to_csv("events.csv", index=False)
    print(ev.groupby(["category", "material"]).size())


if __name__ == "__main__":
    main()
