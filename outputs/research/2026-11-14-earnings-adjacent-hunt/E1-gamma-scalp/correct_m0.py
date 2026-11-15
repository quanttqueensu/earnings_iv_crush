"""
correct_m0.py
Lane E1, trial 2,694: basis correction after the outcomes were computed. The 2025-26 ledger's
``spot_entry`` is a dividend-back-adjusted close (``research/chains.py::_spot_table`` calls
``yf.download(auto_adjust=True)``), so ``m0 = 0.20 spot_entry + s0`` and the attrition check's
reaction move were built on the adjusted price for broad_2025_2026 events. This script replaces
the entry spot with the 15:59:00 parity forward of the cached strike on D0 (F = K + C_mid - P_mid,
the same proxy the scalp hedges with), recomputes every m0-based figure and the attrition check,
and reports the entry moneyness of the sold strike. The rule, the debit-basis primary and its
pass/fail are unchanged: the debit never used ``spot_entry``.

The held-out block is recomputed here for the m0 denominator only, a second computation on an
already-read block, disclosed in diagnosis.log entry 7. ``heldout.py`` is not run again.

Usage:
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E1-gamma-scalp/correct_m0.py
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
import run  # noqa: E402

K_ENTRY = lib.k_of("15:59:00")


def entry_forward(ev: pd.DataFrame, grid: np.ndarray) -> tuple[np.ndarray, int]:
    """D0 15:59:00 parity forward; falls back to the last finite forward in the D0 hour (counted)."""
    f = lib.session(ev, grid, "D0").fwd
    out = f[:, K_ENTRY].copy()
    miss = ~np.isfinite(out)
    for i in np.where(miss)[0]:
        row = f[i, : K_ENTRY + 1]
        row = row[np.isfinite(row)]
        out[i] = row[-1] if row.size else np.nan
    return out, int(miss.sum())


def main() -> None:
    ev, grid = lib.load()
    broad = (ev["block"] == "broad_2025_2026").to_numpy()
    f0, n_fb = entry_forward(ev, grid)
    lines = [f"D0 15:59:00 parity forward: {int(np.isfinite(f0).sum())} of {len(ev)} events; "
             f"{n_fb} fell back to an earlier D0 forward; {int((~np.isfinite(f0)).sum())} missing"]
    gap = f0 / ev["spot_entry"].to_numpy(float) - 1.0
    q = ev["entry_date"].dt.to_period("Q").astype(str)
    for name, m in (("broad_2025_2026", broad), ("megacap_2023_2024", ~broad)):
        g = gap[m & np.isfinite(gap)]
        lines.append(f"  {name}: F/spot_entry - 1 median {np.median(g) * 100:+.2f}%, mean "
                     f"{g.mean() * 100:+.2f}%, 90th pct {np.quantile(g, 0.9) * 100:+.2f}% (N={g.size})")
    by_q = pd.Series(gap[broad]).groupby(q[broad].to_numpy()).mean() * 100
    lines.append("  broad mean gap by entry quarter, %: "
                 + ", ".join(f"{k} {v:+.2f}" for k, v in by_q.items()))
    # corrected spot: parity forward on broad 2025-26, CRSP-based spot kept on megacap
    spot = np.where(broad & np.isfinite(f0), f0, ev["spot_entry"].to_numpy(float))
    ev = ev.assign(spot_fix=spot, m0_fix=0.20 * spot + ev["s0"].to_numpy(float))
    dm0 = ev["m0_fix"] / ev["m0"] - 1.0
    lines.append(f"  broad m0 corrected / old - 1: median {np.median(dm0[broad]) * 100:+.2f}%, "
                 f"mean {np.mean(dm0[broad]) * 100:+.2f}%")
    # moneyness of the sold strike at the 15:59 entry, on the true forward
    lm = np.log(f0 / ev["strike"].to_numpy(float))
    for name, m in (("broad_2025_2026", broad), ("megacap_2023_2024", ~broad)):
        x = lm[m & np.isfinite(lm)]
        qs = np.quantile(x, [0.1, 0.25, 0.5, 0.75, 0.9]) * 100
        lines.append(f"  entry ln(F/K), {name}: deciles 10/25/50/75/90 = "
                     + "/".join(f"{v:+.2f}" for v in qs)
                     + f" %; mean |ln F/K| {np.abs(x).mean() * 100:.2f}%; share |ln F/K| > 1% "
                     f"{np.mean(np.abs(x) > 0.01):.2f}")
    d1 = lib.session(ev, grid, "D1")
    ok_all = lib.entry_ok(d1) & np.isfinite(ev["s0"].to_numpy())
    move = run.first_finite_move(d1, ev["spot_fix"].to_numpy(float))
    for blk, mask in (("discovery", run.discovery_mask(ev)),
                      ("held-out", (broad & (ev["entry_date"] >= run.SPLIT)).to_numpy())):
        kept, dropped = mask & ok_all, mask & ~ok_all
        lines.append(f"{blk}: attrition |reaction move| on the corrected spot: kept "
                     f"{np.nanmean(move[kept]):.4f} (N={int(np.isfinite(move[kept]).sum())}), "
                     f"dropped {np.nanmean(move[dropped]):.4f} "
                     f"(N={int(np.isfinite(move[dropped]).sum())})")
        e = ev[kept].reset_index(drop=True)
        s = lib.session(e, grid[kept], "D1")
        dates = e["exit_date"]
        out = lib.scalp(s, clock_sec=300)
        net_m0 = out["net"].to_numpy() / e["m0_fix"].to_numpy()
        lines.append(run.score(f"2694 {blk} primary rule, net % of corrected m0", 2694, blk,
                               net_m0, dates, "frozen primary 2,682, m0 from the D0 parity forward",
                               "% m0 (corrected), net touch", "basis correction",
                               "post-outcome recomputation; replaces the % m0 figure of 2,682"))
        old = out["net"].to_numpy() / e["m0"].to_numpy()
        lines.append(f"      previously reported on the adjusted m0: {old.mean() * 100:+.3f}%")
        if blk == "discovery":
            sh = lib.scalp(s, clock_sec=300, side=-1)
            unwind = np.abs(sh["h_end"].to_numpy()) * s.fwd[:, lib.k_of("15:59:00")] * (
                lib.STOCK_HALF_BPS + lib.STOCK_EXTRA_BPS) / 1e4
            diff = (sh["hedge_pnl"] - sh["stock_cost"]).to_numpy() + np.nan_to_num(unwind)
            lines.append("  2694 mirror (2,691) on the corrected m0, % m0: "
                         + run.fmt(run.ci(diff / e["m0_fix"].to_numpy(), dates))
                         + f"; previously {np.mean(diff / e['m0'].to_numpy()) * 100:+.3f}%")
    txt = "\n".join(lines)
    print(txt)
    (HERE / "correct_m0.log").write_text(txt + "\n", encoding="utf-8")
    ev.to_parquet(HERE / "cache" / "events_m0fix.parquet", index=False)


if __name__ == "__main__":
    sys.exit(main())
