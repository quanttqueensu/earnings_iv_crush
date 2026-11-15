"""
s04_surface_round2.py
Round 2: main effects of 15:59 quote-surface states on the net buy-back return per unit premium.

Each spec names the feature, the side treated (top or bottom causal tercile) and the mechanism,
all written before the block is scored. Cuts use strictly earlier events.

Usage
-----
    python s04_surface_round2.py [--block 2014 2019] [--log] [--only 1695 1696]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import lib


def build() -> pd.DataFrame:
    d = pd.read_parquet(lib.HERE / "richness_events.parquet")
    f = pd.read_parquet(lib.HERE / "chain_features.parquet").drop(columns=["chain_status"])
    d = d.merge(f, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    d["abs_skew"] = d["wing_skew"].abs()
    gap = d["s1_t"] - d["front_t"]
    d["carry_mag"] = (np.log(d["front_fwd"] / d["s1_fwd"]).abs() / gap).where(gap > 0)
    # depth against the name's own history (mean of log depth over up to eight earlier events)
    d = d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    ld = np.log(d["depth_tot"].where(d["depth_tot"] > 0))
    prior = ld.groupby(d["ticker"]).transform(lambda s: s.shift(1).rolling(8, min_periods=3).mean())
    d["depth_rel"] = ld - prior
    # stored lead: wide front-minus-next IV spread with a tight entry spread
    t_hi, t_def = lib.top_bin(d, "iv_term_spread", 3)
    s_lo, s_def = lib.top_bin(d, "entry_spread", 3, sign=-1)
    d["lead_def"] = t_def & s_def
    d["lead"] = t_hi & s_lo
    d["tight"] = s_lo
    d["term_hi"] = t_hi
    return d


SPECS = [
    # id, feature, sign (+1 top tercile treated, -1 bottom), hypothesis, mechanism
    (1695, "wing_curv", -1, "H6 concave front smile on quotes (bottom tercile of wing over ATM IV)",
     "a bimodal event density prices ATM gamma above the wings (Alexiou et al. 2025); the ATM "
     "straddle is then rich against the move"),
    (1696, "depth_imb", 1, "H7 bid-heavy displayed depth on the held legs (top tercile)",
     "dealers short event vol lean on the bid to buy back; a bid-heavy touch marks net customer "
     "buying and a rich premium"),
    (1697, "last_vs_mid", 1, "H8 last-hour prints above the 15:59 mid (top tercile)",
     "customers lifting offers into the close are net buyers of event vol; dealers are short and "
     "premium is rich"),
    (1698, "lead", 1, "H9 stored lead: top-tercile front-minus-next IV spread with bottom-tercile entry spread",
     "a large event premium that can be sold without paying it away at the touch"),
    (1699, "abs_skew", 1, "H10 large absolute wing skew at one implied move (top tercile)",
     "one-sided protection demand lifts the whole front smile including the ATM straddle"),
    (1700, "carry_mag", 1, "H11 large absolute implied carry between the first two expiries (top tercile)",
     "a parity forward far from carry marks borrow cost or constrained supply; options replace "
     "the stock and are bid, magnitude only"),
    (1701, "depth_rel", -1, "H12 displayed depth thin against the name's own history (bottom tercile)",
     "dealers who have pulled size are charging for event risk, so the mid is rich"),
    (1702, "tight", 1, "H13 bottom-tercile entry spread alone (control for H9)",
     "a tight quote means the measured cost overstates what is paid; at a fixed cost basis it "
     "should not lift the mid-marked return"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", nargs=2, type=int, default=[2014, 2019])
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--only", nargs="*", type=int)
    a = ap.parse_args()
    blk = (a.block[0], a.block[1])
    d = build()
    d.to_parquet(lib.HERE / "all_features.parquet")
    m = d["year"].between(*blk)
    cc = ["wing_curv", "depth_imb", "last_vs_mid", "abs_skew", "carry_mag", "depth_rel",
          "entry_spread", "iv_term_spread", "jump_share", "log_im", "dte", "rich_event"]
    print(d.loc[m, cc].corr(method="spearman").round(2).to_string())
    for tid, col, sign, hyp, mech in SPECS:
        if a.only and tid not in a.only:
            continue
        print(f"\n[{tid}] {hyp}")
        if d[col].dtype == bool:
            tr = d[col]
            df = d["lead_def"]
        else:
            tr, df = lib.top_bin(d, col, 3, sign)
            df = df & d[col].notna()
            print(lib.bins_table(d, col, blk, 3).to_string())
            print(lib.bins_table(d, col, blk, 3, by="tenor").drop(columns=["y", "im"]).to_string())
        res = lib.score(d, tr, df, blk)
        if a.log:
            ok = res.get("ci_low", -1) > 0 and res.get("null_pct", 0) >= 95 and res.get("t", 0) >= 3
            lib.log_trial(tid, hyp, mech, res, "pass discovery" if ok else "fail discovery")


if __name__ == "__main__":
    main()
