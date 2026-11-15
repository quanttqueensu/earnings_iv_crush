"""
r7_diag.py
Descriptive robustness for logged trials 2,074 and 2,080 (no new trial): name carriage of the
2019-24 hold persistence, the causal EB tau2 on all-tenor hold residuals over 2019-24, and the
premium-to-margin ratio that converts per-premium figures to m0.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/r7_diag.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib

CTRL = ["half_spread", "log_im", "dte"]


def carriage(blk: pd.DataFrame, r: pd.Series, tag: str) -> None:
    x = blk.assign(_r=r).dropna(subset=["_r"])
    a = x[x.year.between(2019, 2021)].groupby("ticker")["_r"].agg(["mean", "size"])
    b = x[x.year.between(2022, 2024)].groupby("ticker")["_r"].agg(["mean", "size"])
    j = a.join(b, lsuffix="_a", rsuffix="_b", how="inner")
    j = j[(j.size_a >= 3) & (j.size_b >= 3)]
    za = (j.mean_a - j.mean_a.mean()) / j.mean_a.std()
    zb = (j.mean_b - j.mean_b.mean()) / j.mean_b.std()
    infl = (za * zb).sort_values(ascending=False)
    for k in (0, 5, 10):
        keep = j.drop(infl.index[:k])
        print(f"  {tag}: r without top-{k} influential names "
              f"{np.corrcoef(keep.mean_a, keep.mean_b)[0, 1]:+.4f} (names {len(keep)})")
    print(f"  {tag}: top-10 influential {', '.join(infl.index[:10])}")
    print(f"  {tag}: names positive in both halves {int(((j.mean_a > 0) & (j.mean_b > 0)).sum())},"
          f" negative in both {int(((j.mean_a < 0) & (j.mean_b < 0)).sum())}, of {len(j)}")


def main() -> None:
    d = lib.load()
    d = d[d["im_bin"] >= 0].reset_index(drop=True)
    blk = d[d.year.between(2019, 2024)].reset_index(drop=True)
    carriage(blk, lib.within_block_residual(blk, "y"), "J24 hold y")
    carriage(blk, lib.within_block_residual(blk, "y", CTRL), "J30 hold y after controls")
    ratio = (d["mid0"] / d["m0"]).median()
    print(f"\nmedian entry mid premium / m0 = {ratio:.3f} (premium units x this = m0 units)")
    s = lib.causal_name_effect(d, "y", "expiry", shrink_to="zero")
    h = d.year.between(2019, 2024)
    print(f"causal EB on all-tenor hold y, 2019-24 entry dates: tau2 median "
          f"{s.loc[h, 'tau2'].median():.5f}, share of events with tau2 = 0 "
          f"{(s.loc[h, 'tau2'] == 0).mean():.3f}, median B {s.loc[h, 'B'].median():.3f}; "
          f"by year tau2 median {s.loc[h].groupby(d.loc[h, 'year'])['tau2'].median().round(5).to_dict()}")


if __name__ == "__main__":
    main()
