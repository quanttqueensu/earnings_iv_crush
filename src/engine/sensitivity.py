"""sensitivity.py
Filter-threshold sensitivity sweep for the IV-crush strategy.

Re-prices the strategy across a grid of the two filter thresholds — the
implied-vs-fair ratio and the term-structure percentile — and scores each cell
against the unfiltered Agent 0 control. The sweep is the raw material for the
31 July sensitivity deliverable and, crucially, for an honest Deflated Sharpe:
the number of cells is the effective number of trials, which the DSR uses to
discount the best cell's Sharpe for selection bias.

This module implements:

* ``threshold_sweep``    — grid of (ratio, pctl) -> strategy-vs-control metrics.
* ``sweep_dsr_params``   — derive (n_trials, per-period Sharpe dispersion) from a
  sweep, for ``stats.deflated_sharpe_ratio``.

References
----------
Bailey, D. H., & López de Prado, M. (2014). The deflated Sharpe ratio.
*Journal of Portfolio Management*, 40(5), 94-107.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..baseline.agent0 import run_agent0
from ..strategy.fair_move_model import FairMoveModel
from ..strategy.filters import select_events
from .backtester import backtest
from .pnl import ACCOUNT_SIZE, build_ledger

SWEEP_COLUMNS = ["ratio", "pctl", "n_trades", "sharpe", "sharpe_delta",
                 "total_return", "hit_rate", "max_drawdown"]


def threshold_sweep(events: pd.DataFrame, model: FairMoveModel,
                    ratios, pctls, account: float = ACCOUNT_SIZE,
                    fraction: float = 0.05, r: float = 0.0, costs=None,
                    agent0_seed: int = 0) -> pd.DataFrame:
    """
    Score the strategy across a grid of filter thresholds.

    Parameters
    ----------
    events : pd.DataFrame
        Per-event frame with the filter and execution columns.
    model : FairMoveModel
        A fitted fair-move model (the fair move is held fixed; only the filter
        thresholds vary across the grid).
    ratios : sequence of float
        Implied-vs-fair ratio grid (e.g. ``1.05 .. 1.50``).
    pctls : sequence of float
        Term-structure percentile grid (e.g. ``0.50 .. 0.90``).
    account, fraction, r, costs :
        Passed to the ledger builder.
    agent0_seed : int
        Seed for the unfiltered control, scored once as the comparison baseline.

    Returns
    -------
    pd.DataFrame
        One row per grid cell with ``SWEEP_COLUMNS``; ``sharpe_delta`` is the
        strategy Sharpe minus the Agent 0 Sharpe on the same events.
    """
    fair = model.predict(events)
    agent0_sharpe = backtest(
        run_agent0(events, seed=agent0_seed, account=account, fraction=fraction,
                   r=r, costs=costs),
        account,
    )["sharpe"]

    rows = []
    for ratio in ratios:
        for pctl in pctls:
            selected = select_events(events, fair, ratio=ratio, pctl=pctl)
            stats = backtest(build_ledger(selected, account=account,
                                          fraction=fraction, r=r, costs=costs), account)
            rows.append({
                "ratio": float(ratio),
                "pctl": float(pctl),
                "n_trades": stats["n_trades"],
                "sharpe": stats["sharpe"],
                "sharpe_delta": stats["sharpe"] - agent0_sharpe,
                "total_return": stats["total_return"],
                "hit_rate": stats["hit_rate"],
                "max_drawdown": stats["max_drawdown"],
            })
    return pd.DataFrame(rows, columns=SWEEP_COLUMNS)


def sweep_dsr_params(sweep: pd.DataFrame, periods_per_year: int = 252) -> tuple[int, float]:
    """
    Derive Deflated-Sharpe inputs from a threshold sweep.

    Parameters
    ----------
    sweep : pd.DataFrame
        Output of ``threshold_sweep``.
    periods_per_year : int
        Annualisation factor used to convert the annualised cell Sharpes to the
        per-period units the DSR expects. Defaults to ``252``.

    Returns
    -------
    tuple
        ``(n_trials, sr_trials_std)`` — the number of grid cells and the standard
        deviation of the cells' per-period Sharpe ratios.
    """
    n_trials = int(len(sweep))
    per_period = sweep["sharpe"].to_numpy() / np.sqrt(periods_per_year)
    sr_trials_std = float(np.std(per_period, ddof=1)) if n_trials > 1 else 0.0
    return n_trials, sr_trials_std
