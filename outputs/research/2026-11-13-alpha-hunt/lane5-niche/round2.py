"""
round2.py
Round 2 of the lane5-niche hunt, discovery block 2013-18. Hypotheses follow from diag1.log: the
seller keeps more on the first reporters of an industry and less on the last, the reverse of the
round 1 "information already revealed" prior.

Usage
-----
    python round2.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import lib

SECTOR_MIN_PRIOR = 30
NAME_MIN_PRIOR = 4
OBSERVABLE = {"10", "55", "60"}  # energy, utilities, real estate


def expanding_name_mean(d: pd.DataFrame, col: str) -> np.ndarray:
    """Mean of `col` over the same ticker's strictly earlier events; NaN below NAME_MIN_PRIOR."""
    out = np.full(len(d), np.nan)
    for _, g in d.sort_values("announce_date").groupby("ticker"):
        v = g[col].to_numpy(float)
        cs = np.concatenate([[0.0], np.cumsum(v)[:-1]])
        n = np.arange(len(v))
        out[d.index.get_indexer(g.index)] = np.where(n >= NAME_MIN_PRIOR, cs / np.maximum(n, 1), np.nan)
    return out


def sector_scores(d: pd.DataFrame) -> pd.DataFrame:
    """Expanding sector mean of cell-residual y from strictly earlier announcement dates."""
    cell_sum: dict[int, float] = {}
    cell_n: dict[int, int] = {}
    sec_sum: dict[str, float] = {}
    sec_n: dict[str, int] = {}
    top = np.zeros(len(d), bool)
    defined = np.zeros(len(d), bool)
    order = d.sort_values("announce_date")
    for _, g in order.groupby("announce_date"):
        ranked = sorted(
            ((s, sec_sum[s] / sec_n[s]) for s in sec_n if sec_n[s] >= SECTOR_MIN_PRIOR),
            key=lambda kv: -kv[1],
        )
        if len(ranked) >= 6:
            best = {s for s, _ in ranked[:3]}
            for ix, s in zip(g.index, g["sector"], strict=True):
                if isinstance(s, str) and s in dict(ranked):
                    defined[d.index.get_loc(ix)] = True
                    top[d.index.get_loc(ix)] = s in best
        for s, c, y in zip(g["sector"], g["cell"], g["y"], strict=True):
            if c < 0 or not np.isfinite(y):
                continue
            if cell_n.get(c, 0) >= 20 and isinstance(s, str):
                r = y - cell_sum[c] / cell_n[c]
                sec_sum[s] = sec_sum.get(s, 0.0) + r
                sec_n[s] = sec_n.get(s, 0) + 1
            cell_sum[c] = cell_sum.get(c, 0.0) + y
            cell_n[c] = cell_n.get(c, 0) + 1
    return pd.DataFrame({"sec_top": top, "sec_def": defined}, index=d.index)


def main() -> None:
    d = lib.load()
    T = pd.Series(True, index=d.index)
    b = lib.causal_quantile_bins(d["peer_share"].to_numpy(float), d["announce_date"], 3)
    early, early_def = pd.Series(b == 0, index=d.index), pd.Series(b >= 0, index=d.index)
    d[["early", "early_def"]] = np.column_stack([early, early_def])
    lib.score(d, early, early_def, "discovery", hyp="early_in_industry", trial_id=1759,
              mechanism="bottom causal tercile of the share of industry-group peers already "
              "reported: the first reporters carry unresolved industry uncertainty that buyers "
              "over-insure (Savor and Wilson 2016 early-announcer premium); feature dated entry-1")
    print()
    lib.score(d, d["peer_week"] == 0, d["peer_week"].notna(), "discovery",
              hyp="no_peer_prior_week", trial_id=1760,
              mechanism="no same-industry peer reported in the 7 days before entry: same "
              "mechanism as early_in_industry on a narrower peer set and window")
    print()
    # mechanism check: is the effect position in the season, or which names report early?
    dn = d.copy()
    dn["y"] = d["y"] - expanding_name_mean(d, "y")
    dn["H"] = d["H"] - expanding_name_mean(d, "H")
    ok = early_def & dn["y"].notna()
    print(f"within-name funnel: early defined {int(early_def.sum())}, with >= {NAME_MIN_PRIOR} "
          f"prior events of the name {int(ok.sum())}")
    lib.score(dn, early, ok, "discovery", hyp="early_in_industry_within_name", trial_id=1761,
              mechanism="as 1759 with each outcome measured against the name's own mean over "
              "strictly earlier events, so a fixed name effect cannot carry it")
    print()
    obs = d["sector"].isin(OBSERVABLE)
    lib.score(d, obs, d["sector"].notna(), "discovery", hyp="observable_fundamentals_sectors",
              trial_id=1762,
              mechanism="energy, utilities and real estate: earnings are largely a function of "
              "public commodity prices, regulated rates or contracted rents, so the print "
              "reveals less than the straddle prices; static GICS sector")
    print()
    s = sector_scores(d)
    print(f"sector-rank funnel: defined {int(s['sec_def'].sum())}, treated {int(s['sec_top'].sum())}")
    lib.score(d, s["sec_top"], s["sec_def"], "discovery", hyp="sector_expanding_top3",
              trial_id=1763,
              mechanism="the three sectors with the highest expanding mean of cell-residual "
              "residual value over strictly earlier events: a persistent sector premium")
    print()
    # balance beyond medians for the lead candidate
    blk = d[d.year.between(2013, 2018) & early_def & (d.im_bin >= 0)]
    print("early vs rest, discovery: tenor mix and sector mix (share of group)")
    print(pd.crosstab(blk["early"], blk["tenor"], normalize="index").round(3).to_string())
    print(pd.crosstab(blk["early"], blk["sector"], normalize="index").round(3).to_string())
    print(pd.crosstab(blk["early"], blk["im_bin"], normalize="index").round(3).to_string())
    print("early by year: n treated, mean cell-residual y treated minus rest")
    blk = blk.assign(yr=blk["y"] - blk.groupby("cell")["y"].transform("mean"))
    print(blk.groupby(["year", "early"])["yr"].agg(["size", "mean"]).round(4).unstack().to_string())


if __name__ == "__main__":
    main()
