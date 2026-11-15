"""
recon.py
Lane E1: reconcile the extracted quote grid with the book's own marks on shared events before
any outcome is trusted. The long scalp is a different trade from ``engine/pnl.py::build_trade``,
so the reconciliation is of the inputs both paths read: the straddle mid at 15:59 on the entry
and reaction sessions (ledger ``straddle_entry`` and ``straddle_exit``, built by
``earnings_iv_crush/research/chains.py`` from the backfill chains) and the reaction-session spot
(ledger ``spot_exit``) against the grid's parity forward. Also audits the parity forward for bias
by subgroup (rule 4 of the brief): days to expiry and the strike's moneyness.

Usage:
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E1-gamma-scalp/recon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

LEDGER = ROOT / "outputs/research/oos_2026_ledger.csv"


def main() -> None:
    ev, grid = lib.load()
    led = pd.read_csv(LEDGER, parse_dates=["entry_date"])
    b = ev["block"] == "broad_2025_2026"
    e = ev[b].reset_index(drop=True)
    g = grid[b.to_numpy()]
    m = e.merge(led[["ticker", "entry_date", "straddle_entry", "straddle_exit", "spot_exit"]]
                .drop_duplicates(["ticker", "entry_date"]),
                on=["ticker", "entry_date"], how="left", validate="one_to_one")
    k = lib.k_of("15:59:00")
    d0 = lib.session(e, g, "D0")
    d1 = lib.session(e, g, "D1")
    lines = [f"shared events (broad_2025_2026): {len(m)}"]
    for name, sess, col in (("D0 15:59 mid", d0, "straddle_entry"),
                            ("D1 15:59 mid", d1, "straddle_exit")):
        x, y = sess.mid[:, k], m[col].to_numpy(float)
        ok = np.isfinite(x) & np.isfinite(y)
        rel = (x[ok] - y[ok]) / y[ok]
        lines.append(f"  {name} vs ledger {col}: N={ok.sum()}, median rel gap {np.median(rel):+.5f},"
                     f" mean {rel.mean():+.5f}, share within 1% {np.mean(np.abs(rel) < 0.01):.3f},"
                     f" corr {np.corrcoef(x[ok], y[ok])[0, 1]:.5f}")
    f1 = d1.fwd[:, k]
    y = m["spot_exit"].to_numpy(float)
    ok = np.isfinite(f1) & np.isfinite(y)
    gap = (f1[ok] - y[ok]) / y[ok]
    dte = (e["expiry"] - e["exit_date"]).dt.days.to_numpy()[ok]
    mny = np.abs(np.log(y[ok] / e["strike"].to_numpy(float)[ok]))
    lines.append(f"  D1 15:59 parity F vs ledger spot_exit: N={ok.sum()}, mean signed gap "
                 f"{gap.mean() * 1e4:+.2f} bp, median {np.median(gap) * 1e4:+.2f} bp, "
                 f"corr {np.corrcoef(f1[ok], y[ok])[0, 1]:.6f}")
    for lab, mask in (("dte <= 3", dte <= 3), ("dte 4-10", (dte > 3) & (dte <= 10)),
                      ("dte > 10", dte > 10), ("|ln S/K| < 2%", mny < 0.02),
                      ("|ln S/K| >= 5%", mny >= 0.05)):
        lines.append(f"    {lab}: N={mask.sum()}, mean signed gap {gap[mask].mean() * 1e4:+.2f} bp,"
                     f" mean |gap| {np.abs(gap[mask]).mean() * 1e4:.2f} bp")
    # within-hour noise of F: lag-1 autocorrelation of 5-second F changes on D1
    df = np.diff(d1.fwd[:, lib.k_of("15:01:00"):k + 1], axis=1)
    num = np.nansum(df[:, 1:] * df[:, :-1], axis=1)
    den = np.nansum(df ** 2, axis=1)
    rho = num[den > 0] / den[den > 0]
    lines.append(f"  lag-1 autocorrelation of 5-s parity-F changes on D1: median {np.median(rho):+.3f}"
                 " (i.i.d. noise alone pushes this towards -0.5)")
    txt = "\n".join(lines)
    print(txt)
    (HERE / "recon.log").write_text(txt + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
