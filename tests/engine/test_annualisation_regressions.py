"""
test_annualisation_regressions.py
Pin the annualisation basis across every reporting path: compare() must infer
the book's own cadence (the sqrt(252) default once inflated the headline Sharpe
~3x on a ~30-trade/yr book), and the sweep-to-DSR round trip must un-annualise
each cell by the same factor that annualised it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.engine import stats
from earnings_iv_crush.engine.backtester import compare, daily_return_series
from earnings_iv_crush.engine.sensitivity import sweep_dsr_params


def _sparse_ledger(n: int, seed: int) -> pd.DataFrame:
    """~n trades spread over a full year (an event book, not a daily book)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-06", periods=n, freq="8B")
    return pd.DataFrame(
        {
            "pnl": rng.normal(400.0, 2000.0, n),
            "return_on_margin": rng.normal(0.01, 0.05, n),
            "exit_date": dates,
        }
    )


def test_infer_periods_per_year_matches_cadence():
    idx = pd.bdate_range("2025-01-06", periods=30, freq="8B")  # ~30 obs / year
    ppy = stats.infer_periods_per_year(idx)
    span_years = (idx.max() - idx.min()).days / 365.25
    assert ppy == pytest.approx(len(idx) / span_years, rel=1e-9)
    assert ppy < 50  # nowhere near 252


def test_infer_periods_per_year_fallbacks():
    assert stats.infer_periods_per_year(pd.RangeIndex(10)) == 252.0
    assert stats.infer_periods_per_year(pd.DatetimeIndex([])) == 252.0


def test_compare_default_annualises_at_book_cadence():
    strat, ctrl = _sparse_ledger(30, 1), _sparse_ledger(60, 2)
    c = compare(strat, ctrl, n_boot=100, seed=0)
    idx = daily_return_series(strat).index.union(daily_return_series(ctrl).index)
    expected_ppy = stats.infer_periods_per_year(idx)
    assert c["periods_per_year"] == pytest.approx(expected_ppy)
    assert c["periods_per_year"] < 100  # the old default silently used 252

    s = daily_return_series(strat).reindex(idx, fill_value=0.0)
    assert c["sharpe_strategy"] == pytest.approx(stats.sharpe(s, expected_ppy))


def test_compare_explicit_override_still_respected():
    strat, ctrl = _sparse_ledger(30, 1), _sparse_ledger(60, 2)
    c = compare(strat, ctrl, periods_per_year=252, n_boot=50, seed=0)
    assert c["periods_per_year"] == 252.0


def test_compare_inferred_sharpe_below_252_scaling():
    strat, ctrl = _sparse_ledger(30, 1), _sparse_ledger(60, 2)
    honest = compare(strat, ctrl, n_boot=50, seed=0)
    inflated = compare(strat, ctrl, periods_per_year=252, n_boot=50, seed=0)
    ratio = np.sqrt(252.0 / honest["periods_per_year"])
    assert abs(inflated["sharpe_strategy"]) == pytest.approx(
        abs(honest["sharpe_strategy"]) * ratio, rel=1e-6
    )


def test_sweep_dsr_params_uses_per_cell_basis():
    sweep = pd.DataFrame(
        {
            "sharpe": [0.6, 0.9, 0.3],
            "periods_per_year": [36.0, 36.0, 36.0],
        }
    )
    n_trials, sr_std = sweep_dsr_params(sweep)
    per_period = sweep["sharpe"] / np.sqrt(36.0)
    assert n_trials == 3
    assert sr_std == pytest.approx(float(np.std(per_period, ddof=1)))
    # A 252 divisor on inferred-cadence cells understates the dispersion ~2.6x.
    wrong = float(np.std(sweep["sharpe"] / np.sqrt(252.0), ddof=1))
    assert sr_std > wrong


def test_sweep_dsr_params_falls_back_without_column():
    sweep = pd.DataFrame({"sharpe": [0.6, 0.9, 0.3]})
    _, sr_std = sweep_dsr_params(sweep, periods_per_year=252)
    assert sr_std == pytest.approx(float(np.std(sweep["sharpe"] / np.sqrt(252.0), ddof=1)))
