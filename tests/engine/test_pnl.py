"""Tests for engine.pnl: margin, sizing, short-straddle P&L, ledger rows."""
from __future__ import annotations

import math

import pytest

from src.engine import pnl


# --- margin / sizing ---------------------------------------------------------

def test_margin_scales_with_contracts():
    one = pnl.regt_straddle_margin(100, 100, premium_per_share=6.0, contracts=1)
    five = pnl.regt_straddle_margin(100, 100, premium_per_share=6.0, contracts=5)
    assert one > 0
    assert five == pytest.approx(5 * one)


def test_size_contracts_respects_fraction():
    account, spot, strike, premium, frac = 250_000, 100.0, 100.0, 6.0, 0.05
    n = pnl.size_contracts(account, spot, strike, premium, fraction=frac)
    used = pnl.regt_straddle_margin(spot, strike, premium, n)
    one = pnl.regt_straddle_margin(spot, strike, premium, 1)
    # Margin used stays within the budget, and one more contract would exceed it.
    assert used <= frac * account
    assert used + one > frac * account


# --- straddle P&L ------------------------------------------------------------

def test_short_straddle_profits_on_iv_crush_and_small_move():
    # Sell at IV 0.60, buy back at 0.20 with the spot barely moving -> profit.
    p = pnl.straddle_pnl(
        spot_entry=100, strike=100, t_entry=0.02, t_exit=0.005,
        iv_entry=0.60, iv_exit=0.20, spot_exit=100.5, r=0.0, contracts=1,
    )
    assert p > 0


def test_short_straddle_loses_on_large_move():
    # A big realised move overwhelms the premium collected -> loss.
    p = pnl.straddle_pnl(
        spot_entry=100, strike=100, t_entry=0.02, t_exit=0.005,
        iv_entry=0.60, iv_exit=0.20, spot_exit=130.0, r=0.0, contracts=1,
    )
    assert p < 0


def test_commissions_reduce_pnl():
    kw = dict(spot_entry=100, strike=100, t_entry=0.02, t_exit=0.005,
              iv_entry=0.60, iv_exit=0.20, spot_exit=100.0, r=0.0, contracts=3)
    gross = pnl.straddle_pnl(**kw, cost_per_contract=0.0)
    net = pnl.straddle_pnl(**kw, cost_per_contract=0.65)
    assert gross - net == pytest.approx(0.65 * pnl.FILLS_PER_STRADDLE * 3)


# --- ledger row --------------------------------------------------------------

def test_build_trade_has_full_schema_and_consistent_pnl():
    row = pnl.build_trade(
        ticker="AAPL", entry_date="2026-05-29", exit_date="2026-06-02",
        spot_entry=100, strike=100, t_entry=0.02, t_exit=0.005,
        iv_entry=0.60, iv_exit=0.20, spot_exit=101.0, contracts=2,
    )
    assert set(row) == set(pnl.LEDGER_COLUMNS)
    assert row["pnl"] == pytest.approx(
        row["entry_credit"] - row["exit_value"] - row["commissions"]
    )
    assert row["return_on_margin"] == pytest.approx(row["pnl"] / row["margin"])


def test_build_trade_intrinsic_fallback_at_expiry():
    # t_exit = 0 -> exit value is intrinsic |spot_exit - strike| per share.
    row = pnl.build_trade(
        ticker="X", entry_date="d0", exit_date="d1",
        spot_entry=100, strike=100, t_entry=0.02, t_exit=0.0,
        iv_entry=0.5, iv_exit=0.2, spot_exit=105.0, contracts=1,
    )
    assert row["exit_value"] == pytest.approx(5.0 * pnl.CONTRACT_MULTIPLIER)
    assert not math.isnan(row["pnl"])
