"""
ladder.py
Clock-driven limit-order ladder that trades every entry and exit leg of a session together.

The forward-test specification (section 2.1) trades the straddle leg by leg with limits
that start at the mid and walk to the touch, finishing before the 15:59 ET mark the
backtest uses:

==========  ===========================================================
15:45:00    rung 0, every leg at mid
15:47:30    rung 1, 25% of the way from mid to the touch
15:50:00    rung 2, 50%
15:52:30    rung 3, 75%
15:55:00    rung 4, the touch (bid for a sell, ask for a buy)
15:58:00    cancel every working order; re-read status after the settle time
15:59:00    NBBO of every leg, filled or not (the counterfactual basis)
==========  ===========================================================

Entry legs sell and walk down toward the bid; exit legs buy and walk up toward the ask.
Each rung re-quotes the open legs. A failed re-quote holds the resting order rather
than walking a stale book, and a leg whose book is unusable is not priced. Every limit
is rounded to a legal tick away from the far touch (``ib_orders.round_to_tick``).

**Legging.** An entry is complete only when both legs fill in full. If one leg (or
part of one) fills and the other does not by the cancel time, the filled quantity is
bought back at the touch before 15:59 and the event is reported ``legged_flattened``.
An exit that ends incomplete is not forced: its working orders are cancelled and the
caller raises an alarm, because a naked leg is closed by the next session's ladder or
by the operator.

**Switches.** ``halted()`` is checked before every rung and before the flatten. When it
returns ``True`` every working order is cancelled and nothing further is sent on any
path, flatten included.

**Dry run.** With ``transmit=False`` the ladder runs the same clock and prices, writes
every intended order to the log with ``transmit=False``, and places nothing.

Every state change is written to the order-event log before the ladder acts on it.
The clock and the quote source are injected, so the whole schedule runs offline in
tests against a fake gateway.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd

from ..config import LIVE
from .ib_orders import round_to_tick
from .order_events import OrderEventLog

EXCHANGE_TZ = "America/New_York"


# ── quotes ───────────────────────────────────────────────────────────────────


def _tick(price: float) -> float:
    """Penny-programme tick for an option price (0.01 below 3.00, 0.05 at or above)."""
    return 0.01 if price < 3.0 else 0.05


@dataclass(frozen=True)
class LegQuote:
    """Touch of one option leg at one instant."""

    bid: float
    ask: float
    bid_size: float = float("nan")
    ask_size: float = float("nan")
    ts: pd.Timestamp | None = None

    def usable_for(self, side: str) -> bool:
        """Whether this book can price an order on ``side``.

        A sell needs a positive bid and an ask at or above it. A buy needs a positive
        ask; a missing or zero bid is allowed, because after a large gap the far
        out-of-the-money leg often shows no bid and must still be closable (ticket
        T11). A crossed book is never usable.
        """
        bid_ok = np.isfinite(self.bid) and self.bid > 0
        ask_ok = np.isfinite(self.ask) and self.ask > 0
        if side == "SELL":
            return bool(bid_ok and ask_ok and self.ask >= self.bid)
        if side == "BUY":
            return bool(ask_ok and (not bid_ok or self.bid <= self.ask))
        raise ValueError(f"side must be BUY or SELL, got {side!r}")

    def limit(self, side: str, frac: float) -> float:
        """Rounded limit ``frac`` of the way from mid to the touch on ``side``.

        For a buy with no bid, the walk runs from one tick to the ask instead of from
        the mid, so rung 0 sits half-way between them and the final rung is the ask.
        """
        frac = float(np.clip(frac, 0.0, 1.0))
        if side == "SELL":
            mid = 0.5 * (self.bid + self.ask)
            raw = mid - frac * 0.5 * (self.ask - self.bid)
            return round_to_tick(raw, "SELL", self.bid, self.ask)
        bid = self.bid if (np.isfinite(self.bid) and self.bid > 0) else _tick(self.ask)
        bid = min(bid, self.ask)
        mid = 0.5 * (bid + self.ask)
        raw = mid + frac * 0.5 * (self.ask - bid)
        return round_to_tick(raw, "BUY", None, self.ask)


# ── legs ─────────────────────────────────────────────────────────────────────


@dataclass
class LadderLeg:
    """One option leg the ladder works, with its live order state.

    Attributes
    ----------
    group : str
        Legs that must complete together (one straddle entry or one exit).
    purpose : str
        ``"entry"`` or ``"exit"``.
    side : str
        ``"SELL"`` (entries) or ``"BUY"`` (exits).
    right : str
        ``"C"`` or ``"P"``.
    contract : ib_async.Contract
        The qualified option contract.
    quantity : int
        Contracts to trade on this leg.
    """

    group: str
    ticker: str
    position_key: str
    purpose: str
    side: str
    right: str
    contract: Any
    quantity: int
    strike: float
    expiry: pd.Timestamp
    order: Any = None
    trade: Any = None
    limit_price: float = float("nan")
    rung: int | None = None
    last_status: str = ""
    seen_exec: set[str] = field(default_factory=set)
    last_quote: LegQuote | None = None

    @property
    def key(self) -> str:
        return f"{self.group}:{self.right}"

    @property
    def filled_qty(self) -> int:
        """Contracts the broker reports filled on this leg's order."""
        status = getattr(self.trade, "orderStatus", None)
        filled = getattr(status, "filled", 0.0) if status is not None else 0.0
        if filled is None or not np.isfinite(filled):
            return 0
        return int(round(float(filled)))

    @property
    def avg_fill(self) -> float:
        status = getattr(self.trade, "orderStatus", None)
        px = getattr(status, "avgFillPrice", float("nan")) if status is not None else float("nan")
        return float(px) if px is not None and self.filled_qty > 0 else float("nan")

    @property
    def done(self) -> bool:
        return self.filled_qty >= self.quantity

    def working(self) -> bool:
        status = getattr(getattr(self.trade, "orderStatus", None), "status", "")
        return self.trade is not None and status not in (
            "Filled",
            "Cancelled",
            "ApiCancelled",
            "Inactive",
        )

    def base_fields(self) -> dict[str, Any]:
        order_id = getattr(self.order, "orderId", None) if self.order is not None else None
        perm_id = getattr(self.order, "permId", None) if self.order is not None else None
        return {
            "ticker": self.ticker,
            "position_key": self.position_key,
            "leg": self.right,
            "con_id": getattr(self.contract, "conId", None),
            "strike": float(self.strike),
            "expiry": str(pd.Timestamp(self.expiry).date()),
            "purpose": self.purpose,
            "side": self.side,
            "order_id": order_id or None,
            "perm_id": perm_id or None,
            "order_qty": int(self.quantity),
        }


# ── schedule and clock ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class LadderSchedule:
    """Absolute times (exchange time zone) for one session's ladder."""

    rungs: tuple[tuple[pd.Timestamp, float], ...]
    cancel_at: pd.Timestamp
    nbbo_at: pd.Timestamp
    latest_start: pd.Timestamp

    @classmethod
    def for_session(cls, session_date: pd.Timestamp, config: Any = LIVE) -> LadderSchedule:
        """Build the schedule from ``LiveConfig`` for an exchange date."""
        day = pd.Timestamp(session_date).date()

        def at(hhmmss: str) -> pd.Timestamp:
            return pd.Timestamp(f"{day} {hhmmss}", tz=EXCHANGE_TZ)

        rungs = tuple((at(t), float(f)) for t, f in config.ladder_rungs)
        sched = cls(
            rungs=rungs,
            cancel_at=at(config.ladder_cancel_at),
            nbbo_at=at(config.ladder_nbbo_at),
            latest_start=at(config.ladder_latest_start),
        )
        times = [t for t, _ in rungs] + [sched.cancel_at, sched.nbbo_at]
        if any(b <= a for a, b in zip(times, times[1:], strict=False)):
            raise ValueError("Ladder times must be strictly increasing.")
        return sched


class Clock(Protocol):
    def now(self) -> pd.Timestamp: ...

    def wait_until(self, when: pd.Timestamp) -> None: ...


class IBClock:
    """Wall clock that waits through ``ib.sleep`` so order events keep arriving."""

    def __init__(self, ib: Any, step_s: float = 2.0) -> None:
        self.ib = ib
        self.step_s = step_s

    def now(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz=EXCHANGE_TZ)

    def wait_until(self, when: pd.Timestamp) -> None:
        while True:
            remaining = (when - self.now()).total_seconds()
            if remaining <= 0:
                return
            self.ib.sleep(min(remaining, self.step_s))


class LadderTooLate(RuntimeError):
    """Raised when a pass reaches the ladder after its latest permitted start."""


# ── outcome ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GroupOutcome:
    """How one straddle entry or exit finished.

    ``status`` is one of ``filled``, ``unfilled``, ``legged_flattened``,
    ``legged_open`` (entry legged and the flatten failed: an alarm) or
    ``incomplete`` (exit not fully closed: an alarm).
    """

    group: str
    purpose: str
    status: str
    fill_ps: float
    legs: tuple[LadderLeg, ...]
    nbbo_1559: dict[str, LegQuote | None]

    @property
    def alarm(self) -> bool:
        return self.status in ("legged_open", "incomplete")


QuoteFn = Callable[[list[LadderLeg]], dict[str, LegQuote | None]]


# ── engine ───────────────────────────────────────────────────────────────────


def _observe(leg: LadderLeg, log: OrderEventLog) -> None:
    """Log any new status and any new execution on one leg's order."""
    trade = leg.trade
    if trade is None:
        return
    status = getattr(trade.orderStatus, "status", "")
    for fill in list(getattr(trade, "fills", []) or []):
        execution = getattr(fill, "execution", None)
        exec_id = str(getattr(execution, "execId", id(fill)))
        if exec_id in leg.seen_exec:
            continue
        leg.seen_exec.add(exec_id)
        report = getattr(fill, "commissionReport", None)
        commission = getattr(report, "commission", None)
        when = getattr(fill, "time", None)
        log.record(
            "fill",
            **leg.base_fields(),
            ts_broker=pd.Timestamp(when).isoformat() if when is not None else None,
            fill_qty=int(getattr(execution, "shares", 0)),
            fill_price=float(getattr(execution, "price", float("nan"))),
            cum_filled=leg.filled_qty,
            avg_fill_price=leg.avg_fill,
            commission=float(commission) if commission else None,
            status=status,
            rung=leg.rung,
        )
    if status != leg.last_status:
        leg.last_status = status
        if status == "Inactive":
            messages = [getattr(e, "message", "") for e in getattr(trade, "log", []) or []]
            log.record(
                "reject",
                **leg.base_fields(),
                status=status,
                reason=next((m for m in reversed(messages) if m), "rejected"),
            )
        else:
            remaining = getattr(trade.orderStatus, "remaining", None)
            log.record(
                "status",
                **leg.base_fields(),
                status=status,
                cum_filled=leg.filled_qty,
                avg_fill_price=leg.avg_fill,
                remaining=int(remaining) if remaining is not None else None,
                limit_price=leg.limit_price,
            )


def _place(
    ib: Any,
    leg: LadderLeg,
    limit: float,
    rung: int,
    frac: float,
    log: OrderEventLog,
    *,
    transmit: bool,
    quote: LegQuote,
) -> None:
    """Submit or modify one leg's limit, logging the intent before sending it.

    A rung whose rounded limit equals the resting one sends nothing: re-placing an
    unchanged order costs a message and gains no queue priority.
    """
    posted = bool(np.isfinite(leg.limit_price))
    if posted and np.isclose(limit, leg.limit_price):
        return
    event = "modify" if posted else "submit"
    qty = int(leg.quantity)
    fields = leg.base_fields()
    leg.rung = rung
    leg.limit_price = float(limit)
    if transmit:
        from ib_async import LimitOrder

        if leg.order is None:
            leg.order = LimitOrder(leg.side, qty, float(limit))
            leg.order.transmit = True
            # Reserve the id now so the submit row, written before sending, carries
            # it; ib_async's placeOrder keeps an id that is already set.
            leg.order.orderId = ib.client.getReqId()
            fields["order_id"] = leg.order.orderId
        else:
            leg.order.lmtPrice = float(limit)
    log.record(
        event,
        **fields,
        rung=rung,
        cross_frac=frac,
        limit_price=float(limit),
        nbbo_bid=quote.bid,
        nbbo_ask=quote.ask,
        nbbo_bid_size=quote.bid_size,
        nbbo_ask_size=quote.ask_size,
        nbbo_ts_utc=quote.ts.isoformat() if quote.ts is not None else None,
        status="intent" if not transmit else None,
    )
    if transmit:
        leg.trade = ib.placeOrder(leg.contract, leg.order)
        # The broker assigns the order id on first placement; later rows carry it.
        _observe(leg, log)


def _cancel_working(ib: Any, legs: Iterable[LadderLeg], log: OrderEventLog) -> None:
    for leg in legs:
        if leg.working():
            log.record("cancel_req", **leg.base_fields(), limit_price=leg.limit_price)
            ib.cancelOrder(leg.order)


def run_ladder(
    ib: Any,
    legs: list[LadderLeg],
    *,
    quote_fn: QuoteFn,
    clock: Clock,
    schedule: LadderSchedule,
    log: OrderEventLog,
    transmit: bool,
    halted: Callable[[], bool] = lambda: False,
    settle_s: float = LIVE.exit_cancel_settle_s,
) -> list[GroupOutcome]:
    """Work every leg through the rung schedule and report each group's outcome.

    Parameters
    ----------
    ib : ib_async.IB or a fake with ``placeOrder``, ``cancelOrder`` and ``sleep``
        The gateway. Never called when ``transmit`` is ``False``.
    legs : list of LadderLeg
        Every entry and exit leg of the session.
    quote_fn : callable
        Returns the current :class:`LegQuote` per leg key, or ``None`` for a leg it
        could not quote.
    clock : Clock
        Supplies ``now`` and ``wait_until``.
    schedule : LadderSchedule
        The session's rung times.
    log : OrderEventLog
        Destination for every event.
    transmit : bool
        Whether orders are actually placed.
    halted : callable, optional
        The ``HALT`` switch; checked before each rung and before the flatten.
    settle_s : float, optional
        Seconds to wait after cancelling before re-reading status, because a fill can
        reach the exchange ahead of the cancel.

    Returns
    -------
    list of GroupOutcome
        One per group, in first-seen order.

    Raises
    ------
    LadderTooLate
        If the pass reaches the ladder after ``schedule.latest_start``. Nothing is sent.
    """
    if not legs:
        return []
    if clock.now() > schedule.latest_start:
        raise LadderTooLate(
            f"ladder reached at {clock.now():%H:%M:%S} ET, after the latest start "
            f"{schedule.latest_start:%H:%M:%S}; no orders sent"
        )
    was_halted = False
    try:
        for rung, (when, frac) in enumerate(schedule.rungs):
            clock.wait_until(when)
            for leg in legs:
                _observe(leg, log)
            if halted():
                was_halted = True
                log.record("halt", reason=f"HALT present before rung {rung}; cancelling all")
                _cancel_working(ib, legs, log)
                break
            # A leg whose order ended without filling (a reject) is not re-placed:
            # modifying a finished order raises inside ib_async, and resending blindly
            # loops on the same reject (ticket T13 adds a single fresh retry).
            open_legs = [
                leg for leg in legs if not leg.done and (leg.trade is None or leg.working())
            ]
            if not open_legs:
                break
            quotes = quote_fn(open_legs)
            for leg in open_legs:
                q = quotes.get(leg.key)
                if q is None:
                    log.record("hold_stale_quote", **leg.base_fields(), rung=rung)
                    continue
                leg.last_quote = q
                if not q.usable_for(leg.side):
                    log.record(
                        "skip_bad_book",
                        **leg.base_fields(),
                        rung=rung,
                        nbbo_bid=q.bid,
                        nbbo_ask=q.ask,
                    )
                    continue
                _place(
                    ib, leg, q.limit(leg.side, frac), rung, frac, log, transmit=transmit, quote=q
                )

        if not was_halted:
            clock.wait_until(schedule.cancel_at)
        for leg in legs:
            _observe(leg, log)
        _cancel_working(ib, legs, log)
        if transmit:
            ib.sleep(settle_s)
        for leg in legs:
            _observe(leg, log)

        flatten_legs = _flatten(
            ib,
            legs,
            quote_fn,
            clock,
            schedule,
            log,
            transmit=transmit,
            halted=was_halted or halted(),
            settle_s=settle_s,
        )

        clock.wait_until(schedule.nbbo_at)
        final = quote_fn(legs)
        for leg in legs:
            q = final.get(leg.key)
            log.record(
                "nbbo_1559",
                **leg.base_fields(),
                nbbo_bid=q.bid if q else None,
                nbbo_ask=q.ask if q else None,
                nbbo_bid_size=q.bid_size if q else None,
                nbbo_ask_size=q.ask_size if q else None,
                nbbo_ts_utc=q.ts.isoformat() if q is not None and q.ts is not None else None,
                cum_filled=leg.filled_qty,
                reason=None if q else "no quote at 15:59",
            )
    except BaseException:
        _cancel_working(ib, legs, log)
        raise

    return _outcomes(legs, flatten_legs, final)


def _flatten(
    ib: Any,
    legs: list[LadderLeg],
    quote_fn: QuoteFn,
    clock: Clock,
    schedule: LadderSchedule,
    log: OrderEventLog,
    *,
    transmit: bool,
    halted: bool,
    settle_s: float,
) -> dict[str, LadderLeg]:
    """Buy back the filled quantity of every legged entry at the touch.

    Returns the flatten legs by group so the outcome can tell a repaired legging from
    an open one. With ``halted`` set nothing is sent, and the legging is reported open.
    """
    by_group: dict[str, list[LadderLeg]] = {}
    for leg in legs:
        if leg.purpose == "entry":
            by_group.setdefault(leg.group, []).append(leg)
    legged = {
        g: [leg for leg in group if leg.filled_qty > 0]
        for g, group in by_group.items()
        if not all(leg.done for leg in group) and any(leg.filled_qty > 0 for leg in group)
    }
    flat: dict[str, LadderLeg] = {}
    if not legged or halted or not transmit:
        return flat
    to_close = [leg for group in legged.values() for leg in group]
    probes = [
        LadderLeg(
            group=f"{leg.group}:flatten",
            ticker=leg.ticker,
            position_key=leg.position_key,
            purpose="flatten",
            side="BUY",
            right=leg.right,
            contract=leg.contract,
            quantity=leg.filled_qty,
            strike=leg.strike,
            expiry=leg.expiry,
        )
        for leg in to_close
    ]
    quotes = quote_fn(probes)
    for probe in probes:
        q = quotes.get(probe.key)
        if q is None or not q.usable_for("BUY"):
            log.record("alarm", **probe.base_fields(), reason="legged entry: no book to flatten")
            continue
        _place(
            ib, probe, q.limit("BUY", 1.0), len(schedule.rungs), 1.0, log, transmit=True, quote=q
        )
    clock.wait_until(schedule.nbbo_at - pd.Timedelta(seconds=10))
    for probe in probes:
        _observe(probe, log)
    _cancel_working(ib, probes, log)
    ib.sleep(settle_s)
    for probe in probes:
        _observe(probe, log)
        flat[f"{probe.group.rsplit(':flatten', 1)[0]}:{probe.right}"] = probe
    return flat


def _outcomes(
    legs: list[LadderLeg],
    flat: dict[str, LadderLeg],
    final: dict[str, LegQuote | None],
) -> list[GroupOutcome]:
    groups: dict[str, list[LadderLeg]] = {}
    for leg in legs:
        groups.setdefault(leg.group, []).append(leg)
    out: list[GroupOutcome] = []
    for group, members in groups.items():
        purpose = members[0].purpose
        nbbo = {leg.right: final.get(leg.key) for leg in members}
        if all(leg.done for leg in members):
            status = "filled"
            fill_ps = float(sum(leg.avg_fill for leg in members))
        elif not any(leg.filled_qty > 0 for leg in members):
            status = "unfilled"
            fill_ps = float("nan")
        elif purpose == "entry":
            repaired = [flat.get(leg.key) for leg in members if leg.filled_qty > 0]
            ok = all(p is not None and p.done for p in repaired)
            status = "legged_flattened" if ok else "legged_open"
            fill_ps = float("nan")
        else:
            status = "incomplete"
            fill_ps = float("nan")
        out.append(
            GroupOutcome(
                group=group,
                purpose=purpose,
                status=status,
                fill_ps=fill_ps,
                legs=tuple(members),
                nbbo_1559=nbbo,
            )
        )
    return out
