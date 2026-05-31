"""run_research.py
Enriched end-to-end research run: filtered strategy vs Agent 0, net of costs.

Runs the full chain on a synthetic, VIX- and sector-tagged event set with a
planted edge: fit the fair-move model, select through both filters, book the
ledger both gross (commission-only) and net (full cost stack), score with the
expanded metric set, run the significance comparison (Sharpe spread, paired
t-test, bootstrap CI, Deflated Sharpe), report the regime structure mix and the
Greek P&L attribution, and write a tearsheet.

It validates the W1-W7 machinery against a known answer. It is NOT evidence of
real edge — that needs historical option surfaces.

Usage (from the project root):
    python scripts/run_research.py

Outputs: outputs/research/tearsheet.png and outputs/research/metrics.csv
Runtime: a few seconds (pure CPU, no network).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.baseline.agent0 import run_agent0                  # noqa: E402
from src.engine.backtester import backtest, compare         # noqa: E402
from src.engine.costs import CostModel                      # noqa: E402
from src.engine.reporting import (                          # noqa: E402
    aggregate_pnl_attribution, build_tearsheet,
)
from src.engine.simulate import simulate_events             # noqa: E402
from src.strategy.fair_move_model import FairMoveModel      # noqa: E402
from src.strategy.filters import select_events              # noqa: E402
from src.strategy.regime import assign_structures           # noqa: E402
from src.strategy.strategy import run_strategy              # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs" / "research"
N_FILTER_TRIALS = 20      # filter-threshold grid points effectively tried
# Per-period (daily) Sharpe dispersion across those trials. A daily Sharpe of
# ~0.06 corresponds to an annual Sharpe of ~1, so trial dispersion is small in
# per-period units; 0.02 is a realistic spread for a modest threshold grid.
SR_TRIALS_STD = 0.02


def _show(name: str, stats: dict, keys) -> None:
    print(f"\n{name}")
    print("-" * len(name))
    for k in keys:
        v = stats.get(k)
        if isinstance(v, float):
            print(f"  {k:24s} {v:,.4f}")
        else:
            print(f"  {k:24s} {v}")


def main() -> None:
    events = simulate_events(n=600, seed=11, edge_frac=0.35,
                             with_vix=True, with_sectors=True)
    rich = int(events["is_rich"].sum())
    print("=" * 70)
    print("Earnings IV-Crush — enriched research run (synthetic, planted edge)")
    print("=" * 70)
    print(f"Events: {len(events)}  |  rich (planted): {rich}  |  output: {OUTPUT_DIR}")

    model = FairMoveModel().fit(events, events["realised_move"])
    costs = CostModel()

    # Gross (commission-only) vs net (full cost stack) — the thesis is net.
    gross = backtest(run_strategy(events, model))
    net_strat_ledger = run_strategy(events, model, costs=costs)
    net_agent0_ledger = run_agent0(events, seed=11, costs=costs)
    net_strat = backtest(net_strat_ledger)
    net_agent0 = backtest(net_agent0_ledger)

    metric_keys = ("n_trades", "total_return", "hit_rate", "sharpe", "sortino",
                   "profit_factor", "win_loss_ratio", "max_drawdown",
                   "max_dd_duration", "avg_return_on_margin")
    _show("Filtered strategy — GROSS (commission only)", gross, metric_keys)
    _show("Filtered strategy — NET (full cost stack)", net_strat, metric_keys)
    _show("Agent 0 control — NET", net_agent0, metric_keys)

    cost_drag = gross["total_return"] - net_strat["total_return"]
    print(f"\nCost drag (gross - net total return): {cost_drag:+.4%}")

    # Significance of the filter, net of costs.
    cmp = compare(net_strat_ledger, net_agent0_ledger,
                  n_trials=N_FILTER_TRIALS, sr_trials_std=SR_TRIALS_STD, seed=1)
    _show("Filter significance (net of costs)", cmp,
          ("sharpe_strategy", "sharpe_agent0", "sharpe_delta",
           "sharpe_delta_ci_low", "sharpe_delta_ci_high",
           "spread_tstat", "spread_pvalue", "psr_strategy", "dsr_strategy"))

    # Regime structure mix over the selected events.
    selected = select_events(events, model.predict(events))
    structure_counts = (
        assign_structures(selected, model.predict(selected)).value_counts().to_dict()
    )
    print("\nStructure mix (selected events):")
    for label, count in structure_counts.items():
        print(f"  {label:10s} {count}")

    # Greek P&L attribution.
    attrib = aggregate_pnl_attribution(net_strat_ledger)
    print("\nP&L attribution (USD, net book):")
    for k, v in attrib.items():
        print(f"  {k:12s} {v:,.0f}")

    png = build_tearsheet(net_strat_ledger, net_agent0_ledger, cmp,
                          account=net_strat["final_equity"] - net_strat["total_pnl"],
                          outdir=OUTPUT_DIR, structure_counts=structure_counts)

    gate = "PASS" if cmp["filter_gate_pass"] else "below gate"
    print("\n" + "=" * 70)
    print(f"Verdict (synthetic): filter beats control by "
          f"{cmp['sharpe_delta']:+.2f} Sharpe net of costs — {gate} "
          f"(>= +0.50 gate).")
    print(f"Tearsheet: {png}")


if __name__ == "__main__":
    main()
