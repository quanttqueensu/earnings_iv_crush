"""dolt_universe.py: list the symbols the free DoltHub option_chain table carries on sample dates.

Feasibility input for lane H: which names have a free historical chain at all.
"""
from __future__ import annotations

import json
import string
import sys
import time

import requests

API = "https://www.dolthub.com/api/v1alpha1/dolthub/options/master"


def q(sql: str) -> list[dict]:
    for attempt in range(4):
        try:
            r = requests.get(API, params={"q": sql}, timeout=90,
                             headers={"User-Agent": "research-client"})
            b = r.json()
            if b.get("query_execution_status") == "Success":
                return b.get("rows") or []
            print("retry", b.get("query_execution_message", "")[:80], file=sys.stderr)
        except Exception as exc:  # transport failure: retry then raise
            print("retry", exc, file=sys.stderr)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed: {sql}")


out = {}
for d in sys.argv[1:]:
    syms: set[str] = set()
    letters = string.ascii_uppercase
    for i, a in enumerate(letters):
        hi = letters[i + 1] if i + 1 < len(letters) else "ZZZZ"
        rows = q(f"select distinct act_symbol from option_chain where date='{d}' "
                 f"and act_symbol >= '{a}' and act_symbol < '{hi}'")
        syms |= {r["act_symbol"] for r in rows}
    out[d] = sorted(syms)
    print(d, len(syms))
json.dump(out, open("dolt_universe.json", "w"))
