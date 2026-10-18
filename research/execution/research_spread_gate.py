"""
research_spread_gate.py
Pre-registered causal spread gate on both megacap blocks.

Test S of ``research/execution/preregs/cost_levers_prereg.md``. Each event's expected round-trip cost is
built from information available at the 15:59 entry: the current entry half-spread relative
to mid, plus the mean relative exit half-spread over the name's earlier completed events.
The book trades an event only when that expected cost is at or below the causal expanding
median of strictly earlier events. P&L is charged at each event's own quoted touch (sell the
entry bid, buy the exit ask), because a flat percentage cost would charge every event alike
and give a cost gate nothing to act on.

The pre-stated counter-hypothesis, that tight-spread names are the most efficiently priced,
is reported as the gated book's mean gross return at the mid against the ungated book's.

Usage:
    python research/execution/research_spread_gate.py

References
----------
Bailey, D. H. and Lopez de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of
Portfolio Management* 40(5), 94-107.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402

PANEL = Path("outputs/research/reverse_alpha/panel.parquet")
QUOTES = Path("outputs/research/reverse_alpha/quotes.parquet")
PERF = Path("outputs/research/performance_panel.csv")
OUT = Path("outputs/research/cost_levers")

GATE_Q = 0.50
MIN_HIST = 25
MIN_NAME_PRIOR = 3
ENTRY_HALF, EXIT_HALF = 0.012714, 0.030182  # measured flat basis, diagnostic only
N_NULL = 1000
N_TRIALS = 1491
N_BOOT = 5000
SEED = 0


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    return float(x.mean() / x.std(ddof=1)) if len(x) > 1 and x.std(ddof=1) > 0 else float("nan")


def build(block: str, panel: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Join quotes to the block's events, attach the cost signal and both P&L bases."""
    # The panel carries its own exit_ask from the marking pass; the quote file is the single
    # source for every touch price here, so the panel copy is dropped before the join.
    p = panel[panel["block"] == block].drop(columns=["exit_ask"]).copy()
    q = quotes[quotes["block"] == block].drop(columns=["block"])
    for f in (p, q):
        f["entry_date"] = pd.to_datetime(f["entry_date"])
    d = p.merge(q, on=["ticker", "entry_date"], how="inner", validate="one_to_one")
    d = d[(d["entry_ask"] > d["entry_bid"]) & (d["entry_bid"] > 0) & (d["exit_ask"] > 0)]
    print(f"  {block}: panel {len(p)}, quoted on both sessions {len(d)}")

    d["announce_date"] = pd.to_datetime(d["announce_date"])
    d["exit_date"] = pd.to_datetime(d["exit_date"])
    d = d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    d["entry_rel"] = (d["entry_ask"] - d["entry_bid"]) / (d["entry_ask"] + d["entry_bid"])
    exit_spread = (d["exit_ask"] - d["exit_bid"]).clip(lower=0)
    d["exit_rel"] = exit_spread / (d["exit_ask"] + d["exit_bid"].clip(lower=0))

    prior_exit = np.full(len(d), np.nan)
    for i in range(len(d)):
        m = (d["ticker"] == d.at[i, "ticker"]) & (d["exit_date"] < d.at[i, "entry_date"])
        if m.sum() >= MIN_NAME_PRIOR:
            prior_exit[i] = float(d.loc[m, "exit_rel"].mean())
    d["cost_signal"] = d["entry_rel"] + prior_exit

    k = d["contracts"] * 100
    d["rom_touch"] = (d["entry_bid"] - d["exit_ask"]) * k / d["margin"]
    d["rom_gross_mid"] = (d["credit_mkt"] - d["exit_mkt"]) * k / d["margin"]
    flat = (ENTRY_HALF * d["credit_mkt"] + EXIT_HALF * d["exit_mkt"]) * k
    d["rom_flat"] = ((d["credit_mkt"] - d["exit_mkt"]) * k - flat) / d["margin"]
    return d


def gate(d: pd.DataFrame) -> np.ndarray:
    """Trade when the cost signal is at or below the causal median of strictly earlier events."""
    sig = d["cost_signal"].to_numpy(dtype=float)
    ad = d["announce_date"].to_numpy()
    out = np.zeros(len(d), dtype=bool)
    for i in range(len(d)):
        if not np.isfinite(sig[i]):
            continue
        prior = sig[(ad < ad[i]) & np.isfinite(sig)]
        if prior.size >= MIN_HIST and sig[i] <= np.quantile(prior, GATE_Q):
            out[i] = True
    return out


def score_block(block: str, d: pd.DataFrame, sr_std: float) -> list[dict]:
    eligible = d[np.isfinite(d["cost_signal"])].copy()
    take = gate(d)[np.isfinite(d["cost_signal"]).to_numpy()]
    gated = eligible[take]
    if len(gated) < 3:
        raise SystemExit(f"{block}: gate selected {len(gated)} events - an empty slice, not a null")
    print(f"  {block}: eligible {len(eligible)}, gated {len(gated)}")

    rng = np.random.default_rng(SEED)
    null = np.array(
        [
            sharpe(rng.choice(eligible["rom_touch"].to_numpy(), size=len(gated), replace=False))
            for _ in range(N_NULL)
        ]
    )

    rows = []
    for label, book in (("gated", gated), ("ungated", eligible)):
        x = book["rom_touch"].to_numpy()
        keys = book["entry_date"].dt.strftime("%Y-%m-%d").to_numpy()
        lo, hi = cluster_bootstrap_ci(x, keys, sharpe, n_boot=N_BOOT, seed=SEED)
        rows.append(
            {
                "block": block,
                "book": label,
                "n": len(book),
                "mean_rom_touch": float(x.mean()),
                "sharpe_touch": sharpe(x),
                "sharpe_ci_low": lo,
                "sharpe_ci_high": hi,
                "hit_rate": float((x > 0).mean()),
                "mean_rom_gross_mid": float(book["rom_gross_mid"].mean()),
                "sharpe_flat_measured": sharpe(book["rom_flat"].to_numpy()),
                "mean_cost_signal": float(book["cost_signal"].mean()),
                "null_median_sharpe": float(np.median(null)) if label == "gated" else np.nan,
                "gate_null_percentile": (
                    float((null < sharpe(x)).mean()) if label == "gated" else np.nan
                ),
                "dsr": float(
                    deflated_sharpe_ratio(pd.Series(x), n_trials=N_TRIALS, sr_trials_std=sr_std)
                ),
            }
        )
    return rows


def main() -> None:
    argparse.ArgumentParser(description=__doc__.split("\n")[2]).parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    panel = pd.read_parquet(PANEL)
    quotes = pd.read_parquet(QUOTES)
    sr_std = float(pd.read_csv(PERF).iloc[0]["sr_trials_std"])

    rows = []
    verdicts = {}
    for block in ("holdout_2013_2018", "discovery_2019_2024"):
        print(f"\n== test S, {block}")
        d = build(block, panel, quotes)
        r = score_block(block, d, sr_std)
        rows += r
        g = r[0]
        verdicts[block] = (g["sharpe_ci_low"] > 0) and (g["sharpe_touch"] > g["null_median_sharpe"])

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "spread_gate.csv", index=False)
    print(res.T.to_string(float_format=lambda v: f"{v:.4f}"))
    passed = all(verdicts.values())
    print(f"\n  per block: {verdicts}")
    print(f"  PRIMARY CRITERION: {'PASS' if passed else 'FAIL'}")
    print(f"  wrote {(OUT / 'spread_gate.csv').resolve()}")


if __name__ == "__main__":
    main()
