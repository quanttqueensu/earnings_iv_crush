"""
dolthub_symbols.py
List the underlyings the public DoltHub ``dolthub/options`` database holds on given dates, and
flag the foreign issuers among them. Counts only; no quotes are written.

Usage
-----
    python .../scripts/dolthub_symbols.py 2024-04-18 2022-10-20
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

API = "https://www.dolthub.com/api/v1alpha1/dolthub/options/master"
HEADERS = {"User-Agent": "research-client"}
PAUSE = 1.1
OUT = Path(__file__).resolve().parents[1] / "cache"


def q(sql: str) -> list[dict]:
    time.sleep(PAUSE)
    r = requests.get(API, params={"q": sql}, headers=HEADERS, timeout=120)
    r.raise_for_status()
    b = r.json()
    if b.get("query_execution_status") != "Success":
        raise RuntimeError(b.get("query_execution_message", "unknown failure"))
    return b.get("rows") or []


def main() -> None:
    for d in sys.argv[1:]:
        rows = q(
            "SELECT act_symbol, COUNT(*) AS n FROM option_chain "
            f"WHERE date = '{d}' GROUP BY act_symbol"
        )
        syms = sorted(r["act_symbol"] for r in rows)
        print(d, "symbols:", len(syms))
        print(" ".join(syms))
        (OUT / f"dolthub_symbols_{d}.json").write_text(json.dumps(syms))


if __name__ == "__main__":
    main()
