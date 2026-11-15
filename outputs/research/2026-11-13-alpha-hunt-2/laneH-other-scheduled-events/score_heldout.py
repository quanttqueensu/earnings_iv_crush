"""score_heldout.py: the single held-out read (2022-01-01 to 2024-11-08) under freeze_scheduled_events.md.

Trials 2,014 to 2,017. Also prints per-event detail and the pooled descriptive (both blocks).
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from lib_score import level, log_trial, paired, usable

FREEZE_SHA = "ee2c167faee4e12e1c3b865f6e579f5fb5195dc299a3e35043b76278a4522a82"
got = hashlib.sha256(open("freeze_scheduled_events.md", "rb").read()).hexdigest()
if got != FREEZE_SHA:
    raise SystemExit(f"freeze note changed: {got}")

pd.set_option("display.width", 240)
W = pd.read_parquet("windows4_priced.parquet")
W["bid1"] = 2 * W["mid1"] - W["ask1"]
W["long_touch_prem"] = (W["bid1"] - W["ask0"]) / W["ask0"]
T = "trials.csv"
B = "held-out 2022-01 to 2024-11"


def show(name: str, r: dict) -> None:
    print(f"{name}: N={r['N']} eff={r['effect']:+.4f} [{r['ci_low']:+.4f},{r['ci_high']:+.4f}] "
          f"t={r['t']:+.2f} null={r.get('null_percentile', float('nan'))}")


def conf(r: dict, need_null: bool) -> str:
    ok = r["ci_low"] > 0 and r["t"] >= 3 and (not need_null or r["null_percentile"] >= 95)
    return "CONFIRMATORY pass" if ok else "fails held-out (descriptive pilot)"


h = W[W["block"] == "held_2022_24"]
ep, cp = usable(h[h["category"] == "product"])
ea, ca = usable(h[h["category"] == "adcomm"])
print(f"held-out usable: product {len(ep)} events / {len(cp)} controls; adcomm {len(ea)} / {len(ca)}")

r, _ = paired(ep, cp, "long_touch_prem")
show("F1 2014 product long paired touch", r)
log_trial(T, {"trial_id": 2014, "hypothesis": "FROZEN F1: long straddle product events minus "
              "controls, net at touch > 0", "mechanism": "product events realise ~3x control move; "
              "term structure prices little jump", "block": B, **r,
              "basis": "per trade, share of premium paid, net at touch, paired",
              "verdict": conf(r, True)})
r = level(ep, "long_touch_prem")
show("F1 2015 product long level touch", r)
log_trial(T, {"trial_id": 2015, "hypothesis": "FROZEN F1: long straddle product events net at "
              "touch > 0 (level)", "mechanism": "as 2,014", "block": B, **r, "null_percentile": "",
              "basis": "per trade, share of premium paid, net at touch", "verdict": conf(r, False)})
r = level(ea, "pnl_touch_m0")
show("F2 2016 adcomm short level touch", r)
log_trial(T, {"trial_id": 2016, "hypothesis": "FROZEN F2: short straddle FDA AdComm events net "
              "at touch > 0", "mechanism": "buyers pay for a scheduled binary outcome", "block": B,
              **r, "null_percentile": "", "basis": "per trade, share of m0, net at touch",
              "verdict": conf(r, False)})
r, _ = paired(ea, ca, "pnl_mid_m0")
show("F2 2017 adcomm short paired mid", r)
log_trial(T, {"trial_id": 2017, "hypothesis": "FROZEN F2: short straddle AdComm minus controls "
              "gross at mid > 0", "mechanism": "event premium exceeds event move beyond VRP",
              "block": B, **r, "basis": "per trade, share of m0, gross at mid, paired",
              "verdict": conf(r, True)})

cols = ["event_id", "ticker", "event_date", "dte_entry", "bounded_exit", "iv0", "crush_vp",
        "impl_jump_abs", "real_abs", "pnl_mid_m0", "pnl_touch_m0", "long_touch_prem"]
for nm, ev in [("product", ep), ("adcomm", ea)]:
    print(f"\n#### held-out {nm}")
    print(ev[cols].sort_values("pnl_mid_m0").to_string(index=False, float_format="%.4f"))

print("\n#### POOLED both blocks (descriptive only)")
for cat in ["adcomm", "product"]:
    ev, ct = usable(W[W["category"] == cat])
    print(f"-- {cat}: events {len(ev)}, controls {len(ct)}")
    for col in ["pnl_mid_m0", "pnl_touch_m0", "pnl_touch_prem", "long_touch_prem", "crush_vp",
                "real_abs", "impl_abs_window", "impl_jump_abs", "entry_halfspread_prem"]:
        a, c = level(ev, col), level(ct, col)
        print(f"  {col:22s} event {a['effect']:+.4f} [{a['ci_low']:+.4f},{a['ci_high']:+.4f}] "
              f"N={a['N']} | control {c['effect']:+.4f} [{c['ci_low']:+.4f},{c['ci_high']:+.4f}]"
              f" N={c['N']}")
    pr, _ = paired(ev, ct, "pnl_mid_m0")
    show(f"  {cat} pooled paired short mid", pr)
    print(f"  median real/implied window move: event "
          f"{(ev['real_abs'] / ev['impl_abs_window']).median():.2f}, control "
          f"{(ct['real_abs'] / ct['impl_abs_window']).median():.2f}")
    if cat == "adcomm":
        m = ev[ev["material"].astype(bool)]
        print(f"  material sponsors: N={len(m)}, short mid mean {m['pnl_mid_m0'].mean():+.4f}, "
              f"touch {m['pnl_touch_m0'].mean():+.4f}, real_abs mean {m['real_abs'].mean():.4f}, "
              f"impl_jump_abs mean {m['impl_jump_abs'].mean():.4f}")
        d = ev[~ev["material"].astype(bool)]
        print(f"  diversified sponsors: N={len(d)}, short mid mean {d['pnl_mid_m0'].mean():+.4f},"
              f" touch {d['pnl_touch_m0'].mean():+.4f}, real_abs mean {d['real_abs'].mean():.4f}")
