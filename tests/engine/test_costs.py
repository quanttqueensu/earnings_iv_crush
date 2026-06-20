"""Tests for engine.costs and its integration into engine.pnl.

Covers the cost-stack arithmetic (commission, spread, slippage), the headline
cost figures, and the optional cost path through the ledger builder (which must
leave the commission-only default untouched).
"""

from __future__ import annotations

import pytest

from earnings_iv_crush.engine import pnl
from earnings_iv_crush.engine.costs import CostModel

# --- cost arithmetic ---------------------------------------------------------


def test_default_commission_round_trip():
    # IBKR Pro $0.65 x 4 fills (2 legs, open+close) = $2.60 for one contract.
    b = CostModel().round_trip_cost(5.0, 5.0, contracts=1)
    assert b.commission == pytest.approx(2.60)
    assert b.exchange_fee == 0.0


def test_spread_charges_full_quoted_width_each_side():
    # 8% of mid on entry and exit, contracts=1, $5 premium each side:
    # 0.08 * 1.0 * (5 + 5) * 100 = $80.
    b = CostModel().round_trip_cost(5.0, 5.0, contracts=1)
    assert b.spread_cost == pytest.approx(80.0)


def test_cross_fraction_halves_spread():
    full = CostModel(cross_fraction=1.0).round_trip_cost(5.0, 5.0, 2)
    half = CostModel(cross_fraction=0.5).round_trip_cost(5.0, 5.0, 2)
    assert half.spread_cost == pytest.approx(0.5 * full.spread_cost)


def test_slippage_is_per_leg_per_crossing():
    # 1 tick * $0.01 * 2 legs * 2 fills * 100 shares = $4 for one contract.
    b = CostModel().round_trip_cost(5.0, 5.0, contracts=1)
    assert b.slippage_cost == pytest.approx(4.0)


def test_total_is_sum_of_components_and_scales_with_contracts():
    one = CostModel().round_trip_cost(5.0, 5.0, 1)
    assert one.total_cost == pytest.approx(
        one.commission + one.exchange_fee + one.spread_cost + one.slippage_cost
    )
    ten = CostModel().round_trip_cost(5.0, 5.0, 10)
    assert ten.total_cost == pytest.approx(10 * one.total_cost)


def test_zero_contracts_is_free():
    b = CostModel().round_trip_cost(5.0, 5.0, 0)
    assert b.total_cost == 0.0


def test_cost_fraction_of_credit():
    b = CostModel().round_trip_cost(5.0, 5.0, contracts=1)
    # credit = 5 * 100 = 500; frac = total / 500.
    assert b.cost_frac_of_credit == pytest.approx(b.total_cost / 500.0)


# --- integration with pnl ----------------------------------------------------


def test_costs_reduce_straddle_pnl():
    kw = dict(
        spot_entry=100,
        strike=100,
        t_entry=0.02,
        t_exit=0.005,
        iv_entry=0.60,
        iv_exit=0.20,
        spot_exit=100.0,
        r=0.0,
        contracts=3,
    )
    commission_only = pnl.straddle_pnl(**kw)
    full = pnl.straddle_pnl(**kw, costs=CostModel())
    assert full < commission_only


def test_default_ledger_schema_unchanged():
    # Without a CostModel the schema must stay exactly LEDGER_COLUMNS.
    row = pnl.build_trade(
        ticker="X",
        entry_date="d0",
        exit_date="d1",
        spot_entry=100,
        strike=100,
        t_entry=0.02,
        t_exit=0.005,
        iv_entry=0.6,
        iv_exit=0.2,
        spot_exit=101.0,
        contracts=2,
    )
    assert set(row) == set(pnl.LEDGER_COLUMNS)


def test_cost_ledger_adds_columns_and_nets_pnl():
    row = pnl.build_trade(
        ticker="X",
        entry_date="d0",
        exit_date="d1",
        spot_entry=100,
        strike=100,
        t_entry=0.02,
        t_exit=0.005,
        iv_entry=0.6,
        iv_exit=0.2,
        spot_exit=101.0,
        contracts=2,
        costs=CostModel(),
    )
    assert set(row) == set(pnl.LEDGER_COLUMNS) | set(pnl.COST_COLUMNS)
    assert row["pnl"] == pytest.approx(row["entry_credit"] - row["exit_value"] - row["total_cost"])
    assert row["total_cost"] == pytest.approx(
        row["commissions"] + row["exchange_fee"] + row["spread_cost"] + row["slippage_cost"]
    )
