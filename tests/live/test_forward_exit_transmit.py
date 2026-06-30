"""
test_forward_exit_transmit.py
Offline tests for the transmitting managed-exit path and the dry/offline booking
path of the forward exit. A fake gateway drives every order so the suite needs
no network and no IB gateway.

Three things are covered:

* the assume-fill branch is unchanged (no broker fill injected);
* the transmit branch books the broker fill price and ``filled_at_limit`` flag
  rather than the modelled mid mark; and
* the offline path runs ``build_forward_exit`` + ``record_forward_exit`` end to
  end and writes a complete reconciliation row.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from earnings_iv_crush.engine.pnl import CONTRACT_MULTIPLIER, LEDGER_COLUMNS
from earnings_iv_crush.live import paper_book
from earnings_iv_crush.live.forward_test import (
    FORWARD,
    StraddleQuote,
    build_forward_exit,
    managed_exit_price,
)
from earnings_iv_crush.live.ib_orders import place_managed_buyback


def _quote(cb=1.0, ca=1.2, pb=0.9, pa=1.1) -> StraddleQuote:
    return StraddleQuote(call_bid=cb, call_ask=ca, put_bid=pb, put_ask=pa)


def _position(credit_ps=2.0, contracts=1, margin=400.0) -> dict:
    return {
        "ticker": "TEST",
        "announce_date": "2026-01-06",
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
        "status": "open",
    }


# ── fake gateway ─────────────────────────────────────────────────────────────


class _Status:
    def __init__(self, status: str, avg_fill: float) -> None:
        self.status = status
        self.avgFillPrice = avg_fill


class _Trade:
    def __init__(self, contract: object, order: object, status: str, avg_fill: float) -> None:
        self.contract = contract
        self.order = order
        self.orderStatus = _Status(status, avg_fill)


class FakeFillIB:
    """Fills a leg the moment its limit reaches a per-right threshold."""

    def __init__(self, fill_at: dict[str, float] | None = None) -> None:
        self.fill_at = fill_at or {}
        self.placed: list[object] = []
        self.slept = 0.0

    def sleep(self, seconds: float) -> None:
        self.slept += seconds

    def placeOrder(self, contract: object, order: object) -> _Trade:
        self.placed.append((getattr(contract, "right", "?"), order.lmtPrice))
        threshold = self.fill_at.get(getattr(contract, "right", "?"))
        if threshold is not None and order.lmtPrice + 1e-9 >= threshold:
            return _Trade(contract, order, "Filled", order.lmtPrice)
        return _Trade(contract, order, "Submitted", 0.0)


def _legs() -> tuple[object, object]:
    return SimpleNamespace(right="C"), SimpleNamespace(right="P")


# ── (a) assume-fill branch unchanged ─────────────────────────────────────────


def test_assume_fill_branch_unchanged():
    pos = _position()
    q = _quote()
    nostop, _stop, recon = build_forward_exit(
        pos, q, spot_exit=101.0, iv_exit=0.3, exit_date="2026-01-07", t_exit=0.03
    )
    # No broker fill injected: the no-stop fill is the modelled managed limit.
    modelled = managed_exit_price(q, FORWARD.exit_limit_cross_frac)
    assert recon["nostop_fill_ps"] == pytest.approx(modelled)
    assert recon["filled_at_limit"] is True
    scale = CONTRACT_MULTIPLIER * int(pos["contracts"])
    assert nostop["exit_value"] == pytest.approx(modelled * scale)


# ── (b) transmit branch books the broker fill ────────────────────────────────


def test_managed_buyback_fills_at_first_rung():
    call, put = _legs()
    q = _quote()
    # Thresholds at mid: the very first (mid-seeking) rung clears both legs.
    ib = FakeFillIB(fill_at={"C": 1.10, "P": 1.00})
    fill = place_managed_buyback(ib, call, put, 1, q, transmit=True, cross_frac=0.5)
    # Per-leg limit at cross_frac=0.5 is each leg's mid + 0.5*half-spread.
    expected = managed_exit_price(q, 0.5)
    assert fill.fill_price_ps == pytest.approx(expected, abs=0.02)  # rounded to cents
    assert fill.filled_at_limit is True
    assert ib.slept > 0  # rested at the rung


def test_managed_buyback_crosses_to_touch_when_unfilled():
    call, put = _legs()
    q = _quote()
    # Thresholds above the touch: never fills, books the conservative touch.
    ib = FakeFillIB(fill_at={"C": 99.0, "P": 99.0})
    fill = place_managed_buyback(
        ib, call, put, 1, q, transmit=True, cross_frac=0.5, reprice_steps=2
    )
    assert fill.fill_price_ps == pytest.approx(q.touch_buy)
    assert fill.filled_at_limit is False


def test_managed_buyback_rejects_nonpositive_contracts():
    call, put = _legs()
    with pytest.raises(ValueError):
        place_managed_buyback(FakeFillIB(), call, put, 0, _quote(), transmit=True)


def test_transmit_branch_books_broker_fill_not_modelled():
    pos = _position()
    q = _quote()
    # A realised fill deliberately worse than the modelled mid-seeking limit.
    broker_fill = managed_exit_price(q, FORWARD.exit_limit_cross_frac) + 0.07
    nostop, _stop, recon = build_forward_exit(
        pos,
        q,
        spot_exit=101.0,
        iv_exit=0.3,
        exit_date="2026-01-07",
        t_exit=0.03,
        filled_at_limit=False,
        transmitted_fill_ps=broker_fill,
    )
    scale = CONTRACT_MULTIPLIER * int(pos["contracts"])
    assert recon["nostop_fill_ps"] == pytest.approx(broker_fill)
    assert nostop["exit_value"] == pytest.approx(broker_fill * scale)
    assert recon["slippage_vs_mid_ps"] == pytest.approx(broker_fill - q.mid)
    assert recon["filled_at_limit"] is False


# ── (c) offline path: end-to-end reconciliation row ──────────────────────────

RECON_KEYS = {
    "ticker",
    "entry_date",
    "exit_date",
    "assumed_mid_mark_ps",
    "nostop_fill_ps",
    "filled_at_limit",
    "slippage_vs_mid_ps",
    "assumed_exit_spread",
    "realised_exit_spread",
    "stop_was_triggered",
    "stop_fill_ps",
    "stop_gap_slippage_ps",
    "realised_round_trip_cost",
    "breakeven_round_trip",
    "over_breakeven",
}


def test_offline_path_writes_complete_reconciliation(tmp_path):
    pos = pd.Series(_position())
    open_path = tmp_path / "open.parquet"
    pd.DataFrame([_position()]).to_parquet(open_path, index=False)

    nostop_path = tmp_path / "nostop.parquet"
    stop_path = tmp_path / "stop.parquet"
    recon_path = tmp_path / "recon.parquet"

    nostop, stop, recon = paper_book.forward_exit_from_quote(
        pos,
        _quote(),
        spot_exit=101.0,
        iv_exit=0.3,
        exit_date=pd.Timestamp("2026-01-07"),
        t_exit=0.03,
        nostop_path=nostop_path,
        stop_path=stop_path,
        reconciliation_path=recon_path,
        open_path=open_path,
    )

    # Complete reconciliation row, keyed to the canonical break-even.
    assert set(recon.keys()) == RECON_KEYS
    assert recon["breakeven_round_trip"] > 0
    assert isinstance(recon["over_breakeven"], bool)

    # Both ledger rows persisted in the backtest schema.
    saved_nostop = pd.read_parquet(nostop_path)
    saved_recon = pd.read_parquet(recon_path)
    assert list(saved_nostop.columns) == LEDGER_COLUMNS
    assert len(saved_recon) == 1
    assert saved_recon.iloc[0]["ticker"] == "TEST"

    # The open position was flipped to closed.
    closed = pd.read_parquet(open_path)
    assert (closed["status"] == "closed").all()
    assert nostop["ticker"] == "TEST" and stop["ticker"] == "TEST"
