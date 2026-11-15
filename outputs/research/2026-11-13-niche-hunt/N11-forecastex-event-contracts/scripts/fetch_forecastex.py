"""fetch_forecastex.py: stream ForecastEx public daily CSVs and keep non-weather, non-crypto rows.

Source: the exchange's public bucket behind https://data.forecastex.com (linked from
https://forecastex.com/data). One request a second, User-Agent research-client. Raw CSVs are
not kept; filtered rows go to data/*.parquet. Rebuild: python scripts/fetch_forecastex.py
"""
from __future__ import annotations

import io
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BUCKET = "https://forecastex-public-data.s3.amazonaws.com/"
UA = {"User-Agent": "research-client"}
OUT = Path(__file__).resolve().parents[1] / "data"
# weather (UH*, UL*, HR*, and other daily temperature families) and crypto (CF*, YX*) dominate
# row counts and are outside this lane's scheduled-release scope
DROP = re.compile(r"^(UH|UL|HR|CF|YX)")
_ALLOW_FILE = OUT / "econ_product_ids.txt"
# allowlist built from daily_summary rows with product_category "Economic Indicators"
ALLOW: set[str] = (
    set(_ALLOW_FILE.read_text().split()) if "--econ-only" in sys.argv and _ALLOW_FILE.exists() else set()
)


def _get(url: str) -> bytes:
    for attempt in range(4):
        try:
            time.sleep(1.0)
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        except Exception as exc:  # retry transient network failures, then raise
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
    OUT.mkdir(exist_ok=True)
    kinds = [a for a in sys.argv[1:] if not a.startswith("--")]
    for kind in kinds or ["daily_summary", "pairs", "prices"]:
        keys = sorted(_list(kind + "/"))
        print(kind, len(keys), "files", flush=True)
        frames = []
        nraw = 0
        for i, k in enumerate(keys):
            df = pd.read_csv(io.BytesIO(_get(BUCKET + urllib.parse.quote(k))), dtype=str)
            df["file"] = k.split("/")[-1]
            nraw += len(df)
            if kind != "daily_summary":
                pref = df["event_contract"].str.split("_").str[0]
                if ALLOW:  # economic-indicator product codes from the daily summaries
                    df = df[pref.isin(ALLOW)]
                else:
                    df = df[~pref.str.match(DROP)]
            frames.append(df)
            if i % 50 == 0:
                print(kind, i, k, "kept", sum(len(f) for f in frames), "of", nraw, flush=True)
        out = pd.concat(frames, ignore_index=True)
        out.to_parquet(OUT / f"{kind}.parquet", compression="zstd")
        print(kind, "DONE rows kept", len(out), "of", nraw, flush=True)


if __name__ == "__main__":
    main()
