"""Tests for engine.stats: risk-adjusted, win/loss, and significance metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine import stats

# --- risk-adjusted -----------------------------------------------------------


def test_sharpe_zero_for_constant_series():
    assert stats.sharpe(pd.Series([0.01, 0.01, 0.01])) == 0.0


def test_sortino_only_penalises_downside():
    # Symmetric series and a one-sided-down series with equal mean: Sortino of
    # the all-upside series is higher (no downside dispersion -> 0 by convention
    # only when there is truly no downside).
    mixed = pd.Series([0.02, -0.01, 0.03, -0.02, 0.04])
    sortino = stats.sortino_ratio(mixed)
    sharpe = stats.sharpe(mixed)
    assert sortino > sharpe  # downside dev < total dev for a right-skewed mean


# --- win / loss --------------------------------------------------------------


def test_profit_factor():
    assert stats.profit_factor(pd.Series([100, -50, 200, -50])) == pytest.approx(3.0)


def test_profit_factor_edge_cases():
    assert stats.profit_factor(pd.Series([10, 20])) == float("inf")
    assert stats.profit_factor(pd.Series([-10, -20])) == 0.0


def test_win_loss_ratio():
    assert stats.win_loss_ratio(pd.Series([100, 200, -50, -50])) == pytest.approx(3.0)


def test_max_drawdown_duration():
    equity = pd.Series([100, 90, 80, 95, 120, 130])
    # Peak 100 held until 120 recovers it: underwater at 90, 80, 95 -> 3 periods.
    assert stats.max_drawdown_duration(equity) == 3
    assert stats.max_drawdown_duration(pd.Series([1, 2, 3, 4])) == 0


# --- significance ------------------------------------------------------------


def test_bootstrap_ci_brackets_point_estimate():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.01, 250))
    lo, hi = stats.bootstrap_sharpe_ci(r, n_boot=500, seed=1)
    point = stats.sharpe(r)
    assert lo <= point <= hi
    assert lo < hi


def test_psr_high_for_consistent_positive_returns():
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0.002, 0.005, 300))  # strong, steady edge
    assert stats.probabilistic_sharpe_ratio(r) > 0.9


def test_psr_nan_for_tiny_sample():
    assert np.isnan(stats.probabilistic_sharpe_ratio(pd.Series([0.01, 0.02])))


def test_expected_max_sharpe_grows_with_trials():
    assert stats.expected_max_sharpe(1, 0.1) == 0.0
    assert stats.expected_max_sharpe(50, 0.1) > stats.expected_max_sharpe(5, 0.1) > 0


def test_dsr_not_above_psr_when_deflated():
    rng = np.random.default_rng(2)
    r = pd.Series(rng.normal(0.002, 0.005, 300))
    psr = stats.probabilistic_sharpe_ratio(r)
    dsr = stats.deflated_sharpe_ratio(r, n_trials=20, sr_trials_std=0.1)
    assert dsr <= psr
    assert 0.0 <= dsr <= 1.0
