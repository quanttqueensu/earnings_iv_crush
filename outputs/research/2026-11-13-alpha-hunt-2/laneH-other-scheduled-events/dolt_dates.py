"""dolt_dates.py: the set of DoltHub option_chain snapshot dates, read off a liquid symbol (AAPL).

Snapshots are taken for all symbols on the same dates (about three sessions a week), so AAPL's
date set is the candidate set; each event's chain pull then confirms its own symbol is present.
"""
from __future__ import annotations

import json
import sys
import time

import pandas as pd
import requests

API = "https://www.dolthub.com/api/v1alpha1/dolthub/options/master"


def q(sql: str) -> list[dict]:
    for attempt in range(5):
        try:
            r = requests.get(API, params={"q": sql}, timeout=90,
                             headers={"User-Agent": "research-client"})
            b = r.json()
            if b.get("query_execution_status") == "Success":
                return b.get("rows") or []
        except Exception as exc:
            print("retry", exc, file=sys.stderr)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(sql)


dates: list[str] = []
for start in pd.date_range("2018-12-01", "2024-12-31", freq="7D"):
    end = start + pd.Timedelta(days=6)
    rows = q(f"select distinct date from option_chain where act_symbol='AAPL' and date between "
             f"'{start:%Y-%m-%d}' and '{end:%Y-%m-%d}'")
    dates += [r["date"] for r in rows]
dates = sorted(set(dates))
json.dump(dates, open("dolt_dates.json", "w"))
s = pd.to_datetime(pd.Series(dates))
print(len(dates), s.min(), s.max())
print(s.dt.day_name().value_counts())
print(s.dt.year.value_counts().sort_index())
