"""Agent 0 - the unfiltered control.

Sells a random sample of unfiltered short ATM straddles. This replicates the
Khan & Khan (2024) result (~0 net Sharpe) and is the benchmark the filtered
strategy must beat by >= 0.5 Sharpe to justify the filter.

Deliberately independent of the strategy package: Agent 0 shares only the
trade-economics engine, so the comparison differs in *selection* alone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..engine.pnl import ACCOUNT_SIZE, build_ledger


def run_agent0(events: pd.DataFrame, seed: int = 0, account: float = ACCOUNT_SIZE,
               fraction: float = 0.05, r: float = 0.0,
               sample_frac: float = 1.0, costs=None) -> pd.DataFrame:
    """Trade an unfiltered random subset of events; return the trade ledger.

    No filter is applied: `sample_frac` of the events are chosen at random
    (default all) and each is booked as a short straddle, identically to the
    strategy. `seed` makes the draw reproducible. Pass a ``CostModel`` via
    ``costs`` to book net-of-cost P&L on the same basis as the strategy.
    """
    n = len(events)
    if n == 0:
        return build_ledger(events, account=account, fraction=fraction, r=r, costs=costs)

    k = int(round(sample_frac * n))
    if k >= n:
        chosen = events
    else:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(n, size=k, replace=False))
        chosen = events.iloc[idx]
    return build_ledger(chosen, account=account, fraction=fraction, r=r, costs=costs)
