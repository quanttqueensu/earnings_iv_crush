"""Tests for engine.backtester: ledger scoring, drawdown, Sharpe, empties."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from earnings_iv_crush.engine import backtester


def _ledger(pnls, dates=None, margins=None):
    n = len(pnls)
    dates = dates or pd.bdate_range("2026-01-02", periods=n).astype(str).tolist()
    margins = margins or [10_000] * n
    return pd.DataFrame(
        {
            "pnl": pnls,
            "exit_date": dates,
            "return_on_margin": [p / m for p, m in zip(pnls, margins)],
        }
    )


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


def test_frequency_neutral_rewards_better_per_trade_book():
    # Strategy: a few high-mean, low-dispersion trades (a selective filter).
    # Control: many noisier trades (the unfiltered book). The daily Sharpe in
    # compare() zero-fills the strategy on the control's extra dates, but the
    # frequency-neutral per-trade Sharpe must still favour the cleaner book.
    dates = pd.bdate_range("2026-01-02", periods=40).astype(str).tolist()
    strat = _ledger([120.0, 130.0, 110.0, 125.0], dates=dates[:4])
    ctrl_pnls = [120.0, -200.0, 130.0, 110.0, -180.0, 125.0, 90.0, -150.0] * 5
    ctrl = _ledger(ctrl_pnls, dates=dates[: len(ctrl_pnls)])

    fn = backtester.frequency_neutral_stats(strat, ctrl, n_boot=200, seed=0)
    assert fn["per_trade_sharpe_strategy"] > fn["per_trade_sharpe_agent0"]
    assert fn["filter_edge_per_trade"] is True
    # Size-matched control is drawn down to the strategy's trade count.
    assert 0.0 <= fn["size_matched_win_prob"] <= 1.0
    assert (
        fn["size_matched_delta_ci_low"]
        <= fn["size_matched_delta_mean"]
        <= fn["size_matched_delta_ci_high"]
    )


def test_frequency_neutral_merged_into_compare():
    dates = pd.bdate_range("2026-01-02", periods=12).astype(str).tolist()
    strat = _ledger([100.0, 110.0, 95.0], dates=dates[:3])
    ctrl = _ledger([100.0, -50.0, 110.0, 95.0, -40.0, 80.0], dates=dates[:6])
    cmp = backtester.compare(strat, ctrl, n_boot=100, seed=1)
    for key in (
        "per_trade_sharpe_strategy",
        "per_trade_sharpe_delta",
        "size_matched_win_prob",
        "filter_edge_per_trade",
    ):
        assert key in cmp
