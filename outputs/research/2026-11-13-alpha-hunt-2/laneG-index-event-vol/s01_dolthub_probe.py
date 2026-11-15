"""s01_dolthub_probe.py: how dense is DoltHub's free option_chain for XLK and QQQ (zero spend).

Usage
-----
    python s01_dolthub_probe.py
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master?q="


def q(sql: str) -> dict[str, object]:
    url = BASE + urllib.parse.quote(sql)
    req = urllib.request.Request(url, headers={"User-Agent": "research-client/1.0"})
    js = json.loads(urllib.request.urlopen(req, timeout=150).read().decode())
    return {
        "status": js.get("query_execution_status"),
        "msg": js.get("query_execution_message"),
        "rows": js.get("rows", []),
    }


def main() -> None:
    out = {}
    # single-date point lookups (the primary key leads with date); event nights and neighbours
    days = ["2024-07-29", "2024-07-30", "2024-07-31", "2024-08-01", "2024-08-02",
            "2022-01-25", "2022-01-26", "2022-01-27", "2025-10-28", "2025-10-29", "2025-10-30"]
    for sym in ("XLK", "QQQ"):
        for d in days:
            sql = (
                "SELECT date, COUNT(*) AS n, COUNT(DISTINCT expiration) AS ne, "
                "MIN(expiration) AS e0, MAX(expiration) AS e1 FROM option_chain "
                f"WHERE date = '{d}' AND act_symbol = '{sym}'"
            )
            try:
                r = q(sql)
            except Exception as exc:  # report, never hide
                r = {"status": "exc", "msg": str(exc), "rows": []}
            out[f"{sym}_{d}"] = r
            print(sym, d, r["status"], r["msg"], len(r["rows"]))
            for row in r["rows"]:
                print("   ", row)
    (HERE / "dolthub_probe.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

