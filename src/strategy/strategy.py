"""Filtered strategy entry point.

Turns a per-event dataset into a trade ledger: predicts the fair move with the
regression, applies both cross-sectional gates, and emits short-straddle trades
for the surviving events. The ledger is scored by `engine.backtester` and
compared against the `baseline.agent0` control.
"""
from __future__ import annotations

import pandas as pd

from ..engine.pnl import ACCOUNT_SIZE, build_ledger
from .fair_move_model import FairMoveModel
from .filters import select_events


def run_strategy(events: pd.DataFrame, model: FairMoveModel,
                 account: float = ACCOUNT_SIZE, fraction: float = 0.05,
                 r: float = 0.0, costs=None) -> pd.DataFrame:
    """Select tradeable events and return the short-straddle trade ledger.

    Predicts the fair move, keeps only events that pass both filters (implied
    move >= 1.20x fair AND term spread above its trailing 75th percentile), and
    books one short ATM straddle per surviving event. `model` must already be
    fitted. Pass a ``CostModel`` via ``costs`` to book net-of-cost P&L (spread
    and slippage); ``None`` keeps the commission-only default.
    """
    fair = model.predict(events)
    selected = select_events(events, fair)
    return build_ledger(selected, account=account, fraction=fraction, r=r, costs=costs)
