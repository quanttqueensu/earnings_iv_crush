"""
diag_path.py
Descriptive diagnosis of the reaction-session last hour: straddle mid, ask and half-spread by
minute (sum of both legs, m0 units, relative to 15:59:00), and a reconciliation of the tick
taker buy-back against the hedged-hold table's B on the same contract.

Usage:
    python outputs/research/2026-11-13-alpha-hunt-2/laneF-resting-exit/diag_path.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import END, HERE, ask_at, load, mean_ci, quote_at  # noqa: E402
from run import block_mask, hold_table  # noqa: E402

MINS = [0, 5, 15, 30, 45, 50, 55, 58, 59]


def main() -> None:
    ev, legs = load()
    ev["entry_date"] = pd.to_datetime(ev["entry_date"])
    rows = []
    for e in ev.itertuples(index=False):
        lc, lp = legs.get((e.eid, "C")), legs.get((e.eid, "P"))
        if lc is None or lp is None:
            continue
        r = {"eid": e.eid}
        for m in MINS:
            t = min(m * 60.0, END)
            qc, qp = quote_at(lc, t, 60.0 if m == 0 else 0.0), quote_at(lp, t, 60.0 if m == 0 else 0.0)
            ac, ap = ask_at(lc, t), ask_at(lp, t)
            if m == 0:  # files open at 15:00:00, so take the first quote of the minute
                ac = ac or (qc[1] if qc else None)
                ap = ap or (qp[1] if qp else None)
            r[f"mid_{m}"] = (sum(qc) + sum(qp)) / 2 if qc and qp else np.nan
            r[f"half_{m}"] = ((qc[1] - qc[0]) + (qp[1] - qp[0])) / 2 if qc and qp else np.nan
            r[f"ask_{m}"] = ac + ap if ac and ap else np.nan
        rows.append(r)
    p = ev.merge(pd.DataFrame(rows), on="eid")
    for blk in ("disc_broad_2025", "hold_broad_2026", "hold_megacap_2023_24"):
        g = p[block_mask(p, blk)]
        print(f"\n{blk}  N={len(g)}  (m0 units, minus the 15:59:00 value; mean [date-clustered CI])")
        for m in MINS[:-1]:
            out = []
            for k in ("mid", "half", "ask"):
                x = (g[f"{k}_{m}"] - g[f"{k}_59"]) / g["m0"]
                ok = x.notna()
                ci = mean_ci(x[ok], g.loc[ok, "exit_date"])
                out.append(f"{k} {ci.point:+.5f} [{ci.low:+.5f},{ci.high:+.5f}]")
            print(f"  15:{m:02d}  " + "  ".join(out))
        print(f"  15:59 level: half-spread {np.nanmean(g['half_59'] / g['m0']):.5f} m0, "
              f"{np.nanmean(g['half_59'] / g['mid_59']):.4f} of premium")
    # reconciliation of the tick taker book against the hedged-hold B on the same strike
    h = hold_table()
    d = p.merge(h, on=["ticker", "entry_date"], how="left")
    d["b_tick"] = (d["s0_c"] + d["s0_p"] - d["ask_59"] - 4 * 0.0065) / d["m0"]
    same = d["strike"] == d["strike_h"]
    x = d.loc[same & d["B_h"].notna()]
    print(f"\nreconciliation on matched strikes: N={len(x)}, median |b_tick - B_h| "
          f"{(x['b_tick'] - x['B_h']).abs().median():.5f}, share > 0.01: "
          f"{((x['b_tick'] - x['B_h']).abs() > 0.01).mean():.3f}, corr {x['b_tick'].corr(x['B_h']):.4f}")
    for blk in ("disc_broad_2025", "hold_broad_2026", "hold_megacap_2023_24"):
        g = d[block_mask(d, blk)]
        print(f"  {blk}: mean b_tick {g['b_tick'].mean():+.5f} (N={g['b_tick'].notna().sum()}), "
              f"B_h same events {g['B_h'].mean():+.5f} (N={g['B_h'].notna().sum()}), "
              f"H same events {g['H'].mean():+.5f}, strike match {(g['strike'] == g['strike_h']).mean():.2f}")
    p.to_parquet(HERE / "path_panel.parquet")


if __name__ == "__main__":
    main()
