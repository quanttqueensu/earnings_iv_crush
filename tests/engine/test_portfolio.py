"""Tests for engine.portfolio: daily P&L booking, equity curves, risk metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine import portfolio


@pytest.fixture
def calendar() -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-01", periods=10)


def test_ledger_daily_pnl_books_on_exit_date(calendar):
    led = pd.DataFrame(
        {
            "exit_date": [calendar[2], calendar[2], calendar[5]],
            "pnl": [100.0, 50.0, -30.0],
        }
    )
    daily = portfolio.ledger_daily_pnl(led, calendar)
    assert daily.loc[calendar[2]] == pytest.approx(150.0)  # same-day trades net
    assert daily.loc[calendar[5]] == pytest.approx(-30.0)
    assert daily.loc[calendar[0]] == 0.0  # flat day filled with zero
    assert daily.sum() == pytest.approx(120.0)


def test_ledger_daily_pnl_empty_ledger(calendar):
    daily = portfolio.ledger_daily_pnl(pd.DataFrame(columns=["exit_date", "pnl"]), calendar)
    assert (daily == 0.0).all()
    assert len(daily) == len(calendar)


def test_equity_curve_is_fixed_notional_cumsum(calendar):
    pnl = pd.Series([0.0, 10.0, -5.0] + [0.0] * 7, index=calendar)
    eq = portfolio.equity_curve(pnl, capital=1000.0)
    assert eq.iloc[0] == pytest.approx(1000.0)
    assert eq.iloc[1] == pytest.approx(1010.0)
    assert eq.iloc[2] == pytest.approx(1005.0)
    assert eq.iloc[-1] == pytest.approx(1005.0)


def test_drawdown_non_positive_and_zero_at_new_high(calendar):
    eq = pd.Series([100, 110, 105, 120, 90], index=calendar[:5])
    dd = portfolio.drawdown(eq)
    assert (dd <= 1e-12).all()
    assert dd.iloc[0] == pytest.approx(0.0)
    assert dd.iloc[3] == pytest.approx(0.0)  # new high
    assert dd.iloc[-1] == pytest.approx(90 / 120 - 1)


def test_risk_metrics_sharpe_and_scale_invariance(calendar):
    rng = np.random.default_rng(0)
    pnl = pd.Series(rng.normal(20.0, 100.0, len(calendar)), index=calendar)
    eq_small = portfolio.equity_curve(pnl, 10_000.0)
    eq_big = portfolio.equity_curve(pnl, 1_000_000.0)
    m_small = portfolio.risk_metrics(pnl / 10_000.0, eq_small)
    m_big = portfolio.risk_metrics(pnl / 1_000_000.0, eq_big)
    # Sharpe is invariant to the capital base; total return is not.
    assert m_small.sharpe == pytest.approx(m_big.sharpe)
    assert m_small.total_return > m_big.total_return


def test_risk_metrics_beta_of_market_on_itself_is_one(calendar):
    rng = np.random.default_rng(1)
    mkt = pd.Series(rng.normal(0.0, 0.01, len(calendar)), index=calendar)
    eq = (1.0 + mkt).cumprod() * 1000.0
    m = portfolio.risk_metrics(mkt, eq, market_returns=mkt)
    assert m.beta_vs_market == pytest.approx(1.0, abs=1e-9)
    assert m.corr_vs_market == pytest.approx(1.0, abs=1e-9)


def test_risk_metrics_no_market_series_gives_nan(calendar):
    pnl = pd.Series([1.0] * len(calendar), index=calendar)
    m = portfolio.risk_metrics(pnl / 1000.0, portfolio.equity_curve(pnl, 1000.0))
    assert np.isnan(m.beta_vs_market)
    assert np.isnan(m.corr_vs_market)


def test_book_equity_round_trip(calendar):
    led = pd.DataFrame({"exit_date": [calendar[1], calendar[4]], "pnl": [200.0, -50.0]})
    ret, eq = portfolio.book_equity(led, capital=2000.0, calendar=calendar)
    assert eq.iloc[-1] == pytest.approx(2000.0 + 150.0)
    assert ret.loc[calendar[1]] == pytest.approx(0.1)
    assert m_dict_keys_present(portfolio.risk_metrics(ret, eq).as_dict())


def m_dict_keys_present(d: dict) -> bool:
    return {"sharpe", "max_drawdown", "beta_vs_market", "active_days"} <= set(d)
