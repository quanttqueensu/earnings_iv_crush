"""
r5_heldout.py
Held-out read, lane J: 2019-24, run once, exactly as frozen in freeze_J23_persistence.md
(trials 2,073 to 2,077) and freeze_J28_short_eb_selector.md (trial 2,078).

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/r5_heldout.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib
from earnings_iv_crush.research.protocol import sha256_file
from r2_components import split_half

HELD = lib.BLOCKS["heldout"]
HA, HB = (2019, 2021), (2022, 2024)
FREEZES = ("freeze_J23_persistence.md", "freeze_J28_short_eb_selector.md")
LAB = "exploratory (held-out read, frozen, discovery-derived)"


def persist(
    dblk, tid, hyp, col, controls, basis, label, mech="frozen in freeze_J23_persistence.md"
) -> dict:
    print(f"\n== {hyp}")
    r = lib.within_block_residual(dblk, col, controls)
    p = split_half(dblk, r, h1=HA, h2=HB)
    t = p["r"] / p["null_sd"]
    print(f"  r {p['r']:+.4f} [{p['ci'][0]:+.4f}, {p['ci'][1]:+.4f}] Spearman {p['spearman']:+.4f}; "
          f"null pct {p['null_pct']:.1f}; t {t:+.2f}; names {p['n']} (mean events per half "
          f"{p['nbar']:.1f}); implied name sd {p['tau_point']:.4f} (upper {p['tau_upper']:.4f})")
    lib.log_trial(tid, {"hyp": hyp, "block": "heldout 2019-21 vs 2022-24", "N": p["n"],
                        "n_treated": "", "n_names": p["n"], "effect": p["r"],
                        "ci_low": p["ci"][0], "ci_high": p["ci"][1], "t": t,
                        "null_pct": p["null_pct"], "treated_level": p["tau_point"],
                        "pool_level": p["tau_upper"]},
                  mechanism=mech, basis=basis, label=label)
    return p


def main() -> None:
    for f in FREEZES:
        path = lib.HERE / f
        if not path.exists():
            raise FileNotFoundError(f)
        print(f"[freeze] {f} sha256 {sha256_file(path)}")
    d = lib.load()
    d = d[d["im_bin"] >= 0].reset_index(drop=True)
    blk = d[d.year.between(*HELD)].reset_index(drop=True)
    short = blk[blk["tenor"] == "0-1d"].reset_index(drop=True)
    print(f"[funnel] held-out events {len(blk)}, 0-1 day {len(short)}")
    base = ("Pearson r of name mean cell x year residual, 2019-21 vs 2022-24, names with >= 3 "
            "events per half; treated_level = implied name sd, pool_level = its upper bound; ")
    persist(short, 2073, "J23 held-out persistence, hold y, 0-1 day (primary)", "y", None,
            base + "y = H per unit mid premium, net at touch, 0-1 day tenor", LAB)
    persist(blk, 2074, "J24 held-out persistence, hold y, all tenors (secondary)", "y", None,
            base + "y net at touch, all tenors", "exploratory (held-out secondary)")
    persist(blk, 2075, "J25 held-out persistence, buy-back yb, all tenors (secondary)", "yb",
            None, base + "yb = B per unit mid premium, net at touch, all tenors",
            "exploratory (held-out secondary)")
    persist(short, 2076, "J26 held-out persistence, hold y at the mid, 0-1 day", "y_mid", None,
            base + "y_mid = H_mid per unit mid premium, at the mid, 0-1 day", LAB)
    persist(short, 2077, "J27 held-out persistence, hold y after controls, 0-1 day", "y",
            ["half_spread", "log_im", "dte"],
            base + "y net less OLS on half-spread, log implied move, dte, 0-1 day", LAB)

    print("\n== J28 EB name selector, 0-1 day events, held-out")
    ds = d[d["tenor"] == "0-1d"].reset_index(drop=True)
    s = lib.causal_name_effect(ds, "y", "expiry", shrink_to="zero")
    v = s["shrunk"].to_numpy(float)
    held = ds.year.between(*HELD)
    print(f"  tau2 on held-out entry dates: median {s.loc[held, 'tau2'].median():.5f}, share zero "
          f"{(s.loc[held, 'tau2'] == 0).mean():.3f}; B median {s.loc[held, 'B'].median():.3f}")
    bins = lib.causal_quantile_bins(v, ds["announce_date"], 5, min_prior=100)
    flag, defined = pd.Series(bins == 4), pd.Series(bins >= 0)
    if not (flag & held).any():
        raise ValueError("J28: no treated event on the held-out block")
    r = lib.score(ds, flag, defined, "heldout", hyp="J28_short_eb_selector", ycol="y",
                  level_col="H")
    passed = r["ci_low"] > 0 and r["null_pct"] >= 95
    lib.log_trial(2078, r, mechanism="frozen in freeze_J28_short_eb_selector.md",
                  basis="within-cell treated minus untreated, per trade, y per unit mid premium, "
                  "net at touch, 0-1 day events; level H on m0 net at touch",
                  label=LAB + ("; fragile" if passed and r["effect_ex_top5"] <= 0 else ""),
                  passed=passed)
    sel = ds[flag & held & defined]
    print(f"  treated events by year: {sel.groupby('year').size().to_dict()}")


if __name__ == "__main__":
    main()
