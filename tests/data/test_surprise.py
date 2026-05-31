"""Tests for src.data.surprise: earnings surprise and the lagged feature."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data import surprise


def test_earnings_surprise_formula():
    s = surprise.earnings_surprise(
        eps_actual=[1.10, 0.90, 1.00],
        eps_estimate=[1.00, 1.00, 0.00],   # zero estimate -> NaN, not inf
    )
    assert s.iloc[0] == pytest.approx(0.10)
    assert s.iloc[1] == pytest.approx(-0.10)
    assert np.isnan(s.iloc[2])


def test_prior_surprise_lags_one_event_per_ticker():
    cal = pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "MSFT", "AAPL"],
        "announce_date": ["2025-08-01", "2025-11-01", "2025-10-01", "2026-02-01"],
        "eps_estimate": [1.00, 1.00, 2.00, 1.00],
        "eps_actual": [1.20, 0.90, 2.20, 1.05],
    })
    ps = surprise.prior_surprise(cal)

    # First AAPL event and the only MSFT event have no prior -> NaN.
    assert np.isnan(ps.loc[0])
    assert np.isnan(ps.loc[2])
    # AAPL second event sees the first's |surprise| = |0.20| = 0.20.
    assert ps.loc[1] == pytest.approx(0.20)
    # AAPL third event sees the second's |(-0.10)| = 0.10.
    assert ps.loc[3] == pytest.approx(0.10)


def test_prior_surprise_missing_columns_returns_aligned_nan():
    cal = pd.DataFrame({"ticker": ["A", "B"], "announce_date": ["2026-01-01", "2026-02-01"]})
    ps = surprise.prior_surprise(cal)
    assert ps.index.equals(cal.index)
    assert ps.isna().all()
