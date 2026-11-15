"""score_r3.py: round 3 on the DISCOVERY block (2019-2021), fixed windows and bounded exits.

Trials 2,001 to 2,007 (trial_log.txt addenda 1 and 2). Prints per-event detail, the right-driver
split and an attrition check. Held-out rows are not read.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from lib_score import level, log_trial, paired, usable

pd.set_option("display.width", 240)
W = pd.read_parquet("windows3_priced.parquet")
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

# H-A1 / H-P1 levels, net at touch
for cat, tid in [("adcomm", 2003), ("product", 2006)]:
    r = level(evs[cat], "pnl_touch_m0")
    show(f"{cat} level touch", r)
    log_trial(T, {"trial_id": tid, "hypothesis": f"{cat} event windows short ATM straddle net at "
                  "touch > 0 (round-3 measurement)", "mechanism": "buyers pay for a scheduled "
                  "binary outcome as before earnings", "block": B, **r, "null_percentile": "",
                  "basis": "per trade, share of m0, net at touch, bounded exit where unquoted",
                  "verdict": verdict(r, False)})
# H-A2 / H-P2 paired
for cat, tid in [("adcomm", 2004), ("product", 2007)]:
    r, _ = paired(evs[cat], cts[cat], "pnl_mid_m0")
    show(f"{cat} paired mid", r)
    log_trial(T, {"trial_id": tid, "hypothesis": f"{cat} event minus control gross at mid > 0 "
                  "(round-3 measurement)", "mechanism": "event premium priced exceeds the event "
                  "move beyond the ordinary variance premium", "block": B, **r, "basis": MID,
                  "verdict": verdict(r)})
# H-A3 material subset
ea = evs["adcomm"]
r, _ = paired(ea[ea["material"].astype(bool)], cts["adcomm"], "pnl_mid_m0")
show("adcomm material paired mid", r)
log_trial(T, {"trial_id": 2005, "hypothesis": "adcomm material sponsors event minus control gross "
              "at mid > 0", "mechanism": "a committee moves only a stock whose value rests on the "
              "product", "block": B, **r, "basis": MID, "verdict": verdict(r)})
# H-A4 implied-jump subset vs rest (selector inside AdComm events)
sel = ea["impl_jump_abs"] >= 0.02
r_sel, d_all = paired(ea, cts["adcomm"], "pnl_mid_m0")
d_all = d_all.join(ea.set_index("event_id")["impl_jump_abs"])
dsel = d_all[d_all["impl_jump_abs"] >= 0.02]
from lib_score import date_clustered_ci, matched_random_null  # noqa: E402

if len(dsel) >= 2 and len(dsel) < len(d_all):
    ci = date_clustered_ci(dsel["diff"], dsel["event_date"], stat=np.mean)
    nc = matched_random_null(d_all["diff"].to_numpy(float),
                             (d_all["impl_jump_abs"] >= 0.02).to_numpy(bool), stat=np.mean)
    hw = (ci.high - ci.low) / 2
    r4 = {"N": ci.n, "effect": ci.point, "ci_low": ci.low, "ci_high": ci.high,
          "t": ci.point / (hw / 1.96) if hw > 0 else np.nan, "null_percentile": nc.percentile}
else:
    r4 = {"N": len(dsel), "effect": np.nan, "ci_low": np.nan, "ci_high": np.nan, "t": np.nan,
          "null_percentile": np.nan}
show("adcomm implied-jump>=2% paired mid", r4)
log_trial(T, {"trial_id": 2001, "hypothesis": "adcomm events with entry implied jump >= 2% "
              "(two-expiry split), paired event minus control gross at mid > 0, selector vs "
              "other adcomm events", "mechanism": "the event premium exists only where buyers "
              "paid for a jump", "block": B, **r4,
              "basis": MID + "; null = matched random among adcomm events",
              "verdict": verdict(r4) if np.isfinite(r4["t"]) else "not scoreable"})
# H-X1 pooled, net at touch, paired
pe = pd.concat([evs["adcomm"], evs["product"]])
pc = pd.concat([cts["adcomm"], cts["product"]])
r, _ = paired(pe, pc, "pnl_touch_m0")
show("pooled paired touch", r)
log_trial(T, {"trial_id": 2002, "hypothesis": "pooled scheduled events (adcomm + product) event "
              "minus control net at touch > 0", "mechanism": "event surplus clears the spread",
              "block": B, **r, "basis": "per trade, share of m0, net at touch, paired",
              "verdict": verdict(r)})

# descriptives, right driver, detail
for cat in ["adcomm", "product"]:
    ev, ct = evs[cat], cts[cat]
    print(f"\n#### {cat}: events {len(ev)} (bounded {int(ev['bounded_exit'].sum())}), "
          f"controls {len(ct)} (bounded {int(ct['bounded_exit'].sum())})")
    for col in ["pnl_mid_m0", "pnl_touch_m0", "pnl_touch_prem", "crush_vp", "vega_pnl_m0",
                "entry_halfspread_prem", "real_abs", "impl_abs_window", "impl_jump_abs"]:
        a, c = level(ev, col), level(ct, col)
        print(f"  {col:22s} event {a['effect']:+.4f} [{a['ci_low']:+.4f},{a['ci_high']:+.4f}] "
              f"N={a['N']} | control {c['effect']:+.4f} [{c['ci_low']:+.4f},{c['ci_high']:+.4f}]"
              f" N={c['N']}")
    cols = ["event_id", "ticker", "event_date", "material", "entry", "exit", "dte_entry",
            "bounded_exit", "iv0", "crush_vp", "impl_jump_abs", "real_abs", "pnl_mid_m0",
            "pnl_touch_m0", "vega_pnl_m0"]
    print(ev[cols].sort_values("pnl_mid_m0").to_string(index=False, float_format="%.4f"))
    ev[cols].to_csv(f"detail_r3_{cat}.csv", index=False)

# attrition: realised close-to-close move (CRSP cache) for priced vs unpriced discovery events
spot_dir = r"C:\Users\jodor\Documents\QUANTT_IVCrush_Project\data\cache\postea_spots_crsp"
e0 = w[w["shift"] == 0].copy()
moves = []
for _, r0 in e0.iterrows():
    p = os.path.join(spot_dir, f"{r0['ticker']}.parquet")
    if not os.path.exists(p):
        moves.append(np.nan)
        continue
    s = pd.read_parquet(p).set_index("date")["close"]
    s.index = pd.to_datetime(s.index)
    before = s[s.index < r0["event_date"]]
    after = s[s.index > r0["event_date"]]
    moves.append(abs(np.log(after.iloc[0] / before.iloc[-1]))
                 if len(before) and len(after) else np.nan)
e0["crsp_move"] = moves
e0["priced"] = (e0["price_status"] == "ok") & (~e0["earn_in_window"].fillna(True).astype(bool))
print("\nattrition (discovery): CRSP |log move| D-1 close to D+1 close")
print(e0.groupby(["category", "priced"])["crsp_move"].agg(["count", "mean", "median"]))
