"""Tests for engine.backtester: ledger scoring, drawdown, Sharpe, empties."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from src.engine import backtester


def _ledger(pnls, dates=None, margins=None):
    n = len(pnls)
    dates = dates or pd.bdate_range("2026-01-02", periods=n).astype(str).tolist()
    margins = margins or [10_000] * n
    return pd.DataFrame({
        "pnl": pnls,
        "exit_date": dates,
        "return_on_margin": [p / m for p, m in zip(pnls, margins)],
    })


def test_basic_aggregates():
    stats = backtester.backtest(_ledger([100.0, -50.0, 200.0, -300.0]), account=250_000)
    assert stats["n_trades"] == 4
    assert stats["total_pnl"] == pytest.approx(-50.0)
    assert stats["total_return"] == pytest.approx(-50.0 / 250_000)
    assert stats["hit_rate"] == pytest.approx(0.5)
    assert stats["avg_pnl"] == pytest.approx(-12.5)


def test_max_drawdown_from_equity_curve():
    # Equity (acct=250k): +100, +50, +250, -50 -> peak at +250, trough -50.
    stats = backtester.backtest(_ledger([100.0, -50.0, 200.0, -300.0]), account=250_000)
    assert stats["max_drawdown"] == pytest.approx(-300.0 / 250_250)
    assert stats["final_equity"] == pytest.approx(250_000 - 50.0)


def test_sharpe_positive_for_winning_book():
    stats = backtester.backtest(_ledger([100.0, 120.0, 90.0, 110.0]))
    assert stats["sharpe"] > 0


def test_empty_ledger_is_flat():
    stats = backtester.backtest(pd.DataFrame(), account=250_000)
    assert stats["n_trades"] == 0
    assert stats["total_pnl"] == 0.0
    assert stats["sharpe"] == 0.0
    assert stats["final_equity"] == 250_000
    assert not math.isnan(stats["total_return"])


def test_same_day_trades_aggregate_into_one_period():
    # Two trades on the same exit date collapse to a single daily P&L point.
    led = _ledger([100.0, -40.0], dates=["2026-01-02", "2026-01-02"])
    stats = backtester.backtest(led)
    assert stats["n_trades"] == 2
    assert stats["total_pnl"] == pytest.approx(60.0)
