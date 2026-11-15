"""s03_gate.py: economic gate, held-out surplus as a share of premium against the quoted touch.

Implements the economic gate in diagnosis.log. Costs come from the Cboe public delayed GLD and SLV
snapshots of 2026-11-13 (raw/touch/, s00_snap_touch.py) taken while the options session was open
(quote timestamp before 21:00 UTC, 16:00 ET): for each snapshot, the ATM straddle (strike where
call and put mids are closest, both legs two-sided) at the nearest expiry one session ahead and at
the expiry three sessions ahead; c_1 = half-spread / mid + 2 x 0.65 / (100 x mid), held to expiry;
c_3 = full spread / mid + 4 x 0.65 / (100 x mid), bought back. Median over snapshots. The surplus
shares pi_1 and pi_3 come from results_heldout.json (s02_score.py).

Usage:
    python outputs/research/2026-11-13-niche-hunt/N12-metals-macro/scripts/s03_gate.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
TOUCH = HERE / "raw" / "touch"
COMMISSION = 0.65  # USD per contract per side, the project's equity-option commission basis
MULT = 100.0
SESSION_CLOSE_UTC = pd.Timestamp("2026-11-13 21:00:00")
# Sessions after Friday 2026-11-13: Mon 16th is one session ahead, Wed 18th three sessions ahead.
EXPIRY_1, EXPIRY_3 = pd.Timestamp("2026-11-16"), pd.Timestamp("2026-11-18")


def straddle(df: pd.DataFrame, expiry: pd.Timestamp) -> tuple[float, float] | None:
    g = df[df["expiry"] == expiry]
    c = g[g["right"] == "C"].set_index("strike")
    p = g[g["right"] == "P"].set_index("strike")
    k = c.index.intersection(p.index)
    ok = [x for x in k if 0 < c.at[x, "bid"] <= c.at[x, "ask"] and 0 < p.at[x, "bid"] <= p.at[x, "ask"]]
    if not ok:
        return None
    cm = (c.loc[ok, "bid"] + c.loc[ok, "ask"]) / 2
    pm = (p.loc[ok, "bid"] + p.loc[ok, "ask"]) / 2
    ks = (cm - pm).abs().idxmin()
    mid = float(cm[ks] + pm[ks])
    spread = float(c.at[ks, "ask"] - c.at[ks, "bid"] + p.at[ks, "ask"] - p.at[ks, "bid"])
    return mid, spread


def main() -> None:
    rows = []
    for f in sorted(TOUCH.glob("touch_*.csv")):
        d = pd.read_csv(f, parse_dates=["expiry"])
        for sym, g in d.groupby("sym"):
            ts = pd.Timestamp(g["quote_ts"].iloc[0])
            if ts >= SESSION_CLOSE_UTC:
                print(f"{f.name} {sym}: quote {ts} after the close, excluded")
                continue
            s1, s3 = straddle(g, EXPIRY_1), straddle(g, EXPIRY_3)
            if s1 is None or s3 is None:
                print(f"{f.name} {sym}: missing two-sided ATM straddle, excluded")
                continue
            c1 = s1[1] / 2 / s1[0] + 2 * COMMISSION / (MULT * s1[0])
            c3 = s3[1] / s3[0] + 4 * COMMISSION / (MULT * s3[0])
            rows.append({"file": f.name, "sym": sym, "quote_ts": ts, "mid_1": s1[0],
                         "spread_1": s1[1], "c_1": c1, "mid_3": s3[0], "spread_3": s3[1], "c_3": c3})
    snaps = pd.DataFrame(rows)
    print(snaps.round(4).to_string(index=False))
    res = json.loads((HERE / "results_heldout.json").read_text(encoding="utf-8"))
    out = {}
    for tid, sym in (("2412", "GLD"), ("2413", "SLV")):
        s = snaps[snaps["sym"] == sym]
        if tid not in res or s.empty:
            print(f"trial {tid}: no held-out result or no snapshot, gate not evaluated")
            continue
        c1, c3 = float(np.median(s["c_1"])), float(np.median(s["c_3"]))
        p1, p3 = res[tid]["pi_1"], res[tid]["pi_3"]
        gate = bool(p1 > c1 or p3 > c3)
        out[tid] = {"pi_1": p1, "c_1": c1, "pi_3": p3, "c_3": c3, "gate_pass": gate,
                    "n_snapshots": int(len(s))}
        print(f"trial {tid} {sym}: pi_1 {p1:+.4f} vs c_1 {c1:.4f}; pi_3 {p3:+.4f} vs c_3 {c3:.4f}; "
              f"gate {'PASS' if gate else 'FAIL'} ({len(s)} snapshots)")
    (HERE / "gate_heldout.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
