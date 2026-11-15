"""probe_dolthub.py: coverage probe of the public DoltHub option_chain table for commodity ETFs.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N17-commodity-etf-options/probe_dolthub.py
"""

from __future__ import annotations

import json
import sys
import time

import requests

API = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"
HEADERS = {"User-Agent": "research-client"}
SYMS = "('USO','UNG','GLD','SLV','TLT','DBA','CORN','WEAT','SOYB','IAU','GDX','XLE','IEF','UCO','BNO','SPY')"


def q(sql: str) -> dict:
    r = requests.get(API, params={"q": sql}, headers=HEADERS, timeout=90)
    time.sleep(1.2)
    return r.json()


if __name__ == "__main__":
    dates = sys.argv[1:] or ["2021-06-09", "2023-06-14", "2024-06-12", "2025-06-11"]
    for d in dates:
        sql = (
            "SELECT act_symbol, COUNT(*) AS n, COUNT(DISTINCT expiration) AS ne "
            f"FROM option_chain WHERE date='{d}' AND act_symbol IN {SYMS} GROUP BY act_symbol"
        )
        body = q(sql)
        print(d, body.get("query_execution_status"), json.dumps(body.get("rows")))
