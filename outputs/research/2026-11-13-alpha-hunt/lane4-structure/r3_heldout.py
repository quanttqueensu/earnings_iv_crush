"""r3_heldout.py: the single held-out read of the two frozen candidates (see freeze_2026-11-13.md).

Real data (cached cmbp-1 ticks), broad events entered in 2026. Run once.

Usage
-----
    python r3_heldout.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import COMM, OUT, ci, fmt, load_ticks, log_trial, split_ticks, tstat
from r1_stack import build_arms, shares

BLOCK = "held_broad_2026H1"


def signflip_pct(x: pd.Series, dates: pd.Series, n: int = 5000) -> float:
    """Percentile of the observed mean under random sign flips of whole date clusters."""
    rng = np.random.default_rng(0)
    s = x.groupby(dates.to_numpy()).sum().to_numpy()
    flips = rng.choice([-1.0, 1.0], size=(n, len(s)))
    return float(100 * ((flips @ s) < s.sum()).mean())


def main() -> None:
    S = split_ticks(load_ticks())
    pk, xpk = shares(S["disc_broad_2025"])
    g = S[BLOCK]
    n0 = len(g)
    g = g[g["en_two_15:59"] & g["ex_ask_15:59"].notna()].copy()
    print(f"{BLOCK}: files {n0}, scored {len(g)}; frozen shares entry {pk:.3f}, exit {xpk:.3f}")
    dt, m0, c4 = g["exit_date"], g["m0"], 4 * COMM
    A = build_arms(g, pk, xpk)
    has = A.pop("has_pk")
    fb = ~g["en_two_15:45"]
    sell45 = g["en_bid_15:45"].where(~fb, g["en_bid_15:59"])
    A["TC"] = (sell45 - g["ex_ask_15:30"].fillna(g["ex_ask_15:59"]) - c4) / m0
    sh = lambda v: float(np.mean(v) / np.std(v, ddof=1))  # noqa: E731
    for k in ("B0", "gross_mid", "E45", "X15:30", "TC", "PKo59", "E45+PKs", "E45+PKs+XPKs", "stack_p0.25", "stack_p0.5", "stack_p0.75"):
        d = A[k] - A["B0"]
        print(f"{k:14s} level {fmt(ci(A[k], dt)):36s} Sharpe {fmt(ci(A[k], dt, sh), 1.0):34s} diff {fmt(ci(d, dt)):34s} t {tstat(d, dt):+.2f}")
    hs = g["hs0"]
    q1, q2 = hs.quantile(1 / 3), hs.quantile(2 / 3)
    for lab, s in (("low", hs <= q1), ("mid", (hs > q1) & (hs <= q2)), ("high", hs > q2)):
        print(f"  half-spread tercile {lab:5s} TC-B0 {fmt(ci((A['TC'] - A['B0'])[s], dt[s]))} | TC level {fmt(ci(A.loc[s, 'TC'], dt[s]))}")
    mid45 = (g["en_bid_15:45"] + g["en_ask_15:45"]) / 2
    xm30 = (g["ex_bid0_15:30"] + g["ex_ask_15:30"]) / 2
    xm59 = (g["ex_bid0_15:59"] + g["ex_ask_15:59"]) / 2
    print("driver check, % of m0: entry mid 15:45 minus 15:59", fmt(ci((mid45 - g["mid0"]) / m0, dt)),
          "| exit mid 15:59 minus 15:30", fmt(ci((xm59 - xm30) / m0, dt)))
    print("package prints: events with a late seller-side print", int(has.sum()), "of", len(g))
    n1 = signflip_pct(A["TC"] - A["B0"], dt)
    n2 = signflip_pct(A["stack_p0.5"] - A["B0"], dt)
    t1, t2 = tstat(A["TC"] - A["B0"], dt), tstat(A["stack_p0.5"] - A["B0"], dt)
    c1 = ci(A["TC"] - A["B0"], dt)
    v1 = "PASS (exploratory: block not clean on the ledger)" if c1[1] > 0 and t1 >= 3 and n1 >= 95 else "FAIL"
    c2 = ci(A["stack_p0.5"] - A["B0"], dt)
    v2 = "PASS on the paired statistic (exploratory; level rests on an assumed fill rate)" if c2[1] > 0 and t2 >= 3 and n2 >= 95 else "FAIL"
    basis = "paired diff vs B0, fraction of m0, net, per trade"
    log_trial(1727, "touch-only clock stack: sell 15:45 bid, buy back 15:30 ask", "quotes widen into the close on both days", BLOCK,
              A["TC"] - A["B0"], dt, basis + ", at touch", v1, null_pct=n1)
    log_trial(1724, "full stack at 50% fill haircut, else touch at 15:59", "fill probability not measured", BLOCK,
              A["stack_p0.5"] - A["B0"], dt, basis + ", package shares from discovery", v2, null_pct=n2)
    log_trial(1729, "level of the touch-only clock-stack book", "is the modified book net positive", BLOCK, A["TC"], dt,
              "level, fraction of m0, net at touch, per trade", "secondary: positive only if interval excludes zero")
    A.assign(ticker=g["ticker"], entry_date=g["entry_date"], exit_date=dt, hs0=hs, dte=g["dte"]).to_parquet(OUT / f"r3_arms_{BLOCK}.parquet")


if __name__ == "__main__":
    main()
