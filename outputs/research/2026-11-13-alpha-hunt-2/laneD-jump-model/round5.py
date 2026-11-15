"""
round5.py
Right-driver check on the strongest discovery read (bid above model-fair value, trial 1,888).
R_touch = (bid - model) / m0 rises as the entry spread narrows, and the outcome pays the spread,
so the flag may be the closed spread gate. (1,894) the spread-free threshold, mid above model-fair
value; (1,895) R_touch > 0 inside implied-move x tenor x entry half-spread tercile cells. M4 model.

Usage
-----
    python round5.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib
from selector import score


def main() -> None:
    e = pd.read_parquet(lib.HERE / "rich_m4.parquet")
    d = e[e["year"].between(*lib.BLOCKS["discovery"])]
    print(f"M4 discovery: share R_touch > 0 {np.nanmean(d['R_touch'] > 0):.3f},"
          f" share R > 0 {np.nanmean(d['R'] > 0):.3f}; Spearman R_touch vs half-spread"
          f" {d['R_touch'].corr(d['half_spread'], method='spearman'):+.3f}, R vs half-spread"
          f" {d['R'].corr(d['half_spread'], method='spearman'):+.3f}")
    score(e, "R", "yb", "discovery", 1894, fixed=0.0,
          hyp="m4 mid above model-fair value (R > 0) -> yb",
          mech="spread-free threshold: the mid exceeds the model's expected payoff")
    e["hs_bin"] = lib.causal_bins(e["half_spread"].to_numpy(float), e["announce_date"], 3)
    e2 = e[e["hs_bin"] >= 0].copy()
    e2["cell"] = e2["cell"] * 10 + e2["hs_bin"]
    score(e2, "R_touch", "yb", "discovery", 1895, fixed=0.0,
          hyp="m4 bid above model-fair value -> yb, cells implied move x tenor x half-spread",
          mech="the bid-above-fair flag pays beyond the entry spread it partly measures")


if __name__ == "__main__":
    main()


def driver_check() -> None:
    """(1,896) M4 demeaned richness inside implied-move x tenor x jump-share x half-spread cells."""
    e = pd.read_parquet(lib.HERE / "rich_m4.parquet")
    tv = e["jsplit_jump_var"] + e["jsplit_sd2"] * e["front_t"]
    e["jump_share"] = np.where(e["jsplit_valid"].astype(bool), e["jsplit_jump_var"] / tv, np.nan)
    e["js_bin"] = lib.causal_bins(e["jump_share"].to_numpy(float), e["announce_date"], 3)
    e["hs_bin"] = lib.causal_bins(e["half_spread"].to_numpy(float), e["announce_date"], 3)
    e2 = e[(e["js_bin"] >= 0) & (e["hs_bin"] >= 0)].copy()
    e2["cell"] = (e2["cell"] * 10 + e2["js_bin"]) * 10 + e2["hs_bin"]
    score(e2, "R_dm", "yb", "discovery", 1896,
          hyp="m4 top-tercile demeaned R_ratio -> yb, cells implied move x tenor x jump share x half-spread",
          mech="demeaned richness pays beyond both jump share and the entry spread")
