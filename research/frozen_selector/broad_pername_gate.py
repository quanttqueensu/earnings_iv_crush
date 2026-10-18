"""
broad_pername_gate.py
Can the broad book use a per-name trailing gate instead of the coarse pooled cut?

``broad_verdict.py`` gates the broad universe on a single cross-sectional quantile of
``iv_term_spread`` pooled across all 346 names. That picks structurally steep, sector-
tilted names rather than each name's own unusually-feared events, which is the confound
the mega-cap per-name panel gate avoids. This script tests the like-for-like alternative:
gate each event on its *own name's* expanding trailing term-spread percentile.

The broad event set spans 2024-2025 only, so most names carry a handful of events. A
per-name expanding gate needs a minimum prior history per name (``K_MIN``), so the test is
expected to be thin; reporting *how* thin is itself the result. If only a small fraction of
events qualify, the coarse pooled gate is the only feasible breadth gate and the broad result
must be read with that caveat.

Output: ``outputs/research/broad_pername_gate.csv``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from earnings_iv_crush.baseline.agent0 import run_agent0
from earnings_iv_crush.engine.backtester import frequency_neutral_stats
from earnings_iv_crush.engine.costs import CostModel
from earnings_iv_crush.engine.pnl import build_ledger
from earnings_iv_crush.strategy.filters import TERM_SPREAD_PCTL

EVENTS = Path("outputs/research/events_broad_full.parquet")
OUT = Path("outputs/research/broad_pername_gate.csv")

K_MIN = 3  # minimum strictly-earlier events for a name before its gate can fire
Q = TERM_SPREAD_PCTL  # 0.80, same percentile as the pooled gate


def _load() -> pd.DataFrame:
    df = pd.read_parquet(EVENTS)
    df = df[df["iv_exit"] != df["iv_entry"]].reset_index(drop=True)
    df["announce_date"] = pd.to_datetime(df["announce_date"])
    return df.sort_values(["ticker", "announce_date"]).reset_index(drop=True)


def _per_name_gate(df: pd.DataFrame) -> pd.DataFrame:
    """Flag each event that clears its own name's expanding term-spread percentile."""
    qualifies = np.zeros(len(df), dtype=bool)  # had >= K_MIN priors (gate could fire)
    passes = np.zeros(len(df), dtype=bool)  # cleared the per-name percentile
    for _, idx in df.groupby("ticker").groups.items():
        spreads = df.loc[idx, "iv_term_spread"].to_numpy()
        for j in range(len(idx)):
            priors = spreads[:j]
            if len(priors) < K_MIN:
                continue
            qualifies[idx[j]] = True
            # Expanding percentile of this event within its own name's history.
            pct = float((priors <= spreads[j]).mean())
            if pct >= Q:
                passes[idx[j]] = True
    out = df.copy()
    out["pername_qualifies"] = qualifies
    out["pername_passes"] = passes
    return out


def main() -> None:
    df = _per_name_gate(_load())
    costs = CostModel()

    n_events = len(df)
    n_names = df["ticker"].nunique()
    events_per_name = df.groupby("ticker").size()
    names_with_history = int((events_per_name > K_MIN).sum())
    n_qualifying = int(df["pername_qualifies"].sum())
    gated = df[df["pername_passes"]]
    n_gated = int(len(gated))

    print(f"Broad universe: {n_events} events, {n_names} names")
    print(f"Median events per name: {events_per_name.median():.0f} (max {events_per_name.max()})")
    print(f"Names with > {K_MIN} events (gate can ever fire): {names_with_history}/{n_names}")
    print(f"Events with >= {K_MIN} priors (gate-eligible): {n_qualifying}/{n_events}")
    print(f"Events passing the per-name {Q:.0%} gate: {n_gated}")

    thin = n_gated < 50  # too few to read a per-trade Sharpe with any confidence
    stats: dict = {}
    if n_gated > 0:
        led = build_ledger(gated, costs=costs)
        ctrl = run_agent0(df, seed=11, costs=costs)
        stats = frequency_neutral_stats(led, ctrl, n_boot=2000, seed=0)
        print(f"  booked trades             {len(led)}")
        print(f"  per_trade_sharpe (pername){stats['per_trade_sharpe_strategy']:+.3f}")
        print(f"  per_trade_sharpe_delta    {stats['per_trade_sharpe_delta']:+.3f}")
        print(
            f"  size_matched_95_CI        [{stats['size_matched_delta_ci_low']:+.2f}, "
            f"{stats['size_matched_delta_ci_high']:+.2f}]"
        )
    print(
        f"\nThin sample: {thin}  (the per-name gate is {'NOT ' if not thin else ''}feasible here)"
    )

    pd.DataFrame(
        [
            {
                "n_events": n_events,
                "n_names": n_names,
                "median_events_per_name": float(events_per_name.median()),
                "names_with_history": names_with_history,
                "n_gate_eligible": n_qualifying,
                "n_gated": n_gated,
                "k_min": K_MIN,
                "q": Q,
                "thin_sample": thin,
                "per_trade_sharpe_strategy": stats.get("per_trade_sharpe_strategy", float("nan")),
                "per_trade_sharpe_delta": stats.get("per_trade_sharpe_delta", float("nan")),
                "size_matched_delta_ci_low": stats.get("size_matched_delta_ci_low", float("nan")),
                "size_matched_delta_ci_high": stats.get("size_matched_delta_ci_high", float("nan")),
            }
        ]
    ).to_csv(OUT, index=False)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
