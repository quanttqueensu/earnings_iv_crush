"""fetch_cboe.py: download free Cboe/CFE public files for the N09 VIX-complex lane.

Pulls (public, no key, no login; User-Agent ``research-client``; one request a second):
  * CFE VX monthly futures daily files, archive format 2004-2013 and current format 2013-2026;
  * Cboe index histories (VIX, VIX9D, VIX3M, VIX1D, VVIX) from the global indices CDN.

Usage
-----
    python -I outputs/research/2026-11-13-niche-hunt/N09-vix-complex/scripts/fetch_cboe.py <raw_dir>
"""

from __future__ import annotations

import datetime as dt
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "research-client"}
PAUSE_S = 1.1  # brief: at most one request a second per host
MONTH_CODES = "FGHJKMNQUVXZ"
NEW_BASE = "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{d}.csv"
OLD_BASE = "https://cdn.cboe.com/resources/futures/archive/volume-and-price/CFE_{c}{yy}_VX.csv"
IDX_BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{s}_History.csv"


def _get(url: str) -> bytes | None:
    time.sleep(PAUSE_S)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError:
        return None


def _rule_expiry(year: int, month: int) -> dt.date:
    """Wednesday 30 days before the third Friday of the following month (holiday-unadjusted)."""
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    first = dt.date(ny, nm, 1)
    third_fri = first + dt.timedelta(days=(4 - first.weekday()) % 7 + 14)
    return third_fri - dt.timedelta(days=30)


def main(raw: Path) -> None:
    vx = raw / "vx"
    vx.mkdir(parents=True, exist_ok=True)
    funnel = {"old_ok": 0, "old_miss": 0, "new_ok": 0, "new_miss": 0}
    # archive format: contract months 2004-05 to 2013-12
    for y in range(2004, 2014):
        for m in range(1, 13):
            if (y, m) < (2004, 5):
                continue
            out = vx / f"old_{y}{m:02d}.csv"
            if out.exists():
                funnel["old_ok"] += 1
                continue
            b = _get(OLD_BASE.format(c=MONTH_CODES[m - 1], yy=f"{y % 100:02d}"))
            if b and len(b) > 500:
                out.write_bytes(b)
                funnel["old_ok"] += 1
            else:
                funnel["old_miss"] += 1
                print(f"old miss {y}-{m:02d}")
    # current format: contract months 2013-01 to 2027-12 (future ones simply exist with partial data)
    for y in range(2013, 2028):
        for m in range(1, 13):
            out = vx / f"new_{y}{m:02d}.csv"
            if out.exists():
                funnel["new_ok"] += 1
                continue
            base = _rule_expiry(y, m)
            got = False
            for shift in (0, -1, -2, 1):
                d = base + dt.timedelta(days=shift)
                b = _get(NEW_BASE.format(d=d.isoformat()))
                if b and len(b) > 200:
                    out.write_bytes(b)
                    funnel["new_ok"] += 1
                    got = True
                    break
            if not got:
                funnel["new_miss"] += 1
                print(f"new miss {y}-{m:02d} (rule {base})")
    idx = raw / "indices"
    idx.mkdir(exist_ok=True)
    for s in ("VIX", "VIX9D", "VIX3M", "VIX1D", "VVIX", "VIX6M"):
        b = _get(IDX_BASE.format(s=s))
        if b:
            (idx / f"{s}_History.csv").write_bytes(b)
        else:
            print(f"index miss {s}")
    print("funnel", funnel)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
