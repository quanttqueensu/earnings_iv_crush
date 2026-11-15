"""score_heldout.py: the single frozen held-out read for N06 (2025-01-01 to 2026-11-12).

Trial 2,238: pre-registered primary (V from quartiles, horizons 30-730 days), P1 and P2.
Trial 2,239: secondary bp^2 decomposition (V from bins, same band), reported, not passed on.
Sensitivities (not trials): events without coincident CPI or payrolls; SEP versus non-SEP.

Refuses to run if the output already exists, so the block is read once.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N06-sofr-fomc/score_heldout.py
"""

from __future__ import annotations

import json

import numpy as np

import n06_lib as L

OUT = L.HERE / "heldout_2238_2239.json"


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists: the held-out block has been read")
    mpt = L.load_mpt()
    win = L.block(L.build_windows(mpt, L.load_releases()), "heldout")
    print(f"[heldout] anchors: {win['arm'].value_counts().to_dict()}")

    pay = L.window_payoffs(mpt, win, vcol="V_iqr")
    d = L.per_date(pay)
    f, c = d[d.arm == "fomc"], d[d.arm == "control"]
    eff = L.diff_ci(f["R"].to_numpy(), c["R"].to_numpy())
    mf = L.mean_ci(f["R"].to_numpy(), f["anchor"].to_numpy())
    mc = L.mean_ci(c["R"].to_numpy(), c["anchor"].to_numpy())
    net = L.mean_ci((f["R"] - f["hurdle_pass"]).to_numpy(), f["anchor"].to_numpy())
    p1 = eff[0] > 0 and eff[1] > 0
    p2 = net.point > 0 and net.low > 0
    clean = f[~f["coincident"].astype(bool)]
    sep = f[f["anchor"].isin(L.SEP)]
    nsep = f[~f["anchor"].isin(L.SEP)]
    res_primary = dict(
        trial=2238, block="heldout", vcol="V_iqr", n_fomc=len(f), n_control=len(c),
        R_fomc=[mf.point, mf.low, mf.high], R_control=[mc.point, mc.low, mc.high],
        effect=list(eff), net_fomc_pass_hurdle=[net.point, net.low, net.high],
        hurdle_pass_mean=float(f["hurdle_pass"].mean()), P1=bool(p1), P2=bool(p2),
        sens_effect_no_coincident=list(L.diff_ci(clean["R"].to_numpy(), c["R"].to_numpy())),
        n_no_coincident=len(clean),
        sens_effect_sep=list(L.diff_ci(sep["R"].to_numpy(), c["R"].to_numpy())),
        sens_effect_nonsep=list(L.diff_ci(nsep["R"].to_numpy(), c["R"].to_numpy())),
        n_sep=len(sep), n_nonsep=len(nsep),
    )

    pay_b = L.window_payoffs(mpt, win, vcol="V_bin")
    db = L.per_date(pay_b)
    fb, cb = db[db.arm == "fomc"], db[db.arm == "control"]
    res_secondary = dict(
        trial=2239, block="heldout", vcol="V_bin", n_fomc=len(fb), n_control=len(cb),
        pi_effect_bp2=list(L.diff_ci(fb["pi"].to_numpy(), cb["pi"].to_numpy())),
        implied_excess_bp2=list(L.diff_ci(fb["dV"].to_numpy(), cb["dV"].to_numpy())),
        realised_excess_bp2=list(L.diff_ci(fb["dF2"].to_numpy(), cb["dF2"].to_numpy())),
        effect_R=list(L.diff_ci(fb["R"].to_numpy(), cb["R"].to_numpy())),
        control_dV_sd_bp2=float(cb["dV"].std()),
        fomc_dF2_median_bp2=float(fb["dF2"].median()),
        control_dF2_median_bp2=float(cb["dF2"].median()),
        realised_excess_share_of_V0=float(
            (fb["dF2"].mean() - cb["dF2"].mean()) / (fb["P0"] / L.CFG.atm_straddle).pow(2).mean()
        ),
    )
    out = dict(primary=res_primary, secondary=res_secondary)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    pe = f[["anchor", "R", "pi", "dV", "dF2", "P0", "n_windows", "coincident"]]
    print(pe.assign(anchor=pe["anchor"].dt.date).round(4).to_string(index=False))
    print(f"[written] {OUT}")
    _ = np


if __name__ == "__main__":
    main()
