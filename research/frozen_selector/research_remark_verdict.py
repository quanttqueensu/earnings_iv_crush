"""
research_remark_verdict.py
Every load-bearing claim, recomputed under the repaired mark.

The historical book marked its straddles on raw daily closes, 20.1% of whose exit
marks were below intrinsic (``engine.marks``). This script re-derives the claims that
rest on those marks, side by side with the unrepaired originals, so the damage is
attributable rather than asserted:

1. **The headline** - per-trade Sharpe of the q=0.80 gated naked book.
2. **The operating point** - is q=0.80 still the interior node, or was the gate fitted
   to the corruption? This is the one that would hurt: the term gate is the edge, and if
   its optimum moves, the parameter was chosen on bad data.
3. **The hold-out** - 2019-2022 in-sample, 2023-2024 out.
4. **The tail** - worst trade and CVaR, which is where the stale marks concentrate.

Usage:
    python research/frozen_selector/research_remark_verdict.py
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

warnings.filterwarnings("ignore")

OUT = Path("outputs/research/remark_verdict.csv")
BOOT = 5000
Q_GRID = [0.50, 0.60, 0.65, 0.70, 0.75, 0.78, 0.80, 0.82, 0.85, 0.90, 0.95]
HOLDOUT_CUT = pd.Timestamp("2023-01-01")


def _load(mode: str):
    """Reload market_validate under the given mark mode and return the prepared frame."""
    os.environ["IVCRUSH_MARK"] = mode
    import earnings_iv_crush.research.market_marks as mv

    importlib.reload(mv)
    from earnings_iv_crush.research.gates import expanding_high_term_mask

    ev, _ = mv._prepare(mv.EVENTS_FULL)
    return mv, ev, expanding_high_term_mask


def _stats(rom: np.ndarray, rng) -> dict:
    rom = np.asarray(rom, dtype=float)
    if len(rom) < 3:
        return {
            "n": len(rom),
            "sharpe": np.nan,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "mean_rom": np.nan,
            "worst": np.nan,
            "cvar5": np.nan,
            "win": np.nan,
        }
    sd = rom.std(ddof=1)
    sh = rom.mean() / sd if sd > 0 else np.nan
    d = rng.choice(rom, size=(BOOT, len(rom)), replace=True)
    dsd = d.std(axis=1, ddof=1)
    bs = np.divide(d.mean(axis=1), dsd, out=np.full(BOOT, np.nan), where=dsd > 0)
    k = max(1, int(0.05 * len(rom)))
    return {
        "n": len(rom),
        "sharpe": float(sh),
        "ci_lo": float(np.nanpercentile(bs, 2.5)),
        "ci_hi": float(np.nanpercentile(bs, 97.5)),
        "mean_rom": float(rom.mean()),
        "worst": float(rom.min()),
        "cvar5": float(np.sort(rom)[:k].mean()),
        "win": float((rom > 0).mean()),
    }


def _book(mv, ev, mask_fn, q: float, rng, lo=None, hi=None) -> dict:
    m = mask_fn(ev, q)
    g = ev[m].reset_index(drop=True)
    if lo is not None or hi is not None:
        d = pd.to_datetime(g["entry_date"])
        if lo is not None:
            g = g[d >= lo]
        if hi is not None:
            g = g[d < hi]
        g = g.reset_index(drop=True)
    if g.empty:
        return {
            "n": 0,
            "sharpe": np.nan,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "mean_rom": np.nan,
            "worst": np.nan,
            "cvar5": np.nan,
            "win": np.nan,
        }
    led = mv._ledger(g, defined_risk=False, costs=mv.MEGACAP_COST)
    return _stats(led["return_on_margin"].to_numpy(float), rng)


def main() -> int:
    rows = []
    print("=" * 92)
    print("1. THE HEADLINE  (q=0.80 gated naked book, mega-cap ~2% round-trip cost)")
    print("=" * 92)
    for mode, tag in (("raw", "raw closes (historical)"), ("parity", "stale ITM leg repaired")):
        rng = np.random.default_rng(7)
        mv, ev, mask_fn = _load(mode)
        s = _book(mv, ev, mask_fn, 0.80, rng)
        rows.append({"claim": "headline", "mode": mode, "q": 0.80, **s})
        print(
            f"  {tag:26s} n={s['n']:4d}  Sharpe {s['sharpe']:+.3f}  "
            f"CI [{s['ci_lo']:+.3f},{s['ci_hi']:+.3f}]  meanRoM {s['mean_rom']:+.2%}  "
            f"win {s['win']:.0%}  worst {s['worst']:+.1%}  CVaR5 {s['cvar5']:+.1%}"
        )

    print("\n" + "=" * 92)
    print("2. THE OPERATING POINT  (does q=0.80 survive? was the gate fitted to the corruption?)")
    print("=" * 92)
    print(
        f"  {'q':>5s}  {'raw n':>6s} {'raw Sharpe':>11s}   {'rep n':>6s} {'rep Sharpe':>11s}   {'delta':>7s}"
    )
    grid = {}
    for mode in ("raw", "parity"):
        rng = np.random.default_rng(7)
        mv, ev, mask_fn = _load(mode)
        grid[mode] = {q: _book(mv, ev, mask_fn, q, rng) for q in Q_GRID}
        for q in Q_GRID:
            rows.append({"claim": "q_sweep", "mode": mode, "q": q, **grid[mode][q]})
    for q in Q_GRID:
        a, b = grid["raw"][q], grid["parity"][q]
        star = "  <- historical operating point" if q == 0.80 else ""
        print(
            f"  {q:5.2f}  {a['n']:6d} {a['sharpe']:+11.3f}   {b['n']:6d} {b['sharpe']:+11.3f}   "
            f"{b['sharpe'] - a['sharpe']:+7.3f}{star}"
        )
    best_raw = max(
        Q_GRID,
        key=lambda q: (grid["raw"][q]["sharpe"] if np.isfinite(grid["raw"][q]["sharpe"]) else -9),
    )
    best_rep = max(
        Q_GRID,
        key=lambda q: (
            grid["parity"][q]["sharpe"] if np.isfinite(grid["parity"][q]["sharpe"]) else -9
        ),
    )
    print(f"\n  argmax q on raw marks     : {best_raw:.2f}")
    print(f"  argmax q on repaired marks: {best_rep:.2f}")
    print("  (if these differ, the operating point was partly fitted to stale prints)")

    print("\n" + "=" * 92)
    print("3. THE HOLD-OUT  (in-sample 2019-2022 -> out-of-sample 2023-2024, q=0.80)")
    print("=" * 92)
    for mode, tag in (("raw", "raw closes"), ("parity", "repaired")):
        rng = np.random.default_rng(7)
        mv, ev, mask_fn = _load(mode)
        ins = _book(mv, ev, mask_fn, 0.80, rng, hi=HOLDOUT_CUT)
        oos = _book(mv, ev, mask_fn, 0.80, rng, lo=HOLDOUT_CUT)
        rows.append({"claim": "in_sample", "mode": mode, "q": 0.80, **ins})
        rows.append({"claim": "out_sample", "mode": mode, "q": 0.80, **oos})
        print(
            f"  {tag:12s} IS  n={ins['n']:4d} Sharpe {ins['sharpe']:+.3f}  |  "
            f"OOS n={oos['n']:4d} Sharpe {oos['sharpe']:+.3f} CI [{oos['ci_lo']:+.3f},{oos['ci_hi']:+.3f}]"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\nwrote {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
