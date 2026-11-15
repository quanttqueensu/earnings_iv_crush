"""fetch_usda_calendar.py: build the USDA grain-report release calendar from ESMIS.

Scrapes the public release lists on esmis.nal.usda.gov (USDA National Agricultural Library,
no key, robots.txt allows /publication/) for WASDE, Grain Stocks, Prospective Plantings,
Acreage and Crop Production, one request a second, User-Agent ``research-client``. Writes
``data/usda_report_dates.csv`` (report, release_date) and prints a funnel.

Usage
-----
    python -I scripts/fetch_usda_calendar.py --out data/usda_report_dates.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import time
import urllib.request
from pathlib import Path

# ── constants ──
_BASE = "https://esmis.nal.usda.gov/publication/"
_SLUGS = {
    "WASDE": "world-agricultural-supply-and-demand-estimates",
    "GrainStocks": "grain-stocks",
    "ProspectivePlantings": "prospective-plantings",
    "Acreage": "acreage",
    "CropProduction": "crop-production",
}
_UA = "research-client"
_PAUSE_S = 1.1  # brief: at most one request a second per host
_MAX_PAGES = 40  # hard stop; WASDE needs about 20 pages of 10 back to 2010
_FIRST_YEAR = 2010
_DATE_RE = re.compile(r'<td headers="view-release-date-table-column"[^>]*><time datetime="(\d{4}-\d{2}-\d{2})')


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch(report: str, slug: str) -> list[str]:
    """Return release dates (ISO) for one publication, newest first, back to _FIRST_YEAR."""
    dates: list[str] = []
    for page in range(_MAX_PAGES):
        html = _get(f"{_BASE}{slug}?page={page}")
        time.sleep(_PAUSE_S)
        found = _DATE_RE.findall(html)
        if not found:
            break
        dates.extend(found)
        if int(found[-1][:4]) < _FIRST_YEAR:
            break
    else:
        print(f"WARNING {report}: hit the {_MAX_PAGES}-page cap; list may be truncated")
    out = sorted({d for d in dates if int(d[:4]) >= _FIRST_YEAR})
    print(f"{report}: {len(dates)} rows scraped, {len(out)} distinct dates since {_FIRST_YEAR}")
    if not out:
        raise RuntimeError(f"{report}: no dates parsed; page layout may have changed")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rows = [(rep, d) for rep, slug in _SLUGS.items() for d in fetch(rep, slug)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["report", "release_date"])
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
