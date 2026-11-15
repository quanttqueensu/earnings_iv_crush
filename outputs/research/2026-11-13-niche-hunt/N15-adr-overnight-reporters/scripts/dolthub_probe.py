"""
dolthub_probe.py
Probe the public DoltHub ``dolthub/options`` database for ADR coverage and sampling cadence.

Public SQL-over-HTTP API, no key, generic User-Agent, one request per 1.1 seconds. Writes only
counts (dates present, rows per date) to the lane cache; no quotes are kept by this script.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N15-adr-overnight-reporters/scripts/dolthub_probe.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

API = "https://www.dolthub.com/api/v1alpha1/dolthub/options/master"
HEADERS = {"User-Agent": "research-client"}
PAUSE = 1.1  # seconds between requests: the brief caps us at one per second per host
OUT = Path(__file__).resolve().parents[1] / "cache" / "dolthub_probe.json"


def q(sql: str) -> list[dict]:
    time.sleep(PAUSE)
    r = requests.get(API, params={"q": sql}, headers=HEADERS, timeout=60)
    r.raise_for_status()
    b = r.json()
    if b.get("query_execution_status") != "Success":
        raise RuntimeError(b.get("query_execution_message", "unknown failure"))
    return b.get("rows") or []


def main() -> None:
    syms = sys.argv[1:] or [
        "TSM", "ASML", "SAP", "NVO", "BABA", "TM", "SONY", "AZN", "BP", "SHEL",
        "HSBC", "BHP", "PDD", "JD", "BIDU", "UBS", "DEO", "GSK", "NVS", "INFY",
    ]
    res: dict = {}
    # One wide window per symbol is a scan; pin each date instead (date-led primary key).
    # DoltHub samples Monday, Wednesday and Friday (a Thursday probe returned zero rows for AAPL
    # on 2024-04-18 while the Wednesday and Friday either side held 134 and 136), so probe Wednesdays.
    days = ["2022-04-20", "2023-04-19", "2024-04-17"]
    for s in syms:
        res[s] = {}
        for d in days:
            try:
                rows = q(
                    f"SELECT COUNT(*) AS n FROM option_chain WHERE date = '{d}' "
                    f"AND act_symbol = '{s}'"
                )
                res[s][d] = int(rows[0]["n"]) if rows else 0
            except Exception as exc:  # recorded, never swallowed silently
                res[s][d] = f"ERR {type(exc).__name__}: {str(exc)[:80]}"
        print(s, res[s], flush=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
