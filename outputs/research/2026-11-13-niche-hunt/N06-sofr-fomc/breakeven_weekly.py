"""breakeven_weekly.py: break-even premium share for a weekly mid-curve straddle over FOMC.

Realised two-day FOMC squared moves in the futures-implied mean (both blocks, already seen) for
windows 300-500 days out (the 1-year mid-curve underlying), and the share s of implied event
variance that must be premium for a short straddle, sold one tick wide and held to expiry, to
break even. Gaussian increments: premium 0.7979 sqrt(K), expected payoff 0.7979 sqrt(K (1 - s)).
Exploratory projection, not a test.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N06-sofr-fomc/breakeven_weekly.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

import n06_lib as L

TICK_OPT_BP = 0.5  # weekly mid-curve premium tick 0.005 points (CME filing 19-366)
TICK_FUT_BP = 0.5  # deferred SR3 futures tick assumed 0.005 points (recalled, not verified)
FEES_BP = 0.1  # IB USD 0.85/contract = 0.034 bp per leg; exchange fees assumed similar


def main() -> None:
    L.CFG = dataclasses.replace(L.CFG, h_min=300, h_max=500)
    mpt = L.load_mpt()
    win = L.build_windows(mpt, L.load_releases())
    pay = L.window_payoffs(mpt, win, vcol="V_iqr")
    f = pay[pay.arm == "fomc"].groupby("anchor")["dF"].apply(lambda x: float(np.mean(x**2)))
    c = pay[pay.arm == "control"].groupby("anchor")["dF"].apply(lambda x: float(np.mean(x**2)))
    cost = 2 * TICK_OPT_BP / 2 + 0.5 * TICK_FUT_BP / 2 * 2 + FEES_BP  # entry 2 legs, ITM leg's futures close
    print(f"FOMC two-day squared move, 300-500 d windows: mean {f.mean():.1f} bp^2, median "
          f"{f.median():.1f}, N={len(f)}; controls mean {c.mean():.1f}, median {c.median():.1f}, N={len(c)}")
    print(f"cost per straddle at the touch, one-tick markets, held to expiry: {cost:.2f} bp")
    for name, r in [("median", f.median()), ("mean", f.mean()), ("discovery-band median", 117.5)]:
        k = 0.7979 * np.sqrt(r)
        # gross = k (1/sqrt(1-s) - 1) = cost  ->  s = 1 - 1/(1 + cost/k)^2
        s = 1 - 1 / (1 + cost / k) ** 2
        print(f"  realised {name} {r:.0f} bp^2: fair straddle {k:.2f} bp; break-even premium "
              f"share s = {s:.1%}; cost = {cost / k:.1%} of fair premium")


if __name__ == "__main__":
    main()
