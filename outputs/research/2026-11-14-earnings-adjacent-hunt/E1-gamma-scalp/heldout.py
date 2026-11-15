"""
heldout.py
Lane E1 held-out scorer: reads broad_2025_2026 entries from 2025-07-01 onward ONCE, for the rule
frozen in ``freeze_2026-11-14_e1.md``. Written before the freeze note, which records this file's
SHA-256. It refuses to run if the freeze note is missing or a held-out log already exists.

Frozen rule (the declared primary, trial 2,682, unchanged): buy the held straddle (entry strike,
front expiry) at the 15:01:00 ET ask on the reaction session, delta-hedge in the stock on a
5-minute clock with the hedge ratio from the parity forward and straddle-mid IV observed 30 s
earlier, sell at the 15:59:00 bid (a leg without a bid sold at zero). Option legs pay the touch
plus USD 0.65 per contract per leg; stock legs pay 3 bp plus 1 bp of traded notional. Statistic:
mean net P&L per trade in % of the debit, date-clustered 95% interval over reaction dates.
Pass: mean > 0 with the interval excluding zero.

Usage:
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E1-gamma-scalp/heldout.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
)

FREEZE = HERE / "freeze_2026-11-14_e1.md"
OUT = HERE / "heldout.log"
SPLIT = pd.Timestamp("2025-07-01")
TRIAL = 2682


def main() -> None:
    if not FREEZE.exists():
        raise SystemExit("freeze note missing: the held-out block is read only after the freeze")
    if OUT.exists():
        raise SystemExit("held-out already read once; not reading it again")
    ev, grid = lib.load()
    hold = ((ev["block"] == "broad_2025_2026") & (ev["entry_date"] >= SPLIT)).to_numpy()
    d1 = lib.session(ev, grid, "D1")
    ok = hold & lib.entry_ok(d1) & np.isfinite(ev["s0"].to_numpy())
    e = ev[ok].reset_index(drop=True)
    s = lib.session(e, grid[ok], "D1")
    out = lib.scalp(s, clock_sec=300)
    dates = e["exit_date"]
    x = out["net"].to_numpy() / out["debit"].to_numpy()
    iv = date_clustered_ci(x, dates, stat=np.mean)
    g = out["gross_mid"].to_numpy() / out["debit"].to_numpy()
    gm = np.isfinite(g)
    ivg = date_clustered_ci(g[gm], dates[gm], stat=np.mean)
    rt = out["touch_rt"].to_numpy() / out["debit"].to_numpy()
    ivm = date_clustered_ci(out["net"].to_numpy() / e["m0"].to_numpy(), dates, stat=np.mean)
    passed = iv.low > 0
    lines = [
        f"held-out read {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"funnel: held-out events {int(hold.sum())} -> scored {int(ok.sum())}",
        f"trial {TRIAL} net % of debit: {iv.point * 100:+.3f} [{iv.low * 100:+.3f}, "
        f"{iv.high * 100:+.3f}] (N={iv.n}, {iv.clusters} dates); per-trade Sharpe "
        f"{per_trade_sharpe(x):+.3f}",
        f"  same, % of m0: {ivm.point * 100:+.3f} [{ivm.low * 100:+.3f}, {ivm.high * 100:+.3f}]",
        f"  C1 gross at mid, % of debit: {ivg.point * 100:+.3f} [{ivg.low * 100:+.3f}, "
        f"{ivg.high * 100:+.3f}] (N={ivg.n})",
        f"  mean round-trip option touch, % of debit: {np.nanmean(rt[gm]) * 100:.3f}",
        f"  pass: {passed}",
    ]
    lib.log_trial({"trial": TRIAL, "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "block": "held-out 2025H2-2026H1", "rule": "frozen primary",
                   "statistic": "mean", "basis": "% debit, net touch", "n": iv.n,
                   "clusters": iv.clusters, "point": round(iv.point * 100, 4),
                   "low": round(iv.low * 100, 4), "high": round(iv.high * 100, 4),
                   "per_trade_sharpe": round(per_trade_sharpe(x), 4),
                   "label": "pass" if passed else "fail", "note": "held-out, read once"})
    txt = "\n".join(lines)
    print(txt)
    OUT.write_text(txt + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
