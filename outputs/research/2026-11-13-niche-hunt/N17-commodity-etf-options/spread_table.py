"""spread_table.py: ATM straddle touch cost as a share of premium, from delayed-quote snapshots.

For each ETF and each expiry in the snapshot, take the listed strike nearest spot, require a
two-sided quote on both the call and the put, and report the straddle mid, the round-trip touch
cost (call spread plus put spread: sell at the bids, buy back at the asks) and that cost as a share
of the mid. One-sided quotes are dropped and counted, never turned into a mid.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N17-commodity-etf-options/spread_table.py
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SNAPS = HERE / "raw" / "spreads"
OUT = HERE / "spread_table.csv"


def atm_rows(df: pd.DataFrame, snap_tag: str) -> list[dict]:
    rows: list[dict] = []
    asof = pd.Timestamp(re.search(r"\d{8}", snap_tag).group(0))
    for (sym, exp), g in df.groupby(["sym", "expiry"]):
        spot = float(g.spot.iloc[0])
        strikes = np.sort(g.strike.unique())
        k = float(strikes[np.argmin(np.abs(strikes - spot))])
        c = g[(g.strike == k) & (g.right == "C")]
        p = g[(g.strike == k) & (g.right == "P")]
        rec = {"snap": snap_tag, "sym": sym, "expiry": pd.Timestamp(exp).date(),
               "dte_cal": (pd.Timestamp(exp) - asof).days, "spot": spot, "strike": k}
        if c.empty or p.empty:
            rec["status"] = "missing_leg"
            rows.append(rec)
            continue
        cb, ca, pb, pa = (float(c.bid.iloc[0]), float(c.ask.iloc[0]),
                          float(p.bid.iloc[0]), float(p.ask.iloc[0]))
        if min(cb, pb) <= 0 or ca <= cb or pa <= pb:
            rec["status"] = "one_sided_or_crossed"
            rows.append(rec)
            continue
        mid = 0.5 * (cb + ca) + 0.5 * (pb + pa)
        rt = (ca - cb) + (pa - pb)
        rec.update(status="ok", call_bid=cb, call_ask=ca, put_bid=pb, put_ask=pa,
                   straddle_mid=mid, roundtrip_cost=rt, rt_cost_share=rt / mid,
                   half_spread_share=0.5 * rt / mid,
                   iv_call=float(c.iv.iloc[0]), iv_put=float(p.iv.iloc[0]))
        rows.append(rec)
    return rows


if __name__ == "__main__":
    out: list[dict] = []
    for f in sorted(SNAPS.glob("snap_*.csv")):
        tag = f.stem.replace("snap_", "")
        df = pd.read_csv(f, parse_dates=["expiry"])
        out.extend(atm_rows(df, tag))
    t = pd.DataFrame(out)
    t.to_csv(OUT, index=False)
    print(t.status.value_counts().to_string())
    ok = t[t.status == "ok"]
    pd.set_option("display.width", 200)
    cols = ["snap", "sym", "expiry", "dte_cal", "strike", "straddle_mid", "roundtrip_cost",
            "rt_cost_share", "iv_call"]
    print(ok[ok.dte_cal <= 40][cols].round(4).to_string(index=False))
    # Vehicle summary: median round-trip share at 5-10 and 21-35 days, with commission.
    ok = ok.assign(total=ok.rt_cost_share + 0.65 * 4 / (100 * ok.straddle_mid))
    summ = []
    for sym, g in ok.groupby("sym"):
        row = {"sym": sym, "spot": g.spot.iloc[0], "n_expiries_le40": int((g.dte_cal <= 40).sum())}
        for lo, hi, tag in [(5, 10, "7d"), (21, 35, "30d")]:
            h = g[g.dte_cal.between(lo, hi)]
            row[f"rt_touch_{tag}"] = h.rt_cost_share.median() if len(h) else np.nan
            row[f"rt_total_{tag}"] = h.total.median() if len(h) else np.nan
            row[f"n_{tag}"] = len(h)
        summ.append(row)
    s = pd.DataFrame(summ).sort_values("rt_total_7d")
    s.to_csv(HERE / "vehicle_cost_summary.csv", index=False)
    print(s.round(4).to_string(index=False))
