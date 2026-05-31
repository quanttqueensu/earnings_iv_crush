"""Event-driven backtester for the short-straddle book.

Opens a position 1-3 days pre-announcement, closes into the post-event IV
collapse, and books the realised-vs-implied spread net of Khan & Khan costs.
"""
from __future__ import annotations

import pandas as pd

from .pnl import ACCOUNT_SIZE, COST_PER_CONTRACT  # noqa: F401  (re-exported)


_EMPTY_STATS = {
    "n_trades": 0, "total_pnl": 0.0, "total_return": 0.0, "hit_rate": 0.0,
    "avg_pnl": 0.0, "avg_return_on_margin": float("nan"), "sharpe": 0.0,
    "max_drawdown": 0.0, "final_equity": None,
}


def backtest(trades: pd.DataFrame, account=ACCOUNT_SIZE,
             periods_per_year: int = 252) -> dict:
    """Score a trade ledger and return performance stats.

    Expects a ledger as produced by `pnl.build_trade` (columns include `pnl`,
    `return_on_margin`, and ideally `exit_date`). P&L is aggregated by exit date
    into a daily series; Sharpe is annualised from those daily returns and max
    drawdown is read off the equity curve (starting capital = `account`).
    """
    if trades is None or len(trades) == 0:
        return {**_EMPTY_STATS, "final_equity": float(account)}

    pnl = trades["pnl"].astype(float)

    if "exit_date" in trades:
        dated = trades.assign(exit_date=pd.to_datetime(trades["exit_date"]))
        daily_pnl = dated.groupby("exit_date")["pnl"].sum().sort_index()
    else:
        daily_pnl = pnl.reset_index(drop=True)

    daily_return = daily_pnl / account
    equity = account + daily_pnl.cumsum()
    drawdown = (equity - equity.cummax()) / equity.cummax()
    ror = trades["return_on_margin"] if "return_on_margin" in trades else None

    return {
        "n_trades": int(len(trades)),
        "total_pnl": float(pnl.sum()),
        "total_return": float(pnl.sum() / account),
        "hit_rate": float((pnl > 0).mean()),
        "avg_pnl": float(pnl.mean()),
        "avg_return_on_margin": float(ror.mean()) if ror is not None else float("nan"),
        "sharpe": float(sharpe(daily_return, periods_per_year)),
        "max_drawdown": float(drawdown.min()),
        "final_equity": float(equity.iloc[-1]),
    }


def sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Annualised Sharpe ratio of a per-trade or per-day return series."""
    if returns.std() == 0:
        return 0.0
    return (returns.mean() / returns.std()) * (periods_per_year ** 0.5)
