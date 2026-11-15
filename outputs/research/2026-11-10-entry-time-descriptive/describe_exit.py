"""Descriptive only, no trial: the buy-back straddle's ask and spread through the exit day's last hour.

Usage: python outputs/research/2026-11-10-entry-time-descriptive/describe_exit.py
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

GRID = ["15:05", "15:15", "15:30", "15:45", "15:55", "15:59"]
for block in ("broad_2025_2026", "megacap_2023_2024"):
    rows, funnel = [], {"files": 0, "legs": 0, "no_ref": 0, "ok": 0}
    for f in sorted(glob.glob(str(ROOT / f"data/cache/flow/{block}/*_exit.parquet"))):
        funnel["files"] += 1
        d = pd.read_parquet(f, columns=["bid_px_00", "ask_px_00", "symbol"])
        d.index = d.index.tz_convert("America/New_York")
        day = d.index.max().normalize()
        legs = [g for _, g in d[d.index >= day].groupby("symbol")]
        if len(legs) != 2:
            funnel["legs"] += 1
            continue
        rec = {"day": day.tz_localize(None)}
        for t in GRID:
            ts = day + pd.Timedelta(t + ":00")
            bid = ask = 0.0
            for g in legs:
                q = g[g.index <= ts]
                if q.empty or not q["ask_px_00"].iloc[-1] > 0:
                    ask = np.nan
                    break
                bid += max(q["bid_px_00"].iloc[-1], 0.0)
                ask += q["ask_px_00"].iloc[-1]
            rec[f"bid_{t}"], rec[f"ask_{t}"] = (bid, ask) if np.isfinite(ask) else (np.nan, np.nan)
        if not np.isfinite(rec["ask_15:59"]):
            funnel["no_ref"] += 1
            continue
        funnel["ok"] += 1
        rows.append(rec)
    r = pd.DataFrame(rows)
    print(block, "funnel:", funnel)
    ref_mid = (r["bid_15:59"] + r["ask_15:59"]) / 2
    print("time   N     ask vs 15:59 ask, % of 15:59 mid (negative = cheaper to buy back) [95% CI]   mid vs 15:59 mid, %")
    for t in GRID:
        ok = np.isfinite(r[f"ask_{t}"])
        da = ((r[f"ask_{t}"] - r["ask_15:59"]) / ref_mid)[ok]
        dm = (((r[f"bid_{t}"] + r[f"ask_{t}"]) / 2 - ref_mid) / ref_mid)[ok]
        ci = date_clustered_ci(da, r.loc[ok, "day"], lambda a: float(np.mean(a)))
        print(f"{t}  {int(ok.sum()):5d}  {100*ci.point:+6.2f} [{100*ci.low:+6.2f}, {100*ci.high:+6.2f}]   {100*dm.mean():+6.2f}")
