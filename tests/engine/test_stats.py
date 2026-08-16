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


# --- exchange calendar -------------------------------------------------------

# Published NYSE session counts. 2017 and 2018 lose a day to a Saturday
# Independence Day and the 5 December 2018 Bush funeral closure respectively;
# 2020 is long at 253; 2023 is short at 250.
NYSE_SESSION_COUNTS = {
    2013: 252,
    2014: 252,
    2015: 252,
    2016: 252,
    2017: 251,
    2018: 251,
    2019: 252,
    2020: 253,
    2021: 252,
    2022: 251,
    2023: 250,
    2024: 252,
}


@pytest.mark.parametrize("year,expected", sorted(NYSE_SESSION_COUNTS.items()))
def test_nyse_session_counts(year, expected):
    sessions = stats.nyse_sessions(pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31"))
    assert len(sessions) == expected


def test_nyse_saturday_new_year_is_not_observed():
    # 1 January 2022 fell on a Saturday and the exchange traded 31 December
    # 2021, unlike a Saturday Christmas where it closes the preceding Friday.
    sessions = stats.nyse_sessions(pd.Timestamp("2021-12-20"), pd.Timestamp("2021-12-31"))
    assert pd.Timestamp("2021-12-31") in sessions
    assert pd.Timestamp("2021-12-24") not in sessions


def test_calendar_sharpe_matches_sqrt_trade_count_for_a_spaced_book():
    # One trade a month, never overlapping: zero-filling to the calendar and
    # scaling by sqrt(252) must agree with scaling the per-trade Sharpe by
    # sqrt(trades per year). The two conventions only diverge on overlap.
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2019-01-31", periods=60, freq="BME")
    r = pd.Series(rng.normal(0.004, 0.02, len(dates)), index=dates)
    per_trade = r.mean() / r.std(ddof=1)
    assert stats.calendar_sharpe(r) == pytest.approx(per_trade * np.sqrt(12), rel=0.05)


def test_calendar_sharpe_penalises_idleness_relative_to_a_daily_book():
    # Identical per-observation mean and sd by construction (a fixed repeating
    # pattern, not a random draw, so no sampling noise can flip the comparison).
    # Only the frequency differs, and the idle book must score lower on the
    # capital-allocation basis.
    pattern = [0.02, -0.01, 0.03, -0.02]
    daily_idx = stats.nyse_sessions(pd.Timestamp("2019-01-01"), pd.Timestamp("2019-12-31"))
    daily = pd.Series(np.resize(pattern, len(daily_idx)), index=daily_idx)
    sparse_idx = daily_idx[:: len(daily_idx) // 12][:12]
    sparse = pd.Series(np.resize(pattern, len(sparse_idx)), index=sparse_idx)
    assert stats.calendar_sharpe(sparse) < stats.calendar_sharpe(daily)


def test_calendar_sharpe_sums_same_day_trades():
    # Two positions exiting together are one daily observation, not two.
    dup = pd.Series([0.01, 0.01], index=pd.to_datetime(["2019-03-01", "2019-03-01"]))
    single = pd.Series([0.02], index=pd.to_datetime(["2019-03-01"]))
    span = pd.date_range("2019-03-01", "2019-03-29", freq="B")
    dup = pd.concat([dup, pd.Series(0.0, index=span[1:])])
    single = pd.concat([single, pd.Series(0.0, index=span[1:])])
    assert stats.calendar_sharpe(dup) == pytest.approx(stats.calendar_sharpe(single))


def test_calendar_sharpe_handles_empty_and_undated():
    assert stats.calendar_sharpe(pd.Series(dtype=float)) == 0.0
    assert stats.calendar_sharpe(pd.Series([0.01, -0.02, 0.03])) == stats.sharpe(
        pd.Series([0.01, -0.02, 0.03])
    )


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
