"""s03_heldout.py: N08 held-out scorer for trial 2,312 (frozen rule of trial 2,307), block H only.

Rule (frozen in freeze_2026-11-13_cpi-short-tenor-hedged-hold.md): on SPY, sell the ATM straddle of
the shortest expiry strictly after an 08:30 CPI or payrolls release day D at the 15:59 bids on the
session before D, only when that expiry is at most 3 calendar days after entry; delta-hedge at
each close at the entry implied volatility; settle at intrinsic with the adopted netting
(HEDGED_NET). Paired against clean nights with the same weekday and days to expiry within 60
sessions (at least 5). Statistic: mean per trade in units of the entry mid premium, net, with
protocol.date_clustered_ci (mean, 5,000 draws, seed 0, 95%).

PASS: event-book mean > 0 and paired mean > 0 with its interval excluding zero.

Secondary, cannot rescue the primary: QQQ and IWM under the same rule; SPY with PCE added; the
SPY result on margin; per-event list.

Refuses to run if its output already exists (one read only).

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N08-index-macro-cached/s03_heldout.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from earnings_iv_crush.research.protocol import date_clustered_ci, per_trade_sharpe

HERE = Path(__file__).resolve().parent
OUT = HERE / "heldout_2312.json"
MAX_DTE = 3.0
H_START, H_END = pd.Timestamp("2025-01-02"), pd.Timestamp("2026-10-30")

_s = importlib.util.spec_from_file_location("disc", HERE / "s02_discovery.py")
assert _s is not None and _s.loader is not None
disc = importlib.util.module_from_spec(_s)
_s.loader.exec_module(disc)


def run(df: pd.DataFrame, tk: str, mask: pd.Series) -> tuple[dict[str, object], pd.DataFrame]:
    d = df[(df["family"] == "T4") & (df["ticker"] == tk) & (df["status"] == "ok")]
    ev = d[mask.reindex(d.index).fillna(False).to_numpy()]
    pool = d[disc.is_clean(d)]
    e = disc.matched(ev, pool, "short_net")
    n_all = len(e)
    e = e[(e["n_ctl"] >= disc.MIN_CONTROLS) & np.isfinite(e["short_net"])].copy()
    e["diff"] = e["short_net"] - e["ctl"]
    if e.empty:
        raise ValueError(f"{tk}: no held-out events survive matching")
    b = date_clustered_ci(e["short_net"].to_numpy(), e["event_date"].to_numpy(), stat=np.mean)
    p = date_clustered_ci(e["diff"].to_numpy(), e["event_date"].to_numpy(), stat=np.mean)
    res = {"ticker": tk, "events": n_all, "n": b.n, "book": [b.point, b.low, b.high],
           "diff": [p.point, p.low, p.high], "sharpe_pt": per_trade_sharpe(e["short_net"]),
           "rom_mean": float(e["short_net_rom"].mean()), "mid_mean": float(e["short_mid"].mean()),
           "control_pool": int(len(pool)),
           "pass": bool(b.point > 0 and p.low > 0)}
    return res, e


def main() -> None:
    if OUT.exists():
        sys.exit(f"{OUT.name} exists: the held-out block has been read once already")
    a = pd.read_parquet(HERE / "trades_all.parquet")
    r2 = pd.read_parquet(HERE / "trades_round2.parquet")
    df = pd.concat([a, r2], ignore_index=True)
    df = df[(df["block"] == "H") & (df["dte"] <= MAX_DTE)].copy()
    if df["entry"].min() < H_START or df["entry"].max() > H_END:
        sys.exit("rows outside the held-out block")
    r = df["ev_cpi"] | df["ev_nfp"]
    rp = r | df["ev_pce"]
    out: dict[str, object] = {}
    prim, e = run(df, "SPY", r)
    out["primary_SPY_R"] = prim
    print(f"PRIMARY 2312 SPY R, T4, dte<=3, block H: N={prim['n']} of {prim['events']} events")
    print(f"  book {prim['book']}  paired {prim['diff']}  Sharpe/trade {prim['sharpe_pt']:+.3f}")
    print(f"  on margin {prim['rom_mean']:+.5f}; mid {prim['mid_mean']:+.4f}; "
          f"verdict {'PASS' if prim['pass'] else 'FAIL'}")
    print(e[["event_date", "dte", "short_net", "ctl", "diff", "n_ctl"]].round(4).to_string())
    for tk, m, key in (("QQQ", r, "sec_QQQ_R"), ("IWM", r, "sec_IWM_R"), ("SPY", rp, "sec_SPY_Rplus")):
        try:
            s, _ = run(df, tk, m)
        except ValueError as exc:
            s = {"error": str(exc)}
        out[key] = s
        print(f"secondary {key}: {s}")
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
