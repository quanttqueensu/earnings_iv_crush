"""score_discovery.py: score an N06 configuration on the discovery block only (to 2024-12-31).

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N06-sofr-fomc/score_discovery.py \
        --trial 2232 [--vcol V_iqr|V_bin] [--hmin 30 --hmax 730]

Held-out anchors are removed before any payoff is computed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json

import numpy as np

import n06_lib as L


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trial", type=int, required=True)
    ap.add_argument("--vcol", default="V_iqr")
    ap.add_argument("--hmin", type=int, default=L.CFG.h_min)
    ap.add_argument("--hmax", type=int, default=L.CFG.h_max)
    a = ap.parse_args()
    L.CFG = dataclasses.replace(L.CFG, h_min=a.hmin, h_max=a.hmax)

    mpt = L.load_mpt()
    win = L.block(L.build_windows(mpt, L.load_releases()), "discovery")
    print(f"[discovery] anchors: {win['arm'].value_counts().to_dict()}")
    pay = L.window_payoffs(mpt, win, vcol=a.vcol)
    d = L.per_date(pay)
    f, c = d[d.arm == "fomc"], d[d.arm == "control"]
    eff = L.diff_ci(f["R"].to_numpy(), c["R"].to_numpy())
    mf = L.mean_ci(f["R"].to_numpy(), f["anchor"].to_numpy())
    mc = L.mean_ci(c["R"].to_numpy(), c["anchor"].to_numpy())
    net = L.mean_ci((f["R"] - f["hurdle_pass"]).to_numpy(), f["anchor"].to_numpy())
    netc = L.mean_ci((c["R"] - c["hurdle_pass"]).to_numpy(), c["anchor"].to_numpy())
    share_f = float(pay.loc[pay.arm == "fomc", "pi"].sum() / pay.loc[pay.arm == "fomc", "dV"].sum())
    share_c = float(
        pay.loc[pay.arm == "control", "pi"].sum() / pay.loc[pay.arm == "control", "dV"].sum()
    )
    res = dict(
        trial=a.trial, block="discovery", vcol=a.vcol, hmin=a.hmin, hmax=a.hmax,
        n_fomc=len(f), n_control=len(c), windows_per_date=float(d["n_windows"].mean()),
        R_fomc=[mf.point, mf.low, mf.high], R_control=[mc.point, mc.low, mc.high],
        effect=list(eff), net_fomc_pass_hurdle=[net.point, net.low, net.high],
        net_control_pass_hurdle=[netc.point, netc.low, netc.high],
        hurdle_pass_mean_fomc=float(f["hurdle_pass"].mean()),
        hurdle_low_mean_fomc=float(f["hurdle_low"].mean()),
        straddle_premium_bp_mean=float(f["P0"].mean()),
        dV_fomc_bp2=float(f["dV"].mean()), dV_control_bp2=float(c["dV"].mean()),
        dF2_fomc_bp2=float(f["dF2"].mean()), dF2_control_bp2=float(c["dF2"].mean()),
        pi_fomc_bp2=float(f["pi"].mean()), pi_control_bp2=float(c["pi"].mean()),
        premium_share_fomc=share_f, premium_share_control=share_c,
    )
    print(json.dumps(res, indent=1))
    per_event = f[["anchor", "R", "pi", "dV", "dF2", "P0", "n_windows", "coincident"]]
    print(per_event.assign(anchor=per_event["anchor"].dt.date).round(4).to_string(index=False))
    out = L.HERE / f"trial_{a.trial}_discovery.json"
    out.write_text(json.dumps(res, indent=1))
    print(f"[written] {out}")
    _ = np  # numpy kept for interactive use


if __name__ == "__main__":
    main()
