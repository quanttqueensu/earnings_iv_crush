"""describe.py: descriptive context for evidence.md (no new configurations, no pass rules).

Prints (a) the realised and implied report-day excess in units of one ordinary trading day of
30-day implied variance, per family and block, and (b) the listed expiry weekdays in the
2026-11-13 snapshot.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N17-commodity-etf-options/describe.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DAYS_IN_30D = 21.0  # trading sessions in 30 calendar days, to express excess in ordinary days


def excess_days() -> None:
    for block in ["discovery", "heldout"]:
        p = pd.read_csv(HERE / f"pairs_{block}.csv")
        for fam, g in p.groupby("family"):
            real = (g.real_norm - g.ctrl_real_norm).mean() * DAYS_IN_30D
            imp = (g.imp_norm - g.ctrl_imp_norm).mean() * DAYS_IN_30D
            med = np.median(g.r2) / np.median(g.ctrl_r2)
            print(f"{block:9s} {fam:10s} N={len(g):4d} realised excess {real:+.2f} days, "
                  f"implied excess {imp:+.2f} days, median r2 ratio event/control {med:.2f}")


def expiry_cycle() -> None:
    f = HERE / "raw" / "spreads" / "snap_20261113_1435.csv"
    s = pd.read_csv(f, parse_dates=["expiry"])
    for sym, g in s.groupby("sym"):
        ex = sorted(g.expiry.unique())
        near = [pd.Timestamp(e) for e in ex if (pd.Timestamp(e) - pd.Timestamp("2026-11-13")).days <= 14]
        print(f"{sym}: expiries within 14 days: {[e.strftime('%a %d') for e in near]}")


if __name__ == "__main__":
    excess_days()
    expiry_cycle()
