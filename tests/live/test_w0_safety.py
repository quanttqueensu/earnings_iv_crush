"""
test_w0_safety.py
Safety properties of the paper harness that must hold before any order is transmitted.

Each test pins one defect found in review and fixed:

* one transmission rule for entry and exit (``--transmit`` sends unless ``--dry-run``),
  with entries held back until the entry ladder exists;
* exits close the stored strike and expiry, never the strike nearest today's spot;
* an exit is not transmitted when the broker does not hold the expected short legs;
* the managed buy-back re-quotes per rung, reprices only unfilled legs, cancels what
  is left and reports a legged result rather than inventing a fill;
* limits are rounded to a legal tick without crossing the far touch.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from earnings_iv_crush.live import ib_orders
from earnings_iv_crush.live.forward_test import StraddleQuote
from scripts import paper_trade_ibkr as pti

# ── transmission rule ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "argv, expected",
    [
        (["forward-exit"], False),
        (["forward-exit", "--transmit"], True),
        (["forward-exit", "--transmit", "--dry-run"], False),
        (["enter"], False),
        (["enter", "--transmit"], True),
        (["enter", "--transmit", "--dry-run"], False),
    ],
)
def test_one_transmission_rule(argv: list[str], expected: bool) -> None:
    args = pti.build_parser().parse_args(argv)
    assert pti.transmit_requested(args) is expected


def test_entry_transmission_only_with_its_preconditions() -> None:
    # Spec T4: entries may transmit only once the order log (T1), the ladder (T2), the
    # HALT switch (T3) and separate dry stores (T5) exist.
    if not pti.ENTRY_TRANSMIT_READY:
        return
    from earnings_iv_crush.config import LIVE
    from earnings_iv_crush.live import ladder, order_events, session

    assert callable(order_events.OrderEventLog.record)
    assert callable(ladder.run_ladder)
    assert LIVE.halt_file and LIVE.dry_dir
    live, dry = session.Stores.for_mode(True), session.Stores.for_mode(False)
    assert not set(live.__dict__.values()) & set(dry.__dict__.values())


def test_legacy_enter_never_transmits(monkeypatch, capsys) -> None:
    sent: list[object] = []
    monkeypatch.setattr(pti.ib_orders, "place_short_straddle", lambda *a, **k: sent.append(1))
    monkeypatch.setattr(pti, "candidate_events", lambda *a: pd.DataFrame())
    monkeypatch.setattr(pti.paper_book, "record_heartbeat", lambda *a, **k: None)
    pti.run_enter(pti.build_parser().parse_args(["enter", "--transmit"]))
    assert sent == []
    assert "never transmits" in capsys.readouterr().out


# ── exact-strike quoting ─────────────────────────────────────────────────────


def _chain(strikes: list[float]) -> pd.DataFrame:
    exp = pd.Timestamp("2026-01-16")
    rows = []
    for k in strikes:
        for right in ("C", "P"):
            rows.append(
                {"expiry": exp, "strike": k, "right": right, "bid": 1.0, "ask": 1.2, "iv": 0.4}
            )
    return pd.DataFrame(rows)


def test_exit_quote_refuses_a_neighbouring_strike() -> None:
    chain = _chain([105.0, 110.0])
    exp = pd.Timestamp("2026-01-16")
    assert pti._atm_quote(chain, exp, 100.0, exact=True) is None
    assert pti._atm_quote(chain, exp, 100.0) is not None  # the old, permissive behaviour


# ── broker position check and stored-strike exit ─────────────────────────────


class _Pos(SimpleNamespace):
    pass


class FakeIB:
    """Records qualifications, orders and cancels; holds configurable positions."""

    def __init__(self, positions: dict[int, int], fill_at: dict[str, float] | None = None):
        self._positions = positions
        self.fill_at = fill_at or {}
        self.qualified: list[tuple[str, float, str]] = []
        self.placed: list[tuple[str, float]] = []
        self.cancelled: list[object] = []

    def qualifyContracts(self, *legs):
        out = []
        for i, leg in enumerate(legs):
            self.qualified.append((leg.lastTradeDateOrContractMonth, leg.strike, leg.right))
            leg.conId = 1000 + i
            out.append(leg)
        return out

    def positions(self):
        return [
            _Pos(contract=SimpleNamespace(conId=c), position=q) for c, q in self._positions.items()
        ]

    def placeOrder(self, contract, order):
        self.placed.append((contract.right, order.lmtPrice))
        thr = self.fill_at.get(contract.right)
        status = "Filled" if thr is not None and order.lmtPrice + 1e-9 >= thr else "Submitted"
        return SimpleNamespace(
            orderStatus=SimpleNamespace(status=status, avgFillPrice=order.lmtPrice)
        )

    def cancelOrder(self, order):
        self.cancelled.append(order)

    def sleep(self, _s):
        return None


def _patch_market(monkeypatch, chain: pd.DataFrame, spot: float) -> None:
    under = SimpleNamespace(contract=SimpleNamespace(symbol="TEST"), spot=spot)
    monkeypatch.setattr(pti.ib_market, "qualify_underlying", lambda ib, t: under)
    monkeypatch.setattr(pti.ib_market, "snapshot_chain", lambda ib, u: chain)


def _position() -> pd.Series:
    return pd.Series(
        {
            "ticker": "TEST",
            "front_expiry": "2026-01-16",
            "strike": 100.0,
            "contracts": 1,
        }
    )


def test_exit_qualifies_the_stored_strike_and_refuses_on_mismatch(monkeypatch, capsys) -> None:
    # Spot has moved to 112 after the print; the held strike is 100.
    _patch_market(monkeypatch, _chain([100.0, 110.0, 115.0]), spot=112.0)
    ib = FakeIB(positions={})  # broker holds nothing
    pti._process_forward_exit(ib, _position(), pd.Timestamp("2026-01-07"), transmit=True)
    assert ib.qualified and all(k == 100.0 for _, k, _ in ib.qualified)
    assert ib.placed == []  # nothing transmitted
    assert "ALARM" in capsys.readouterr().out


def test_exit_incomplete_buyback_books_nothing(monkeypatch, capsys) -> None:
    _patch_market(monkeypatch, _chain([100.0]), spot=101.0)
    booked: list[object] = []
    monkeypatch.setattr(pti.paper_book, "forward_exit_from_quote", lambda *a, **k: booked.append(1))
    ib = FakeIB(positions={1000: -1, 1001: -1}, fill_at={"C": 99.0, "P": 99.0})
    pti._process_forward_exit(ib, _position(), pd.Timestamp("2026-01-07"), transmit=True)
    assert booked == []
    assert len(ib.cancelled) == 2
    assert "ALARM" in capsys.readouterr().out


# ── managed buy-back mechanics ───────────────────────────────────────────────


def _quote(cb=1.0, ca=1.2, pb=0.9, pa=1.1) -> StraddleQuote:
    return StraddleQuote(call_bid=cb, call_ask=ca, put_bid=pb, put_ask=pa)


def test_legged_fill_is_reported_and_remainder_cancelled() -> None:
    ib = FakeIB(positions={}, fill_at={"C": 1.15})  # call fills at the first rung, put never
    call, put = SimpleNamespace(right="C"), SimpleNamespace(right="P")
    fill = ib_orders.place_managed_buyback(
        ib, call, put, 1, _quote(), transmit=True, cross_frac=0.5, reprice_steps=2
    )
    assert fill.complete is False and fill.legs_filled == 1
    assert len(ib.cancelled) == 1
    # The filled call is never repriced after it fills.
    assert sum(1 for right, _ in ib.placed if right == "C") == 1


def test_requote_is_used_on_later_rungs() -> None:
    ib = FakeIB(positions={}, fill_at={})
    call, put = SimpleNamespace(right="C"), SimpleNamespace(right="P")
    fresh = _quote(cb=2.0, ca=2.2, pb=1.9, pa=2.1)
    ib_orders.place_managed_buyback(
        ib,
        call,
        put,
        1,
        _quote(),
        transmit=True,
        cross_frac=0.5,
        reprice_steps=1,
        requote=lambda: fresh,
    )
    last_call = [px for right, px in ib.placed if right == "C"][-1]
    assert last_call == pytest.approx(2.2)  # final rung crosses to the fresh ask


@pytest.mark.parametrize(
    "price, side, bid, ask, expected",
    [
        (1.234, "BUY", 1.0, 1.3, 1.24),
        (1.234, "SELL", 1.0, 1.3, 1.23),
        (3.12, "BUY", 3.0, 3.30, 3.15),
        (3.12, "SELL", 3.0, 3.30, 3.10),
        (3.27, "BUY", 3.0, 3.26, 3.26),  # never above the ask
        (3.02, "SELL", 3.03, 3.30, 3.03),  # never below the bid
    ],
)
def test_round_to_tick(price, side, bid, ask, expected) -> None:
    assert ib_orders.round_to_tick(price, side, bid, ask) == pytest.approx(expected)


def test_broker_short_qty_sums_matching_contract() -> None:
    ib = FakeIB(positions={7: -2, 8: 1})
    assert ib_orders.broker_short_qty(ib, SimpleNamespace(conId=7)) == -2
    assert ib_orders.broker_short_qty(ib, SimpleNamespace(conId=9)) == 0
