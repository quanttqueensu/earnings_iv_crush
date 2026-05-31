"""Filtered strategy entry point.

Turns a per-event dataset into a trade ledger: predicts the fair move with the
regression, applies both cross-sectional gates, and emits trades for the
surviving events. ``run_strategy`` books the naked short straddle (the primary
structure); ``run_strategy_structured`` instead books the regime-selected
structure per event (naked straddle, iron fly or calendar). Both ledgers are
scored by `engine.backtester` and compared against the `baseline.agent0` control.
"""
from __future__ import annotations

import pandas as pd

from ..engine.pnl import ACCOUNT_SIZE, build_ledger
from ..engine.risk import RISK_FRAC_PER_TRADE
from ..engine.structured_ledger import build_structured_ledger
from .fair_move_model import FairMoveModel
from .filters import select_events
from .regime import assign_structures


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


def run_strategy_structured(events: pd.DataFrame, model: FairMoveModel,
                            account: float = ACCOUNT_SIZE,
                            risk_frac: float = RISK_FRAC_PER_TRADE,
                            r: float = 0.0, costs=None,
                            vix_level: float | None = None) -> pd.DataFrame:
    """Select tradeable events and book each in its regime-selected structure.

    Predicts the fair move, applies both filters, then routes every surviving
    event to the structure the regime selector picks (iron fly when VIX is high,
    calendar when the term-structure premium dominates, else the naked straddle)
    and books it with worst-case (1% NAV) sizing. `model` must already be fitted.

    Returns the structured ledger (``structured_ledger.STRUCTURED_COLUMNS``);
    ``engine.backtester`` scores it directly off the ``pnl`` column.
    """
    fair = model.predict(events)
    selected = select_events(events, fair)
    structures = assign_structures(selected, model.predict(selected), vix_level=vix_level)
    return build_structured_ledger(selected, structures, account=account,
                                   risk_frac=risk_frac, r=r, costs=costs)
