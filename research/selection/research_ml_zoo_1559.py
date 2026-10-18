"""
research_ml_zoo_1559.py
Rebuild the broad-universe event features from the 15:59 ET consolidated quotes and re-run the
walk-forward zoo, to test whether the broad-block result survives on features a trader could
compute at the 15:59 entry.

The 2025-2026 broad features were built from Alpaca daily bars, whose "close" is each contract's
last trade of the day (possibly after 15:59, or days stale). Their 25-delta skew correlates only
0.09 with the skew from 15:59 quotes, and only the Alpaca version predicts straddle P&L. This script
feeds ``build_execution_events`` a chain fetcher that returns the cached 15:59 Databento chain, with
implied volatility inverted from each quote's mid against the expiry's put-call-parity forward, and
leaves every other step unchanged.

Usage:
    python research/selection/research_ml_zoo_1559.py --features
    python research/selection/research_ml_zoo_1559.py --run [--workers 6]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data.options import CHAIN_COLUMNS  # noqa: E402
from earnings_iv_crush.data.real_events import build_execution_events  # noqa: E402
from earnings_iv_crush.engine.greeks import implied_vol  # noqa: E402
from earnings_iv_crush.research.chains import _parse_chain  # noqa: E402
from scripts.build.build_broad_oos_2025 import _fetch_prices  # noqa: E402

CHAINS = Path("data/cache/backfill_chains")
OUT = Path("outputs/research/ml_zoo")
FEATS = OUT / "broad_features_1559.parquet"
HORIZON_DAYS = 75
STRIKE_BAND = 0.45


def fetch_chain_1559(ticker: str, asof: str, **_: object) -> pd.DataFrame:
    """Cached 15:59 chain in the canonical schema, IV inverted from the quote mid."""
    p = CHAINS / f"{ticker}_{asof}.parquet"
    empty = pd.DataFrame(columns=CHAIN_COLUMNS)
    if not p.exists():
        return empty
    d = _parse_chain(pd.read_parquet(p))
    if d is None:
        return empty
    day = pd.Timestamp(asof)
    d = d[(d["expiry"] >= day) & (d["expiry"] <= day + pd.Timedelta(days=HORIZON_DAYS))].copy()
    rows = []
    for exp, g in d.groupby("expiry"):
        c = g[g["right"] == "C"].set_index("strike")["mid"]
        pp = g[g["right"] == "P"].set_index("strike")["mid"]
        both = c.index.intersection(pp.index)
        if len(both) == 0:
            continue
        diff = (c[both] - pp[both]).abs().nsmallest(3).index
        fwd = float(np.median(np.asarray(diff, dtype=float) + (c[diff] - pp[diff]).to_numpy()))
        t = max((pd.Timestamp(exp) - day).days, 0.5) / 365.0
        g = g[(g["strike"] >= fwd * (1 - STRIKE_BAND)) & (g["strike"] <= fwd * (1 + STRIKE_BAND))]
        for k, right, bid, ask, mid in zip(
            g["strike"], g["right"], g["bid_px_00"], g["ask_px_00"], g["mid"], strict=True
        ):
            iv = implied_vol(float(mid), fwd, float(k), t, 0.0, right, hi=10.0)
            rows.append(
                {
                    "expiry": pd.Timestamp(exp),
                    "strike": float(k),
                    "right": right,
                    "bid": float(bid),
                    "ask": float(ask),
                    "iv": iv,
                    "open_interest": np.nan,
                }
            )
    return pd.DataFrame(rows, columns=CHAIN_COLUMNS) if rows else empty


def features() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cal_a = pd.read_parquet("outputs/research/events_master_broad.parquet")
    cal_a = cal_a[pd.to_datetime(cal_a["announce_date"]) >= "2025-01-01"][
        ["ticker", "announce_date", "session"]
    ]
    led = pd.read_csv(
        "outputs/research/backfill_ledger.csv", parse_dates=["announce_date", "entry_date"]
    )
    cal_b = led[["ticker", "announce_date"]].assign(
        session=np.where(led["entry_date"] == led["announce_date"], "amc", "bmo")
    )
    cal = pd.concat([cal_a, cal_b]).drop_duplicates(["ticker", "announce_date"])
    cal["announce_date"] = pd.to_datetime(cal["announce_date"])
    parts = []
    for i, (t, sub) in enumerate(cal.groupby("ticker"), start=1):
        try:
            ev = build_execution_events(
                sub, fetch_chain=fetch_chain_1559, fetch_prices=_fetch_prices
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {t}: failed ({type(exc).__name__})", flush=True)
            continue
        if not ev.empty:
            parts.append(ev)
        if i % 25 == 0:
            print(f"  {i} names, {sum(len(p) for p in parts)} events", flush=True)
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(FEATS, index=False)
    print(f"  15:59 features for {len(out)} of {len(cal)} events", flush=True)


def run(workers: int) -> None:
    import research.selection.research_ml_zoo as zoo

    base = pd.read_parquet(zoo.EVENTS)
    f = pd.read_parquet(FEATS)
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    f = f.drop_duplicates(["ticker", "entry_date"])
    cols = ["ticker", "entry_date", *zoo.BASE]
    is_broad = base["block"].str.startswith("broad")
    b = (
        base[is_broad]
        .drop(columns=zoo.BASE)
        .merge(f[cols], on=["ticker", "entry_date"], how="inner")
    )
    b["log_implied"] = np.log(b["implied_move"])
    b["implied_over_daily_rv"] = b["implied_move"] / (b["trailing_rv"] * np.sqrt(1 / 252))
    b["implied_over_hist"] = b["implied_move"] / b["hist_move_8"]
    # the outcome ratio keeps its realised move but uses the 15:59 implied move
    b["y"] = b["realised_move"] / b["implied_move"]
    merged = pd.concat([base[~is_broad], b], ignore_index=True).sort_values("entry_date")
    print(f"  broad rows with 15:59 features: {len(b)} of {int(is_broad.sum())}", flush=True)
    target = OUT / "events_1559.parquet"
    merged.to_parquet(target, index=False)
    os.environ["ZOO_EVENTS"] = str(target)
    zoo.EVENTS = target
    zoo_out_csv = OUT / "zoo_results.csv"
    zoo_out_pred = OUT / "zoo_predictions.parquet"
    keep = {p: p.read_bytes() for p in (zoo_out_csv, zoo_out_pred) if p.exists()}
    zoo.run(workers)
    (OUT / "zoo_results.csv").rename(OUT / "zoo_results_1559.csv")
    (OUT / "zoo_predictions.parquet").rename(OUT / "zoo_predictions_1559.parquet")
    for p, data in keep.items():
        p.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--features", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.features:
        features()
    if a.run:
        run(a.workers)


if __name__ == "__main__":
    main()
