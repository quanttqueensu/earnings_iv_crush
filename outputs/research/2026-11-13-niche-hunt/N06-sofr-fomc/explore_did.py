"""explore_did.py: discovery-only difference-in-differences of the variance payoff in bp^2.

Event premium = mean pi over FOMC dates minus mean pi over control dates, where
pi = V_{t-1} - V_{t+1} - dF^2 per window, averaged within date. Also the implied and realised
components separately, and the row-noise floor (SD of dV on controls).

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N06-sofr-fomc/explore_did.py --trial0 2234
"""

from __future__ import annotations

import argparse
import dataclasses
import json

import numpy as np

import n06_lib as L

BANDS = [("pooled", 30, 730), ("30-180", 30, 180), ("181-400", 181, 400), ("401-730", 401, 730)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trial0", type=int, required=True)
    ap.add_argument("--vcol", default="V_bin")
    a = ap.parse_args()
    mpt = L.load_mpt()
    win = L.block(L.build_windows(mpt, L.load_releases()), "discovery")
    rows = []
    for k, (name, lo, hi) in enumerate(BANDS):
        L.CFG = dataclasses.replace(L.CFG, h_min=lo, h_max=hi)
        pay = L.window_payoffs(mpt, win, vcol=a.vcol)
        d = L.per_date(pay)
        f, c = d[d.arm == "fomc"], d[d.arm == "control"]
        res = dict(
            trial=a.trial0 + k, band=name, vcol=a.vcol, n_fomc=len(f), n_control=len(c),
            pi_effect_bp2=L.diff_ci(f["pi"].to_numpy(), c["pi"].to_numpy()),
            implied_excess_bp2=L.diff_ci(f["dV"].to_numpy(), c["dV"].to_numpy()),
            realised_excess_bp2=L.diff_ci(f["dF2"].to_numpy(), c["dF2"].to_numpy()),
            control_dV_sd_bp2=float(c["dV"].std()),
            control_V0_mean_bp2=float((c["P0"] / L.CFG.atm_straddle).pow(2).mean()),
            fomc_dF2_median_bp2=float(f["dF2"].median()),
            control_dF2_median_bp2=float(c["dF2"].median()),
        )
        rows.append(res)
        print(json.dumps(res))
    out = L.HERE / f"trial_{a.trial0}_{a.trial0 + len(BANDS) - 1}_did_discovery.json"
    out.write_text(json.dumps(rows, indent=1))
    print(f"[written] {out}")
    _ = np


if __name__ == "__main__":
    main()
