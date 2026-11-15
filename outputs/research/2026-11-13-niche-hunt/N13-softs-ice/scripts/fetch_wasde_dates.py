"""fetch_wasde_dates.py: WASDE release dates from the USDA ESMIS publication listing.

Public HTML, no key. Respects the site's robots.txt Crawl-delay of 10 seconds. Writes
raw/wasde_dates.csv (one row per release date). Usage:
    python -I scripts/fetch_wasde_dates.py --pages 27
"""
from __future__ import annotations

import argparse
import re
import time
import urllib.request
from pathlib import Path

URL = "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates?page={p}"
UA = "research-client"
CRAWL_DELAY_S = 11.0  # robots.txt Crawl-delay is 10


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=27)
    ap.add_argument("--start", type=int, default=0, help="first page; merges into an existing file")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "raw" / "wasde_dates.csv"))
    a = ap.parse_args()
    dates: set[str] = set()
    if a.start > 0 and Path(a.out).exists():
        dates |= set(Path(a.out).read_text(encoding="utf-8").split()[1:])
    for p in range(a.start, a.pages):
        req = urllib.request.Request(URL.format(p=p), headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
        found = set(re.findall(r'datetime="(\d{4}-\d{2}-\d{2})T', html))
        if not found:
            raise RuntimeError(f"page {p}: no release dates parsed")
        dates |= found
        print(f"page {p}: {len(found)} dates, {min(found)} to {max(found)}", flush=True)
        time.sleep(CRAWL_DELAY_S)
    Path(a.out).write_text("date\n" + "\n".join(sorted(dates)) + "\n", encoding="utf-8")
    print(f"wrote {len(dates)} dates to {a.out}")


if __name__ == "__main__":
    main()
