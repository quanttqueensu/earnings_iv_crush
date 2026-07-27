"""Tests for earnings_iv_crush.data.lse_options.

The LSE transport (``_pull_chain_raw``) and spot lookup are monkeypatched so
chain normalization, IV inversion, caching and filtering are tested offline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.data import lse_options as lo
from earnings_iv_crush.data.options import CHAIN_COLUMNS
from earnings_iv_crush.engine.greeks import bs_price

ASOF = pd.Timestamp("2024-08-01")
SPOT = 220.0
SIGMA = 0.35


def _synthetic_history() -> pd.DataFrame:
    """Synthetic LSE history() response matching the observed vault schema."""
    rows = []
    for exp in (ASOF + pd.Timedelta(days=d) for d in (2, 9, 16, 30, 44)):
        for k in range(195, 246, 5):
            for opt_type in ("C", "P"):
                t = max((exp - ASOF).days, 1) / 365.0
                close = float(bs_price(SPOT, k, t, 0.0, SIGMA, opt_type))
                rows.append(
                    {
                        "ts": ASOF,
                        "underlying": "AAPL",
                        "expiry": exp.strftime("%Y-%m-%d"),
                        "opt_type": opt_type,
                        "strike": float(k),
                        "osi": f"O:AAPL{exp.strftime('%y%m%d')}{opt_type}{int(k*1000):08d}",
                        "open": close * 1.01,
                        "high": close * 1.02,
                        "low": close * 0.98,
                        "close": close,
                        "volume": 100,
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Wire synthetic LSE data and a tmp cache dir."""
    synthetic = _synthetic_history()

    def fake_pull(ticker, asof):
        return synthetic

    monkeypatch.setattr(lo, "_pull_chain_raw", fake_pull)
    monkeypatch.setattr(lo, "_spot_on_or_before", lambda *a, **k: SPOT)
    monkeypatch.setattr(lo, "_CACHE_ROOT", tmp_path)
    return synthetic


def test_schema_matches_canonical_chain(patched):
    chain = lo.fetch_option_chain("AAPL", "2024-08-01")
    assert list(chain.columns) == CHAIN_COLUMNS


def test_chain_not_empty(patched):
    chain = lo.fetch_option_chain("AAPL", "2024-08-01")
    assert len(chain) > 0


def test_iv_positive_and_finite(patched):
    chain = lo.fetch_option_chain("AAPL", "2024-08-01")
    valid_iv = chain["iv"].dropna()
    assert len(valid_iv) > 0
    assert (valid_iv > 0).all()
    assert np.isfinite(valid_iv).all()


def test_iv_recovers_input_sigma(patched):
    """ATM IV should round-trip close to the synthetic sigma."""
    chain = lo.fetch_option_chain("AAPL", "2024-08-01")
    atm = chain[(chain["strike"] - SPOT).abs() / SPOT < 0.03]
    assert len(atm) > 0
    median_iv = atm["iv"].median()
    assert abs(median_iv - SIGMA) < 0.02, f"median IV {median_iv:.4f} too far from {SIGMA}"


def test_expiry_within_horizon(patched):
    chain = lo.fetch_option_chain("AAPL", "2024-08-01", horizon_days=30)
    max_dte = (pd.to_datetime(chain["expiry"]) - ASOF).dt.days.max()
    assert max_dte <= 30


def test_strike_window_respected(patched):
    chain = lo.fetch_option_chain("AAPL", "2024-08-01", strike_window=0.05)
    lo_bound = SPOT * 0.95
    hi_bound = SPOT * 1.05
    assert chain["strike"].min() >= lo_bound
    assert chain["strike"].max() <= hi_bound


def test_right_values(patched):
    chain = lo.fetch_option_chain("AAPL", "2024-08-01")
    assert set(chain["right"].unique()) == {"C", "P"}


def test_bid_ask_carry_close(patched):
    """No bid/ask on historical bars; both sides should equal the close."""
    chain = lo.fetch_option_chain("AAPL", "2024-08-01")
    assert (chain["bid"] == chain["ask"]).all()
    assert (chain["bid"] > 0).all()


def test_cache_roundtrip(patched, tmp_path):
    """Second call reads from cache without hitting the API."""
    chain1 = lo.fetch_option_chain("AAPL", "2024-08-01")
    cache_file = tmp_path / "AAPL" / "2024-08-01_chain.parquet"
    assert cache_file.exists()

    chain2 = lo.fetch_option_chain("AAPL", "2024-08-01")
    pd.testing.assert_frame_equal(chain1, chain2, check_dtype=False)


def test_empty_sentinel_cached(monkeypatch, tmp_path):
    """An empty response is cached as a sentinel to prevent re-fetch."""
    monkeypatch.setattr(lo, "_pull_chain_raw", lambda *a: pd.DataFrame())
    monkeypatch.setattr(lo, "_spot_on_or_before", lambda *a, **k: 100.0)
    monkeypatch.setattr(lo, "_CACHE_ROOT", tmp_path)

    chain = lo.fetch_option_chain("XYZ", "2024-01-01")
    assert chain.empty
    assert list(chain.columns) == CHAIN_COLUMNS

    cache_file = tmp_path / "XYZ" / "2024-01-01_chain.parquet"
    assert cache_file.exists()


def test_nan_spot_caches_empty(monkeypatch, tmp_path):
    """NaN spot caches an empty chain, does not call the API."""
    calls = {"count": 0}

    def fake_pull(ticker, asof):
        calls["count"] += 1
        return pd.DataFrame()

    monkeypatch.setattr(lo, "_pull_chain_raw", fake_pull)
    monkeypatch.setattr(lo, "_spot_on_or_before", lambda *a, **k: float("nan"))
    monkeypatch.setattr(lo, "_CACHE_ROOT", tmp_path)

    chain = lo.fetch_option_chain("XYZ", "2024-01-01")
    assert chain.empty
    assert calls["count"] == 0


def test_zero_volume_filtered(monkeypatch, tmp_path):
    """Contracts with volume == 0 should be excluded."""
    raw = _synthetic_history()
    raw.loc[raw.index[:10], "volume"] = 0

    monkeypatch.setattr(lo, "_pull_chain_raw", lambda *a: raw)
    monkeypatch.setattr(lo, "_spot_on_or_before", lambda *a, **k: SPOT)
    monkeypatch.setattr(lo, "_CACHE_ROOT", tmp_path)

    chain = lo.fetch_option_chain("AAPL", "2024-08-01")
    assert len(chain) == len(raw) - 10


def test_prefetch_event(patched, tmp_path):
    lo.prefetch_event("AAPL", "2024-08-01", "2024-08-02")
    entry_cache = tmp_path / "AAPL" / "2024-08-01_chain.parquet"
    exit_cache = tmp_path / "AAPL" / "2024-08-02_chain.parquet"
    assert entry_cache.exists()
    assert exit_cache.exists()
