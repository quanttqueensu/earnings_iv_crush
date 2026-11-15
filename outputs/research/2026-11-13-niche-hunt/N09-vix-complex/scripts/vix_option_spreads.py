"""vix_option_spreads.py: half-spread as a share of premium for VIX options, from one public
Cboe delayed-quote snapshot (raw/snap/vix_opts_20261113.json, taken 2026-11-13 about 14:38 ET).

One snapshot on one day: a description of today's touch, not a history.

Usage
-----
    python -I scripts/vix_option_spreads.py <lane_dir>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def main(lane: Path) -> None:
    d = json.loads((lane / "raw/snap/vix_opts_20261113.json").read_text())
    rows = []
    for o in d["data"]["options"]:
        m = re.match(r"VIXW?(\d{6})([CP])(\d{8})", o["option"])
        if not m:
            continue
        rows.append({"sym": o["option"], "exp": pd.Timestamp("20" + m.group(1)), "cp": m.group(2),
                     "k": int(m.group(3)) / 1000, "bid": o["bid"], "ask": o["ask"],
                     "delta": o["delta"], "vega": o["vega"], "oi": o["open_interest"],
                     "weekly": o["option"].startswith("VIXW")})
    t = pd.DataFrame(rows)
    t = t[(t["bid"] > 0) & (t["ask"] > t["bid"])].copy()
    t["mid"] = (t["bid"] + t["ask"]) / 2
    t["half_share"] = (t["ask"] - t["bid"]) / 2 / t["mid"]
    print("spot VIX", d["data"]["current_price"], "VIX option iv30 (VVIX-like)", d["data"]["iv30"])
    out = []
    for exp, g in t.groupby("exp"):
        # near-the-money: |delta| between 0.35 and 0.65
        g2 = g[g["delta"].abs().between(0.35, 0.65)]
        if g2.empty:
            continue
        c = g2[g2["cp"] == "C"]
        p = g2[g2["cp"] == "P"]
        strad = None
        common = sorted(set(c["k"]) & set(p["k"]))
        if common:
            k = common[len(common) // 2]
            cc, pp = c[c["k"] == k].iloc[0], p[p["k"] == k].iloc[0]
            mid = cc["mid"] + pp["mid"]
            half = ((cc["ask"] - cc["bid"]) + (pp["ask"] - pp["bid"])) / 2
            vega = cc["vega"] + pp["vega"]
            strad = {"k": k, "mid": mid, "half_spread": half, "half_share": half / mid,
                     "vega_per_volpt": vega}
        out.append({"exp": exp.date().isoformat(), "n_ntm": len(g2),
                    "median_half_share_ntm": float(g2["half_share"].median()), "straddle": strad})
    for o in out[:6]:
        print(json.dumps(o, default=float))
    (lane / "logs/vix_option_spreads.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
