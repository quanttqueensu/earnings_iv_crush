"""
write_cards.py
Lane D1: ``cards.parquet``, one row per event and frozen configuration on 2019-24 and 2025-26,
keyed as the L4 cards (ticker, entry_date, expiry, announce_date, block): the quadrature
predictive mean and sd of H_net (% of m0 per trade), P(H_net > 0), the log score (nats, H_net
space), PIT, the decision, and L4's log score on the same event. Copies the held-out cards;
computes nothing.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D1-surface-net/write_cards.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
COLS = [
    "ticker",
    "entry_date",
    "expiry",
    "announce_date",
    "block",
    "refit_date",
    "mean",
    "sd",
    "p_pos",
    "log_score",
    "pit",
    "decide",
    "m_log_score",
    "b_log_score",
    "y",
    "rv",
]
RENAME = {
    "mean": "pred_mean_H_net_pct",
    "sd": "pred_sd_H_net_pct",
    "p_pos": "pred_p_pos",
    "decide": "decision_mean_gt_0",
    "m_log_score": "l4_log_score",
    "b_log_score": "l4_baseline_log_score",
    "y": "H_net_pct",
    "rv": "residual_value_pct",
}


def main() -> None:
    parts = []
    for p in sorted((HERE / "heldout").glob("cards_*.parquet")):
        if p.name.endswith(".partial.parquet"):
            raise ValueError(f"{p.name} is a partial file")
        which, block = p.stem.removeprefix("cards_").rsplit("_", 1)
        c = pd.read_parquet(p)[COLS].rename(columns=RENAME)
        c.insert(0, "config", which)
        parts.append(c)
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(HERE / "cards.parquet")
    print(out.groupby(["config", "block"]).size())


if __name__ == "__main__":
    main()
