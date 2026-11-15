"""score_r1.py: round 2, the five pre-stated hypotheses re-scored after the strike-grid fix on the DISCOVERY block only (2019-2021).

Trials 1,996 to 2,000. Prints per-event detail for the diagnosis. Held-out rows are not read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib_score import level, log_trial, paired, usable

pd.set_option("display.width", 220)
w = pd.read_parquet("windows2_priced.parquet")
w = w[w["block"] == "disc_2019_21"]
T = "trials.csv"
B = "discovery 2019-21"


def verdict(r: dict, need_null: bool) -> str:
    ok = r["ci_low"] > 0 and r["t"] >= 3 and (not need_null or r["null_percentile"] >= 95)
    return "passes discovery bar" if ok else "fails discovery"


for cat, tid_level, tid_pair in [("adcomm", 1996, 1997), ("product", 1999, 2000)]:
    ev, ct = usable(w[w["category"] == cat])
    print(f"\n######## {cat}: usable event windows {len(ev)}, control windows {len(ct)}")
    r = level(ev, "pnl_touch_m0")
    print("level net touch per m0", r)
    log_trial(T, {"trial_id": tid_level, "hypothesis": f"{cat} event windows short ATM straddle "
                  "D-1 to D+1 net at touch > 0", "mechanism": "buyers pay for a scheduled binary "
                  "outcome as before earnings", "block": B, **r, "null_percentile": "",
                  "basis": "per trade, share of m0, net at touch (DoltHub bid/ask)",
                  "verdict": verdict(r, False)})
    rp, d = paired(ev, ct, "pnl_mid_m0")
    print("paired event-control gross mid per m0", rp)
    log_trial(T, {"trial_id": tid_pair, "hypothesis": f"{cat} event minus same-name control "
                  "windows (-28,-56d), short straddle gross at mid > 0",
                  "mechanism": "event premium priced exceeds event move delivered beyond the "
                  "ordinary variance premium", "block": B, **rp,
                  "basis": "per trade, share of m0, gross at mid, paired difference",
                  "verdict": verdict(rp, True)})
    if cat == "adcomm":
        evm = ev[ev["material"].astype(bool)]
        rm, dm = paired(evm, ct, "pnl_mid_m0")
        print("material subset paired", rm)
        log_trial(T, {"trial_id": 1998, "hypothesis": "adcomm material sponsors (not diversified "
                      "large pharma/medtech/tobacco) event minus control gross at mid > 0",
                      "mechanism": "a committee moves only a stock whose value rests on the product",
                      "block": B, **rm,
                      "basis": "per trade, share of m0, gross at mid, paired difference",
                      "verdict": verdict(rm, True)})
    # descriptives
    for col in ["pnl_mid_m0", "pnl_touch_m0", "pnl_mid_prem", "pnl_touch_prem", "crush_vp",
                "spread_cost_m0", "entry_halfspread_prem"]:
        e = level(ev, col)
        c = level(ct, col)
        print(f"  {col:22s} event {e['effect']:+.4f} [{e['ci_low']:+.4f},{e['ci_high']:+.4f}] "
              f"N={e['N']} | control {c['effect']:+.4f} [{c['ci_low']:+.4f},{c['ci_high']:+.4f}] "
              f"N={c['N']}")
    for nm, g in [("event", ev), ("control", ct)]:
        print(f"  {nm}: median implied jump abs {g['impl_jump_abs'].median():.4f}, J2<=0 share "
              f"{(g['jump2'] <= 0).mean():.2f}, mean real_abs {g['real_abs'].mean():.4f}, "
              f"mean impl_abs_window {g['impl_abs_window'].mean():.4f}, "
              f"ratio of means {g['real_abs'].mean() / g['impl_abs_window'].mean():.2f}")
    cols = ["event_id", "ticker", "event_date", "sub", "material", "entry", "exit", "dte_entry",
            "iv0", "crush_vp", "impl_jump_abs", "real_abs", "pnl_mid_m0", "pnl_touch_m0"]
    det = ev[cols].merge(d[["ctrl"]].rename(columns={"ctrl": "ctrl_mid_m0"}),
                         left_on="event_id", right_index=True, how="left")
    det.to_csv(f"detail_r2_{cat}.csv", index=False)
    print(det.sort_values("pnl_mid_m0").round(4).to_string(index=False))
