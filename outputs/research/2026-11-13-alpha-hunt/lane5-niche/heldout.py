"""
heldout.py
The single held-out read (2019-24) of early_in_industry, as frozen in freeze_early_in_industry.md.

Usage
-----
    python heldout.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

import lib
from round2 import expanding_name_mean

HERE = Path(__file__).resolve().parent


def main() -> None:
    note = HERE / "freeze_early_in_industry.md"
    print(f"freeze note sha256 {hashlib.sha256(note.read_bytes()).hexdigest()[:16]}")
    d = lib.load()
    b = lib.causal_quantile_bins(d["peer_share"].to_numpy(float), d["announce_date"], 3)
    early, ok = pd.Series(b == 0, index=d.index), pd.Series(b >= 0, index=d.index)
    r = lib.score(
        d, early, ok, "heldout", hyp="early_in_industry", trial_id=1770,
        label="confirmatory read, frozen",
        mechanism="frozen: bottom causal tercile of the share of industry-group peers reported "
        "before entry; early reporters carry over-insured common uncertainty",
    )
    blk = d[ok & d.year.between(2019, 2024) & (d.im_bin >= 0)].assign(early=early)
    blk = blk.assign(yr=blk["y"] - blk.groupby("cell")["y"].transform("mean"))
    print("by year: n and mean cell-residual y, rest | early")
    print(blk.groupby(["year", "early"])["yr"].agg(["size", "mean"]).round(4).unstack().to_string())
    print()
    dn = d.copy()
    dn["y"] = d["y"] - expanding_name_mean(d, "y")
    dn["H"] = d["H"] - expanding_name_mean(d, "H")
    lib.score(
        dn, early, ok & dn["y"].notna(), "heldout", hyp="early_in_industry", trial_id=1771,
        label="secondary on the frozen read, within name",
        mechanism="frozen secondary: as 1770 with outcomes less the name's own prior mean",
    )
    print(f"\nprimary verdict: {r['verdict'].upper()}")


if __name__ == "__main__":
    main()
