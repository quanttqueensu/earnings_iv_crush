"""s02b_regression_discovery.py: regression variant of the event surplus, discovery block only.

Trial 2,417 (exploratory robustness of 2,412). Uses every non-event GLD session in the discovery
block as a control instead of the +/-60-session matched set: regress the one-session short
30-day variance P&L in ordinary-day units, y_t = (-dW_t - r_t^2) / u_t, on an event dummy with
weekday-by-gap fixed effects. The event coefficient estimates the same surplus S as 2,412.
Interval: date-clustered bootstrap of the event-minus-cell-mean differences (each event minus the
mean of all non-event sessions in its weekday-by-gap cell of the block).

Usage:
    python outputs/research/2026-11-13-niche-hunt/N12-metals-macro/scripts/s02b_regression_discovery.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

CAL = ROOT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"


def main() -> None:
    p = pd.read_parquet(HERE / "panel.parquet")
    p = p[(p["sym"] == "GLD") & (p["date"] <= "2021-12-31")].dropna(subset=["dW", "r", "u"])
    p = p[~p["stale"]]
    p["y"] = (-p["dW"] - p["r2"]) / p["u"]
    p["cell"] = p["weekday"].astype(str) + "_" + p["gap"].astype(int).astype(str)
    base = p[~p["is_event"]].groupby("cell")["y"].agg(["mean", "size"])
    ev = p[p["is_event"]].join(base, on="cell")
    few = ev["size"].fillna(0) < 5
    print(f"discovery GLD sessions {len(p)}, events {len(ev)}, events in thin cells dropped {int(few.sum())}")
    ev = ev[~few]
    diff = ev["y"] - ev["mean"]
    ci = date_clustered_ci(diff.to_numpy(), ev["date"].to_numpy(), stat=lambda x: float(np.mean(x)))
    print(f"trial 2417 GLD pooled, weekday-by-gap cell controls [discovery]: mean S {ci}")
    for k, sel in (("fomc", ev["kind"].str.contains("fomc")), ("cpi", ev["kind"] == "cpi"),
                   ("nfp", ev["kind"] == "nfp")):
        c = date_clustered_ci(diff[sel].to_numpy(), ev.loc[sel, "date"].to_numpy(),
                              stat=lambda x: float(np.mean(x)))
        print(f"  {k}: {c}")
    ctrl_y = p.loc[~p["is_event"], "y"]
    # y omits the implied accrual for the elapsed session (about one u), which cancels in the
    # event-minus-cell difference; the level below is therefore not a P&L, only a sanity check.
    print(f"sanity: non-event mean y (excludes the accrual term, not a P&L) {ctrl_y.mean():+.3f}, "
          f"mean r^2/u {(p.loc[~p['is_event'], 'r2'] / p.loc[~p['is_event'], 'u']).mean():.3f}, "
          f"N={len(ctrl_y)}")


if __name__ == "__main__":
    main()
