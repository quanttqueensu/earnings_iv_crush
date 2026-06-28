"""
test_forward_test.py
Offline tests for the forward paper-test decision layer: the canonical
break-even arithmetic, the managed mid-seeking exit, the parallel hard-stop book
and the cost reconciliation. No broker, no network.
"""

from __future__ import annotations

import math

import pytest

from earnings_iv_crush.engine.pnl import CONTRACT_MULTIPLIER, LEDGER_COLUMNS
from earnings_iv_crush.live.forward_test import (
    ASSUMED_ENTRY_SPREAD,
    BREAKEVEN_ROUND_TRIP,
    FORWARD,
    StraddleQuote,
    build_forward_exit,
    managed_exit_price,
    mark_to_market_rom,
    realised_exit_price,
    round_trip_cost_frac,
    stop_triggered,
)

# ── Task A: the canonical break-even number ──────────────────────────────────


def test_round_trip_is_half_cross_of_each_leg():
    # Round trip = entry half-cross + exit half-cross, both as fraction of premium.
    assert round_trip_cost_frac(0.0613, 0.171) == pytest.approx(0.0613 / 2 + 0.171 / 2)


def test_breakeven_round_trip_canonical_value():
    # (6.13% + 17.1%) / 2 = 11.6% round-trip of premium.
    assert BREAKEVEN_ROUND_TRIP == pytest.approx(0.1162, abs=5e-4)


def test_measured_round_trip_sits_just_under_breakeven():
    measured = round_trip_cost_frac(ASSUMED_ENTRY_SPREAD, 0.1647)
    assert measured == pytest.approx(0.113, abs=1e-3)
    assert measured < BREAKEVEN_ROUND_TRIP  # the edge survives, but only just


def test_one_way_half_of_breakeven_explains_the_6pct_figure():
    # The stale "~6% round trip" was a one-way half-cross, not a round trip;
    # doubling it recovers the ~12% true round trip.
    one_way = BREAKEVEN_ROUND_TRIP / 2
    assert one_way == pytest.approx(0.058, abs=2e-3)
    assert 2 * one_way == pytest.approx(BREAKEVEN_ROUND_TRIP)


# ── managed exit price ───────────────────────────────────────────────────────


def _quote(cb=1.0, ca=1.2, pb=0.9, pa=1.1) -> StraddleQuote:
    return StraddleQuote(call_bid=cb, call_ask=ca, put_bid=pb, put_ask=pa)


def test_quote_mid_and_half_spread():
    q = _quote()
    assert q.mid == pytest.approx(1.1 + 1.0)  # call mid 1.1 + put mid 1.0
    assert q.half_spread == pytest.approx(0.1 + 0.1)  # half of each 0.2 width
    assert q.touch_buy == pytest.approx(1.2 + 1.1)
    assert q.relative_spread == pytest.approx((0.2 + 0.2) / q.mid)


def test_managed_exit_mid_and_touch_endpoints():
    q = _quote()
    assert managed_exit_price(q, 0.0) == pytest.approx(q.mid)  # mid
    assert managed_exit_price(q, 1.0) == pytest.approx(q.touch_buy)  # full cross
    half = managed_exit_price(q, 0.5)
    assert q.mid < half < q.touch_buy


def test_realised_exit_uses_fallback_when_unfilled():
    q = _quote()
    filled = realised_exit_price(q, 0.0, filled_at_limit=True, fallback_full_cross=True)
    unfilled = realised_exit_price(q, 0.0, filled_at_limit=False, fallback_full_cross=True)
    assert filled == pytest.approx(q.mid)
    assert unfilled == pytest.approx(q.touch_buy)  # fell back to the touch


# ── stop book ────────────────────────────────────────────────────────────────


def test_mark_to_market_rom_and_stop_trigger():
    # credit 2.0/sh, margin sized so a 0.6/sh adverse move is -30% of margin.
    credit_ps, contracts = 2.0, 1
    margin = 0.6 * CONTRACT_MULTIPLIER * contracts / 0.30
    rom_at_stop = mark_to_market_rom(credit_ps, credit_ps + 0.6, margin, contracts)
    assert rom_at_stop == pytest.approx(-0.30)
    assert stop_triggered(credit_ps, credit_ps + 0.6, margin, contracts, -0.30)
    assert not stop_triggered(credit_ps, credit_ps + 0.3, margin, contracts, -0.30)


# ── parallel books assembled ─────────────────────────────────────────────────


def _position(credit_ps=2.0, contracts=1, margin=400.0) -> dict:
    return {
        "ticker": "TEST",
        "entry_date": "2026-01-05",
        "exit_date": "2026-01-07",
        "front_expiry": "2026-01-16",
        "strike": 100.0,
        "contracts": contracts,
        "spot_entry": 100.0,
        "iv_entry": 0.5,
        "t_entry": 0.05,
        "entry_credit": credit_ps * CONTRACT_MULTIPLIER * contracts,
        "margin": margin,
    }


def test_build_forward_exit_no_stop_when_small_move():
    # Small adverse move: stop not hit, both books identical, schema correct.
    pos = _position()
    q = _quote(cb=1.0, ca=1.1, pb=1.0, pa=1.1)  # buy-back mid ~2.10, small loss
    nostop, stop, recon = build_forward_exit(
        pos, q, spot_exit=101.0, iv_exit=0.3, exit_date="2026-01-07", t_exit=0.03
    )
    assert list(nostop.keys()) == LEDGER_COLUMNS
    assert not recon["stop_was_triggered"]
    assert stop["pnl"] == pytest.approx(nostop["pnl"])  # identical when no stop
    assert recon["stop_gap_slippage_ps"] == 0.0


def test_build_forward_exit_stop_costs_more_on_gap():
    # Big gap: buy-back mid far above credit, stop trips, stop book pays the touch.
    pos = _position(margin=400.0)
    q = _quote(cb=3.0, ca=3.4, pb=3.0, pa=3.4)  # mid 6.4 >> credit 2.0: deep loss
    nostop, stop, recon = build_forward_exit(
        pos,
        q,
        spot_exit=120.0,
        iv_exit=0.3,
        exit_date="2026-01-07",
        t_exit=0.03,
        config=FORWARD,
        filled_at_limit=True,
    )
    assert recon["stop_was_triggered"]
    # Stop crosses fully to the touch; the no-stop managed exit sits at the limit.
    assert stop["exit_value"] >= nostop["exit_value"]
    assert recon["stop_gap_slippage_ps"] >= 0.0
    # The reconciliation flags the realised round trip against break-even.
    assert recon["realised_round_trip_cost"] == pytest.approx(
        round_trip_cost_frac(ASSUMED_ENTRY_SPREAD, q.relative_spread)
    )


def test_pnl_real_two_leg_mark_matches_manual():
    pos = _position(credit_ps=2.0, contracts=2, margin=800.0)
    q = _quote(cb=0.7, ca=0.7, pb=0.7, pa=0.7)  # zero-spread mark at 1.4
    nostop, _, _ = build_forward_exit(
        pos, q, spot_exit=100.0, iv_exit=0.3, exit_date="2026-01-07", t_exit=0.03
    )
    scale = CONTRACT_MULTIPLIER * 2
    gross = (2.0 - 1.4) * scale
    assert nostop["pnl"] == pytest.approx(gross - nostop["commissions"])
    assert math.isclose(nostop["entry_credit"], 2.0 * scale)
