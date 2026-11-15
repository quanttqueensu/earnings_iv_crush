"""r2_clock_screen.py: round 2 on the tick panel. Touch-only clock stack and a causal entry-spread screen.

TC   sell at the 15:45:00 bids, buy back at the 15:30:00 asks next session (both at the touch,
     no reliance on trading inside the quote).
SCR  trade TC only when the 15:45 half-spread (share of mid) is at or below the expanding median of
     strictly earlier events (minimum history 50); scored as selected minus unselected within tenor
     and against a tenor-matched random selection of the same size.
Real data (cached cmbp-1 ticks).

Usage
-----
    python r2_clock_screen.py [--blocks disc_broad_2025,megacap_2023_24] [--log]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import COMM, OUT, ci, fmt, load_ticks, log_trial, split_ticks, tstat

MIN_HIST = 50
TENOR_BINS = [0, 4, 9, 400]


def causal_median_flag(g: pd.DataFrame, col: str) -> pd.Series:
    """True when col is at or below the median of events with a strictly earlier entry date."""
    g = g.sort_values("entry_date")
    by_date = g.groupby("entry_date")[col].apply(list)
    hist: list[float] = []
    thr = {}
    for d, vals in by_date.items():
        thr[d] = float(np.nanmedian(hist)) if len(hist) >= MIN_HIST else np.nan
        hist.extend(vals)
    t = g["entry_date"].map(thr)
    return (g[col] <= t).where(t.notna())


def matched_null(y: pd.Series, sel: pd.Series, tenor: pd.Series, n_draw: int = 5000) -> float:
    """Percentile of the selected mean among random selections of the same count per tenor bucket."""
    rng = np.random.default_rng(0)
    obs = y[sel].mean()
    draws = np.zeros(n_draw)
    tot = int(sel.sum())
    for b in tenor.unique():
        yb = y[tenor == b].to_numpy()
        k = int(sel[tenor == b].sum())
        if k == 0:
            continue
        idx = np.argsort(rng.random((n_draw, len(yb))), axis=1)[:, :k]
        draws += yb[idx].sum(axis=1)
    return float(100 * (draws / tot < obs).mean())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", default="disc_broad_2025")
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args()
    R = load_ticks()
    # the screen's history runs over the whole universe file in date order (causal), not per block
    S = split_ticks(R)
    for name in a.blocks.split(","):
        uni = R[R["block"] == ("megacap_2023_2024" if name.startswith("megacap") else "broad_2025_2026")].copy()
        uni["hs45"] = (uni["en_ask_15:45"] - uni["en_bid_15:45"]) / (uni["en_ask_15:45"] + uni["en_bid_15:45"])
        uni["tight"] = causal_median_flag(uni, "hs45")
        g = uni.loc[S[name].index]
        g = g[g["en_two_15:59"] & g["ex_ask_15:59"].notna()].copy()
        fb = ~g["en_two_15:45"]
        dt, m0, c4 = g["exit_date"], g["m0"], 4 * COMM
        sell45 = g["en_bid_15:45"].where(~fb, g["en_bid_15:59"])
        buy30 = g["ex_ask_15:30"].fillna(g["ex_ask_15:59"])
        B0 = (g["en_bid_15:59"] - g["ex_ask_15:59"] - c4) / m0
        TC = (sell45 - buy30 - c4) / m0
        E45 = (sell45 - g["ex_ask_15:59"] - c4) / m0
        X30 = (g["en_bid_15:59"] - buy30 - c4) / m0
        print(f"\n=== {name}: scored {len(g)}; exit 15:30 ask missing (falls back to 15:59) {int(g['ex_ask_15:30'].isna().sum())}")
        print("B0 level        ", fmt(ci(B0, dt)), " sd", round(100 * B0.std(), 2))
        print("TC level        ", fmt(ci(TC, dt)), " sd", round(100 * TC.std(), 2))
        print("TC - B0         ", fmt(ci(TC - B0, dt)), "t", round(tstat(TC - B0, dt), 2))
        print("additivity: E45 lift", round(100 * (E45 - B0).mean(), 3), "+ X30 lift", round(100 * (X30 - B0).mean(), 3),
              "= stacked", round(100 * (TC - B0).mean(), 3), "| corr of the two lifts", round(float(np.corrcoef(E45 - B0, X30 - B0)[0, 1]), 3))
        print("TC per-trade Sharpe", fmt(ci(TC, dt, lambda v: float(np.mean(v) / np.std(v, ddof=1))), 1.0))
        hs = g["hs0"]
        for lab, s in (("hs0 tercile low", hs <= hs.quantile(1 / 3)), ("mid", (hs > hs.quantile(1 / 3)) & (hs <= hs.quantile(2 / 3))),
                       ("high", hs > hs.quantile(2 / 3))):
            print(f"  TC-B0 by 15:59 half-spread, {lab:16s}", fmt(ci((TC - B0)[s], dt[s])), "| TC level", fmt(ci(TC[s], dt[s])))
        for half, s in (("first half", g["entry_date"] < g["entry_date"].median()), ("second half", g["entry_date"] >= g["entry_date"].median())):
            print(f"  TC-B0 {half:12s}", fmt(ci((TC - B0)[s], dt[s])))
        print("  worst 5 TC:", (100 * TC).nsmallest(5).round(1).tolist(), "| share of events TC>B0", round(float((TC > B0).mean()), 3))
        # ── spread screen on the TC book ──
        k = g["tight"].notna()
        sel = g.loc[k, "tight"].astype(bool)
        y, d2 = TC[k], dt[k]
        ten = pd.cut(g.loc[k, "dte"], TENOR_BINS, labels=False)
        print(f"screen funnel: scored {len(g)}, with causal history {int(k.sum())}, selected {int(sel.sum())}")
        wt = []
        for b in sorted(ten.unique()):
            mb = ten == b
            if sel[mb].sum() >= 5 and (~sel[mb]).sum() >= 5:
                wt.append((y[mb & sel].mean() - y[mb & ~sel].mean(), int(sel[mb].sum())))
                print(f"    tenor bucket {b}: selected {int(sel[mb].sum())} mean {100*y[mb & sel].mean():+.2f}, unselected {int((~sel[mb]).sum())} mean {100*y[mb & ~sel].mean():+.2f}")
        demean = y - y.groupby(ten).transform("mean")
        diff = ci(demean, d2, None)  # placeholder to keep N
        s_arr = sel.to_numpy()

        def within_gap(idx_vals: np.ndarray) -> float:
            return float(np.mean(idx_vals))

        # selected minus unselected within tenor, via bootstrap over dates on a tenor-demeaned outcome
        z = pd.Series(np.where(s_arr, demean / max(sel.mean(), 1e-9), -demean / max(1 - sel.mean(), 1e-9)), index=y.index)
        gap = ci(z, d2)
        null = matched_null(y, sel, ten)
        print("  screen: TC selected", fmt(ci(y[sel], d2[sel])), "| unselected", fmt(ci(y[~sel], d2[~sel])))
        print("  screen: selected minus unselected within tenor", fmt(gap), "t", round(tstat(z, d2), 2), "| tenor-matched null percentile", null)
        gross = ((g["mid0"] - (g["ex_bid0_15:59"] + g["ex_ask_15:59"]) / 2) / m0)[k]
        print("  decomposition: gross at mid selected", round(100 * gross[sel].mean(), 2), "unselected", round(100 * gross[~sel].mean(), 2),
              "| cost (gross - TC) selected", round(100 * (gross - y)[sel].mean(), 2), "unselected", round(100 * (gross - y)[~sel].mean(), 2))
        pd.DataFrame({"ticker": g["ticker"], "entry_date": g["entry_date"], "exit_date": dt, "B0": B0, "TC": TC, "tight": g["tight"],
                      "hs0": g["hs0"], "dte": g["dte"], "m0": m0}).to_parquet(OUT / f"r2_tc_{name}.parquet")
        if a.log:
            log_trial(1727, "touch-only clock stack: sell 15:45 bid, buy back 15:30 ask", "quotes widen into the close on both days; no inside-quote fill needed",
                      name, TC - B0, dt, "paired diff vs B0, fraction of m0, net at touch, per trade", "scored")
            log_trial(1728, "causal tight-spread screen on the clock-stack book", "cost is the binding constraint; closed spread gate found no gross premium in tight names",
                      name, z, d2, "selected minus unselected within tenor, fraction of m0, net at touch", "scored", null_pct=null)


if __name__ == "__main__":
    main()
