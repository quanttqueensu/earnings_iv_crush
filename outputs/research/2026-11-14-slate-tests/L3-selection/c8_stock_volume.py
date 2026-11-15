"""c8_stock_volume.py: CRSP daily share volume for the megacap permnos, from the local dsf cache.

The cached ``crsp_a_stock.dsf.<hash>.parquet`` slices carry no permno column (the permno sits in
the hashed filter). Each slice is identified by matching its (date, |prc|) rows against
``crsp_paths.parquet``; a slice is assigned to a permno only if at least 95% of its priced rows
match that permno and no other permno matches more than 5%. Writes ``c8_stock_volume.parquet``
(permno, date, vol) and prints the funnel. Reads no option outcome.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c8_stock_volume.py
"""

from __future__ import annotations

import glob
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib import ROOT  # noqa: E402

CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
DSF = ROOT / "data" / "processed" / "wrds" / "raw"
MATCH_MIN, OTHER_MAX = 0.95, 0.05  # identification thresholds, share of a slice's priced rows
OUT = HERE / "c8_stock_volume.parquet"


def main() -> None:
    mega = pd.read_parquet(HERE / "c8_megacap_corrected.parquet", columns=["permno"])
    want = set(mega["permno"].astype(int))
    c = pd.read_parquet(CRSP, columns=["permno", "date", "prc"])
    c["prc"] = pd.to_numeric(c["prc"], errors="coerce").abs().round(4)
    c["date"] = pd.to_datetime(c["date"]).dt.normalize()
    c = c.dropna()
    idx = c.groupby(["date", "prc"])["permno"].apply(lambda s: tuple(sorted(set(s)))).to_dict()
    funnel: Counter = Counter()
    parts = []
    for f in glob.glob(str(DSF / "crsp_a_stock.dsf.*.parquet")):
        d = pd.read_parquet(f)
        if not {"date", "prc", "vol"} <= set(d.columns):
            funnel["no_vol_column"] += 1
            continue
        d["date"] = pd.to_datetime(d["date"]).dt.normalize()
        p = pd.to_numeric(d["prc"], errors="coerce").abs().round(4)
        hits: Counter = Counter()
        n = 0
        for dt, px in zip(d["date"], p, strict=True):
            if not np.isfinite(px):
                continue
            n += 1
            for pm in idx.get((dt, px), ()):
                hits[pm] += 1
        if n == 0 or not hits:
            funnel["unmatched"] += 1
            continue
        (best, nb), *rest = hits.most_common()
        if nb / n < MATCH_MIN or (rest and rest[0][1] / n > OTHER_MAX):
            funnel["ambiguous"] += 1
            continue
        if best not in want:
            funnel["matched_other_permno"] += 1
            continue
        funnel["matched_megacap"] += 1
        parts.append(
            pd.DataFrame(
                {"permno": best, "date": d["date"], "vol": pd.to_numeric(d["vol"], errors="coerce")}
            )
        )
    print("slice funnel:", dict(funnel))
    v = pd.concat(parts).dropna().drop_duplicates(["permno", "date"])
    print(
        f"megacap permnos with volume: {v['permno'].nunique()} of {len(want)}; rows {len(v)}; "
        f"{v['date'].min().date()} to {v['date'].max().date()}"
    )
    v.to_parquet(OUT)


if __name__ == "__main__":
    main()
