"""e5_fetch.py: ForecastEx FES and FNQ rows from the exchange's public daily CSVs.

Source: the public bucket behind https://data.forecastex.com, linked from
https://forecastex.com/data. No robots.txt exists on forecastex.com, data.forecastex.com or the
bucket (all three return 404, checked 2026-11-15), and the data page offers the files without
registration. One request a second, User-Agent ``research-client``. Raw CSVs are not kept: each
file is filtered on arrival to FES and FNQ rows and written as a part file under
``e5_data/<kind>/``, so an interrupted run resumes where it stopped.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/e5_fetch.py
"""

from __future__ import annotations

import io
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BUCKET = "https://forecastex-public-data.s3.amazonaws.com/"
UA = {"User-Agent": "research-client"}
HERE = Path(__file__).resolve().parent
OUT = HERE / "e5_data"
FIRST, LAST = "20250418", "20261113"  # FES first trades 2025-04-21; summaries end 2026-11-12
PRODUCTS = ("FES_", "FNQ_")
PAUSE_S = 1.0  # one request a second per host


def _get(url: str) -> bytes:
    for attempt in range(4):
        try:
            time.sleep(PAUSE_S)
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=120).read()
        except Exception as exc:  # transient network failures are retried, then raised
            print(f"retry {attempt} {url}: {exc}", flush=True)
            time.sleep(5)
    raise RuntimeError(f"failed {url}")


def _list(prefix: str) -> list[str]:
    keys: list[str] = []
    tok = None
    while True:
        q = {"list-type": "2", "prefix": prefix}
        if tok:
            q["continuation-token"] = tok
        s = _get(BUCKET + "?" + urllib.parse.urlencode(q)).decode()
        keys += re.findall(r"<Key>(.*?)</Key>", s)
        t = re.findall(r"<NextContinuationToken>(.*?)</", s)
        if not t:
            return [k for k in keys if k.endswith(".csv")]
        tok = t[0]


def main() -> None:
    for kind in ("pairs", "prices"):
        out = OUT / kind
        out.mkdir(parents=True, exist_ok=True)
        keys = [
            k for k in sorted(_list(kind + "/")) if FIRST <= re.findall(r"(\d{8})", k)[-1] <= LAST
        ]
        print(kind, len(keys), "files in range", flush=True)
        n_raw = n_kept = 0
        for i, k in enumerate(keys):
            part = out / (Path(k).stem + ".parquet")
            if part.exists():
                continue
            df = pd.read_csv(io.BytesIO(_get(BUCKET + urllib.parse.quote(k))), dtype=str)
            n_raw += len(df)
            df = df[df["event_contract"].str.startswith(PRODUCTS, na=False)]
            df["file"] = Path(k).name
            n_kept += len(df)
            tmp = part.with_suffix(".tmp")
            df.to_parquet(tmp)
            tmp.replace(part)
            if i % 50 == 0:
                print(kind, i, k, "kept", n_kept, "of", n_raw, flush=True)
        print(kind, "DONE kept", n_kept, "of", n_raw, flush=True)
    (OUT / "DONE").write_text("complete\n", encoding="utf-8")


if __name__ == "__main__":
    main()
