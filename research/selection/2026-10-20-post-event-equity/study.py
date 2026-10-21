"""
study.py
Post-event put skew (E1) and implied term slope (E2) as predictors of the stock's next 20
sessions, traded in the stock, scored exactly as frozen in ``prereg.md``.

Usage
-----
    python research/selection/2026-10-20-post-event-equity/study.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
OUT = ROOT / "outputs" / "research" / HERE.name
FEATS = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold"
PANEL_DAILY = ROOT / "outputs" / "research" / "panel_daily.parquet"

BLOCKS = {"discovery": (2013, 2018), "validation": (2019, 2024)}
N_TRIALS = 1539
SR_TRIALS_STD = 0.127475
SIGNALS = {"E1_skew": ("post_skew", -1), "E2_slope": ("post_slope", +1)}  # +1 long high decile


def forward_returns(ev: pd.DataFrame, crsp: pd.DataFrame) -> pd.DataFrame:
    """Market-adjusted 20-session return from the exit close and its round-trip cost."""
    mkt = (
        pd.read_parquet(PANEL_DAILY, columns=["date", "mktrf", "rf"])
        .drop_duplicates("date")
        .set_index("date")
    )
    mkt.index = pd.to_datetime(mkt.index)
    m = mkt["mktrf"] + mkt["rf"]
    floor = HEDGED.equity_cost_floor_bps / 1e4
    by = {int(p): g.set_index("date").sort_index() for p, g in crsp.groupby("permno")}
    h = HEDGED.equity_hold_days
    rows = []
    for p, d in zip(ev["permno"], pd.to_datetime(ev["exit_date"]), strict=True):
        g = by.get(int(p)) if np.isfinite(p) else None
        if g is None or d not in g.index:
            rows.append((np.nan, np.nan, "no_path"))
            continue
        pos = g.index.get_loc(d)
        w = g.iloc[pos : pos + h + 1]
        if len(w) < h + 1 or w["ret"].iloc[1:].isna().any():
            rows.append((np.nan, np.nan, "path_incomplete"))
            continue
        mk = m.reindex(w.index[1:])
        if mk.isna().any():
            rows.append((np.nan, np.nan, "no_market"))
            continue
        stock = float(np.prod(1 + w["ret"].iloc[1:].to_numpy(float)) - 1)
        market = float(np.prod(1 + mk.to_numpy(float)) - 1)
        hs = []
        for i in (0, -1):
            b, a, px = w["bid"].iloc[i], w["ask"].iloc[i], abs(w["prc"].iloc[i])
            hs.append(max((a - b) / 2 / px, floor) if b > 0 and a > b else np.nan)
        if not np.isfinite(hs).all():
            rows.append((np.nan, np.nan, "no_quotes"))
            continue
        rows.append((stock - market, float(sum(hs)), "ok"))
    return pd.DataFrame(rows, columns=["adj_ret", "rt_cost", "reason"], index=ev.index)


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f"pre-registration verified, sha256 {verify_prereg(PREREG, RECORD)[:12]}")
    feat = pd.read_parquet(FEATS / "features.parquet")
    crsp = pd.read_parquet(FEATS / "crsp_paths.parquet")
    y = pd.to_datetime(feat["exit_date"]).dt.year
    feat["block"] = "other"
    for name, (a, b) in BLOCKS.items():
        feat.loc[(y >= a) & (y <= b), "block"] = name
    ev = feat[feat["block"].isin(list(BLOCKS))].reset_index(drop=True)
    fr = forward_returns(ev, crsp)
    ev = pd.concat([ev, fr], axis=1)
    print(f"funnel: {len(ev)} events; {fr['reason'].value_counts().to_dict()}")
    ok = ev[ev["reason"] == "ok"].copy()
    summary: dict = {"prereg_sha256": verify_prereg(PREREG, RECORD), "results": {}}
    for name, (col, side) in SIGNALS.items():
        print(f"\n== {name} ({col}) ==")
        d = ok[np.isfinite(ok[col])].copy()
        d["bin"] = hh.causal_bins(d[col], d["exit_date"], 10, HEDGED.decile_min_prior)
        long_bin, short_bin = (9, 0) if side > 0 else (0, 9)
        dec = (
            d[d["bin"] >= 0]
            .groupby(["block", "bin"])["adj_ret"]
            .agg(["size", "mean"])
            .unstack("block")
        )
        for blk in BLOCKS:
            if blk == "validation" and not summary["results"][f"{name}_discovery"]["pass"]:
                print(f"  {name} fails discovery: validation not run (kill criterion)")
                continue
            b = d[(d["block"] == blk) & d["bin"].isin([long_bin, short_bin])]
            sign = np.where(b["bin"] == long_bin, 1.0, -1.0)
            pos = sign * b["adj_ret"].to_numpy(float) - b["rt_cost"].to_numpy(float)
            ci = date_clustered_ci(pos, b["exit_date"], stat=np.mean)
            res = {
                "n_positions": int(len(pos)),
                "n_long": int((sign > 0).sum()),
                "n_short": int((sign < 0).sum()),
                "mean_net_per_position": ci.point,
                "ci": [ci.low, ci.high],
                "per_position_sharpe": per_trade_sharpe(pos),
                "dsr": float(deflated_sharpe_ratio(pd.Series(pos), N_TRIALS, SR_TRIALS_STD)),
                "median_rt_cost": float(np.median(b["rt_cost"])),
                "pass": bool(ci.low > 0),
            }
            summary["results"][f"{name}_{blk}"] = res
            print(
                f"  {blk}: {res['n_positions']} positions, mean net per 20-day position {ci};"
                f" Sharpe {res['per_position_sharpe']:+.3f}, DSR {res['dsr']:.3f},"
                f" median round-trip cost {res['median_rt_cost'] * 1e4:.1f} bp"
            )
        print("  deciles (mean market-adjusted 20-day return, gross):")
        print(dec.loc[:, [c for c in dec.columns if c[1] == "discovery"]].to_string())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(f"wrote {OUT / 'summary.json'}")


if __name__ == "__main__":
    main()
