"""
run_sensitivity.py
Filter-threshold sensitivity sweep plus an out-of-sample walk-forward check.

Sweeps the implied-vs-fair ratio against the term-structure percentile on a
synthetic, VIX-tagged event set; scores each cell versus Agent 0; writes a
Sharpe-spread heatmap and the sweep CSV; and reports the Deflated Sharpe of the
best cell with the number of trials set to the grid size (so the headline Sharpe
is discounted for having searched the grid). It then runs a no-look-ahead
walk-forward backtest at the default thresholds.

This is the 31 July sensitivity / walk-forward deliverable on synthetic data; it
is not evidence of real edge.

Usage
-----
From the project root::

    python scripts/run_sensitivity.py

Outputs
-------
``outputs/sensitivity/heatmap.png`` and ``outputs/sensitivity/sweep.csv``.
Runtime: a few seconds (pure CPU, no network).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.engine.backtester import daily_return_series           # noqa: E402
from src.engine.costs import CostModel                          # noqa: E402
from src.engine.pnl import build_ledger                         # noqa: E402
from src.engine.sensitivity import sweep_dsr_params, threshold_sweep  # noqa: E402
from src.engine.simulate import simulate_events                 # noqa: E402
from src.engine.stats import deflated_sharpe_ratio              # noqa: E402
from src.engine.walkforward import walk_forward_backtest        # noqa: E402
from src.strategy.fair_move_model import FairMoveModel          # noqa: E402
from src.strategy.filters import select_events                  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs" / "sensitivity"
RATIOS = [1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.40, 1.50]
PCTLS = [0.50, 0.60, 0.70, 0.75, 0.80, 0.90]


def _heatmap(sweep, path: Path) -> None:
    grid = sweep.pivot(index="ratio", columns="pctl", values="sharpe_delta")
    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(grid.to_numpy(), aspect="auto", origin="lower", cmap="viridis")
    ax.set_xticks(range(len(grid.columns)))
    ax.set_xticklabels([f"{c:.2f}" for c in grid.columns])
    ax.set_yticks(range(len(grid.index)))
    ax.set_yticklabels([f"{r:.2f}" for r in grid.index])
    ax.set_xlabel("Term-structure percentile")
    ax.set_ylabel("Implied / fair ratio")
    ax.set_title("Sharpe spread over Agent 0 by filter threshold")
    fig.colorbar(im, ax=ax, label="Sharpe delta")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    events = simulate_events(n=600, seed=21, edge_frac=0.35, with_vix=True)
    model = FairMoveModel().fit(events, events["realised_move"])
    costs = CostModel()

    print("=" * 70)
    print("Earnings IV-Crush — threshold sensitivity + walk-forward (synthetic)")
    print("=" * 70)
    print(f"Events: {len(events)}  |  grid: {len(RATIOS)}x{len(PCTLS)} "
          f"= {len(RATIOS) * len(PCTLS)} cells  |  output: {OUTPUT_DIR}")

    sweep = threshold_sweep(events, model, RATIOS, PCTLS, costs=costs, agent0_seed=21)
    sweep.to_csv(OUTPUT_DIR / "sweep.csv", index=False)
    _heatmap(sweep, OUTPUT_DIR / "heatmap.png")

    best = sweep.sort_values("sharpe_delta", ascending=False).iloc[0]
    print(f"\nBest cell: ratio={best['ratio']:.2f}, pctl={best['pctl']:.2f} -> "
          f"Sharpe delta {best['sharpe_delta']:+.2f} on {int(best['n_trades'])} trades")

    # Deflated Sharpe of the best cell, deflated by the whole grid search.
    fair = model.predict(events)
    best_ledger = build_ledger(
        select_events(events, fair, ratio=best["ratio"], pctl=best["pctl"]),
        costs=costs,
    )
    n_trials, sr_trials_std = sweep_dsr_params(sweep)
    dsr = deflated_sharpe_ratio(daily_return_series(best_ledger), n_trials, sr_trials_std)
    print(f"Deflated Sharpe (n_trials={n_trials}, sr_std={sr_trials_std:.4f}): {dsr:.4f}")

    # Out-of-sample walk-forward at the default thresholds.
    wf, _ = walk_forward_backtest(events, events["realised_move"], costs=costs)
    print(f"\nWalk-forward (default thresholds): "
          f"OOS events {wf['n_oos']}, selected {wf['n_selected']}, "
          f"Sharpe {wf['sharpe']:.2f}, hit rate {wf['hit_rate']:.2%}")

    print("\n" + "=" * 70)
    print(f"Heatmap: {OUTPUT_DIR / 'heatmap.png'}")
    print(f"Sweep CSV: {OUTPUT_DIR / 'sweep.csv'}")


if __name__ == "__main__":
    main()
