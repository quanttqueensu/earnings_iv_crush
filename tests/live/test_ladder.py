"""
test_ladder.py
The session ladder against a fake gateway and a fake clock (forward-test spec T1 to T3, T11).

Each test pins one property the transmitting pass depends on: rung prices follow the
schedule on both sides; nothing is working after the cancel time; a legged entry is
flattened; a fill that races the cancel is booked; an exception cancels everything;
HALT stops every path; a dry run places nothing; a late pass sends nothing; a failed
re-quote holds; a no-bid exit leg is still closable; every lifecycle in the order log
is complete; every leg gets a 15:59 NBBO row.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from earnings_iv_crush.live import ladder as ld
from earnings_iv_crush.live.order_events import (
    OrderEventLog,
    check_completeness,
    load_order_events,
)

DAY = pd.Timestamp("2026-10-19")
TZ = "America/New_York"


# ── fakes ────────────────────────────────────────────────────────────────────


class FakeClock:
    def __init__(self, start: str = "15:20:00") -> None:
        self.t = pd.Timestamp(f"{DAY.date()} {start}", tz=TZ)
        self.waits: list[pd.Timestamp] = []

    def now(self) -> pd.Timestamp:
        return self.t

    def wait_until(self, when: pd.Timestamp) -> None:
        self.waits.append(when)
        self.t = max(self.t, when)


class FakeGateway:
    """One persistent trade per order, fills against per-(right, side) thresholds.

    A SELL fills once its limit is at or below ``sell_fill[right]``; a BUY once its limit
    is at or above ``buy_fill[right]``. ``fill_on_cancel`` fills a leg at its resting
    limit when the cancel arrives.
    """

    def __init__(self, sell_fill=None, buy_fill=None, fill_on_cancel=None) -> None:
        self.sell_fill = sell_fill or {}
        self.buy_fill = buy_fill or {}
        self.fill_on_cancel = fill_on_cancel or set()
        self.placed: list[tuple[str, str, float, int]] = []
        self.cancelled: list[Any] = []
        self._trades: dict[int, SimpleNamespace] = {}
        self._next_id = 100
        self.client = SimpleNamespace(getReqId=self._req_id)

    def _req_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _fill(self, trade: SimpleNamespace) -> None:
        order = trade.order
        trade.orderStatus.status = "Filled"
        trade.orderStatus.filled = float(order.totalQuantity)
        trade.orderStatus.remaining = 0.0
        trade.orderStatus.avgFillPrice = float(order.lmtPrice)
        trade.fills.append(
            SimpleNamespace(
                execution=SimpleNamespace(
                    execId=f"x{order.orderId}", shares=order.totalQuantity, price=order.lmtPrice
                ),
                commissionReport=SimpleNamespace(commission=0.65),
                time=pd.Timestamp("2026-10-19 19:50", tz="UTC"),
            )
        )

    def placeOrder(self, contract, order):
        self.placed.append((contract.right, order.action, float(order.lmtPrice), id(order)))
        trade = self._trades.get(id(order))
        if trade is None:
            if not getattr(order, "orderId", 0):
                order.orderId = self._req_id()
            trade = SimpleNamespace(
                contract=contract,
                order=order,
                orderStatus=SimpleNamespace(
                    status="Submitted", filled=0.0, remaining=order.totalQuantity, avgFillPrice=0.0
                ),
                fills=[],
                log=[],
            )
            self._trades[id(order)] = trade
        if trade.orderStatus.status == "Filled":
            return trade
        book = self.sell_fill if order.action == "SELL" else self.buy_fill
        thr = book.get(contract.right)
        if thr is not None:
            hit = (
                order.lmtPrice <= thr + 1e-9
                if order.action == "SELL"
                else order.lmtPrice >= thr - 1e-9
            )
            if hit:
                self._fill(trade)
        return trade

    def cancelOrder(self, order):
        self.cancelled.append(order)
        trade = self._trades[id(order)]
        if trade.contract.right in self.fill_on_cancel:
            self._fill(trade)
        else:
            trade.orderStatus.status = "Cancelled"

    def sleep(self, _s):
        return None


def _leg(purpose: str, right: str, qty: int = 2, group: str = "AAA|2026-10-19") -> ld.LadderLeg:
    side = "SELL" if purpose == "entry" else "BUY"
    return ld.LadderLeg(
        group=f"{group}:{purpose}",
        ticker=group.split("|")[0],
        position_key=group,
        purpose=purpose,
        side=side,
        right=right,
        contract=SimpleNamespace(right=right, conId=1 if right == "C" else 2),
        quantity=qty,
        strike=100.0,
        expiry=pd.Timestamp("2026-10-23"),
    )


def _quotes(book: dict[str, tuple[float, float]] | None = None):
    book = book or {}

    def fn(legs):
        return {leg.key: ld.LegQuote(*book.get(leg.right, (1.00, 1.20))) for leg in legs}

    return fn


def _run(tmp_path, legs, gw, *, quote_fn=None, clock=None, transmit=True, halted=None):
    log = OrderEventLog(tmp_path / "events.csv", DAY, transmit=transmit, market_data_type=1)
    outcomes = ld.run_ladder(
        gw,
        legs,
        quote_fn=quote_fn or _quotes(),
        clock=clock or FakeClock(),
        schedule=ld.LadderSchedule.for_session(DAY),
        log=log,
        transmit=transmit,
        halted=halted or (lambda: False),
        settle_s=0.0,
    )
    return outcomes, load_order_events(tmp_path / "events.csv")


# ── pricing ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "purpose, expected",
    [
        ("entry", [1.10, 1.07, 1.05, 1.02, 1.00]),  # sells walk down to the bid
        ("exit", [1.10, 1.13, 1.15, 1.18, 1.20]),  # buys walk up to the ask
    ],
)
def test_rung_prices_follow_the_schedule(tmp_path, purpose, expected) -> None:
    gw = FakeGateway()
    _run(tmp_path, [_leg(purpose, "C")], gw)
    assert [px for _, _, px, _ in gw.placed] == pytest.approx(expected)


def test_rungs_wait_for_their_clock_times(tmp_path) -> None:
    clock = FakeClock()
    _run(tmp_path, [_leg("entry", "C")], FakeGateway(), clock=clock)
    hhmm = [t.strftime("%H:%M:%S") for t in clock.waits]
    assert hhmm[:5] == ["15:45:00", "15:47:30", "15:50:00", "15:52:30", "15:55:00"]
    assert "15:58:00" in hhmm and hhmm[-1] == "15:59:00"


def test_nothing_is_working_after_the_cancel_time(tmp_path) -> None:
    gw = FakeGateway()
    outcomes, _ = _run(tmp_path, [_leg("exit", "C"), _leg("exit", "P")], gw)
    assert len(gw.cancelled) == 2
    assert all(t.orderStatus.status == "Cancelled" for t in gw._trades.values())
    assert outcomes[0].status == "unfilled"


def test_both_legs_fill_and_book_their_own_prices(tmp_path) -> None:
    gw = FakeGateway(sell_fill={"C": 1.10, "P": 1.05})  # call at rung 0, put at rung 2
    outcomes, _ = _run(tmp_path, [_leg("entry", "C"), _leg("entry", "P")], gw)
    assert outcomes[0].status == "filled"
    assert outcomes[0].fill_ps == pytest.approx(1.10 + 1.05)
    assert gw.cancelled == []


# ── legging, races and failures ──────────────────────────────────────────────


def test_legged_entry_is_flattened(tmp_path) -> None:
    gw = FakeGateway(sell_fill={"C": 1.10}, buy_fill={"C": 1.20})  # put never sells
    outcomes, events = _run(tmp_path, [_leg("entry", "C"), _leg("entry", "P")], gw)
    assert outcomes[0].status == "legged_flattened"
    flatten = events[events["purpose"] == "flatten"]
    assert (flatten["event"] == "submit").sum() == 1
    assert ("C", "BUY", 1.20) in [(r, a, p) for r, a, p, _ in gw.placed]


def test_legged_entry_with_no_flatten_fill_is_an_alarm(tmp_path) -> None:
    gw = FakeGateway(sell_fill={"C": 1.10})  # buy-back never fills
    outcomes, _ = _run(tmp_path, [_leg("entry", "C"), _leg("entry", "P")], gw)
    assert outcomes[0].status == "legged_open" and outcomes[0].alarm


def test_incomplete_exit_is_not_forced(tmp_path) -> None:
    gw = FakeGateway(buy_fill={"C": 1.10})
    outcomes, events = _run(tmp_path, [_leg("exit", "C"), _leg("exit", "P")], gw)
    assert outcomes[0].status == "incomplete" and outcomes[0].alarm
    assert not (events["purpose"] == "flatten").any()


def test_fill_racing_the_cancel_is_booked(tmp_path) -> None:
    gw = FakeGateway(buy_fill={"C": 1.10}, fill_on_cancel={"P"})
    outcomes, _ = _run(tmp_path, [_leg("exit", "C"), _leg("exit", "P")], gw)
    assert outcomes[0].status == "filled"
    assert outcomes[0].fill_ps == pytest.approx(1.10 + 1.20)


def test_exception_at_a_rung_cancels_everything(tmp_path) -> None:
    gw = FakeGateway()
    calls = {"n": 0}

    def flaky(legs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("gateway dropped")
        return _quotes()(legs)

    with pytest.raises(RuntimeError):
        _run(tmp_path, [_leg("exit", "C"), _leg("exit", "P")], gw, quote_fn=flaky)
    assert len(gw.cancelled) == 2


def test_halt_cancels_and_stops_every_path(tmp_path) -> None:
    gw = FakeGateway(sell_fill={"C": 1.10})  # call legs in at rung 0
    rung = {"n": 0}

    def halted() -> bool:
        rung["n"] += 1
        return rung["n"] >= 3

    outcomes, events = _run(tmp_path, [_leg("entry", "C"), _leg("entry", "P")], gw, halted=halted)
    assert (events["event"] == "halt").sum() == 1
    assert not any(a == "BUY" for _, a, _, _ in gw.placed)  # no flatten under HALT
    assert outcomes[0].status == "legged_open"


def test_late_pass_sends_nothing(tmp_path) -> None:
    gw = FakeGateway()
    with pytest.raises(ld.LadderTooLate):
        _run(tmp_path, [_leg("entry", "C")], gw, clock=FakeClock("15:55:30"))
    assert gw.placed == []


def test_dry_run_places_nothing_and_logs_intents(tmp_path) -> None:
    gw = FakeGateway(sell_fill={"C": 9.9, "P": 9.9})
    outcomes, events = _run(tmp_path, [_leg("entry", "C"), _leg("entry", "P")], gw, transmit=False)
    assert gw.placed == [] and gw.cancelled == []
    assert outcomes[0].status == "unfilled"
    intents = events[events["event"].isin(["submit", "modify"])]
    assert len(intents) == 10 and not intents["transmit"].astype(bool).any()
    assert (intents["event"] == "submit").sum() == 2


def test_failed_requote_holds_the_resting_order(tmp_path) -> None:
    gw = FakeGateway()
    calls = {"n": 0}

    def first_only(legs):
        calls["n"] += 1
        return _quotes()(legs) if calls["n"] == 1 else {}

    _, events = _run(tmp_path, [_leg("exit", "C")], gw, quote_fn=first_only)
    assert len(gw.placed) == 1
    assert (events["event"] == "hold_stale_quote").sum() == 4


def test_rejected_leg_is_logged_and_never_re_placed(tmp_path) -> None:
    class Rejecting(FakeGateway):
        def placeOrder(self, contract, order):
            trade = super().placeOrder(contract, order)
            if contract.right == "P":
                trade.orderStatus.status = "Inactive"
                trade.log = [SimpleNamespace(message="Order price is not a legal tick")]
            return trade

    gw = Rejecting()
    _, events = _run(tmp_path, [_leg("exit", "C"), _leg("exit", "P")], gw)
    assert sum(1 for r, *_ in gw.placed if r == "P") == 1
    rejects = events[events["event"] == "reject"]
    assert len(rejects) == 1 and "legal tick" in rejects["reason"].iloc[0]


# ── books ────────────────────────────────────────────────────────────────────


def test_no_bid_exit_leg_walks_from_one_tick_to_the_ask(tmp_path) -> None:
    gw = FakeGateway()
    _run(tmp_path, [_leg("exit", "P")], gw, quote_fn=_quotes({"P": (float("nan"), 0.05)}))
    prices = [px for _, _, px, _ in gw.placed]
    assert prices[-1] == pytest.approx(0.05)
    assert all(0.01 <= p <= 0.05 for p in prices)


def test_sell_leg_with_no_bid_is_never_priced(tmp_path) -> None:
    gw = FakeGateway()
    _, events = _run(tmp_path, [_leg("entry", "C")], gw, quote_fn=_quotes({"C": (0.0, 0.10)}))
    assert gw.placed == []
    assert (events["event"] == "skip_bad_book").sum() == 5


@pytest.mark.parametrize(
    "bid, ask, side, usable",
    [
        (1.0, 1.2, "SELL", True),
        (1.3, 1.2, "SELL", False),  # crossed
        (float("nan"), 1.2, "SELL", False),
        (float("nan"), 1.2, "BUY", True),
        (0.0, 0.0, "BUY", False),
        (1.3, 1.2, "BUY", False),
    ],
)
def test_leg_book_usability(bid, ask, side, usable) -> None:
    assert ld.LegQuote(bid, ask).usable_for(side) is usable


# ── the log ──────────────────────────────────────────────────────────────────


def test_transmitted_lifecycles_are_complete_and_every_leg_has_a_1559_row(tmp_path) -> None:
    gw = FakeGateway(sell_fill={"C": 1.10, "P": 1.05}, buy_fill={"C": 1.15})
    legs = [
        _leg("entry", "C"),
        _leg("entry", "P"),
        _leg("exit", "C", group="BBB|2026-10-16"),
        _leg("exit", "P", group="BBB|2026-10-16"),
    ]
    _, events = _run(tmp_path, legs, gw)
    assert check_completeness(events).empty
    assert (events["event"] == "nbbo_1559").sum() == 4
    fills = events[events["event"] == "fill"]
    assert fills["fill_qty"].sum() == 6  # two entry legs and one exit leg, two contracts each


def test_incomplete_lifecycle_is_detected() -> None:
    events = pd.DataFrame(
        [
            {
                "run_id": "r",
                "order_id": 1,
                "event": "submit",
                "status": None,
                "fill_qty": None,
                "cum_filled": None,
            },
            {
                "run_id": "r",
                "order_id": 2,
                "event": "submit",
                "status": None,
                "fill_qty": None,
                "cum_filled": None,
            },
            {
                "run_id": "r",
                "order_id": 2,
                "event": "fill",
                "status": "Filled",
                "fill_qty": 1,
                "cum_filled": 2,
            },
        ]
    )
    problems = check_completeness(events)
    assert set(problems["problem"]) == {"no_terminal", "fill_sum_mismatch"}
