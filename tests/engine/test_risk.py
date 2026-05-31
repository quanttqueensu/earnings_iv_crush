"""Tests for engine.risk: sizing, stops, circuit breaker, concentration caps."""
from __future__ import annotations

import pandas as pd
import pytest

from src.engine import risk


# --- sizing ------------------------------------------------------------------

def test_worst_case_size_targets_risk_fraction():
    # Naked: worst case = 3 x credit x 100 per contract. 1% of 250k = 2,500.
    # credit 6/sh -> worst 1,800/contract -> floor(2500/1800) = 1 contract.
    n = risk.worst_case_size(250_000, credit_per_share=6.0)
    assert n == 1
    worst = 3.0 * 6.0 * 100 * n
    assert worst <= 0.01 * 250_000


def test_defined_max_loss_allows_more_contracts():
    naked = risk.worst_case_size(250_000, credit_per_share=6.0)
    capped = risk.worst_case_size(250_000, credit_per_share=6.0,
                                  defined_max_loss_per_share=3.0)
    assert capped > naked          # a capped wing loss risks less per contract


def test_zero_credit_sizes_to_zero():
    assert risk.worst_case_size(250_000, credit_per_share=0.0) == 0


# --- stop --------------------------------------------------------------------

def test_premium_stop_floors_scalar_loss():
    # Entry credit 500; stop floor at -1500. A -4000 raw loss is capped.
    assert risk.apply_premium_stop(-4000.0, 500.0) == pytest.approx(-1500.0)
    assert risk.apply_premium_stop(200.0, 500.0) == 200.0    # winners untouched


def test_premium_stop_on_series():
    pnl = pd.Series([-4000.0, 200.0, -800.0])
    credit = pd.Series([500.0, 500.0, 500.0])
    out = risk.apply_premium_stop(pnl, credit)
    assert list(out) == [-1500.0, 200.0, -800.0]


# --- circuit breaker ---------------------------------------------------------

def test_circuit_breaker_detects_breach():
    equity = pd.Series([250_000, 240_000, 210_000, 205_000])  # -16% from peak
    breach = risk.circuit_breaker_breach(equity, threshold=0.15)
    assert breach == 2


def test_circuit_breaker_no_breach():
    equity = pd.Series([250_000, 252_000, 251_000])
    assert risk.circuit_breaker_breach(equity, threshold=0.15) is None


def test_halt_new_entries_after_breach():
    trades = pd.DataFrame({
        "pnl": [-40_000.0, 5_000.0],
        "entry_date": ["2026-01-02", "2026-01-20"],
        "exit_date": ["2026-01-05", "2026-01-22"],
    })
    # First trade alone draws the 250k account down 16% -> breach on its exit;
    # the later entry is dropped.
    kept = risk.halt_new_entries(trades, account=250_000, threshold=0.15)
    assert len(kept) == 1
    assert kept.iloc[0]["entry_date"] == "2026-01-02"


# --- concentration -----------------------------------------------------------

def test_cap_one_per_ticker_and_sector():
    events = pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "MSFT", "NVDA", "JPM"],
        "sector": ["Tech", "Tech", "Tech", "Tech", "Fin"],
        "entry_date": ["d"] * 5,
        "richness": [0.5, 0.9, 0.4, 0.3, 0.2],
    })
    out = risk.cap_concentration(events, rank_col="richness", max_per_sector=2)
    # One AAPL (the richer 0.9), then sector Tech capped at 2 -> AAPL + MSFT;
    # Fin keeps JPM.
    assert (out["ticker"] == "AAPL").sum() == 1
    assert (out["sector"] == "Tech").sum() == 2
    assert "JPM" in set(out["ticker"])
