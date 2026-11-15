"""wright_cost_bar.py: Wright (2020) event VRPs as a share of a one-day straddle, against the touch.

Converts the published event-day variance risk premia for CBOT weekly Treasury options into the
gross share of a one-day ATM straddle's value a seller keeps, and sets it beside the half-spread
and commission share of premium at an assumed quoted width. Inputs are transcribed from the
paper (Tables 2 and 5, Figure 2, read off the plot to two significant figures); nothing here is
a measured fill.

Usage:
    python outputs/research/2026-11-13-niche-hunt/N05-treasuries-macro/scripts/wright_cost_bar.py

References
----------
Wright, J. H. (2020). Event-day options. NBER Working Paper 28306, Tables 2 and 5, Figure 2.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

LANE = Path(__file__).resolve().parents[1]
TICK = 1 / 64  # CBOT Treasury option minimum fluctuation, points of par ($15.625 per contract)
POINT_USD = 1000.0  # $100,000 face: one point is $1,000
FEE_USD = 0.85 + 0.85 + 0.01  # IB commission + CBOT exchange fee (non-member) + regulatory, per contract
FUT_HALF_SPREAD = 1 / 128  # ZN futures trade one half-32nd wide (1/64) when tight; half of that
TRADING_DAYS = 252  # assumption on Wright's annualisation of Figure 2; see evidence.md
ZN_PRICE = 110.0  # recalled 2025-26 level of ZN futures; no robots-compliant free source on disk

# (tenor, event): (event-day ATM IV annualised, read from Figure 2; gamma IV pct^2; gamma VRP pct^2)
WRIGHT = {
    ("10y", "NFP"): (0.095, 0.233, 0.077),
    ("10y", "FOMC"): (0.070, 0.066, 0.031),
    ("30y", "NFP"): (0.155, 0.631, 0.177),
    ("30y", "FOMC"): (0.120, 0.144, 0.116),
    ("5y", "NFP"): (0.067, 0.055, 0.028),
    ("5y", "FOMC"): (0.052, 0.042, 0.019),
}


def main() -> None:
    f = ZN_PRICE
    print(f"ZN price scale (recalled, assumed): {f:.3f}")
    rows = []
    for (tenor, ev), (iv_ann, g_iv, g_vrp) in WRIGHT.items():
        var_day = (iv_ann**2 / TRADING_DAYS) * 1e4  # pct^2 per day
        vrp_share_var = g_vrp / var_day  # event VRP only: a lower bound on the total VRP share
        edge = 1.0 - np.sqrt(1.0 - vrp_share_var)  # straddle share under normal returns
        prem_pts = np.sqrt(2 / np.pi) * np.sqrt(var_day) / 100 * f
        prem_usd = prem_pts * POINT_USD
        for ticks_wide in (1, 2):
            half = ticks_wide * TICK  # two legs, each half of ticks_wide
            cost_entry = (half * POINT_USD + 2 * FEE_USD) / prem_usd
            cost_expiry = (FUT_HALF_SPREAD * POINT_USD + FEE_USD) / prem_usd  # unwind exercised future
            rows.append(
                {
                    "tenor": tenor,
                    "event": ev,
                    "event_day_var_pct2": round(var_day, 3),
                    "event_vrp_pct2": g_vrp,
                    "vrp_share_of_var": round(vrp_share_var, 3),
                    "gross_edge_share_of_premium": round(edge, 3),
                    "straddle_premium_usd": round(prem_usd, 0),
                    "quoted_width_ticks_per_leg": ticks_wide,
                    "cost_share_hold_to_expiry": round(cost_entry + cost_expiry, 3),
                    "net_share": round(edge - cost_entry - cost_expiry, 3),
                }
            )
    for r in rows:
        print(r)
    (LANE / "logs" / "wright_cost_bar.json").write_text(json.dumps({"zn_close": f, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
