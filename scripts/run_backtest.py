"""
run_backtest.py
Crude backtest demo: filtered strategy vs the Agent 0 control.

Runs the full chain end-to-end on a SYNTHETIC event set with a planted edge
(see ``earnings_iv_crush/engine/simulate.py``): fit the fair-move model, select events through
both filters, book the ledger, and score it against an unfiltered Agent 0 book.
This validates the harness wiring. It is NOT evidence of real edge - that needs
historical option data.

Usage
-----
From the project root::

    python scripts/run_backtest.py
"""

from __future__ import annotations

from earnings_iv_crush.baseline.agent0 import run_agent0
from earnings_iv_crush.engine.backtester import backtest
from earnings_iv_crush.engine.simulate import simulate_events
from earnings_iv_crush.strategy.fair_move_model import FairMoveModel
from earnings_iv_crush.strategy.strategy import run_strategy

KEYS = [
    "n_trades",
    "total_pnl",
    "total_return",
    "hit_rate",
    "sharpe",
    "max_drawdown",
    "avg_return_on_margin",
    "final_equity",
]


def _show(name: str, stats: dict) -> None:
    print(f"\n{name}")
    print("-" * len(name))
    for k in KEYS:
        v = stats[k]
        if isinstance(v, float):
            print(f"  {k:22s} {v:,.4f}")
        else:
            print(f"  {k:22s} {v}")


def main() -> None:
    events = simulate_events(n=400, seed=7, edge_frac=0.35)
    print(
        f"Simulated {len(events)} events; {int(events['is_rich'].sum())} rich " f"(planted edge)."
    )

    # Fit the fair-move model on the realised move, then run the filtered book.
    model = FairMoveModel().fit(events, events["realised_move"])
    strat_ledger = run_strategy(events, model)
    agent0_ledger = run_agent0(events, seed=7)

    strat = backtest(strat_ledger)
    agent0 = backtest(agent0_ledger)

    _show("Filtered strategy", strat)
    _show("Agent 0 (unfiltered control)", agent0)

    delta = strat["sharpe"] - agent0["sharpe"]
    print(f"\nSharpe delta (strategy - Agent 0): {delta:+.4f}")
    print(
        "Gate to justify the filter: >= +0.50 Sharpe.  "
        f"{'PASS' if delta >= 0.5 else 'below gate'} (synthetic, harness check only)."
    )


if __name__ == "__main__":
    main()
