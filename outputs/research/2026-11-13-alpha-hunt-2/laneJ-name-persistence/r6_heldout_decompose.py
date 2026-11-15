"""
r6_heldout_decompose.py
Post-read decomposition, lane J, 2019-24 (exploratory: the block was read by r5_heldout.py).
The frozen secondaries J24 (hold y, r +0.129) and J25 (buy-back yb, r +0.184) showed all-tenor
persistence on 2019-24. Is it the entry spread, the implied move or days to expiry inside the
tenor bucket, or something left over?

Trials
  2079 J29 split-half persistence of yb on 2019-24 after half-spread, log implied move and dte
  2080 J30 split-half persistence of y on 2019-24 after the same controls

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/r6_heldout_decompose.py
"""

from __future__ import annotations

import lib
from r5_heldout import HELD, persist

CTRL = ["half_spread", "log_im", "dte"]
LAB = "exploratory (post-read decomposition of a held-out secondary)"
BASE = ("Pearson r of name mean cell x year residual, 2019-21 vs 2022-24, names with >= 3 events "
        "per half, less OLS on entry half-spread, log implied move, dte; ")


def main() -> None:
    d = lib.load()
    d = d[d["im_bin"] >= 0].reset_index(drop=True)
    blk = d[d.year.between(*HELD)].reset_index(drop=True)
    persist(blk, 2079, "J29 held-out persistence, buy-back yb after controls", "yb", CTRL,
            BASE + "yb = B per unit mid premium, net at touch, all tenors", LAB,
            mech="if J25 is the entry spread or tenor mix inside the bucket, it vanishes here")
    persist(blk, 2080, "J30 held-out persistence, hold y after controls", "y", CTRL,
            BASE + "y = H per unit mid premium, net at touch, all tenors", LAB,
            mech="as J29 for the hold (J24)")
    print("\nentry half-spread persistence on the same split (context, not a trial):")
    r = lib.within_block_residual(blk, "half_spread")
    from r2_components import split_half

    p = split_half(blk, r, h1=(2019, 2021), h2=(2022, 2024))
    print(f"  r {p['r']:+.4f} [{p['ci'][0]:+.4f}, {p['ci'][1]:+.4f}], names {p['n']}")


if __name__ == "__main__":
    main()
