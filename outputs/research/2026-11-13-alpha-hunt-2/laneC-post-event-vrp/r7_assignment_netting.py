"""
r7_assignment_netting.py
Trial 1,856: accounting of the hedged hold at expiry. The stored H charges both the unwind of the
whole stock hedge at the expiry close and 5 bp to dispose of delivered stock. When the short leg
finishes in the money, assignment delivers (or takes) one share per straddle against a hedge that
already holds close to that share, so only the mismatch |h_last - sign(S_T - K)| needs trading and
nothing is disposed of. This recomputes that one cost term per event; nothing else changes.

The last hedge ratio is rebuilt with the reaction-close IV inverted on the CRSP close (the stored
hedge used the chain's parity forward), so the per-event figure is an approximation; the stored
unwind term is rebuilt the same way so both arms share the approximation.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneC-post-event-vrp/r7_assignment_netting.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import build_panel as bp
import lanec_lib as L
from earnings_iv_crush.config import HEDGED
from earnings_iv_crush.engine.stats import nyse_sessions
from earnings_iv_crush.research import hedged_hold as hh

FLOOR = HEDGED.equity_cost_floor_bps / 1e4


def main() -> None:
    p = L.load()
    crsp = bp.load_crsp()
    saved = np.full(len(p), np.nan)
    for i, r in enumerate(p.itertuples()):
        g = crsp[int(r.permno)].reindex(nyse_sessions(r.exit_date, r.expiry))
        cl = g["prc"].to_numpy(float)
        hs = np.maximum(((g["ask"] - g["bid"]) / 2 / g["prc"]).to_numpy(float), FLOOR)
        s_t, k = cl[-1], float(r.strike)
        tau = hh.year_frac(g.index[-2], r.expiry)
        h_last = hh.straddle_delta(cl[-2], k, tau, float(r.iv_post))
        old = abs(h_last) * s_t * hs[-1] + float(r.disposal)
        new = abs(h_last - np.sign(s_t - k)) * s_t * hs[-1]
        saved[i] = (old - new) / r.m0
    p["netting_gain"] = saved
    for b, tag in (("discovery", "2013-18"), ("heldout", "2019-24")):
        d = p[p["block"] == b]
        x = L.ci(d["netting_gain"], d["exit_date"])
        hn = L.ci(d["H"] + d["netting_gain"], d["exit_date"])
        print(f"[1856 {tag}] gain {L.fmt(x)}% m0; H {100 * d['H'].mean():+.3f}% -> {L.fmt(hn)}%")
        L.log_trial({"trial_id": 1856, "hypothesis": "let assignment net the stock hedge at expiry "
                     "instead of unwinding the hedge and disposing of delivered stock",
                     "mechanism": "the short in-the-money leg delivers the share the hedge already "
                     "holds; only the mismatch trades and no disposal is paid (accounting, not "
                     "alpha)", "block": tag, "n": x["n"], "effect": x["point"], "ci_low": x["low"],
                     "ci_high": x["high"], "t": x["t"], "null_pct": "",
                     "basis": "per trade, fraction of m0, net at touch; paired change in H on the "
                              "lane-ok events, approximate last hedge ratio",
                     "verdict": "descriptive (cost accounting; needs the analyst's sign-off before "
                                "any book level uses it)",
                     "secondary": f"H level after netting {L.fmt(hn)}%"})


if __name__ == "__main__":
    main()
