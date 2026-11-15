"""score_r4.py: round 4 on the DISCOVERY block, smile-interpolated exit marks.

Trials 2,008 to 2,013. H-A1, H-A2, H-P1, H-P2 re-scored on the round-4 measurement; H-P3 (long
straddle across product events, discovery-derived from the round-3 sign) and H-X1 pooled.
Held-out rows are not read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib_score import level, log_trial, paired, usable

pd.set_option("display.width", 240)
W = pd.read_parquet("windows4_priced.parquet")
W["bid1"] = 2 * W["mid1"] - W["ask1"]
W["long_touch_prem"] = (W["bid1"] - W["ask0"]) / W["ask0"]
W["long_mid_prem"] = (W["mid1"] - W["mid0"]) / W["mid0"]
w = W[W["block"] == "disc_2019_21"]
T = "trials.csv"
B = "discovery 2019-21"
MID = "per trade, share of m0, gross at mid, paired event minus mean of same-name controls"


def verdict(r: dict, need_null: bool = True) -> str:
    ok = r["ci_low"] > 0 and r["t"] >= 3 and (not need_null or r["null_percentile"] >= 95)
    return "passes discovery bar" if ok else "fails discovery"


def show(name: str, r: dict) -> None:
    print(f"{name}: N={r['N']} eff={r['effect']:+.4f} [{r['ci_low']:+.4f},{r['ci_high']:+.4f}] "
          f"t={r['t']:+.2f} null={r.get('null_percentile', float('nan'))}")


evs, cts = {}, {}
for cat in ["adcomm", "product"]:
    evs[cat], cts[cat] = usable(w[w["category"] == cat])
    print(f"{cat}: events {len(evs[cat])} (model-marked exits "
          f"{int(evs[cat]['bounded_exit'].sum())}), controls {len(cts[cat])}")

for cat, tid in [("adcomm", 2008), ("product", 2010)]:
    r = level(evs[cat], "pnl_touch_m0")
    show(f"{cat} short level touch", r)
    log_trial(T, {"trial_id": tid, "hypothesis": f"{cat} event windows short ATM straddle net at "
                  "touch > 0 (round-4 smile exit marks)", "mechanism": "buyers pay for a "
                  "scheduled binary outcome", "block": B, **r, "null_percentile": "",
                  "basis": "per trade, share of m0, net at touch; unquoted exits Black-76 on "
                  "interpolated smile + ATM half-spread", "verdict": verdict(r, False)})
for cat, tid in [("adcomm", 2009), ("product", 2011)]:
    r, _ = paired(evs[cat], cts[cat], "pnl_mid_m0")
    show(f"{cat} short paired mid", r)
    log_trial(T, {"trial_id": tid, "hypothesis": f"{cat} event minus control short straddle "
                  "gross at mid > 0 (round-4 smile exit marks)", "mechanism": "event premium "
                  "exceeds event move beyond ordinary VRP", "block": B, **r, "basis": MID,
                  "verdict": verdict(r)})
r = level(evs["product"], "long_touch_prem")
show("product LONG level touch (premium)", r)
log_trial(T, {"trial_id": 2012, "hypothesis": "LONG ATM straddle across megacap product events, "
              "net at touch > 0 (discovery-derived: reversal of the round-3 short result)",
              "mechanism": "product events realise about 3x the control move while the term "
              "structure prices almost no jump", "block": B, **r, "null_percentile": "",
              "basis": "per trade, share of premium paid (entry ask), net at touch",
              "verdict": verdict(r, False)})
rp, _ = paired(evs["product"], cts["product"], "long_touch_prem")
show("product LONG paired touch (premium)", rp)
pe = pd.concat([evs["adcomm"], evs["product"]])
pc = pd.concat([cts["adcomm"], cts["product"]])
r, _ = paired(pe, pc, "pnl_touch_m0")
show("pooled short paired touch", r)
log_trial(T, {"trial_id": 2013, "hypothesis": "pooled scheduled events short straddle event "
              "minus control net at touch > 0 (round-4 marks)", "mechanism": "event surplus "
              "clears the spread", "block": B, **r, "basis": "per trade, share of m0, net at "
              "touch, paired", "verdict": verdict(r)})

for cat in ["adcomm", "product"]:
    ev, ct = evs[cat], cts[cat]
    print(f"\n#### {cat}")
    for col in ["pnl_mid_m0", "pnl_touch_m0", "long_touch_prem", "crush_vp", "real_abs",
                "impl_abs_window", "impl_jump_abs"]:
        a, c = level(ev, col), level(ct, col)
        print(f"  {col:18s} event {a['effect']:+.4f} [{a['ci_low']:+.4f},{a['ci_high']:+.4f}] "
              f"N={a['N']} | control {c['effect']:+.4f} [{c['ci_low']:+.4f},{c['ci_high']:+.4f}]"
              f" N={c['N']}")
    print(f"  median real/implied window move: event "
          f"{(ev['real_abs'] / ev['impl_abs_window']).median():.2f}, control "
          f"{(ct['real_abs'] / ct['impl_abs_window']).median():.2f}")
    cols = ["event_id", "ticker", "event_date", "dte_entry", "bounded_exit", "iv0", "crush_vp",
            "impl_jump_abs", "real_abs", "pnl_mid_m0", "pnl_touch_m0", "long_touch_prem"]
    print(ev[cols].sort_values("pnl_mid_m0").to_string(index=False, float_format="%.4f"))
