"""Tests for src.data.data_pipeline.build_event_dataset.

Drives the orchestration end-to-end against injected synthetic providers, so
it exercises the real join/feature logic with no network access.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data import data_pipeline


def _rows(expiry, strikes, ivs, mids):
    out = []
    for k, iv, m in zip(strikes, ivs, mids):
        for right in ("C", "P"):
            out.append({
                "expiry": pd.Timestamp(expiry), "strike": float(k), "right": right,
                "bid": m - 0.05, "ask": m + 0.05, "iv": iv, "open_interest": 100,
            })
    return out


def _fake_chain(ticker, asof):
    # Front (06-05) and back (07-03) expiries; ATM straddle mid = 6.0.
    front = _rows("2026-06-05", [95, 100, 105], [.5, .5, .5], [4, 3, 2])
    back = _rows("2026-07-03", [95, 100, 105], [.4, .4, .4], [5, 4, 3])
    return pd.DataFrame(front + back)


def _fake_prices(ticker, start, end):
    spot = 100.0 if ticker == "AAPL" else 200.0
    closes = list(np.linspace(spot * 0.97, spot, 30))
    dates = pd.bdate_range(end=end, periods=30)
    return pd.DataFrame({"date": dates, "close": closes})


def _calendar():
    return pd.DataFrame({
        "ticker": ["AAPL", "MSFT"],
        "announce_date": ["2026-06-01", "2026-06-02"],
        "hour": ["amc", "bmo"],
    })


def test_build_event_dataset_happy_path():
    df = data_pipeline.build_event_dataset(
        "2026-06-01", "2026-06-05",
        calendar=_calendar(), fetch_chain=_fake_chain, fetch_prices=_fake_prices,
    )

    assert list(df.columns) == data_pipeline.COLUMNS
    assert len(df) == 2
    assert list(df["ticker"]) == ["AAPL", "MSFT"]
    assert pd.api.types.is_datetime64_any_dtype(df["announce_date"])

    # Computed features.
    assert (df["front_atm_iv"] == 0.5).all()
    assert (df["back_atm_iv"] == 0.4).all()
    assert np.allclose(df["iv_term_spread"], 0.1)
    assert df["trailing_rv"].notna().all()
    # AAPL spot ~100 -> straddle 6 -> ~0.06; MSFT spot ~200 -> ~0.03.
    assert df.loc[df["ticker"] == "AAPL", "implied_move"].iloc[0] > \
        df.loc[df["ticker"] == "MSFT", "implied_move"].iloc[0]

    # Pending-source features are present but NaN.
    for col in data_pipeline.PENDING_FEATURES:
        assert df[col].isna().all()


def test_prior_surprise_populated_from_eps_columns():
    cal = pd.DataFrame({
        "ticker": ["AAPL", "AAPL"],
        "announce_date": ["2026-03-02", "2026-06-01"],
        "eps_estimate": [1.0, 1.0],
        "eps_actual": [1.2, 1.1],
    })
    df = data_pipeline.build_event_dataset(
        "2026-03-01", "2026-06-05",
        calendar=cal, fetch_chain=_fake_chain, fetch_prices=_fake_prices,
    )
    # First AAPL event has no prior; second sees the first's |surprise| = 0.20.
    assert np.isnan(df["prior_surprise"].iloc[0])
    assert df["prior_surprise"].iloc[1] == pytest.approx(0.20)
    # The genuinely pending features are still NaN.
    assert df["eps_dispersion"].isna().all()
    assert df["oi_growth"].isna().all()


def test_empty_calendar_returns_empty_schema():
    df = data_pipeline.build_event_dataset(
        "2026-06-01", "2026-06-05",
        calendar=pd.DataFrame(columns=["ticker", "announce_date"]),
        fetch_chain=_fake_chain, fetch_prices=_fake_prices,
    )
    assert list(df.columns) == data_pipeline.COLUMNS
    assert df.empty


def test_empty_chain_yields_nan_features_but_keeps_row():
    df = data_pipeline.build_event_dataset(
        "2026-06-01", "2026-06-05",
        calendar=_calendar(),
        fetch_chain=lambda t, a: pd.DataFrame(
            columns=["expiry", "strike", "right", "bid", "ask", "iv", "open_interest"]),
        fetch_prices=_fake_prices,
    )
    assert len(df) == 2
    assert df["front_atm_iv"].isna().all()
    assert df["implied_move"].isna().all()
    assert df["trailing_rv"].notna().all()  # rv only needs prices
