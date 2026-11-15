"""
r1_persistence.py
Round 1, lane J: is there a persistent name component in residual value at all? Discovery block
2013-18 only. Year-to-year cross-name correlation of name-year mean residual against a
within-year name-shuffle null, and the variance share of a fixed name effect (ICC).

Trials 2,051 to 2,056 (descriptive measurements, logged because they set direction):
  2051 hold, net at touch          2052 buy-back, net at touch
  2053 hold, at the mid            2054 buy-back, gross at the mid (exit mid defined only)
  2055 hold, net, after spread / implied move / days-to-expiry controls
  2056 buy-back, net, after the same controls
Unlogged context rows: entry half-spread, log implied move and realised/implied move ratio.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/r1_persistence.py
"""

from __future__ import annotations

import lib

CTRL = ["half_spread", "log_im", "dte"]
DISC = lib.BLOCKS["discovery"]


def run(d, tid, hyp, col, controls, basis, mech, log=True):
    print(f"\n== {hyp} ({col}{' + controls' if controls else ''})")
    r = lib.within_block_residual(d, col, controls)
    p = lib.year_pair_persistence(d, r, DISC)
    ic = lib.icc(d, r, DISC)
    print(
        f"  year-pair r {p['r']:+.4f} [{p['ci'][0]:+.4f}, {p['ci'][1]:+.4f}] (Spearman "
        f"{p['spearman']:+.4f}); null pct {p['null_pct']:.1f}, null sd {p['null_sd']:.4f}; "
        f"name-years {p['n_pairs']}, names {p['n_names']}; per pair {p['per_pair']}"
    )
    print(
        f"  ICC {ic['icc']:.4f} (tau2 {ic['tau2']:.5f}, sigma2 {ic['sigma2']:.5f}, name sd "
        f"{ic['tau_sd_units']:.4f}); tau2 null pct {ic['null_pct']:.1f}"
    )
    if log:
        res = {
            "hyp": hyp, "block": "discovery 2013-2018", "N": p["n_pairs"], "n_treated": "",
            "n_names": p["n_names"], "effect": p["r"], "ci_low": p["ci"][0],
            "ci_high": p["ci"][1], "t": p["t"], "null_pct": p["null_pct"],
            "treated_level": ic["icc"], "pool_level": ic["null_pct"],
        }
        lib.log_trial(tid, res, mechanism=mech, basis=basis, label="descriptive")


def main() -> None:
    d = lib.load()
    d = d[d["im_bin"] >= 0]
    print(f"[funnel] causal cell assigned {len(d)}; discovery {int(d.year.between(*DISC).sum())}")
    b_r = ("Pearson r of name-year mean cell x year residual, consecutive years, Fisher-z pooled;"
           " treated_level holds the ICC, pool_level its null pct; outcome ")
    mech = ("names whose event straddles are chronically over-priced after costs, through "
            "option-market structure, investor base or dealers, keep their residual value "
            "from one year to the next")
    run(d, 2051, "J01 persistence, hold net", "y", None,
        b_r + "y = H per unit mid premium, net at touch", mech)
    run(d, 2052, "J02 persistence, buy-back net", "yb", None,
        b_r + "yb = B per unit mid premium, net at touch", mech)
    run(d, 2053, "J03 persistence, hold at mid", "y_mid", None,
        b_r + "y_mid = H_mid per unit mid premium, at the mid", mech + "; at the mid, so a "
        "persistent spread cannot carry it")
    run(d, 2054, "J04 persistence, buy-back gross at mid", "yb_mid", None,
        b_r + "1 - exit mid / entry mid, gross; exit mid defined only", mech + "; at the mid")
    run(d, 2055, "J05 persistence, hold net, after controls", "y", CTRL,
        b_r + "y net at touch, less OLS on entry half-spread, log implied move, days to expiry",
        mech + "; remainder after the name's spread, implied move and tenor")
    run(d, 2056, "J06 persistence, buy-back net, after controls", "yb", CTRL,
        b_r + "yb net at touch, less the same OLS", mech + "; remainder after controls")
    print("\n-- context (not trials): persistence of characteristics and of the move ratio")
    for col in ("half_spread", "log_im", "ri"):
        run(d, None, f"context {col}", col, None, "", "", log=False)


if __name__ == "__main__":
    main()
