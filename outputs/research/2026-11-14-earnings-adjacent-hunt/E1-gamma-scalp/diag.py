"""
diag.py
Lane E1 diagnostics after the primary failed (discovery only): does more frequent hedging take
more gamma gross of stock costs (the mean-reversion mechanism), and is the mirror's loss a
last-hour reversal of the reaction (a directional effect rather than a gamma one)?

Trials 2,692 (gross hedge P&L by rebalancing clock) and 2,693 (last-hour reversal of the reaction,
traded in the stock at an assumed 4 bp per side), both exploratory.

Usage:
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E1-gamma-scalp/diag.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import lib  # noqa: E402
import run  # noqa: E402


def main() -> None:
    ev, grid = lib.load()
    disc = run.discovery_mask(ev)
    d1 = lib.session(ev, grid, "D1")
    kept = disc & lib.entry_ok(d1) & np.isfinite(ev["s0"].to_numpy())
    e = ev[kept].reset_index(drop=True)
    dates = e["exit_date"]
    lines = []
    k0, k1 = lib.k_of("15:01:00"), lib.k_of("15:59:00")
    for name in ("D1", "Dm1"):
        s = lib.session(e, grid[kept], name)
        ok = lib.entry_ok(s)
        st = lib.scalp(s, clock_sec=None)
        deb = st["debit"].to_numpy()
        for clk in (60, 300, 900):
            o = lib.scalp(s, clock_sec=clk)
            dx = ((o["hedge_pnl"] - st["hedge_pnl"]) / deb).to_numpy()
            m = ok & np.isfinite(dx)
            lines.append(f"2692 {name} hedge P&L, {clk // 60}-min clock minus static, GROSS of stock"
                         " cost, % debit: " + run.fmt(run.ci(dx[m], dates[m])))
        lib.log_trial({"trial": 2692, "block": f"discovery {name}",
                       "rule": "gross hedge P&L by clock minus static", "statistic": "mean",
                       "basis": "% debit, gross", "label": "exploratory",
                       "note": "mechanism; see diag.log"})
        # 2,693: reversal of the reaction in the last hour, in the stock (per unit notional)
        # move since the previous session's 15:59 parity forward (same contract); the ledger spot
        # is not used because it is a dividend-adjusted series (recon.log)
        prev = lib.session(e, grid[kept], {"D1": "D0", "Dm1": "Dm2"}[name]).fwd[:, k1]
        mv = s.fwd[:, k0] / prev - 1.0
        r = s.fwd[:, k1] / s.fwd[:, k0] - 1.0
        rev_gross = -np.sign(mv) * r
        rev_net = rev_gross - 2 * (lib.STOCK_HALF_BPS + lib.STOCK_EXTRA_BPS) / 1e4
        m = ok & np.isfinite(rev_net)
        lines.append(f"2693 {name} fade the reaction 15:01->15:59 in the stock, gross, bp: "
                     + run.fmt(run.ci(rev_gross[m], dates[m]), 1e4))
        lines.append("     net of 2 x 4 bp, bp: " + run.fmt(run.ci(rev_net[m], dates[m]), 1e4))
        big = m & (np.abs(mv) > np.nanmedian(np.abs(mv[m])))
        lines.append(f"     reactions above the median |move| ({np.nanmedian(np.abs(mv[m])):.3f}),"
                     " gross bp: " + run.fmt(run.ci(rev_gross[big], dates[big]), 1e4))
        if name == "D1":
            run.score("2693 D1 fade reaction net, % notional", 2693, "discovery", rev_net[m],
                      dates[m], "short the reaction direction 15:01-15:59, 4 bp per side",
                      "% notional, net assumed stock touch", "exploratory; statistic switch")
    txt = "\n".join(lines)
    print(txt)
    (HERE / "diag.log").write_text(txt + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
