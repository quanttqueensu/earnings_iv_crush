"""walkforward.py
No-look-ahead walk-forward backtest of the filtered strategy.

Validation needs an out-of-sample result, not the in-sample fit. This runs the
strategy so that every fair-move prediction is made
from a model fitted only on earlier events (expanding window), and the term-
structure filter uses its already-causal trailing percentile. The selected,
out-of-sample events are booked and scored exactly like the live strategy.

This module implements:

* ``walk_forward_backtest`` — expanding-window OOS selection, ledger and stats.

References
----------
Khan, W., & Khan, H. (2024). A 17-year backtest of straddles around S&P 500
earnings announcements. *SSRN Working Paper 4832160*.
"""

from __future__ import annotations

import pandas as pd

from ..strategy.fair_move_model import FairMoveModel
from ..strategy.filters import (
    IMPLIED_FAIR_RATIO,
    TERM_SPREAD_PCTL,
    TRAILING_WINDOW,
    select_events,
)
from .backtester import backtest
from .pnl import ACCOUNT_SIZE, build_ledger


def walk_forward_backtest(
    events: pd.DataFrame,
    realised_move,
    model: FairMoveModel | None = None,
    min_train: int = 20,
    account: float = ACCOUNT_SIZE,
    fraction: float = 0.05,
    r: float = 0.0,
    costs=None,
    ratio: float = IMPLIED_FAIR_RATIO,
    pctl: float = TERM_SPREAD_PCTL,
    window: int = TRAILING_WINDOW,
) -> tuple[dict, pd.DataFrame]:
    """
    Score the strategy out-of-sample with an expanding-window fair move.

    For each event past ``min_train`` the fair move is predicted from a model
    fitted only on earlier events (no look-ahead). Those out-of-sample events are
    filtered, booked and scored.

    Parameters
    ----------
    events : pd.DataFrame
        Per-event frame, assumed sorted by announcement date, with the filter
        and execution columns.
    realised_move : array-like
        Realised absolute event move (the fair-move target), aligned to events.
    model : FairMoveModel, optional
        Template model (its feature list / method are reused per window). A
        default OLS model is created if omitted.
    min_train : int
        Events before the first out-of-sample prediction. Defaults to ``20``.
    account, fraction, r, costs :
        Passed through to the ledger builder (see ``pnl.build_ledger``).
    ratio, pctl, window :
        Filter thresholds (see ``strategy.filters.select_events``).

    Returns
    -------
    tuple
        ``(stats, ledger)`` where ``stats`` is the ``backtester.backtest`` dict
        augmented with ``n_oos`` (events with an OOS prediction) and
        ``n_selected`` (events that passed both filters).
    """
    model = model or FairMoveModel()
    fair = model.fit_predict_walk_forward(events, realised_move, min_train=min_train)
    oos_mask = fair.notna()

    events_oos = events[oos_mask]
    fair_oos = fair[oos_mask]
    selected = select_events(events_oos, fair_oos, ratio=ratio, pctl=pctl, window=window)
    ledger = build_ledger(selected, account=account, fraction=fraction, r=r, costs=costs)

    stats = backtest(ledger, account)
    stats["n_oos"] = int(oos_mask.sum())
    stats["n_selected"] = int(len(selected))
    return stats, ledger
