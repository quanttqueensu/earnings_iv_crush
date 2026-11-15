"""c3_mde.py: C3 power check, first reports after listing (earliest CRSP namedt).

Counts the events whose entry falls within a year of the permno's earliest CRSP ``namedt`` (fewer
than four prior quarterly reports) by block, and prints the minimum detectable effect of a
treated-minus-rest difference at 80% power, two-sided 5%. Standard deviations are taken from the
2013-18 block statistics L1 already viewed descriptively (CORRECTIONS.md), not from a declared
block. No outcome of a treated event is read.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c3_mde.py
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib  # noqa: E402

from earnings_iv_crush.research.protocol import min_detectable_effect  # noqa: E402

NAMES = lib.ROOT / "data" / "processed" / "wrds" / "raw"
FIRST_YEAR_DAYS = 365  # under a year listed: at most three prior quarterly reports
TWO_YEAR_DAYS = 730  # sensitivity: at most seven prior reports
SD_RV, SD_H = 0.0497, 0.1121  # 2013-18 block sds of residual_value and H_corr, L1 descriptive view
RUN_IF_MDE_BELOW = 0.01  # fraction of m0, the lane brief's threshold


def main() -> None:
    n = pd.concat(
        [pd.read_parquet(f) for f in glob.glob(str(NAMES / "crsp_a_stock.dsenames.*.parquet"))]
    )
    n["namedt"] = pd.to_datetime(n["namedt"])
    first = n.groupby("permno")["namedt"].min()
    tick_perm = n.sort_values("namedt").groupby("ticker")["permno"].last()
    b = lib.load_base()
    b["block"] = lib.block_of(b["year"])
    perm = b["permno"].where(b["permno"].notna(), b["ticker"].map(tick_perm))
    b["first_namedt"] = perm.map(first)
    print(f"events {len(b)}; with a listing date {b['first_namedt'].notna().sum()}")
    b["listed_days"] = (b["entry_date"] - b["first_namedt"]).dt.days
    out: dict = {}
    for name, _, _ in lib.CFG.blocks:
        g = b[b["block"] == name]
        for lab, cut in (("lt1y", FIRST_YEAR_DAYS), ("lt2y", TWO_YEAR_DAYS)):
            t = g["listed_days"] < cut
            nt, nc = int(t.sum()), int((~t & g["listed_days"].notna()).sum())
            rec = {"n_treated": nt, "n_control": nc, "n_names": int(g.loc[t, "ticker"].nunique())}
            if nt > 0:
                rec["mde_rv_pct"] = 100 * min_detectable_effect(nt, nc, SD_RV)
                rec["mde_H_pct"] = 100 * min_detectable_effect(nt, nc, SD_H)
            out[f"{name}_{lab}"] = rec
            print(name, lab, rec)
    disc = out["2013-18_lt1y"]
    run = disc.get("mde_rv_pct", np.inf) < 100 * RUN_IF_MDE_BELOW
    out["run"] = bool(run)
    print("run C3:", run)
    (HERE / "c3_mde.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
