"""Tests for backtester.compare and the expanded backtest metric set."""
from __future__ import annotations

import numpy as np

from src.baseline.agent0 import run_agent0
from src.engine.backtester import backtest, compare, daily_return_series
from src.engine.simulate import simulate_events
from src.strategy.fair_move_model import FairMoveModel
from src.strategy.strategy import run_strategy


def _books():
    ev = simulate_events(n=300, seed=3, edge_frac=0.35)
    model = FairMoveModel().fit(ev, ev["realised_move"])
    return run_strategy(ev, model), run_agent0(ev, seed=3)


def test_backtest_reports_charter_metrics():
    strat, _ = _books()
    s = backtest(strat)
    for key in ("sortino", "profit_factor", "win_loss_ratio", "max_dd_duration"):
        assert key in s
    assert s["profit_factor"] >= 0.0


def test_empty_ledger_has_new_keys():
    s = backtest(None, account=250_000)
    assert s["sortino"] == 0.0
    assert s["max_dd_duration"] == 0


def test_daily_return_series_aggregates_by_exit_date():
    strat, _ = _books()
    ser = daily_return_series(strat)
    assert ser.index.is_unique          # one point per exit date
    assert ser.index.is_monotonic_increasing


def test_compare_filter_beats_control_on_planted_edge():
    strat, agent0 = _books()
    c = compare(strat, agent0, n_boot=300, seed=1)
    assert c["sharpe_delta"] >= 0.5
    assert c["filter_gate_pass"] is True
    assert c["sharpe_delta_ci_low"] <= c["sharpe_delta"] <= c["sharpe_delta_ci_high"]
    assert 0.0 <= c["dsr_strategy"] <= 1.0


def test_compare_deflation_lowers_significance():
    strat, agent0 = _books()
    naive = compare(strat, agent0, n_trials=1, n_boot=200, seed=1)
    deflated = compare(strat, agent0, n_trials=50, sr_trials_std=0.2, n_boot=200, seed=1)
    assert deflated["dsr_strategy"] <= naive["dsr_strategy"] + 1e-9
