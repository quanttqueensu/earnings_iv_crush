"""
test_harness_lifecycle.py
Order-lifecycle defects of the paper harness found in adversarial review.

Each test pins one property a transmitting pass depends on:

* a limit is never built from a non-finite, negative or zero price;
* a leg whose own book is crossed, empty or unpriced is never priced, even when the
  straddle package as a whole looks sane;
* a failed re-quote holds the resting orders rather than walking the stale book;
* an exception inside the ladder cancels every working order before it propagates;
* a fill that lands while the cancel is in flight is booked, not lost;
* a partial fill inside a leg is reported by quantity;
* one failing position does not stop the remaining exits, and the pass exits non-zero;
* the Windows driver applies the session guard before any pass connects;
* the run date is the exchange date, not the machine's local date.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from earnings_iv_crush.live import ib_orders
from earnings_iv_crush.live.forward_test import StraddleQuote
from scripts import paper_trade_ibkr as pti

ROOT = Path(__file__).resolve().parents[2]


# ── fake gateway ─────────────────────────────────────────────────────────────


class LifecycleIB:
    """Fake gateway with one persistent trade per order, as ``ib_async`` keeps it.

    ``fill_at`` fills a leg once its limit reaches the threshold. ``partial`` reports
    that many contracts filled on a leg while the order stays working.
    ``fill_on_cancel`` fills a leg at its resting limit when the cancel arrives,
    which is the race a cancel can lose at the exchange.
    """

    def __init__(
        self,
        fill_at: dict[str, float] | None = None,
        partial: dict[str, int] | None = None,
        fill_on_cancel: set[str] | None = None,
    ) -> None:
        self.fill_at = fill_at or {}
        self.partial = partial or {}
        self.fill_on_cancel = fill_on_cancel or set()
        self.placed: list[tuple[str, float]] = []
        self.cancelled: list[object] = []
        self._trades: dict[int, SimpleNamespace] = {}

    def placeOrder(self, contract, order):
        right = contract.right
        self.placed.append((right, order.lmtPrice))
        trade = self._trades.get(id(order))
        if trade is None:
            trade = SimpleNamespace(
                contract=contract,
                order=order,
                orderStatus=SimpleNamespace(status="Submitted", avgFillPrice=0.0, filled=0.0),
            )
            self._trades[id(order)] = trade
        thr = self.fill_at.get(right)
        if thr is not None and order.lmtPrice + 1e-9 >= thr:
            trade.orderStatus.status = "Filled"
            trade.orderStatus.avgFillPrice = order.lmtPrice
            trade.orderStatus.filled = float(order.totalQuantity)
        elif right in self.partial:
            trade.orderStatus.filled = float(self.partial[right])
            trade.orderStatus.avgFillPrice = order.lmtPrice
        return trade

    def cancelOrder(self, order):
        self.cancelled.append(order)
        trade = self._trades[id(order)]
        if trade.contract.right in self.fill_on_cancel:
            trade.orderStatus.status = "Filled"
            trade.orderStatus.avgFillPrice = order.lmtPrice
            trade.orderStatus.filled = float(order.totalQuantity)

    def sleep(self, _s):
        return None


def _legs():
    return SimpleNamespace(right="C"), SimpleNamespace(right="P")


def _quote(cb=1.0, ca=1.2, pb=0.9, pa=1.1) -> StraddleQuote:
    return StraddleQuote(call_bid=cb, call_ask=ca, put_bid=pb, put_ask=pa)


# ── tick rounding ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "price, side",
    [(p, s) for p in (float("nan"), float("inf"), -0.03, 0.0) for s in ("BUY", "SELL")]
    + [(0.004, "SELL")],  # a sell floors to zero; a buy rounds up to a legal 0.01
)
def test_round_to_tick_refuses_unusable_prices(price: float, side: str) -> None:
    with pytest.raises(ValueError):
        ib_orders.round_to_tick(price, side)


@pytest.mark.parametrize(
    "price, side, expected",
    [
        (3.00, "BUY", 3.00),
        (3.00, "SELL", 3.00),
        (2.995, "BUY", 3.00),
        (2.995, "SELL", 2.99),
        (3.001, "BUY", 3.05),
        (3.001, "SELL", 3.00),
    ],
)
def test_round_to_tick_at_the_three_dollar_boundary(price, side, expected) -> None:
    assert ib_orders.round_to_tick(price, side) == pytest.approx(expected)


# ── per-leg book validity ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "call_bid, call_ask",
    [
        (1.30, 1.00),  # crossed leg hidden inside a sane package spread
        (0.0, 0.0),  # no offer
        (float("nan"), 1.20),  # no bid
    ],
)
def test_bad_leg_book_is_never_priced(call_bid: float, call_ask: float) -> None:
    ib: Any = LifecycleIB()
    call, put = _legs()
    quote = _quote(cb=call_bid, ca=call_ask, pb=0.9, pa=1.5)
    fill = ib_orders.place_managed_buyback(
        ib, call, put, 1, quote, transmit=True, cross_frac=0.5, reprice_steps=1
    )
    assert all(right == "P" for right, _ in ib.placed)
    assert fill.complete is False
    assert len(ib.cancelled) == 1  # only the put was ever working


def test_locked_leg_is_priced_at_the_touch() -> None:
    ib: Any = LifecycleIB(fill_at={"C": 1.10, "P": 1.00})
    call, put = _legs()
    fill = ib_orders.place_managed_buyback(
        ib, call, put, 1, _quote(cb=1.10, ca=1.10), transmit=True, cross_frac=0.5
    )
    assert fill.complete is True
    assert ("C", 1.10) in ib.placed


def test_exit_quote_refuses_a_crossed_leg() -> None:
    exp = pd.Timestamp("2026-01-16")
    chain = pd.DataFrame(
        [
            {"expiry": exp, "strike": 100.0, "right": "C", "bid": 1.30, "ask": 1.00, "iv": 0.4},
            {"expiry": exp, "strike": 100.0, "right": "P", "bid": 0.90, "ask": 1.50, "iv": 0.4},
        ]
    )
    assert pti._atm_quote(chain, exp, 100.0, exact=True) is None


# ── re-quote failure and exceptions mid-ladder ───────────────────────────────


def test_failed_requote_holds_rather_than_walking_the_stale_book() -> None:
    ib: Any = LifecycleIB()
    call, put = _legs()
    ib_orders.place_managed_buyback(
        ib,
        call,
        put,
        1,
        _quote(),
        transmit=True,
        cross_frac=0.5,
        reprice_steps=2,
        requote=lambda: None,
    )
    assert len(ib.placed) == 2  # first rung only; nothing repriced off the stale book
    assert len(ib.cancelled) == 2


def test_exception_mid_ladder_cancels_working_orders() -> None:
    ib: Any = LifecycleIB()
    call, put = _legs()

    def _boom() -> StraddleQuote | None:
        raise RuntimeError("gateway dropped")

    with pytest.raises(RuntimeError):
        ib_orders.place_managed_buyback(
            ib,
            call,
            put,
            1,
            _quote(),
            transmit=True,
            cross_frac=0.5,
            reprice_steps=2,
            requote=_boom,
        )
    assert len(ib.cancelled) == 2


# ── cancel race and partial fills ────────────────────────────────────────────


def test_fill_racing_the_cancel_is_booked() -> None:
    ib: Any = LifecycleIB(fill_at={"C": 1.15}, fill_on_cancel={"P"})
    call, put = _legs()
    fill = ib_orders.place_managed_buyback(
        ib, call, put, 1, _quote(), transmit=True, cross_frac=0.5, reprice_steps=0
    )
    assert fill.complete is True
    assert fill.legs_filled == 2
    assert fill.fill_price_ps == pytest.approx(1.15 + 1.05)


def test_partial_fill_inside_a_leg_is_reported_by_quantity() -> None:
    ib: Any = LifecycleIB(fill_at={"C": 1.15}, partial={"P": 1})
    call, put = _legs()
    fill = ib_orders.place_managed_buyback(
        ib, call, put, 3, _quote(), transmit=True, cross_frac=0.5, reprice_steps=1
    )
    assert fill.complete is False
    assert fill.legs_filled == 1
    assert fill.filled_qty == (3, 1)


def test_partial_fill_alarm_names_the_quantities(monkeypatch, capsys) -> None:
    exp = pd.Timestamp("2026-01-16")
    chain = pd.DataFrame(
        [
            {"expiry": exp, "strike": 100.0, "right": r, "bid": 1.0, "ask": 1.2, "iv": 0.4}
            for r in ("C", "P")
        ]
    )
    under = SimpleNamespace(contract=SimpleNamespace(symbol="TEST"), spot=100.0)
    monkeypatch.setattr(pti.ib_market, "qualify_underlying", lambda ib, t: under)
    monkeypatch.setattr(pti.ib_market, "snapshot_chain", lambda ib, u: chain)

    class _IB(LifecycleIB):
        def qualifyContracts(self, *legs):
            for i, leg in enumerate(legs):
                leg.conId = 1000 + i
            return list(legs)

        def positions(self):
            return [
                SimpleNamespace(contract=SimpleNamespace(conId=c), position=-3)
                for c in (1000, 1001)
            ]

    ib: Any = _IB(partial={"C": 2})
    pos = pd.Series(
        {"ticker": "TEST", "front_expiry": "2026-01-16", "strike": 100.0, "contracts": 3}
    )
    pti._process_forward_exit(ib, pos, pd.Timestamp("2026-01-07"), transmit=True)
    out = capsys.readouterr().out
    assert "ALARM" in out and "call 2/3" in out and "put 0/3" in out


# ── pass-level resilience ────────────────────────────────────────────────────


def test_one_failing_position_does_not_block_the_rest(monkeypatch, capsys) -> None:
    book = pd.DataFrame(
        {
            "ticker": ["BAD", "GOOD"],
            "exit_date": ["2026-01-07", "2026-01-07"],
        }
    )
    monkeypatch.setattr(pti.paper_book, "load_open_positions", lambda: book)
    monkeypatch.setattr(pti, "connect_paper", lambda: SimpleNamespace(isConnected=lambda: False))
    seen: list[str] = []

    def _process(ib, pos, asof, transmit):
        seen.append(pos["ticker"])
        if pos["ticker"] == "BAD":
            raise ValueError("Could not qualify both straddle legs")

    monkeypatch.setattr(pti, "_process_forward_exit", _process)
    args = pti.build_parser().parse_args(["forward-exit", "--asof", "2026-01-07"])
    with pytest.raises(SystemExit) as exc:
        pti.run_forward_exit(args)
    assert exc.value.code not in (0, None)
    assert seen == ["BAD", "GOOD"]
    assert "ALARM" in capsys.readouterr().out


def test_windows_driver_applies_the_session_guard_first() -> None:
    text = (ROOT / "scripts" / "run_paper_daily.ps1").read_text(encoding="utf-8")
    guard = text.find("deploy.session_check")
    assert guard != -1, "Windows driver never consults the NYSE session guard"
    assert guard < text.find("scripts.paper_trade_ibkr")


@pytest.mark.parametrize(
    "now, expected",
    [
        ("2026-01-07 02:00", "2026-01-06"),  # 21:00 ET the previous evening
        ("2026-07-07 20:30", "2026-07-07"),  # 16:30 EDT
    ],
)
def test_run_date_is_the_exchange_date(now: str, expected: str) -> None:
    stamp = pd.Timestamp(now, tz="UTC")
    assert pti.exchange_today(stamp) == pd.Timestamp(expected)


def test_legs_filled_at_different_rungs_book_each_legs_own_fill() -> None:
    # Call fills at the mid-seeking first rung, put only at the final full cross.
    ib: Any = LifecycleIB(fill_at={"C": 1.15, "P": 1.10})
    call, put = _legs()
    fill = ib_orders.place_managed_buyback(
        ib, call, put, 2, _quote(), transmit=True, cross_frac=0.5, reprice_steps=2
    )
    assert fill.complete is True
    assert fill.fill_price_ps == pytest.approx(1.15 + 1.10)
    assert fill.filled_qty == (2, 2)
    assert fill.filled_at_limit is False  # the ladder had to reach the touch
